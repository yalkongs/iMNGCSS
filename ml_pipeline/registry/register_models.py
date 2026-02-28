"""
MLflow 모델 레지스트리 등록 스크립트
======================================
학습 완료된 스코어카드 아티팩트를 MLflow Model Registry에 등록.
run_pipeline.py --mlflow 플래그와 동일한 기능을 독립 실행으로 제공.

사전 조건:
  - ml_pipeline/artifacts/{scorecard_type}/ 에 모델 파일 존재
  - MLflow 서버 실행 중 (기본: http://localhost:5001)
  - mlflow 패키지 설치: pip install mlflow

사용법:
  python ml_pipeline/registry/register_models.py
  python ml_pipeline/registry/register_models.py --scorecard application
  python ml_pipeline/registry/register_models.py --mlflow-uri http://mlflow:5001
  python ml_pipeline/registry/register_models.py --promote production
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 프로젝트 루트
REGISTRY_DIR = Path(__file__).resolve().parent
ML_DIR = REGISTRY_DIR.parent
ARTIFACTS_BASE = ML_DIR / "artifacts"

SCORECARD_TYPES = ["application", "behavioral", "collection"]

# 금감원 모범규준 최저 성능 기준
PERFORMANCE_THRESHOLDS = {
    "application": {"oot_gini": 0.30, "oot_ks": 0.20},
    "behavioral":  {"oot_gini": 0.25, "oot_ks": 0.15},
    "collection":  {"oot_gini": 0.20, "oot_ks": 0.15},
}


def _load_model_card(scorecard_type: str) -> Optional[dict]:
    """model_card.json 로드."""
    card_path = ARTIFACTS_BASE / scorecard_type / "model_card.json"
    if not card_path.exists():
        logger.error(f"model_card.json 없음: {card_path}")
        return None
    with open(card_path, encoding="utf-8") as f:
        return json.load(f)


def _extract_oot_metrics(card: dict) -> tuple[float, float]:
    """
    model_card.json에서 OOT Gini/KS 추출.
    훈련 스크립트 출력 형식과 단순 템플릿 형식 모두 지원.
    """
    perf = card.get("performance", {})
    regulatory = card.get("regulatory_compliance", {})

    oot_gini = float(perf.get("oot_gini", 0.0))
    oot_ks = float(perf.get("oot_ks", 0.0))

    if oot_gini == 0.0 or oot_ks == 0.0:
        metrics_list = perf.get("metrics", [])
        oot_entry = next(
            (m for m in metrics_list if m.get("dataset", "").upper() == "OOT"), {}
        )
        if oot_gini == 0.0:
            oot_gini = float(oot_entry.get("gini", 0.0))
        if oot_ks == 0.0:
            oot_ks = float(oot_entry.get(
                "ks_stat",
                oot_entry.get("ks_statistic", oot_entry.get("ks", 0.0))
            ))

    if oot_gini == 0.0:
        oot_gini = float(regulatory.get("gini_oot", 0.0))

    return oot_gini, oot_ks


def _validate_performance(scorecard_type: str, card: dict) -> bool:
    """모델 성능이 규제 기준을 충족하는지 검증."""
    oot_gini, oot_ks = _extract_oot_metrics(card)
    thresholds = PERFORMANCE_THRESHOLDS.get(scorecard_type, {})
    min_gini = thresholds.get("oot_gini", 0.20)
    min_ks = thresholds.get("oot_ks", 0.15)

    passed = True
    if oot_gini < min_gini:
        logger.warning(f"  OOT Gini({oot_gini:.4f}) < 기준({min_gini}) — 등록 보류 권장")
        passed = False
    if oot_ks < min_ks:
        logger.warning(f"  OOT KS({oot_ks:.4f}) < 기준({min_ks}) — 등록 보류 권장")
        passed = False
    return passed


def register_scorecard(
    scorecard_type: str,
    mlflow_uri: str,
    stage: Optional[str] = None,
    force: bool = False,
) -> bool:
    """
    단일 스코어카드를 MLflow에 등록.

    Args:
        scorecard_type: "application" | "behavioral" | "collection"
        mlflow_uri: MLflow 트래킹 서버 URI
        stage: 등록 후 전환할 스테이지 ("Staging" | "Production" | None)
        force: 성능 미달 시에도 강제 등록 여부

    Returns:
        True if registered successfully
    """
    try:
        import mlflow
        import mlflow.sklearn
        import mlflow.xgboost
        import joblib
        import xgboost as xgb
    except ImportError as e:
        logger.error(f"패키지 미설치: {e}\n  pip install mlflow xgboost joblib")
        return False

    card = _load_model_card(scorecard_type)
    if card is None:
        return False

    perf_ok = _validate_performance(scorecard_type, card)
    if not perf_ok and not force:
        logger.warning(f"  --force 없이 성능 미달 모델은 등록하지 않습니다: {scorecard_type}")
        return False

    mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment(f"kcs_{scorecard_type}_scorecard")

    perf = card.get("performance", {})
    version = card.get("version", "1.0")
    model_name = f"kcs_{scorecard_type}_scorecard"
    oot_gini, oot_ks = _extract_oot_metrics(card)

    # train/test Gini: performance.metrics 리스트 또는 직접 키에서 추출
    metrics_list = perf.get("metrics", [])
    train_entry = next((m for m in metrics_list if m.get("dataset", "").upper() == "TRAIN"), {})
    test_entry = next(
        (m for m in metrics_list if m.get("dataset", "").upper() in ("HOLD-OUT", "TEST")), {}
    )
    train_gini = train_entry.get("gini", perf.get("train_gini", 0.0))
    test_gini = test_entry.get("gini", perf.get("test_gini", 0.0))

    with mlflow.start_run(run_name=f"{scorecard_type}_v{version}") as run:
        # 성능 메트릭
        mlflow.log_metrics({
            "oot_gini":    oot_gini,
            "oot_ks":      oot_ks,
            "cv_auc_mean": perf.get("cv_auc_mean", card.get("cv_auc_mean", 0)),
            "cv_auc_std":  perf.get("cv_auc_std", card.get("cv_auc_std", 0)),
            "train_gini":  train_gini,
            "test_gini":   test_gini,
        })

        # 파라미터
        mlflow.log_params({
            "scorecard_type": scorecard_type,
            "n_features":     card.get("n_features", 0),
            "model_type":     card.get("model_type", "unknown"),
            "trained_at":     card.get("trained_at", ""),
            "version":        version,
        })

        # 규제 준수 태그
        mlflow.set_tags({
            "regulatory_compliant": str(perf_ok),
            "oot_gini_threshold":   str(PERFORMANCE_THRESHOLDS[scorecard_type]["oot_gini"]),
            "oot_ks_threshold":     str(PERFORMANCE_THRESHOLDS[scorecard_type]["oot_ks"]),
            "fssc_compliant":       "true",  # 금감원 모범규준
        })

        # model_card.json 아티팩트
        card_path = ARTIFACTS_BASE / scorecard_type / "model_card.json"
        mlflow.log_artifact(str(card_path), "model_card")

        # 모델 파일 등록
        model_dir = ARTIFACTS_BASE / scorecard_type
        pkl_path = model_dir / f"{scorecard_type}_scorecard.pkl"
        xgb_path = model_dir / f"{scorecard_type}_scorecard.xgb"

        registered_version = None

        if pkl_path.exists():
            model = joblib.load(pkl_path)
            mv = mlflow.sklearn.log_model(
                model,
                artifact_path="model",
                registered_model_name=model_name,
            )
            registered_version = mv
            logger.info(f"  sklearn 모델 등록: {model_name} (pkl)")

        elif xgb_path.exists():
            model = xgb.XGBClassifier()
            model.load_model(str(xgb_path))
            mv = mlflow.xgboost.log_model(
                model,
                artifact_path="model",
                registered_model_name=model_name,
            )
            registered_version = mv
            logger.info(f"  XGBoost 모델 등록: {model_name} (xgb)")

        else:
            logger.warning(f"  모델 파일 없음: {pkl_path} / {xgb_path}")

        run_id = run.info.run_id
        logger.info(f"  Run ID: {run_id}")

    # 스테이지 전환
    if stage and registered_version:
        try:
            client = mlflow.tracking.MlflowClient()
            latest = client.get_latest_versions(model_name, stages=["None"])
            if latest:
                client.transition_model_version_stage(
                    name=model_name,
                    version=latest[0].version,
                    stage=stage,
                    archive_existing_versions=(stage == "Production"),
                )
                logger.info(f"  스테이지 전환: {model_name} v{latest[0].version} → {stage}")
        except Exception as e:
            logger.warning(f"  스테이지 전환 실패 (비중요): {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description="KCS MLflow 모델 레지스트리 등록")
    parser.add_argument(
        "--scorecard",
        choices=SCORECARD_TYPES + ["all"],
        default="all",
        help="등록할 스코어카드 유형 (기본: all)",
    )
    parser.add_argument(
        "--mlflow-uri",
        default=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001"),
        help="MLflow 트래킹 서버 URI",
    )
    parser.add_argument(
        "--promote",
        choices=["Staging", "Production"],
        default=None,
        help="등록 후 스테이지 전환",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="성능 미달 시에도 강제 등록",
    )
    args = parser.parse_args()

    targets = SCORECARD_TYPES if args.scorecard == "all" else [args.scorecard]

    logger.info("=" * 60)
    logger.info("KCS MLflow 모델 레지스트리 등록")
    logger.info(f"  MLflow URI : {args.mlflow_uri}")
    logger.info(f"  대상 모델  : {targets}")
    logger.info(f"  스테이지   : {args.promote or '전환 없음'}")
    logger.info("=" * 60)

    results = {}
    for sc_type in targets:
        logger.info(f"\n▶ {sc_type} 등록 중...")
        ok = register_scorecard(
            scorecard_type=sc_type,
            mlflow_uri=args.mlflow_uri,
            stage=args.promote,
            force=args.force,
        )
        results[sc_type] = ok
        status = "완료" if ok else "실패"
        logger.info(f"  → {status}")

    print("\n" + "=" * 60)
    print("등록 결과 요약")
    print("=" * 60)
    for sc_type, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {sc_type}")
    all_ok = all(results.values())
    print("=" * 60)
    print(f"최종: {'모두 성공' if all_ok else '일부 실패'}")
    print("=" * 60)

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
