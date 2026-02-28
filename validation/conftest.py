"""
pytest 공통 픽스처
==================
모든 validation 테스트에서 공유하는 픽스처 및 헬퍼.

구조:
  - synthetic_data: 합성 데이터 로드 (신용/행동/추심)
  - mock_scoring_engine: ScoringEngine 단위 테스트용
  - sample_scores / sample_pds: 점수·PD 배열 생성
  - regulation_params: BRMS 기본값 딕셔너리

실행: pytest validation/ -v
"""
import os
import sys
import math
import json
import pytest
import numpy as np
import pandas as pd
from typing import Optional

# 프로젝트 루트를 sys.path에 추가
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

DATA_DIR = os.path.join(BASE_DIR, "ml_pipeline", "data")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "ml_pipeline", "artifacts")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 합성 데이터 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def credit_df() -> pd.DataFrame:
    """신용대출 합성 데이터 (session 범위 — 한 번만 로드)."""
    path = os.path.join(DATA_DIR, "synthetic_credit.parquet")
    if not os.path.exists(path):
        pytest.skip("synthetic_credit.parquet 없음. ml_pipeline/data/synthetic_data.py 먼저 실행")
    return pd.read_parquet(path)


@pytest.fixture(scope="session")
def behavioral_df() -> pd.DataFrame:
    """행동평점 합성 데이터."""
    path = os.path.join(DATA_DIR, "synthetic_behavioral.parquet")
    if not os.path.exists(path):
        pytest.skip("synthetic_behavioral.parquet 없음")
    return pd.read_parquet(path)


@pytest.fixture(scope="session")
def collection_df() -> pd.DataFrame:
    """추심평점 합성 데이터."""
    path = os.path.join(DATA_DIR, "synthetic_collection.parquet")
    if not os.path.exists(path):
        pytest.skip("synthetic_collection.parquet 없음")
    return pd.read_parquet(path)


@pytest.fixture(scope="session")
def application_model_card() -> dict:
    """Application Scorecard model_card.json."""
    path = os.path.join(ARTIFACTS_DIR, "application", "model_card.json")
    if not os.path.exists(path):
        pytest.skip("application model_card.json 없음")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def behavioral_model_card() -> dict:
    """Behavioral Scorecard model_card.json."""
    path = os.path.join(ARTIFACTS_DIR, "behavioral", "model_card.json")
    if not os.path.exists(path):
        pytest.skip("behavioral model_card.json 없음")
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def collection_model_card() -> dict:
    """Collection Scorecard model_card.json."""
    path = os.path.join(ARTIFACTS_DIR, "collection", "model_card.json")
    if not os.path.exists(path):
        pytest.skip("collection model_card.json 없음")
    with open(path) as f:
        return json.load(f)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 스코어링 헬퍼 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCORE_BASE = 600
SCORE_PDO = 40
BASE_PD = 0.072


def _pd_to_score(pd: float) -> int:
    pd = max(1e-6, min(pd, 0.9999))
    odds = pd / (1 - pd)
    base_odds = BASE_PD / (1 - BASE_PD)
    score = SCORE_BASE - (SCORE_PDO / math.log(2)) * math.log(odds / base_odds)
    return int(max(300, min(900, round(score))))


def _monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    if months <= 0 or principal <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


@pytest.fixture(scope="session")
def pd_to_score():
    """PD → 점수 변환 함수."""
    return _pd_to_score


@pytest.fixture(scope="session")
def monthly_payment_fn():
    """월상환액 계산 함수."""
    return _monthly_payment


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 샘플 배열 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def sample_scores() -> np.ndarray:
    """대표 신용점수 샘플 (1,000건, 정규분포 중심 680점)."""
    rng = np.random.default_rng(42)
    scores = rng.normal(680, 80, 1000).clip(300, 900)
    return scores.astype(int)


@pytest.fixture(scope="session")
def sample_pds() -> np.ndarray:
    """대표 PD 샘플 (1,000건, 베타 분포)."""
    rng = np.random.default_rng(42)
    return rng.beta(2, 25, 1000)  # 평균 약 7.4%


@pytest.fixture(scope="session")
def sample_binary_outcomes(sample_pds) -> np.ndarray:
    """PD 기반 이진 부도 결과 (0/1)."""
    rng = np.random.default_rng(42)
    return rng.binomial(1, sample_pds).astype(float)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 규제 파라미터 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def regulation_params() -> dict:
    """BRMS 기본 규제 파라미터."""
    return {
        "dsr_max": 0.40,
        "ltv_general": 0.70,
        "ltv_regulated": 0.60,
        "ltv_speculation": 0.40,
        "max_interest_rate": 0.20,
        "hurdle_rate": 0.15,
        "stress_dsr_phase2": {
            "metropolitan": {"variable": 0.0075, "mixed": 0.0038},
            "non_metropolitan": {"variable": 0.0150, "mixed": 0.0075},
        },
        "stress_dsr_phase3": {
            "metropolitan": {"variable": 0.0150, "mixed": 0.0075},
            "non_metropolitan": {"variable": 0.0300, "mixed": 0.0150},
        },
        "eq_grade": {
            "EQ-S": {"limit_multiplier": 2.0, "rate_adjustment": -0.005},
            "EQ-A": {"limit_multiplier": 1.5, "rate_adjustment": -0.003},
            "EQ-B": {"limit_multiplier": 1.2, "rate_adjustment": -0.001},
            "EQ-C": {"limit_multiplier": 1.0, "rate_adjustment": 0.000},
            "EQ-D": {"limit_multiplier": 0.8, "rate_adjustment": 0.002},
            "EQ-E": {"limit_multiplier": 0.7, "rate_adjustment": 0.005},
        },
        "segments": {
            "SEG-DR":  {"guaranteed_eq": "EQ-B", "limit_multiplier": 3.0, "rate_discount": -0.003},
            "SEG-JD":  {"guaranteed_eq": "EQ-B", "limit_multiplier": 2.5, "rate_discount": -0.002},
            "SEG-ART": {"guaranteed_eq": None,   "limit_multiplier": 1.2, "rate_discount": 0.000},
            "SEG-YTH": {"guaranteed_eq": None,   "limit_multiplier": 1.0, "rate_discount": -0.005},
            "SEG-MIL": {"guaranteed_eq": "EQ-S", "limit_multiplier": 2.0, "rate_discount": -0.005},
            "SEG-MOU": {"guaranteed_eq": None,   "limit_multiplier": 1.5, "rate_discount": -0.003},
        },
        "cutoff_reject": 450,
        "cutoff_manual": 530,
        "score_min": 300,
        "score_max": 900,
        "lgd": {
            "credit": 0.45,
            "credit_soho": 0.50,
            "mortgage": 0.25,
            "micro": 0.60,
        },
        "ccf_revolving": 0.50,
        "capital_ratio": 0.08,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 차주 프로파일 팩토리 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def make_borrower_profile():
    """
    표준 차주 프로파일 생성 팩토리.
    기본값을 오버라이드하여 다양한 시나리오 테스트.
    """
    def _factory(**overrides) -> dict:
        defaults = {
            "applicant_type": "individual",
            "age": 35,
            "employment_type": "employed",
            "income_annual_wan": 5000,     # 5천만원 (만원 단위)
            "cb_score": 700,
            "delinquency_count_12m": 0,
            "worst_delinquency_status": 0,
            "open_loan_count": 1,
            "total_loan_balance_wan": 5000,  # 5천만원
            "inquiry_count_3m": 1,
            "dsr_ratio": 0.25,
            "product_type": "credit",
            "requested_amount_wan": 3000,    # 3천만원
            "requested_term_months": 36,
            "segment_code": "",
            "eq_grade": "EQ-C",
            "irg_code": "M",
        }
        defaults.update(overrides)
        return defaults
    return _factory


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 스트레스 테스트 헬퍼
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def stress_scenarios() -> list[dict]:
    """표준 스트레스 시나리오 3종 (금감원 스트레스 테스트 시나리오)."""
    return [
        {
            "name": "mild",
            "label": "경미 (Mild)",
            "pd_multiplier": 1.5,
            "lgd_addon": 0.05,
            "rate_shock_bp": 100,       # +1%p 금리 충격
            "collateral_drop": 0.10,    # 담보 10% 하락
        },
        {
            "name": "moderate",
            "label": "중간 (Moderate)",
            "pd_multiplier": 2.0,
            "lgd_addon": 0.10,
            "rate_shock_bp": 200,       # +2%p 금리 충격
            "collateral_drop": 0.20,    # 담보 20% 하락
        },
        {
            "name": "severe",
            "label": "심각 (Severe)",
            "pd_multiplier": 3.0,
            "lgd_addon": 0.15,
            "rate_shock_bp": 300,       # +3%p 금리 충격
            "collateral_drop": 0.30,    # 담보 30% 하락
        },
    ]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PSI/Calibration 계산 유틸리티
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="session")
def compute_psi_fn():
    """PSI 계산 함수 (monitoring_engine에서 임포트)."""
    monitoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "monitoring_engine.py")
    if not os.path.exists(monitoring_path):
        # 인라인 구현 폴백
        def _compute_psi(ref, cur, n_bins=10):
            ref = np.asarray(ref, dtype=float)
            cur = np.asarray(cur, dtype=float)
            percentiles = np.linspace(0, 100, n_bins + 1)
            bins = np.percentile(ref, percentiles)
            bins[0] = -np.inf
            bins[-1] = np.inf
            ref_c, _ = np.histogram(ref, bins=bins)
            cur_c, _ = np.histogram(cur, bins=bins)
            ref_p = (ref_c + 0.5) / (len(ref) + 0.5 * n_bins)
            cur_p = (cur_c + 0.5) / (len(cur) + 0.5 * n_bins)
            return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))
        return _compute_psi

    sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
    try:
        from app.core.monitoring_engine import compute_psi
        return lambda ref, cur, n_bins=10: compute_psi(ref, cur, n_bins).psi
    except ImportError:
        return None
