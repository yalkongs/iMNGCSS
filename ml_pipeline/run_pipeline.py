"""
ML 파이프라인 오케스트레이터
==============================
전체 ML 학습 파이프라인을 순서대로 실행.

실행 순서:
  1. 합성 데이터 생성 (synthetic_data.py)
  2. Application Scorecard 학습 (train_application.py)
  3. Behavioral Scorecard 학습 (train_behavioral.py)
  4. Collection Scorecard 학습 (train_collection.py)
  5. 모델 성능 검증 (model_card.json 기준 검증)
  6. MLflow 모델 등록 (선택)

사용법:
  python ml_pipeline/run_pipeline.py                    # 전체 실행
  python ml_pipeline/run_pipeline.py --skip-data        # 데이터 생성 건너뜀
  python ml_pipeline/run_pipeline.py --only application # 특정 모델만 학습
  python ml_pipeline/run_pipeline.py --validate-only    # 검증만 실행
"""
import os
import sys
import json
import argparse
import logging
import subprocess
import time
from datetime import datetime
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_BASE = os.path.join(BASE_DIR, "artifacts")

# 규제 성능 기준 (금감원 모범규준)
PERFORMANCE_THRESHOLDS = {
    "application": {"oot_gini": 0.30, "oot_ks": 0.20},
    "behavioral":  {"oot_gini": 0.25, "oot_ks": 0.15},
    "collection":  {"oot_gini": 0.20, "oot_ks": 0.15},
}


def _run_script(script_path: str, step_name: str) -> bool:
    """서브프로세스로 Python 스크립트 실행."""
    logger.info(f"▶ {step_name} 시작...")
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=False,
            text=True,
            cwd=BASE_DIR,
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            logger.info(f"✓ {step_name} 완료 ({elapsed:.0f}초)")
            return True
        else:
            logger.error(f"✗ {step_name} 실패 (returncode={result.returncode})")
            return False
    except FileNotFoundError:
        logger.error(f"✗ {step_name}: 스크립트 없음 — {script_path}")
        return False
    except Exception as e:
        logger.error(f"✗ {step_name}: {e}")
        return False


def generate_data() -> bool:
    """합성 학습 데이터 생성."""
    script = os.path.join(BASE_DIR, "data", "synthetic_data.py")
    return _run_script(script, "합성 데이터 생성")


def train_application() -> bool:
    """Application Scorecard 학습."""
    script = os.path.join(BASE_DIR, "training", "train_application.py")
    return _run_script(script, "Application Scorecard 학습")


def train_behavioral() -> bool:
    """Behavioral Scorecard 학습."""
    script = os.path.join(BASE_DIR, "training", "train_behavioral.py")
    return _run_script(script, "Behavioral Scorecard 학습")


def train_collection() -> bool:
    """Collection Scorecard 학습."""
    script = os.path.join(BASE_DIR, "training", "train_collection.py")
    return _run_script(script, "Collection Scorecard 학습")


def _extract_oot_metrics(card: dict) -> tuple[float, float]:
    """
    model_card.json에서 OOT Gini/KS 값을 추출.
    훈련 스크립트 출력 형식과 단순 템플릿 형식 모두 지원.

    1순위: performance.oot_gini / performance.oot_ks  (템플릿/단순 형식)
    2순위: performance.metrics 리스트의 'OOT' 항목
    3순위: regulatory_compliance.gini_oot
    """
    perf = card.get("performance", {})
    regulatory = card.get("regulatory_compliance", {})

    oot_gini = perf.get("oot_gini", 0.0)
    oot_ks = perf.get("oot_ks", 0.0)

    # performance.metrics 리스트에서 OOT 항목 탐색
    if oot_gini == 0.0 or oot_ks == 0.0:
        metrics_list = perf.get("metrics", [])
        oot_entry = next(
            (m for m in metrics_list if m.get("dataset", "").upper() == "OOT"), {}
        )
        if oot_gini == 0.0:
            oot_gini = oot_entry.get("gini", 0.0)
        if oot_ks == 0.0:
            oot_ks = oot_entry.get(
                "ks_stat",
                oot_entry.get("ks_statistic", oot_entry.get("ks", 0.0))
            )

    # regulatory_compliance 섹션 폴백 (gini만 있음)
    if oot_gini == 0.0:
        oot_gini = regulatory.get("gini_oot", 0.0)

    return float(oot_gini), float(oot_ks)


def validate_model_card(scorecard_type: str) -> dict:
    """
    model_card.json을 로드하여 규제 기준 충족 여부 검증.

    Returns:
        {"passed": bool, "oot_gini": float, "oot_ks": float, "issues": [str]}
    """
    card_path = os.path.join(ARTIFACTS_BASE, scorecard_type, "model_card.json")
    if not os.path.exists(card_path):
        return {"passed": False, "issues": [f"model_card.json 없음: {card_path}"]}

    with open(card_path) as f:
        card = json.load(f)

    oot_gini, oot_ks = _extract_oot_metrics(card)

    thresholds = PERFORMANCE_THRESHOLDS.get(scorecard_type, {})
    min_gini = thresholds.get("oot_gini", 0.20)
    min_ks = thresholds.get("oot_ks", 0.15)

    issues = []
    if oot_gini < min_gini:
        issues.append(f"OOT Gini({oot_gini:.4f}) < 기준({min_gini})")
    if oot_ks < min_ks:
        issues.append(f"OOT KS({oot_ks:.4f}) < 기준({min_ks})")

    n_features = card.get("features", {}).get("n_features", card.get("n_features", 0))
    return {
        "passed": len(issues) == 0,
        "scorecard_type": scorecard_type,
        "oot_gini": oot_gini,
        "oot_ks": oot_ks,
        "min_gini": min_gini,
        "min_ks": min_ks,
        "issues": issues,
        "model_version": card.get("version", "unknown"),
        "trained_at": card.get("trained_at", ""),
        "n_features": n_features,
    }


def validate_all_models() -> bool:
    """3개 스코어카드 성능 검증."""
    logger.info("\n" + "=" * 60)
    logger.info("모델 성능 검증 (금감원 모범규준 기준)")
    logger.info("=" * 60)

    all_passed = True
    results = []

    for sc_type in ["application", "behavioral", "collection"]:
        result = validate_model_card(sc_type)
        results.append(result)

        status = "통과" if result["passed"] else "미달"
        icon = "✓" if result["passed"] else "✗"

        if "issues" in result and result.get("oot_gini") is not None:
            logger.info(
                f"  {icon} {sc_type:12s}: "
                f"OOT Gini={result['oot_gini']:.4f} (기준={result['min_gini']}) | "
                f"OOT KS={result['oot_ks']:.4f} (기준={result['min_ks']}) | "
                f"{status}"
            )
        else:
            logger.warning(f"  ✗ {sc_type:12s}: " + " | ".join(result["issues"]))

        if not result["passed"]:
            all_passed = False

    logger.info("=" * 60)
    logger.info(f"전체 검증: {'통과 ✓' if all_passed else '일부 미달 ✗'}")

    return all_passed


def register_to_mlflow(scorecard_type: str) -> bool:
    """
    MLflow 모델 레지스트리에 등록 (MLflow 설치 시).
    미설치 시 건너뜀.
    """
    try:
        import mlflow
        import mlflow.sklearn
        import joblib

        mlflow_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
        mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment(f"kcs_{scorecard_type}_scorecard")

        card_path = os.path.join(ARTIFACTS_BASE, scorecard_type, "model_card.json")
        if not os.path.exists(card_path):
            logger.warning(f"MLflow 등록 건너뜀: model_card.json 없음 ({scorecard_type})")
            return False

        with open(card_path) as f:
            card = json.load(f)

        with mlflow.start_run(run_name=f"{scorecard_type}_v{card.get('version', '1.0')}"):
            # 성능 메트릭 기록
            perf = card.get("performance", {})
            mlflow.log_metric("oot_gini", perf.get("oot_gini", 0))
            mlflow.log_metric("oot_ks", perf.get("oot_ks", 0))
            mlflow.log_metric("cv_auc_mean", card.get("cv_auc_mean", 0))
            mlflow.log_metric("cv_auc_std", card.get("cv_auc_std", 0))

            # 파라미터 기록
            mlflow.log_param("scorecard_type", scorecard_type)
            mlflow.log_param("n_features", card.get("n_features", 0))
            mlflow.log_param("model_type", card.get("model_type", "unknown"))
            mlflow.log_param("trained_at", card.get("trained_at", ""))

            # model_card.json 아티팩트로 기록
            mlflow.log_artifact(card_path, "model_card")

            # 모델 등록
            model_path = os.path.join(ARTIFACTS_BASE, scorecard_type)
            pkl_path = os.path.join(model_path, f"{scorecard_type}_scorecard.pkl")
            xgb_path = os.path.join(model_path, f"{scorecard_type}_scorecard.xgb")

            if os.path.exists(pkl_path):
                model = joblib.load(pkl_path)
                mlflow.sklearn.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=f"kcs_{scorecard_type}_scorecard",
                )
            elif os.path.exists(xgb_path):
                import mlflow.xgboost
                import xgboost as xgb
                model = xgb.XGBClassifier()
                model.load_model(xgb_path)
                mlflow.xgboost.log_model(
                    model,
                    artifact_path="model",
                    registered_model_name=f"kcs_{scorecard_type}_scorecard",
                )

        logger.info(f"✓ MLflow 등록 완료: {scorecard_type} → {mlflow_uri}")
        return True

    except ImportError:
        logger.info(f"  MLflow 미설치 — {scorecard_type} 등록 건너뜀")
        return False
    except Exception as e:
        logger.error(f"  MLflow 등록 실패 ({scorecard_type}): {e}")
        return False


def print_summary(results: dict) -> None:
    """파이프라인 실행 결과 요약 출력."""
    print("\n" + "=" * 60)
    print("KCS ML 파이프라인 실행 결과 요약")
    print("=" * 60)
    for step, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {step}")
    all_ok = all(results.values())
    print("=" * 60)
    print(f"최종 결과: {'성공' if all_ok else '일부 실패'}")
    print(f"완료 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="KCS ML 파이프라인 오케스트레이터")
    parser.add_argument("--skip-data", action="store_true", help="합성 데이터 생성 건너뜀")
    parser.add_argument("--validate-only", action="store_true", help="검증만 실행 (학습 건너뜀)")
    parser.add_argument(
        "--only",
        choices=["application", "behavioral", "collection"],
        help="특정 스코어카드만 학습",
    )
    parser.add_argument("--mlflow", action="store_true", help="MLflow 등록 실행")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("KCS ML 파이프라인 시작")
    logger.info(f"시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    step_results = {}

    if args.validate_only:
        passed = validate_all_models()
        if not passed:
            logger.warning("일부 모델이 규제 기준 미달 — 학습 후 재검증 필요")
        return

    # Step 1: 합성 데이터 생성
    if not args.skip_data and not args.only:
        ok = generate_data()
        step_results["합성 데이터 생성"] = ok
        if not ok:
            logger.error("데이터 생성 실패 — 파이프라인 중단")
            print_summary(step_results)
            sys.exit(1)

    # Step 2~4: 모델 학습
    if args.only == "application" or not args.only:
        step_results["Application Scorecard 학습"] = train_application()

    if args.only == "behavioral" or not args.only:
        step_results["Behavioral Scorecard 학습"] = train_behavioral()

    if args.only == "collection" or not args.only:
        step_results["Collection Scorecard 학습"] = train_collection()

    # Step 5: 성능 검증
    validation_passed = validate_all_models()
    step_results["모델 성능 검증"] = validation_passed

    # Step 6: MLflow 등록 (선택)
    if args.mlflow:
        for sc_type in (["application", "behavioral", "collection"] if not args.only else [args.only]):
            ok = register_to_mlflow(sc_type)
            step_results[f"MLflow 등록 ({sc_type})"] = ok

    print_summary(step_results)

    if not all(step_results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
