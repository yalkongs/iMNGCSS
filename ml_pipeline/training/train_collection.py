"""
Collection Scorecard (추심평점) 학습 파이프라인
=================================================
연체 발생 후 회수 가능성 예측.
타겟: recovery_success (1=회수 성공, 0=부실 전환)

모델: Random Forest (해석 가능성 + 안정성)
주요 피처:
  - 연체 특성: 연체 일수, 연체 금액, 채권 유형
  - 자산 현황: 담보 보유, 다른 자산 현황
  - 접촉 이력: 접촉 시도 횟수, 최근 납입 여부
  - 신용 이력: 공공기록, 최악 연체 상태

바젤III:
  - LGD 추정과 연계 (회수율 = 1 - LGD)
  - 회수 시나리오: 현금회수 / 담보처분 / 매각
"""
import os, sys, json, joblib, warnings
import numpy as np
import pandas as pd
from datetime import datetime
from scipy import stats

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts", "collection")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score, roc_curve, classification_report
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.calibration import CalibratedClassifierCV
    HAS_LIBS = True
except ImportError as e:
    print(f"[경고] sklearn 없음: {e}")
    HAS_LIBS = False

TARGET = "recovery_success"   # 1=회수 성공

# ── 추심평점 전용 피처 그룹 ─────────────────────────────────
FEATURE_GROUPS = {
    "delinquency_profile": [
        "delinquency_days",             # 연체 일수 (핵심)
        "delinquency_amount",           # 연체 금액
        "worst_delinquency_status",     # 최악 연체 상태 이력
        "delinquency_count_24m",        # 24개월 연체 횟수
    ],
    "asset_collateral": [
        "has_asset",                    # 담보/자산 보유 여부
        "collateral_value",             # 담보 시세 (주담대)
        "total_loan_balance",           # 총 대출 잔액
    ],
    "contact_recovery": [
        "contact_attempt_count",        # 접촉 시도 횟수
        "last_payment_amount",          # 최근 납입금액
    ],
    "borrower_profile": [
        "cb_score",                     # CB 점수
        "income_annual_wan",            # 연소득
        "age",                          # 연령
        "employment_duration_months",   # 근속기간
        "open_loan_count",              # 보유 대출 수
    ],
    "financial_ratio": [
        "dsr_ratio",
        "debt_to_income",
    ],
}

ALL_FEATURES = [f for grp in FEATURE_GROUPS.values() for f in grp]


def compute_metrics(y_true, y_pred_proba, label=""):
    auc = roc_auc_score(y_true, y_pred_proba)
    gini = 2 * auc - 1
    ks, _ = stats.ks_2samp(y_pred_proba[y_true == 0], y_pred_proba[y_true == 1])
    metrics = {
        "dataset": label, "auc_roc": round(auc, 4),
        "gini": round(gini, 4), "ks_statistic": round(ks, 4),
        "recovery_rate": round(float(y_true.mean()), 4), "n_samples": len(y_true),
    }
    print(f"  [{label}] AUC={auc:.4f} | Gini={gini:.4f} | KS={ks:.4f} | 회수율={y_true.mean():.2%}")
    return metrics


def compute_lgd_from_recovery(recovery_prob: np.ndarray, product_type: str = "credit") -> np.ndarray:
    """
    회수 확률 → LGD 추정
    LGD = (1 - Recovery Rate) × (1 + Recovery Cost)
    Recovery Cost: 담보처분/법적 비용 약 10%
    """
    recovery_cost = 0.10
    lgd = (1 - recovery_prob) * (1 + recovery_cost)
    return np.clip(lgd, 0.0, 1.0)


def train():
    print("=" * 60)
    print("Collection Scorecard (추심평점) 학습 시작")
    print("=" * 60)

    data_path = os.path.join(DATA_DIR, "synthetic_collection.parquet")
    if not os.path.exists(data_path):
        print("[오류] 추심평점 데이터 없음. synthetic_data.py 먼저 실행")
        return

    df = pd.read_parquet(data_path)
    print(f"\n데이터: {len(df):,}건 | 회수 성공률: {df[TARGET].mean():.2%}")
    print(f"  연체 일수 분포: 평균={df['delinquency_days'].mean():.0f}일, 중앙값={df['delinquency_days'].median():.0f}일")

    # 학습/OOT 분리
    df_train_val = df[~df["is_oot"]].copy()
    df_oot       = df[df["is_oot"]].copy()

    df_train_val = df_train_val.sort_values("observation_date")
    cutoff = int(len(df_train_val) * 0.8)
    df_train   = df_train_val.iloc[:cutoff]
    df_holdout = df_train_val.iloc[cutoff:]

    print(f"  학습: {len(df_train):,}건 | Hold-out: {len(df_holdout):,}건 | OOT: {len(df_oot):,}건")

    available = [f for f in ALL_FEATURES if f in df.columns]
    missing = set(ALL_FEATURES) - set(df.columns)
    if missing:
        print(f"  [주의] 피처 없음 (기본값 0 사용): {missing}")

    # 피처 IV 계산
    iv_results = []
    for feat in available:
        try:
            df_tmp = df_train[[feat, TARGET]].dropna()
            if df_tmp[feat].nunique() <= 1:
                iv_results.append({"feature": feat, "iv": 0.0})
                continue
            df_tmp["bin"] = pd.qcut(df_tmp[feat], q=5, duplicates="drop")
            tg = max(1, (df_tmp[TARGET] == 0).sum())
            tb = max(1, (df_tmp[TARGET] == 1).sum())
            iv = 0.0
            for _, g in df_tmp.groupby("bin", observed=True):
                ng = (g[TARGET] == 0).sum()
                nb = (g[TARGET] == 1).sum()
                dg = (ng + 0.5) / (tg + 0.5)
                db = (nb + 0.5) / (tb + 0.5)
                iv += (dg - db) * np.log(dg / db)
            iv_results.append({"feature": feat, "iv": round(iv, 4)})
        except Exception:
            iv_results.append({"feature": feat, "iv": 0.0})

    iv_df = pd.DataFrame(iv_results).sort_values("iv", ascending=False)
    selected = iv_df[iv_df["iv"] >= 0.01]["feature"].tolist()  # 추심: 기준 약간 완화
    if not selected:
        selected = available[:10]  # 최소 피처 보장
    print(f"\n[피처 선택] {len(selected)}개 선택 (IV >= 0.01)")
    print(iv_df.head(10).to_string(index=False))
    iv_df.to_csv(os.path.join(ARTIFACTS_DIR, "iv_report.csv"), index=False)

    if not HAS_LIBS:
        print("[경고] sklearn 미설치")
        return

    X_train    = df_train[selected].fillna(0)
    y_train    = df_train[TARGET]
    X_holdout  = df_holdout[selected].fillna(0)
    y_holdout  = df_holdout[TARGET]
    X_oot      = df_oot[selected].fillna(0) if len(df_oot) > 0 else X_holdout
    y_oot      = df_oot[TARGET] if len(df_oot) > 0 else y_holdout

    # ── Random Forest 학습 ────────────────────────────────────
    print("\n[모델 학습] Random Forest Collection Scorecard...")

    rf_params = {
        "n_estimators": 300,
        "max_depth": 8,
        "min_samples_leaf": 20,
        "max_features": "sqrt",
        "class_weight": "balanced",
        "random_state": 42,
        "n_jobs": -1,
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_aucs = cross_val_score(
        RandomForestClassifier(**rf_params), X_train, y_train,
        cv=cv, scoring="roc_auc", n_jobs=-1
    )
    print(f"  CV AUC: {cv_aucs.mean():.4f} ± {cv_aucs.std():.4f}")

    # 최종 모델 + 확률 보정 (Platt Scaling)
    base_rf = RandomForestClassifier(**rf_params)
    final_model = CalibratedClassifierCV(base_rf, cv=5, method="sigmoid")
    final_model.fit(X_train, y_train)

    # ── 성능 평가 ─────────────────────────────────────────────
    print("\n[성능 평가]")
    all_metrics = []
    for name, X, y in [("Train", X_train, y_train), ("Hold-out", X_holdout, y_holdout), ("OOT", X_oot, y_oot)]:
        pred = final_model.predict_proba(X)[:, 1]
        all_metrics.append(compute_metrics(y.values, pred, name))

    # ── LGD 추정 검증 ─────────────────────────────────────────
    print("\n[LGD 추정 검증]")
    holdout_recovery_prob = final_model.predict_proba(X_holdout)[:, 1]
    estimated_lgd = compute_lgd_from_recovery(holdout_recovery_prob)
    print(f"  추정 LGD (Hold-out): 평균={estimated_lgd.mean():.4f}, 중앙값={np.median(estimated_lgd):.4f}")
    print(f"  실제 회수율 (Hold-out): {y_holdout.mean():.4f}")
    print(f"  참조 LGD (무담보 기본값): 0.45, 주담대: 0.25")

    # 분위별 LGD
    quantiles = np.quantile(estimated_lgd, [0.25, 0.5, 0.75, 0.9])
    print(f"  LGD 분위: Q25={quantiles[0]:.3f}, Q50={quantiles[1]:.3f}, Q75={quantiles[2]:.3f}, Q90={quantiles[3]:.3f}")

    # ── 피처 중요도 ───────────────────────────────────────────
    base_rf_fitted = RandomForestClassifier(**rf_params)
    base_rf_fitted.fit(X_train, y_train)
    feat_importance = pd.DataFrame({
        "feature": selected,
        "importance": base_rf_fitted.feature_importances_,
    }).sort_values("importance", ascending=False)
    print("\n[피처 중요도 Top10]")
    print(feat_importance.head(10).to_string(index=False))

    # ── 아티팩트 저장 ─────────────────────────────────────────
    print("\n[아티팩트 저장]")

    model_path = os.path.join(ARTIFACTS_DIR, "collection_scorecard.pkl")
    joblib.dump(final_model, model_path)
    print(f"  모델: {model_path}")

    with open(os.path.join(ARTIFACTS_DIR, "feature_names.json"), "w") as f:
        json.dump(selected, f)

    feat_importance.to_csv(os.path.join(ARTIFACTS_DIR, "feature_importance.csv"), index=False)
    iv_df.to_csv(os.path.join(ARTIFACTS_DIR, "iv_report.csv"), index=False)

    # LGD 검증 결과 저장
    lgd_validation = {
        "mean_lgd_estimated": round(float(estimated_lgd.mean()), 4),
        "median_lgd_estimated": round(float(np.median(estimated_lgd)), 4),
        "actual_recovery_rate": round(float(y_holdout.mean()), 4),
        "lgd_quantiles": {f"q{int(q*100)}": round(float(v), 4) for q, v in zip([0.25,0.5,0.75,0.9], quantiles)},
        "reference_lgd_unsecured": 0.45,
        "reference_lgd_mortgage": 0.25,
    }

    oot_metric = next((m for m in all_metrics if m["dataset"] == "OOT"), all_metrics[-1])
    model_card = {
        "model_name":    "Collection Scorecard",
        "model_type":    "RandomForest+CalibratedCV",
        "scorecard_type":"collection",
        "version":       "v1.0",
        "trained_at":    datetime.now().isoformat(),
        "data_source":   "synthetic_collection.parquet",
        "features":      selected,
        "n_features":    len(selected),
        "cv_auc_mean":   round(float(cv_aucs.mean()), 4),
        "cv_auc_std":    round(float(cv_aucs.std()), 4),
        "performance": {
            "metrics":  all_metrics,
            "oot_gini": oot_metric["gini"],
            "oot_ks":   oot_metric["ks_statistic"],
        },
        "regulatory": {
            "min_gini_threshold":  0.20,
            "min_ks_threshold":    0.15,
            "passes_oot_gini":     oot_metric["gini"] >= 0.20,
            "passes_oot_ks":       oot_metric["ks_statistic"] >= 0.15,
            "lgd_validation":      lgd_validation,
        },
        "hyperparameters": rf_params,
        "feature_groups": FEATURE_GROUPS,
        "feature_importance_top10": feat_importance.head(10).to_dict("records"),
    }

    with open(os.path.join(ARTIFACTS_DIR, "model_card.json"), "w", encoding="utf-8") as f:
        json.dump(model_card, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("Collection Scorecard 학습 완료")
    print(f"  OOT Gini:   {oot_metric['gini']:.4f} (기준: >= 0.20)")
    print(f"  OOT KS:     {oot_metric['ks_statistic']:.4f} (기준: >= 0.15)")
    print(f"  추정 LGD:   {estimated_lgd.mean():.4f} (무담보 기본값: 0.45)")
    status = "통과" if model_card["regulatory"]["passes_oot_gini"] else "미달"
    print(f"  규제 기준:  {status}")
    print(f"{'='*60}")
    return model_card


if __name__ == "__main__":
    train()
