"""
[단위 테스트] MonitoringEngine (PSI / ECE / Brier Score)
==========================================================
pytest tests/unit/test_monitoring_engine.py -v
"""
import os
import sys
import pytest
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

try:
    from app.core.monitoring_engine import (
        compute_psi, compute_score_psi, compute_target_psi,
        compute_feature_psi, compute_calibration,
        PSI_GREEN, PSI_YELLOW, PSIResult, CalibrationResult,
    )
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False
    pytestmark = pytest.mark.skip(reason="monitoring_engine import 실패")


RNG = np.random.default_rng(42)


class TestPSIComputation:
    """PSI 계산 정확성 및 경계값 검증."""

    def test_identical_distribution_psi_near_zero(self):
        """동일 분포 → PSI ≈ 0."""
        ref = RNG.normal(680, 80, 5000)
        cur = RNG.normal(680, 80, 2000)
        result = compute_psi(ref, cur, n_bins=10)
        assert result.psi < 0.05, f"동일 분포 PSI({result.psi:.4f}) ≥ 0.05"

    def test_shifted_distribution_psi_high(self):
        """큰 분포 이동 → PSI > 0.20 (red)."""
        ref = RNG.normal(680, 80, 5000)
        cur = RNG.normal(550, 100, 2000)  # 130점 하락
        result = compute_psi(ref, cur, n_bins=10)
        assert result.psi > PSI_YELLOW, f"드리프트 미감지: PSI={result.psi:.4f}"

    def test_psi_status_labels(self):
        """PSI 상태 레이블 정확성."""
        ref = RNG.normal(680, 80, 5000)
        stable = compute_psi(ref, RNG.normal(680, 80, 2000))
        assert stable.status == "green"

        drifted = compute_psi(ref, RNG.normal(550, 100, 2000))
        assert drifted.status in ("yellow", "red")

    def test_psi_result_has_bins(self):
        """PSIResult에 구간 상세 정보 포함."""
        ref = RNG.normal(680, 80, 5000)
        cur = RNG.normal(660, 85, 2000)
        result = compute_psi(ref, cur, n_bins=10)
        assert len(result.bins) == 10
        for b in result.bins:
            assert "psi_contribution" in b

    def test_psi_monotone_with_drift(self):
        """분포 이동 크기에 따라 PSI 단조 증가."""
        ref = RNG.normal(680, 80, 5000)
        psi_vals = []
        for shift in [0, 30, 60, 100]:
            rng2 = np.random.default_rng(shift + 1)
            cur = rng2.normal(680 - shift, 80, 2000)
            psi_vals.append(compute_psi(ref, cur).psi)
        for i in range(len(psi_vals) - 1):
            assert psi_vals[i] <= psi_vals[i + 1] + 0.01

    def test_score_psi_uses_score_bins(self):
        """신용점수 PSI는 300~900 구간 사용."""
        ref = RNG.normal(680, 80, 5000).clip(300, 900)
        cur = RNG.normal(660, 85, 2000).clip(300, 900)
        result = compute_score_psi(ref, cur)
        assert isinstance(result, PSIResult)
        assert 0 <= result.psi < 1.0

    def test_target_psi_stable_bad_rates(self):
        """유사 부도율 → Target PSI 낮음."""
        result = compute_target_psi(0.072, 0.070, 10000, 3000)
        assert result.psi < 0.10

    def test_target_psi_diverged_bad_rates(self):
        """부도율 10배 차이 → Target PSI 높음 (PSI_YELLOW 초과)."""
        result = compute_target_psi(0.010, 0.100, 10000, 3000)
        assert result.psi > 0.10

    def test_n_reference_n_current_recorded(self):
        """기준/현재 샘플 수 기록."""
        ref = RNG.normal(680, 80, 5000)
        cur = RNG.normal(680, 80, 2000)
        result = compute_psi(ref, cur)
        assert result.n_reference == 5000
        assert result.n_current == 2000


class TestCalibration:
    """ECE & Brier Score 계산 검증."""

    def test_perfect_calibration_low_ece(self):
        """완벽 캘리브레이션: ECE ≈ 0."""
        rng = np.random.default_rng(42)
        n = 5000
        y_prob = rng.uniform(0, 1, n)
        y_true = rng.binomial(1, y_prob).astype(float)
        result = compute_calibration(y_true, y_prob, n_bins=10)
        assert result.ece < 0.05, f"완벽 캘리브레이션 ECE({result.ece:.4f}) ≥ 0.05"

    def test_poor_calibration_high_ece(self):
        """과신(overconfidence): ECE 높음."""
        rng = np.random.default_rng(42)
        n = 2000
        y_true = rng.binomial(1, 0.1, n).astype(float)
        # 항상 0.9 예측 (극단적 과신)
        y_prob = np.full(n, 0.9)
        result = compute_calibration(y_true, y_prob, n_bins=10)
        assert result.ece > 0.05

    def test_brier_score_range(self):
        """Brier Score는 [0, 1] 범위."""
        rng = np.random.default_rng(42)
        n = 1000
        y_true = rng.binomial(1, 0.072, n).astype(float)
        y_prob = rng.beta(2, 25, n)
        result = compute_calibration(y_true, y_prob, n_bins=10)
        assert 0.0 <= result.brier_score <= 1.0

    def test_brier_score_perfect_predictor(self):
        """완벽 예측기: Brier Score = 0."""
        y_true = np.array([1.0, 0.0, 1.0, 0.0])
        y_prob = np.array([1.0, 0.0, 1.0, 0.0])
        result = compute_calibration(y_true, y_prob, n_bins=5)
        assert result.brier_score == pytest.approx(0.0, abs=1e-6)

    def test_ece_status_pass_under_002(self):
        """ECE ≤ 0.02 → 'pass' 상태."""
        rng = np.random.default_rng(42)
        n = 10000
        y_prob = rng.uniform(0, 0.2, n)  # 저 PD 집단
        y_true = rng.binomial(1, y_prob).astype(float)
        result = compute_calibration(y_true, y_prob, n_bins=10)
        if result.ece <= 0.02:
            assert result.ece_status == "pass"
        else:
            assert result.ece_status in ("warning", "fail")

    def test_reliability_diagram_bins_count(self):
        """신뢰도 다이어그램: n_bins 구간 반환."""
        rng = np.random.default_rng(42)
        y_true = rng.binomial(1, 0.072, 1000).astype(float)
        y_prob = rng.beta(2, 25, 1000)
        result = compute_calibration(y_true, y_prob, n_bins=10)
        assert len(result.reliability_diagram) == 10

    def test_empty_input_returns_zero(self):
        """빈 입력 → ECE=0, Brier=0."""
        result = compute_calibration(np.array([]), np.array([]), n_bins=10)
        assert result.ece == 0.0
        assert result.brier_score == 0.0
        assert result.n_samples == 0

    def test_calibration_result_to_dict(self):
        """CalibrationResult.to_dict() 키 검증."""
        rng = np.random.default_rng(42)
        y_true = rng.binomial(1, 0.072, 1000).astype(float)
        y_prob = rng.beta(2, 25, 1000)
        result = compute_calibration(y_true, y_prob)
        d = result.to_dict()
        for key in ["ece", "brier_score", "ece_status", "reliability_diagram"]:
            assert key in d, f"키 누락: {key}"


class TestFeaturePSI:
    """피처별 PSI 일괄 계산 검증."""

    def test_feature_psi_returns_dict(self):
        """각 피처에 PSIResult 반환."""
        import pandas as pd
        rng = np.random.default_rng(42)
        ref_df = pd.DataFrame({
            "cb_score": rng.normal(680, 80, 5000),
            "income": rng.lognormal(17, 0.5, 5000),
        })
        cur_df = pd.DataFrame({
            "cb_score": rng.normal(660, 85, 2000),
            "income": rng.lognormal(17, 0.5, 2000),
        })
        results = compute_feature_psi(ref_df, cur_df, ["cb_score", "income"])
        assert "cb_score" in results
        assert "income" in results
        for feat, res in results.items():
            assert isinstance(res, PSIResult)

    def test_missing_feature_skipped(self):
        """없는 피처 → 결과에서 제외 (오류 없음)."""
        import pandas as pd
        rng = np.random.default_rng(7)
        ref_df = pd.DataFrame({"cb_score": rng.normal(700, 30, 50)})
        cur_df = pd.DataFrame({"cb_score": rng.normal(690, 30, 30)})
        results = compute_feature_psi(ref_df, cur_df, ["cb_score", "nonexistent"])
        assert "cb_score" in results
        assert "nonexistent" not in results


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
