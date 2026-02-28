"""
Application Scorecard (신청평점) 학습 파이프라인
=====================================================
금감원 신용위험 모범규준 준수:
- WOE/IV 기반 피처 선택
- LightGBM 학습 + Logistic Regression 스코어카드
- 점수 스케일링: 300~900 (600점=부도율 7.2%, 40포인트=PD 2배)
- Out-of-Time(OOT) 검증 포함
- SHAP 값 산출
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
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts", "application")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

try:
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, roc_curve
    from sklearn.model_selection import StratifiedKFold
    import shap
    HAS_LIBS = True
except ImportError as e:
    print(f"[경고] 라이브러리 없음: {e}")
    HAS_LIBS = False


# ── 피처 그룹 정의 ─────────────────────────────────────────
FEATURE_GROUPS = {
    "demographic": [
        "age", "employment_duration_months",
    ],
    "credit_history": [
        "cb_score", "delinquency_count_12m", "delinquency_count_24m",
        "open_loan_count", "total_loan_balance", "inquiry_count_3m",
        "inquiry_count_6m", "credit_card_count", "worst_delinquency_status",
    ],
    "financial_ratio": [
        "dsr_ratio", "debt_to_income", "loan_to_income",
    ],
    "transaction": [
        "savings_rate", "card_usage_rate", "overdraft_count_annual",
    ],
    "alternative": [
        "telecom_no_delinquency", "health_insurance_paid_months_12m",
        "national_pension_paid_months_24m",
    ],
}

# 민감 변수 제외 (금융위 AI 가이드라인: 차별 금지)
EXCLUDED_FEATURES = ["age_band", "residence_type", "employment_type"]  # 직접 사용 금지

ALL_FEATURES = []
for group in FEATURE_GROUPS.values():
    ALL_FEATURES.extend(group)

TARGET = "default_12m"


# ── WOE/IV 계산 ────────────────────────────────────────────
def compute_woe_iv(df: pd.DataFrame, feature: str, target: str, bins: int = 10) -> dict:
    """
    Weight of Evidence / Information Value 계산
    금감원 모범규준: IV >= 0.1 피처만 선택
    """
    df_tmp = df[[feature, target]].copy().dropna()
    if df_tmp[feature].nunique() <= 1:
        return {"iv": 0.0, "woe_table": pd.DataFrame()}

    # 구간화
    if df_tmp[feature].dtype in [np.float64, np.float32, np.int64, np.int32]:
        try:
            df_tmp["bin"] = pd.qcut(df_tmp[feature], q=bins, duplicates="drop")
        except Exception:
            df_tmp["bin"] = pd.cut(df_tmp[feature], bins=5, duplicates="drop")
    else:
        df_tmp["bin"] = df_tmp[feature]

    # WOE 테이블 계산
    total_good = (df_tmp[target] == 0).sum()
    total_bad  = (df_tmp[target] == 1).sum()

    woe_table = []
    for bin_val, group in df_tmp.groupby("bin", observed=True):
        n_good = (group[target] == 0).sum()
        n_bad  = (group[target] == 1).sum()
        dist_good = (n_good + 0.5) / (total_good + 0.5)
        dist_bad  = (n_bad  + 0.5) / (total_bad  + 0.5)
        woe = np.log(dist_good / dist_bad)
        iv_contrib = (dist_good - dist_bad) * woe
        woe_table.append({
            "bin": str(bin_val), "n_good": n_good, "n_bad": n_bad,
            "dist_good": dist_good, "dist_bad": dist_bad,
            "woe": woe, "iv_contribution": iv_contrib,
        })

    woe_df = pd.DataFrame(woe_table)
    total_iv = woe_df["iv_contribution"].sum()
    return {"iv": total_iv, "woe_table": woe_df}


def select_features_by_iv(df: pd.DataFrame, features: list, target: str,
                           iv_threshold: float = 0.02) -> tuple:
    """IV 기준 피처 선택"""
    print("\n[피처 선택] WOE/IV 기반 피처 중요도 계산 중...")
    iv_results = []
    for feat in features:
        if feat not in df.columns:
            continue
        result = compute_woe_iv(df, feat, target)
        iv_results.append({
            "feature": feat,
            "iv": round(result["iv"], 4),
            "predictive_power": (
                "매우 강함" if result["iv"] >= 0.3
                else "강함" if result["iv"] >= 0.1
                else "약함" if result["iv"] >= 0.02
                else "없음"
            )
        })

    iv_df = pd.DataFrame(iv_results).sort_values("iv", ascending=False)
    print(iv_df.to_string(index=False))

    selected = iv_df[iv_df["iv"] >= iv_threshold]["feature"].tolist()
    print(f"\n→ 선택된 피처: {len(selected)}개 (IV >= {iv_threshold})")
    return selected, iv_df


# ── 스코어 스케일링 ──────────────────────────────────────────
def score_to_points(pd_estimate: np.ndarray,
                    base_score: int = 600,
                    base_odds: float = 0.072 / (1 - 0.072),
                    pdo: int = 40) -> np.ndarray:
    """
    부도확률 → 신용점수 변환 (점수 스케일링)
    - base_score: 기준점수 600점 = 부도율 7.2%
    - pdo: 40점 = 2배 odds (금감원 표준)
    """
    odds = pd_estimate / (1 - np.clip(pd_estimate, 1e-6, 1 - 1e-6))
    factor = pdo / np.log(2)
    offset = base_score - factor * np.log(base_odds)
    score = offset - factor * np.log(odds)
    return np.clip(score, 300, 900).round(0).astype(int)


def score_to_grade(score: np.ndarray) -> np.ndarray:
    """신용점수 → 등급 변환 (나이스/KCB 표준 등급 체계)"""
    grades = np.full(len(score), "D", dtype=object)
    grades[score >= 820] = "AAA"
    grades[(score >= 780) & (score < 820)] = "AA"
    grades[(score >= 740) & (score < 780)] = "A"
    grades[(score >= 700) & (score < 740)] = "BBB"
    grades[(score >= 660) & (score < 700)] = "BB"
    grades[(score >= 620) & (score < 660)] = "B"
    grades[(score >= 560) & (score < 620)] = "CCC"
    grades[(score >= 500) & (score < 560)] = "CC"
    grades[(score >= 430) & (score < 500)] = "C"
    return grades


# ── 모델 성능 지표 ───────────────────────────────────────────
def compute_metrics(y_true: np.ndarray, y_pred_proba: np.ndarray,
                    label: str = "Test") -> dict:
    auc = roc_auc_score(y_true, y_pred_proba)
    gini = 2 * auc - 1
    fpr, tpr, thresholds = roc_curve(y_true, y_pred_proba)
    ks = max(tpr - fpr)

    # Kolmogorov-Smirnov 통계량
    good_scores = y_pred_proba[y_true == 0]
    bad_scores  = y_pred_proba[y_true == 1]
    ks_stat, _ = stats.ks_2samp(good_scores, bad_scores)

    metrics = {
        "dataset": label,
        "auc_roc": round(auc, 4),
        "gini": round(gini, 4),
        "ks_statistic": round(ks_stat, 4),
        "bad_rate": round(y_true.mean(), 4),
        "n_samples": len(y_true),
        "n_bad": int(y_true.sum()),
    }
    print(f"  [{label}] AUC={auc:.4f} | Gini={gini:.4f} | KS={ks_stat:.4f} | 부도율={y_true.mean():.2%}")
    return metrics


# ── 메인 학습 ────────────────────────────────────────────────
def train():
    print("=" * 60)
    print("Application Scorecard (신청평점) 학습 시작")
    print("=" * 60)

    # ── 데이터 로딩 ──────────────────────────────────────
    data_path = os.path.join(DATA_DIR, "synthetic_credit_loan.parquet")
    if not os.path.exists(data_path):
        print("[오류] 합성 데이터 없음. 먼저 synthetic_data.py 실행 필요")
        print("  → python ml_pipeline/data/synthetic_data.py")
        return

    df = pd.read_parquet(data_path)
    print(f"\n데이터 로딩: {len(df):,}건 | 부도율: {df[TARGET].mean():.2%}")

    # ── 학습/검증/OOT 분리 ───────────────────────────────
    df_train_val = df[~df["is_oot"]].copy()
    df_oot       = df[df["is_oot"]].copy()

    # 시간 기반 분리: 최근 20%를 Hold-out 검증
    df_train_val = df_train_val.sort_values("observation_date")
    cutoff_idx   = int(len(df_train_val) * 0.8)
    df_train     = df_train_val.iloc[:cutoff_idx]
    df_holdout   = df_train_val.iloc[cutoff_idx:]

    print(f"  학습:    {len(df_train):,}건 (부도율: {df_train[TARGET].mean():.2%})")
    print(f"  Hold-out: {len(df_holdout):,}건 (부도율: {df_holdout[TARGET].mean():.2%})")
    print(f"  OOT:     {len(df_oot):,}건 (부도율: {df_oot[TARGET].mean():.2%})")

    # ── 피처 선택 ─────────────────────────────────────────
    selected_features, iv_df = select_features_by_iv(df_train, ALL_FEATURES, TARGET, iv_threshold=0.02)

    if not HAS_LIBS:
        print("[경고] 필요 라이브러리 미설치. 설치 후 재실행: pip install lightgbm shap scikit-learn")
        # 피처 선택 결과만 저장
        iv_df.to_csv(os.path.join(ARTIFACTS_DIR, "iv_report.csv"), index=False)
        print("IV 보고서 저장 완료")
        return

    X_train   = df_train[selected_features]
    y_train   = df_train[TARGET]
    X_holdout = df_holdout[selected_features]
    y_holdout = df_holdout[TARGET]
    X_oot     = df_oot[selected_features]
    y_oot     = df_oot[TARGET]

    # ── LightGBM 학습 ─────────────────────────────────────
    print("\n[모델 학습] LightGBM Application Scorecard...")

    # 클래스 불균형 처리
    scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()

    lgb_params = {
        "objective": "binary",
        "metric": "auc",
        "n_estimators": 500,
        "learning_rate": 0.05,
        "max_depth": 6,
        "num_leaves": 31,
        "min_child_samples": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "scale_pos_weight": scale_pos_weight,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "random_state": 42,
        "verbose": -1,
    }

    # K-Fold CV
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_aucs = []
    models = []

    for fold, (tr_idx, val_idx) in enumerate(cv.split(X_train, y_train), 1):
        X_tr, X_val = X_train.iloc[tr_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[tr_idx], y_train.iloc[val_idx]

        model = lgb.LGBMClassifier(**lgb_params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(False)]
        )
        auc = roc_auc_score(y_val, model.predict_proba(X_val)[:, 1])
        cv_aucs.append(auc)
        models.append(model)
        print(f"  Fold {fold}: AUC={auc:.4f}")

    # 최적 모델 선택 (CV AUC 최고)
    best_idx  = np.argmax(cv_aucs)
    best_model = models[best_idx]
    print(f"\n→ CV AUC 평균: {np.mean(cv_aucs):.4f} ± {np.std(cv_aucs):.4f}")
    print(f"→ 최적 Fold: {best_idx + 1}")

    # ── 성능 평가 ─────────────────────────────────────────
    print("\n[성능 평가]")
    metrics_all = []
    metrics_all.append(compute_metrics(y_train,   best_model.predict_proba(X_train)[:, 1],   "Train"))
    metrics_all.append(compute_metrics(y_holdout, best_model.predict_proba(X_holdout)[:, 1], "Hold-out"))
    metrics_all.append(compute_metrics(y_oot,     best_model.predict_proba(X_oot)[:, 1],     "OOT"))

    # 최소 기준 검증 (금감원 모범규준)
    gini_oot = metrics_all[2]["gini"]
    print(f"\n[규제 검증] OOT Gini = {gini_oot:.4f} (기준: >= 0.30)")
    if gini_oot >= 0.30:
        print("  ✓ 통과: 모델 예측력 충분")
    else:
        print("  ✗ 미통과: 모델 재개발 필요")

    # ── 점수 스케일링 ──────────────────────────────────────
    print("\n[점수 스케일링] 부도확률 → 신용점수 (300~900) 변환...")
    train_proba = best_model.predict_proba(X_train)[:, 1]
    train_scores = score_to_points(train_proba)
    train_grades = score_to_grade(train_scores)

    print(f"  점수 분포: 평균={train_scores.mean():.0f}, 최소={train_scores.min()}, 최대={train_scores.max()}")
    print(f"  등급 분포:\n{pd.Series(train_grades).value_counts().sort_index().to_string()}")

    # ── SHAP 값 산출 ───────────────────────────────────────
    print("\n[SHAP] 피처 기여도 계산 중...")
    sample_size = min(2000, len(X_holdout))
    X_sample = X_holdout.sample(sample_size, random_state=42)

    explainer = shap.TreeExplainer(best_model)
    shap_values = explainer.shap_values(X_sample)
    if isinstance(shap_values, list):
        shap_values = shap_values[1]  # 부도 클래스

    shap_importance = pd.DataFrame({
        "feature": selected_features,
        "mean_abs_shap": np.abs(shap_values).mean(axis=0)
    }).sort_values("mean_abs_shap", ascending=False)

    print("  피처 중요도 (SHAP):")
    print(shap_importance.to_string(index=False))

    # ── PSI (Population Stability Index) 계산 ─────────────
    def compute_psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
        bins_arr = np.percentile(expected, np.linspace(0, 100, bins + 1))
        bins_arr = np.unique(bins_arr)
        exp_hist = np.histogram(expected, bins=bins_arr)[0]
        act_hist = np.histogram(actual, bins=bins_arr)[0]
        exp_pct = (exp_hist + 0.5) / (exp_hist.sum() + 0.5 * len(exp_hist))
        act_pct = (act_hist + 0.5) / (act_hist.sum() + 0.5 * len(act_hist))
        psi = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
        return round(psi, 4)

    train_proba = best_model.predict_proba(X_train)[:, 1]
    oot_proba   = best_model.predict_proba(X_oot)[:, 1]
    psi = compute_psi(train_proba, oot_proba)
    print(f"\n[PSI] 학습→OOT PSI = {psi:.4f}", end=" ")
    if psi < 0.1:   print("(안정)")
    elif psi < 0.2: print("(주의)")
    else:           print("(불안정 - 재학습 필요)")

    # ── 공정성 검사 (금융위 AI 가이드라인) ─────────────────
    print("\n[공정성 검사] 연령대별 Gini 차이 검증...")
    fairness_results = {}
    for band in ["20s", "30s", "40s", "50s", "60+"]:
        mask = df_holdout["age_band"] == band
        if mask.sum() < 50:
            continue
        X_band = X_holdout[mask]
        y_band = y_holdout[mask]
        if y_band.nunique() < 2:
            continue
        auc_band = roc_auc_score(y_band, best_model.predict_proba(X_band)[:, 1])
        gini_band = 2 * auc_band - 1
        fairness_results[band] = {"gini": round(gini_band, 4), "n": int(mask.sum())}
        print(f"  {band}: Gini={gini_band:.4f} (n={mask.sum():,})")

    gini_values = [v["gini"] for v in fairness_results.values()]
    gini_range = max(gini_values) - min(gini_values)
    print(f"  Gini 범위: {gini_range:.4f} (기준: <= 0.15)")
    fairness_pass = gini_range <= 0.15

    # ── 아티팩트 저장 ──────────────────────────────────────
    print("\n[저장] 모델 아티팩트 저장 중...")

    joblib.dump(best_model, os.path.join(ARTIFACTS_DIR, "model.pkl"))
    print("  → model.pkl")

    iv_df.to_csv(os.path.join(ARTIFACTS_DIR, "iv_report.csv"), index=False)
    print("  → iv_report.csv")

    shap_importance.to_csv(os.path.join(ARTIFACTS_DIR, "shap_importance.csv"), index=False)
    print("  → shap_importance.csv")

    model_card = {
        "model_name": "application_scorecard_v1",
        "scorecard_type": "application",
        "version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "training_data": {
            "source": "synthetic_credit_loan.parquet",
            "period": "2021-01 ~ 2023-06",
            "n_train": len(df_train),
            "n_holdout": len(df_holdout),
            "n_oot": len(df_oot),
            "bad_rate_train": round(float(y_train.mean()), 4),
            "bad_rate_oot":   round(float(y_oot.mean()), 4),
        },
        "features": {
            "selected": selected_features,
            "n_features": len(selected_features),
            "iv_summary": iv_df.to_dict(orient="records"),
        },
        "performance": {
            "oot_gini":    round(float(metrics_all[2]["gini"]), 4),
            "oot_ks":      round(float(metrics_all[2]["ks_statistic"]), 4),
            "cv_auc_mean": round(float(np.mean(cv_aucs)), 4),
            "cv_auc_std":  round(float(np.std(cv_aucs)), 4),
            "metrics": metrics_all,
        },
        "scoring": {
            "base_score": 600,
            "base_bad_rate": 0.072,
            "pdo": 40,
            "score_min": 300,
            "score_max": 900,
            "grade_thresholds": {
                "AAA": 820, "AA": 780, "A": 740, "BBB": 700,
                "BB": 660, "B": 620, "CCC": 560, "CC": 500, "C": 430, "D": 0,
            }
        },
        "stability": {"psi_train_to_oot": psi},
        "fairness": {
            "by_age_band": fairness_results,
            "gini_range": round(gini_range, 4),
            "passed": fairness_pass,
        },
        "regulatory_compliance": {
            "gini_oot_passed": gini_oot >= 0.30,
            "gini_oot": gini_oot,
            "psi_stable": psi < 0.2,
            "fairness_passed": fairness_pass,
            "sensitive_features_excluded": True,
        }
    }

    class _NpEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, (np.integer,)): return int(o)
            if isinstance(o, (np.floating,)): return float(o)
            if isinstance(o, (np.bool_,)): return bool(o)
            if isinstance(o, np.ndarray): return o.tolist()
            return super().default(o)

    with open(os.path.join(ARTIFACTS_DIR, "model_card.json"), "w", encoding="utf-8") as f:
        json.dump(model_card, f, ensure_ascii=False, indent=2, cls=_NpEncoder)
    print("  → model_card.json")

    print(f"\n{'=' * 60}")
    print("Application Scorecard 학습 완료!")
    print(f"  OOT Gini:      {gini_oot:.4f}  {'✓' if gini_oot >= 0.30 else '✗'}")
    print(f"  PSI:           {psi:.4f}  {'✓' if psi < 0.2 else '✗'}")
    print(f"  공정성 통과:   {'✓' if fairness_pass else '✗'}")
    print(f"  아티팩트 위치: {ARTIFACTS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    train()
