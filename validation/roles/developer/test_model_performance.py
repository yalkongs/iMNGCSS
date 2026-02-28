"""
[역할: 모델 개발팀] 모델 성능 검증
===========================================
책임: 모델의 통계적 유효성, 피처 품질, 안정성 검증
기준:
  - OOT Gini >= 0.30 (금감원 모범규준 최소 기준)
  - KS 통계량 >= 0.20
  - PSI < 0.20 (학습→OOT 안정성)
  - IV >= 0.02 피처만 사용
  - 과적합 검사: Train Gini - OOT Gini <= 0.15

실행: pytest validation/roles/developer/ -v
"""
import os, sys, json
import numpy as np
import pandas as pd
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application")
DATA_DIR = os.path.join(BASE_DIR, "ml_pipeline", "data")


def load_model_card() -> dict:
    path = os.path.join(ARTIFACTS_DIR, "model_card.json")
    if not os.path.exists(path):
        pytest.skip("model_card.json 없음. 먼저 train_application.py 실행")
    with open(path) as f:
        return json.load(f)


def load_iv_report() -> pd.DataFrame:
    path = os.path.join(ARTIFACTS_DIR, "iv_report.csv")
    if not os.path.exists(path):
        pytest.skip("iv_report.csv 없음")
    return pd.read_csv(path)


class TestModelDiscrimination:
    """모델 판별력 검증"""

    def test_oot_gini_minimum(self):
        """[DEV-01] OOT Gini >= 0.30 (금감원 모범규준 최소 기준)"""
        mc = load_model_card()
        metrics = {m["dataset"]: m for m in mc["performance"]["metrics"]}
        oot_gini = metrics["OOT"]["gini"]
        assert oot_gini >= 0.30, (
            f"OOT Gini={oot_gini:.4f} < 0.30 → 모델 예측력 불충분. "
            "피처 추가/알고리즘 변경 후 재학습 필요"
        )

    def test_oot_ks_minimum(self):
        """[DEV-02] OOT KS 통계량 >= 0.20"""
        mc = load_model_card()
        metrics = {m["dataset"]: m for m in mc["performance"]["metrics"]}
        oot_ks = metrics["OOT"]["ks_statistic"]
        assert oot_ks >= 0.20, f"OOT KS={oot_ks:.4f} < 0.20"

    def test_oot_auc_minimum(self):
        """[DEV-03] OOT AUC-ROC >= 0.65"""
        mc = load_model_card()
        metrics = {m["dataset"]: m for m in mc["performance"]["metrics"]}
        oot_auc = metrics["OOT"]["auc_roc"]
        assert oot_auc >= 0.65, f"OOT AUC={oot_auc:.4f} < 0.65"

    def test_train_holdout_gini_consistency(self):
        """[DEV-04] Train-HoldOut Gini 차이 <= 0.10 (과적합 검사)"""
        mc = load_model_card()
        metrics = {m["dataset"]: m for m in mc["performance"]["metrics"]}
        train_gini = metrics["Train"]["gini"]
        holdout_gini = metrics["Hold-out"]["gini"]
        diff = train_gini - holdout_gini
        assert diff <= 0.10, (
            f"과적합 의심: Train Gini({train_gini:.4f}) - Hold-out Gini({holdout_gini:.4f}) = {diff:.4f} > 0.10"
        )

    def test_holdout_oot_gini_consistency(self):
        """[DEV-05] Hold-out - OOT Gini 차이 <= 0.15 (시간적 안정성)"""
        mc = load_model_card()
        metrics = {m["dataset"]: m for m in mc["performance"]["metrics"]}
        holdout_gini = metrics["Hold-out"]["gini"]
        oot_gini = metrics["OOT"]["gini"]
        diff = holdout_gini - oot_gini
        assert diff <= 0.15, f"시간적 안정성 불량: Hold-out({holdout_gini:.4f}) - OOT({oot_gini:.4f}) = {diff:.4f} > 0.15"

    def test_cv_auc_stability(self):
        """[DEV-06] CV AUC 표준편차 <= 0.02 (교차검증 안정성)"""
        mc = load_model_card()
        cv_std = mc["performance"]["cv_auc_std"]
        assert cv_std <= 0.02, f"CV AUC Std={cv_std:.4f} > 0.02 → 모델 불안정"


class TestFeatureQuality:
    """피처 품질 검증"""

    def test_all_features_have_positive_iv(self):
        """[DEV-07] 선택된 모든 피처 IV >= 0.02"""
        iv_df = load_iv_report()
        mc = load_model_card()
        selected = mc["features"]["selected"]
        used_iv = iv_df[iv_df["feature"].isin(selected)]
        low_iv = used_iv[used_iv["iv"] < 0.02]
        assert len(low_iv) == 0, (
            f"IV < 0.02 피처가 모델에 포함됨: {low_iv['feature'].tolist()}"
        )

    def test_top_features_high_iv(self):
        """[DEV-08] 상위 3개 피처 중 최소 2개 IV >= 0.10 (중요 피처 충분)"""
        iv_df = load_iv_report()
        mc = load_model_card()
        selected = mc["features"]["selected"]
        used_iv = iv_df[iv_df["feature"].isin(selected)].sort_values("iv", ascending=False)
        top3_high = (used_iv.head(3)["iv"] >= 0.10).sum()
        assert top3_high >= 2, "상위 3개 피처 중 IV >= 0.10이 2개 미만"

    def test_no_sensitive_features_used(self):
        """[DEV-09] 민감 변수 미사용 (성별/거주지 등 직접 차별 변수)"""
        mc = load_model_card()
        selected = set(mc["features"]["selected"])
        forbidden = {"gender", "sex", "nationality", "religion",
                     "marital_status", "disability_status"}
        used_sensitive = selected & forbidden
        assert len(used_sensitive) == 0, f"민감 변수 사용됨: {used_sensitive}"

    def test_feature_count_reasonable(self):
        """[DEV-10] 피처 수 5~50개 (과소/과다 피처 방지)"""
        mc = load_model_card()
        n_feat = mc["features"]["n_features"]
        assert 5 <= n_feat <= 50, f"피처 수 = {n_feat} (기준: 5~50개)"


class TestModelStability:
    """모델 안정성 검증"""

    def test_psi_stable(self):
        """[DEV-11] PSI(학습→OOT) < 0.10 (안정), < 0.20 (주의), >= 0.20 (불안정)"""
        mc = load_model_card()
        psi = mc["stability"]["psi_train_to_oot"]
        assert psi < 0.20, (
            f"PSI={psi:.4f} >= 0.20 → 모집단 변화 감지. 모델 재학습 권장"
        )

    def test_psi_warning_level(self):
        """[DEV-12] PSI < 0.10 (안정 수준 권장)"""
        mc = load_model_card()
        psi = mc["stability"]["psi_train_to_oot"]
        if psi >= 0.10:
            import warnings
            warnings.warn(f"PSI={psi:.4f} >= 0.10 → 주의 수준. 모니터링 강화 필요")

    def test_score_distribution_reasonable(self):
        """[DEV-13] 점수 스케일 300~900 사용"""
        mc = load_model_card()
        scoring = mc["scoring"]
        assert scoring["score_min"] == 300
        assert scoring["score_max"] == 900
        assert scoring["pdo"] == 40  # 40포인트 = 2배 odds (업계 표준)

    def test_bad_rate_consistency(self):
        """[DEV-14] 학습/OOT 부도율 차이 <= 5%p"""
        mc = load_model_card()
        train_br = mc["training_data"]["bad_rate_train"]
        oot_br = mc["training_data"]["bad_rate_oot"]
        diff = abs(train_br - oot_br)
        assert diff <= 0.05, (
            f"부도율 차이: |{train_br:.2%} - {oot_br:.2%}| = {diff:.2%} > 5%p "
            "→ 모집단 이동 의심"
        )
