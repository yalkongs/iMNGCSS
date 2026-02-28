"""
Behavioral Scorecard (행동평점) 학습 파이프라인
==================================================
기존 대출 고객의 상환 행동 패턴 기반 실시간 부도 위험 재평가.
신규 신청 때와 달리 계좌 거래 이력이 주요 피처.

모델: XGBoost (이진 분류)
타겟: default_12m (기 실행 대출 고객 12개월 내 부도 여부)
피처 그룹:
  - 상환 행동: 납입 정시율, 연체 횟수, 선납금액
  - 잔액 추이: 잔액/한도 비율 변화, 잔액 감소율
  - 거래 패턴: 월 입금액, 지출 비율, 저축률
  - CB 업데이트: 최신 CB 점수, 조회 수 변화

금감원 모범규준:
  - OOT Gini >= 0.25 (행동평점은 기준 약간 완화)
  - 3개월 이상 관측 기간 데이터 필요
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
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts", "behavioral")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

try:
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score, roc_curve
    from sklearn.model_selection import StratifiedKFold
    import shap
    HAS_LIBS = True
except ImportError as e:
    print(f"[경고] 라이브러리 없음: {e}")
    HAS_LIBS = False

TARGET = "default_12m"

# ── 행동평점 전용 피처 그룹 ─────────────────────────────────
FEATURE_GROUPS = {
    "repayment_behavior": [
        "payment_on_time_rate",         # 정시 납입률 (핵심)
        "missed_payment_count",         # 납입 누락 횟수
        "outstanding_balance_ratio",    # 잔액/한도 비율
        "prepayment_amount",            # 선납금액
        "months_since_origination",     # 실행 후 경과 월수
    ],
    "account_activity": [
        "avg_monthly_inflow",           # 월 평균 입금액
        "avg_monthly_expense",          # 월 평균 지출액
        "savings_rate",                 # 저축률
        "card_usage_rate",              # 카드 사용 비율
        "overdraft_count_annual",       # 당좌차월 발생 수
    ],
    "credit_dynamics": [
        "cb_score",                     # 최신 CB 점수
        "delinquency_count_12m",        # 12개월 연체 수
        "inquiry_count_3m",             # 최근 조회 수
        "worst_delinquency_status",     # 최악 연체 상태
    ],
    "financial_health": [
        "dsr_ratio",                    # 현재 DSR
        "debt_to_income",               # 부채/소득 비율
        "loan_to_income",               # 대출/소득 비율
    ],
    "alternative": [
        "telecom_no_delinquency",
        "health_insurance_paid_months_12m",
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
        "bad_rate": round(float(y_true.mean()), 4), "n_samples": len(y_true),
    }
    print(f"  [{label}] AUC={auc:.4f} | Gini={gini:.4f} | KS={ks:.4f} | 부도율={y_true.mean():.2%}")
    return metrics


def compute_iv(df, feature, target, bins=10):
    df_tmp = df[[feature, target]].copy().dropna()
    if df_tmp[feature].nunique() <= 1:
        return 0.0
    try:
        df_tmp["bin"] = pd.qcut(df_tmp[feature], q=bins, duplicates="drop")
    except Exception:
        df_tmp["bin"] = pd.cut(df_tmp[feature], bins=5, duplicates="drop")
    total_good = max(1, (df_tmp[target] == 0).sum())
    total_bad  = max(1, (df_tmp[target] == 1).sum())
    iv = 0.0
    for _, group in df_tmp.groupby("bin", observed=True):
        ng = (group[target] == 0).sum()
        nb = (group[target] == 1).sum()
        dg = (ng + 0.5) / (total_good + 0.5)
        db = (nb + 0.5) / (total_bad  + 0.5)
        iv += (dg - db) * np.log(dg / db)
    return iv


def train():
    print("=" * 60)
    print("Behavioral Scorecard (행동평점) 학습 시작")
    print("=" * 60)

    data_path = os.path.join(DATA_DIR, "synthetic_behavioral.parquet")
    if not os.path.exists(data_path):
        print("[오류] 행동평점 데이터 없음. synthetic_data.py 먼저 실행")
        print("  → python ml_pipeline/data/synthetic_data.py")
        return

    df = pd.read_parquet(data_path)
    print(f"\n데이터: {len(df):,}건 | 부도율: {df[TARGET].mean():.2%}")

    # 3개월 이상 경과 고객만 사용 (초기 행동 데이터 불충분 제외)
    df = df[df["months_since_origination"] >= 3].copy()
    print(f"  → 3개월+ 경과 고객: {len(df):,}건")

    # 학습/OOT 분리
    df_train_val = df[~df["is_oot"]].copy()
    df_oot       = df[df["is_oot"]].copy()

    df_train_val = df_train_val.sort_values("observation_date")
    cutoff = int(len(df_train_val) * 0.8)
    df_train    = df_train_val.iloc[:cutoff]
    df_holdout  = df_train_val.iloc[cutoff:]

    print(f"  학습: {len(df_train):,}건 | Hold-out: {len(df_holdout):,}건 | OOT: {len(df_oot):,}건")

    # 피처 선택 (IV >= 0.02)
    available = [f for f in ALL_FEATURES if f in df.columns]
    iv_results = [{"feature": f, "iv": round(compute_iv(df_train, f, TARGET), 4)} for f in available]
    iv_df = pd.DataFrame(iv_results).sort_values("iv", ascending=False)
    selected = iv_df[iv_df["iv"] >= 0.02]["feature"].tolist()
    print(f"\n[피처 선택] {len(selected)}개 선택 (IV >= 0.02)")
    print(iv_df.head(10).to_string(index=False))

    iv_df.to_csv(os.path.join(ARTIFACTS_DIR, "iv_report.csv"), index=False)

    if not HAS_LIBS:
        print("[경고] XGBoost 미설치. IV 보고서만 저장")
        return

    X_train    = df_train[selected].fillna(0)
    y_train    = df_train[TARGET]
    X_holdout  = df_holdout[selected].fillna(0)
    y_holdout  = df_holdout[TARGET]
    X_oot      = df_oot[selected].fillna(0)
    y_oot      = df_oot[TARGET]

    # ── XGBoost 학습 ──────────────────────────────────────────
    print("\n[모델 학습] XGBoost Behavioral Scorecard...")
    scale_pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())

    xgb_params = {
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "n_estimators": 400,
        "learning_rate": 0.05,
        "max_depth": 5,
        "min_child_weight": 30,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": scale_pos_weight,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": 0,
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_aucs = []
    best_model = None

    for fold, (tr_idx, val_idx) in enumerate(cv.split(X_train, y_train), 1):
        Xtr, Xval = X_train.iloc[tr_idx], X_train.iloc[val_idx]
        ytr, yval = y_train.iloc[tr_idx], y_train.iloc[val_idx]

        model = xgb.XGBClassifier(**xgb_params)
        model.fit(
            Xtr, ytr,
            eval_set=[(Xval, yval)],
            verbose=False,
        )
        auc_val = roc_auc_score(yval, model.predict_proba(Xval)[:, 1])
        cv_aucs.append(auc_val)
        print(f"  Fold {fold}: Val AUC={auc_val:.4f}")
        if best_model is None or auc_val == max(cv_aucs):
            best_model = model

    print(f"\n  CV AUC: {np.mean(cv_aucs):.4f} ± {np.std(cv_aucs):.4f}")

    # 최종 모델 전체 학습 데이터로 재학습
    final_model = xgb.XGBClassifier(**xgb_params)
    final_model.fit(X_train, y_train, verbose=False)

    # ── 성능 평가 ─────────────────────────────────────────────
    print("\n[성능 평가]")
    all_metrics = []
    for name, X, y in [("Train", X_train, y_train), ("Hold-out", X_holdout, y_holdout), ("OOT", X_oot, y_oot)]:
        if len(y) == 0:
            continue
        pred = final_model.predict_proba(X)[:, 1]
        all_metrics.append(compute_metrics(y.values, pred, name))

    # ── SHAP 분석 ─────────────────────────────────────────────
    print("\n[SHAP 분석]")
    explainer = shap.TreeExplainer(final_model)
    shap_sample = X_train.sample(min(1000, len(X_train)), random_state=42)
    shap_values = explainer.shap_values(shap_sample)
    feature_importance = pd.DataFrame({
        "feature": selected,
        "mean_abs_shap": np.abs(shap_values).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False)
    print(feature_importance.head(10).to_string(index=False))

    # ── 아티팩트 저장 ─────────────────────────────────────────
    print("\n[아티팩트 저장]")

    model_path = os.path.join(ARTIFACTS_DIR, "behavioral_scorecard.xgb")
    final_model.save_model(model_path)
    print(f"  모델: {model_path}")

    feature_path = os.path.join(ARTIFACTS_DIR, "feature_names.json")
    with open(feature_path, "w") as f:
        json.dump(selected, f, ensure_ascii=False)

    shap_path = os.path.join(ARTIFACTS_DIR, "shap_importance.csv")
    feature_importance.to_csv(shap_path, index=False)

    # Model Card 저장
    oot_metric = next((m for m in all_metrics if m["dataset"] == "OOT"), all_metrics[-1])
    model_card = {
        "model_name":    "Behavioral Scorecard",
        "model_type":    "XGBoost",
        "scorecard_type":"behavioral",
        "version":       "v1.0",
        "trained_at":    datetime.now().isoformat(),
        "data_source":   "synthetic_behavioral.parquet",
        "features":      selected,
        "n_features":    len(selected),
        "cv_auc_mean":   round(float(np.mean(cv_aucs)), 4),
        "cv_auc_std":    round(float(np.std(cv_aucs)), 4),
        "performance": {
            "metrics": all_metrics,
            "oot_gini": oot_metric["gini"],
            "oot_ks":   oot_metric["ks_statistic"],
        },
        "regulatory": {
            "min_gini_threshold":  0.25,
            "min_ks_threshold":    0.15,
            "passes_oot_gini":     oot_metric["gini"] >= 0.25,
            "passes_oot_ks":       oot_metric["ks_statistic"] >= 0.15,
        },
        "hyperparameters": xgb_params,
        "feature_groups": FEATURE_GROUPS,
        "shap_top10": feature_importance.head(10).to_dict("records"),
    }

    class _NpEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (np.integer,)): return int(o)
            if isinstance(o, (np.floating,)): return float(o)
            if isinstance(o, (np.bool_,)): return bool(o)
            if isinstance(o, np.ndarray): return o.tolist()
            return super().default(o)

    card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
    with open(card_path, "w", encoding="utf-8") as f:
        json.dump(model_card, f, ensure_ascii=False, indent=2, cls=_NpEncoder)

    print(f"\n{'='*60}")
    print("Behavioral Scorecard 학습 완료")
    print(f"  OOT Gini:  {oot_metric['gini']:.4f} (기준: >= 0.25)")
    print(f"  OOT KS:    {oot_metric['ks_statistic']:.4f} (기준: >= 0.15)")
    status = "통과" if model_card["regulatory"]["passes_oot_gini"] else "미달"
    print(f"  규제 기준: {status}")
    print(f"{'='*60}")
    return model_card


if __name__ == "__main__":
    train()
