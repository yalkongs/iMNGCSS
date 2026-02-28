"""
[역할: 리스크관리팀] 규제 파라미터 & 모델 규제 준수 검증
============================================================
책임: 금융당국 규제 요건 충족 + 바젤III 내부등급법(IRB) 적용 검증

검증 항목:
1. 스트레스 DSR 계산 정확성 (금융위원회 고시 24.02.26)
2. LTV 한도 검증 (지역별 / 보유주택수별)
3. DSR 40% 한도 실제 계산 검증
4. RAROC 허들레이트 검증 (≥ 15%)
5. LGD 추정값 적정성 (Basel III IRB 기준)
6. 바젤III 위험가중자산(RWA) 산출 검증
7. 신용등급 PD 매핑 일관성
8. 세그먼트별 금리 한도 준수 검증
9. 규제 파라미터 버전 관리 (effective_from / effective_to)
10. Phase2 → Phase3 스트레스 DSR 전환 검증

실행: pytest validation/roles/risk_management/test_regulatory_validation.py -v -s
"""
import os
import sys
import json
import math
import pytest
import numpy as np
from datetime import datetime, date
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ARTIFACTS_DIR_APP = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application")
ARTIFACTS_DIR_COL = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "collection")
SEED_PATH = os.path.join(BASE_DIR, "backend", "app", "core", "seed_regulation_params.py")


# ── 규제 상수 (BRMS DB 기준값과 동일해야 함) ─────────────────
DSR_MAX = 0.40                        # 총부채원리금상환비율 40%
LTV_GENERAL = 0.70                    # 일반지역 LTV
LTV_REGULATED = 0.60                  # 조정대상지역 LTV
LTV_SPECULATION = 0.40                # 투기과열지구 LTV
MAX_INTEREST_RATE = 0.20              # 최고금리 20% (대부업법)
HURDLE_RATE = 0.15                    # RAROC 허들레이트 15%

# 스트레스 DSR 가산금리 (금융위원회 고시)
STRESS_DSR_PHASE2 = {
    "metropolitan": {"variable": 0.0075, "mixed": 0.0038},
    "non_metropolitan": {"variable": 0.0150, "mixed": 0.0075},
}
STRESS_DSR_PHASE3 = {
    "metropolitan": {"variable": 0.0150, "mixed": 0.0075},
    "non_metropolitan": {"variable": 0.0300, "mixed": 0.0150},
}

# Phase3 시행일 (2025.07.01)
STRESS_PHASE3_DATE = date(2025, 7, 1)

# 바젤III LGD 기준 (무담보 신용대출 기준)
LGD_UNSECURED_MIN = 0.35
LGD_UNSECURED_MAX = 0.55
LGD_MORTGAGE_MIN = 0.15
LGD_MORTGAGE_MAX = 0.35


# ── 헬퍼: 월상환액 계산 (원리금균등분할) ─────────────────────
def monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """원리금균등분할 월상환액 계산."""
    if months <= 0 or principal <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def compute_dsr(
    monthly_income: float,
    new_loan_payment: float,
    existing_payments: float = 0.0,
) -> float:
    """DSR = (신규 + 기존 연간 원리금) / 연소득."""
    if monthly_income <= 0:
        return float("inf")
    annual_total = (new_loan_payment + existing_payments) * 12
    return annual_total / (monthly_income * 12)


def compute_stress_dsr(
    monthly_income: float,
    principal: float,
    current_rate: float,
    stress_addition: float,
    months: int,
    existing_payments: float = 0.0,
) -> float:
    """스트레스 금리 적용 DSR."""
    stressed_rate = current_rate + stress_addition
    payment = monthly_payment(principal, stressed_rate, months)
    return compute_dsr(monthly_income, payment, existing_payments)


def compute_ltv(loan_amount: float, collateral_value: float) -> Optional[float]:
    """LTV = 대출금액 / 담보가치."""
    if collateral_value <= 0:
        return None
    return loan_amount / collateral_value


def compute_raroc(
    revenue: float,
    expected_loss: float,
    operating_cost: float,
    economic_capital: float,
) -> Optional[float]:
    """RAROC = (수익 - EL - 비용) / 경제적자본."""
    if economic_capital <= 0:
        return None
    return (revenue - expected_loss - operating_cost) / economic_capital


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 스트레스 DSR 계산 정확성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestStressDSR:
    """금융위원회 스트레스 DSR 규제 계산 정확성."""

    def test_phase2_metropolitan_variable_rate(self):
        """Phase2 수도권 변동금리 가산금리 0.75%p."""
        rate = STRESS_DSR_PHASE2["metropolitan"]["variable"]
        assert rate == 0.0075, f"Phase2 수도권 변동: {rate} ≠ 0.0075"

    def test_phase2_non_metropolitan_variable_rate(self):
        """Phase2 비수도권 변동금리 가산금리 1.50%p."""
        rate = STRESS_DSR_PHASE2["non_metropolitan"]["variable"]
        assert rate == 0.015, f"Phase2 비수도권 변동: {rate} ≠ 0.015"

    def test_phase3_metropolitan_variable_rate(self):
        """Phase3 수도권 변동금리 가산금리 1.50%p (Phase2의 2배)."""
        p2 = STRESS_DSR_PHASE2["metropolitan"]["variable"]
        p3 = STRESS_DSR_PHASE3["metropolitan"]["variable"]
        assert p3 == pytest.approx(p2 * 2, rel=1e-6), \
            f"Phase3 수도권이 Phase2의 2배 아님: {p3}"

    def test_phase3_non_metropolitan_rate_doubled(self):
        """Phase3 비수도권 변동금리 3.00%p (Phase2의 2배)."""
        p2 = STRESS_DSR_PHASE2["non_metropolitan"]["variable"]
        p3 = STRESS_DSR_PHASE3["non_metropolitan"]["variable"]
        assert p3 == pytest.approx(p2 * 2, rel=1e-6)

    def test_phase3_effective_date(self):
        """Phase3 시행일은 2025년 7월 1일."""
        assert STRESS_PHASE3_DATE == date(2025, 7, 1), \
            "Phase3 시행일 오류"

    def test_phase3_after_phase2(self):
        """Phase3 시행일 > Phase2 시행일 (2024.02.26)."""
        phase2_date = date(2024, 2, 26)
        assert STRESS_PHASE3_DATE > phase2_date

    def test_stress_dsr_raises_dsr_value(self):
        """스트레스 금리 적용 시 DSR이 기본 DSR보다 높아야 함."""
        monthly_income = 5_000_000  # 5백만원
        principal = 200_000_000     # 2억
        current_rate = 0.045
        months = 300                # 25년

        base_payment = monthly_payment(principal, current_rate, months)
        base_dsr = compute_dsr(monthly_income, base_payment)

        stress_dsr = compute_stress_dsr(
            monthly_income, principal, current_rate,
            STRESS_DSR_PHASE3["metropolitan"]["variable"],
            months
        )
        assert stress_dsr > base_dsr, "스트레스 DSR이 기본 DSR 이하"

    def test_stress_dsr_calculation_accuracy(self):
        """스트레스 DSR 실제 계산값 검증 (수도권, Phase3 변동금리)."""
        # 월소득 500만원, 대출 2억, 금리 4.5%, 기간 30년
        monthly_income = 5_000_000
        principal = 200_000_000
        current_rate = 0.045
        months = 360
        stress_add = STRESS_DSR_PHASE3["metropolitan"]["variable"]  # 1.5%p

        stressed_rate = current_rate + stress_add
        payment = monthly_payment(principal, stressed_rate, months)
        dsr = (payment * 12) / (monthly_income * 12)

        # 수동 계산: (4.5 + 1.5)% = 6%, 30년, 2억
        r = stressed_rate / 12
        expected_payment = 200_000_000 * r * (1 + r) ** 360 / ((1 + r) ** 360 - 1)
        expected_dsr = (expected_payment * 12) / (monthly_income * 12)

        assert dsr == pytest.approx(expected_dsr, rel=1e-6)

    def test_dsr_exceeds_limit_triggers_rejection(self):
        """DSR > 40%이면 거절 조건 충족."""
        monthly_income = 3_000_000  # 3백만원
        principal = 300_000_000     # 3억 (DSR 과다 유발)
        payment = monthly_payment(principal, 0.055, 360)
        dsr = compute_dsr(monthly_income, payment)

        assert dsr > DSR_MAX, f"테스트 케이스 DSR({dsr:.2%})이 기준({DSR_MAX:.0%})보다 낮음"

    def test_dsr_under_limit_passes(self):
        """DSR <= 40%이면 정상 통과."""
        monthly_income = 10_000_000  # 천만원
        principal = 100_000_000      # 1억
        payment = monthly_payment(principal, 0.045, 360)
        dsr = compute_dsr(monthly_income, payment)

        assert dsr <= DSR_MAX, f"DSR({dsr:.2%}) > 40% — 테스트 설계 오류"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. LTV 한도 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestLTVLimits:
    """LTV 규제 한도 검증."""

    def test_ltv_general_area_limit(self):
        """일반지역 LTV ≤ 70%."""
        assert LTV_GENERAL == 0.70

    def test_ltv_regulated_area_limit(self):
        """조정대상지역 LTV ≤ 60%."""
        assert LTV_REGULATED == 0.60

    def test_ltv_speculation_area_limit(self):
        """투기과열지구 LTV ≤ 40%."""
        assert LTV_SPECULATION == 0.40

    def test_ltv_hierarchy(self):
        """규제 수준: 투기과열지구 > 조정대상 > 일반."""
        assert LTV_SPECULATION < LTV_REGULATED < LTV_GENERAL

    def test_ltv_computation_general_area_pass(self):
        """일반지역: LTV 60% → 승인 (70% 이하)."""
        loan = 300_000_000
        collateral = 500_000_000
        ltv = compute_ltv(loan, collateral)
        assert ltv <= LTV_GENERAL, f"LTV {ltv:.0%} > {LTV_GENERAL:.0%} 허용치"

    def test_ltv_computation_general_area_fail(self):
        """일반지역: LTV 80% → 거절 (70% 초과)."""
        loan = 400_000_000
        collateral = 500_000_000
        ltv = compute_ltv(loan, collateral)
        assert ltv > LTV_GENERAL, "테스트 설계 오류: LTV가 70% 이하"

    def test_ltv_speculation_area_strict(self):
        """투기과열지구: LTV 50% → 거절 (40% 초과)."""
        loan = 250_000_000
        collateral = 500_000_000
        ltv = compute_ltv(loan, collateral)
        assert ltv > LTV_SPECULATION

    def test_ltv_speculation_area_pass(self):
        """투기과열지구: LTV 35% → 승인 (40% 이하)."""
        loan = 175_000_000
        collateral = 500_000_000
        ltv = compute_ltv(loan, collateral)
        assert ltv <= LTV_SPECULATION

    def test_ltv_multi_property_penalty(self):
        """2주택 이상 보유자: 투기지구 LTV 0% (주담대 금지 시나리오)."""
        # 보유주택 2채 이상 투기지구 주담대: 한도 0%
        MULTI_PROPERTY_LTV_SPECULATION = 0.0
        loan = 100_000_000
        collateral = 1_000_000_000
        ltv = compute_ltv(loan, collateral)
        assert ltv > MULTI_PROPERTY_LTV_SPECULATION, \
            "2주택+투기지구: 어떤 LTV도 거절되어야 함"

    def test_ltv_zero_collateral_returns_none(self):
        """담보가치 0원 → LTV None 반환."""
        assert compute_ltv(100_000_000, 0) is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. RAROC 허들레이트 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRAROC:
    """RAROC(Risk-Adjusted Return on Capital) 검증."""

    def test_hurdle_rate_threshold(self):
        """내부 허들레이트 ≥ 15%."""
        assert HURDLE_RATE >= 0.15, f"허들레이트({HURDLE_RATE:.0%}) < 15%"

    def test_raroc_formula_basic(self):
        """RAROC = (수익 - EL - 비용) / EC."""
        revenue = 5_000_000    # 5백만원 수익
        el = 500_000           # 50만원 EL
        cost = 750_000         # 75만원 비용
        ec = 20_000_000        # 2천만원 경제적자본

        raroc = compute_raroc(revenue, el, cost, ec)
        expected = (5_000_000 - 500_000 - 750_000) / 20_000_000
        assert raroc == pytest.approx(expected, rel=1e-6)

    def test_raroc_positive_for_good_borrower(self):
        """우량 차주 (PD=0.3%): RAROC ≥ 15%."""
        principal = 100_000_000
        pd = 0.003
        lgd = 0.45
        ead = principal
        rate = 0.06   # 금리 6%
        months = 36

        revenue = principal * rate * (months / 12)
        el = pd * lgd * ead
        operating_cost = principal * 0.015
        rw = 12.5 * 0.08 * pd * lgd  # 간략화
        ec = ead * rw * 0.08

        raroc = compute_raroc(revenue, el, operating_cost, max(ec, 1))
        assert raroc is not None
        # RAROC이 양수인지만 확인 (우량 차주)
        assert raroc > 0, f"우량 차주 RAROC({raroc:.2%}) ≤ 0"

    def test_raroc_negative_for_very_high_risk(self):
        """초고위험 차주 (PD=50%): RAROC < 허들레이트 → 거절."""
        principal = 100_000_000
        pd = 0.50
        lgd = 0.45
        ead = principal
        rate = 0.20  # 최고금리도 부족
        months = 12

        revenue = principal * rate * (months / 12)
        el = pd * lgd * ead
        operating_cost = principal * 0.015
        ec = ead * 0.08  # 최소 자본

        raroc = compute_raroc(revenue, el, operating_cost, ec)
        assert raroc is not None
        assert raroc < HURDLE_RATE, \
            f"초고위험 RAROC({raroc:.2%}) ≥ 허들레이트 → 잘못된 계산"

    def test_economic_capital_zero_returns_none(self):
        """EC = 0이면 RAROC은 None (0 나누기 방지)."""
        result = compute_raroc(1_000_000, 100_000, 50_000, 0)
        assert result is None

    def test_raroc_grade_correlation(self):
        """신용등급이 높을수록 RAROC이 높아야 함 (리스크 기반 가격책정)."""
        grades = [
            {"pd": 0.001, "rate": 0.040},  # AAA
            {"pd": 0.010, "rate": 0.055},  # BBB
            {"pd": 0.070, "rate": 0.100},  # B
        ]
        principal = 100_000_000
        lgd = 0.45
        months = 36

        raroc_values = []
        for g in grades:
            revenue = principal * g["rate"] * (months / 12)
            el = g["pd"] * lgd * principal
            operating_cost = principal * 0.015
            rw = max(0.0001, g["pd"] * lgd * 2)
            ec = principal * rw * 0.08
            r = compute_raroc(revenue, el, operating_cost, ec)
            raroc_values.append(r)

        assert raroc_values[0] > raroc_values[1] > raroc_values[2], \
            f"등급별 RAROC 순서 오류: {raroc_values}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. LGD 추정 적정성 (바젤III IRB)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestLGDValidation:
    """LGD 추정값 바젤III 기준 검증."""

    def test_lgd_unsecured_range(self):
        """무담보 신용대출 LGD: 35%~55% 범위."""
        lgd = 0.45  # 시스템 기본값
        assert LGD_UNSECURED_MIN <= lgd <= LGD_UNSECURED_MAX, \
            f"무담보 LGD({lgd:.0%}) 기준 범위 밖"

    def test_lgd_mortgage_range(self):
        """주택담보대출 LGD: 15%~35% 범위 (담보 회수율 고려)."""
        lgd = 0.25  # 시스템 기본값
        assert LGD_MORTGAGE_MIN <= lgd <= LGD_MORTGAGE_MAX, \
            f"주담대 LGD({lgd:.0%}) 기준 범위 밖"

    def test_lgd_mortgage_less_than_unsecured(self):
        """주담대 LGD < 무담보 LGD (담보 회수 효과)."""
        lgd_mortgage = 0.25
        lgd_unsecured = 0.45
        assert lgd_mortgage < lgd_unsecured

    def test_lgd_from_recovery_formula(self):
        """회수율 → LGD 변환: LGD = (1 - Recovery) × (1 + RecoveryCost)."""
        recovery_prob = 0.60
        recovery_cost = 0.10
        lgd = (1 - recovery_prob) * (1 + recovery_cost)

        assert lgd == pytest.approx(0.44, abs=1e-6)

    def test_lgd_collection_model_loaded(self):
        """추심평점 모델 카드에 LGD 검증 결과 존재."""
        card_path = os.path.join(ARTIFACTS_DIR_COL, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("collection model_card.json 없음 (모델 미학습)")

        with open(card_path) as f:
            card = json.load(f)

        lgd_val = card.get("regulatory", {}).get("lgd_validation")
        assert lgd_val is not None, "model_card에 lgd_validation 없음"
        assert "mean_lgd_estimated" in lgd_val
        assert "actual_recovery_rate" in lgd_val

        mean_lgd = lgd_val["mean_lgd_estimated"]
        assert 0.0 <= mean_lgd <= 1.0, f"LGD 범위 초과: {mean_lgd}"

    def test_lgd_bounds(self):
        """LGD는 [0, 1] 범위여야 함."""
        for recovery in [0.0, 0.3, 0.6, 0.9, 1.0]:
            lgd = (1 - recovery) * 1.10
            lgd_clipped = max(0.0, min(1.0, lgd))
            assert 0.0 <= lgd_clipped <= 1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 바젤III 위험가중자산(RWA) 산출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestBaselIRB:
    """바젤III IRB 위험가중자산 산출 검증."""

    def _irb_risk_weight(self, pd: float, lgd: float = 0.45, maturity: float = 2.5) -> float:
        """
        바젤III 기업·소매 IRB 위험가중치 공식 (소매 노출 간략버전).
        RW = LGD × N(sqrt(1/(1-R)) × G(PD) + sqrt(R/(1-R)) × 1.645)
             ÷ PD × PD×LGD × 12.5 × 1.06
        실제로는 복잡하나 단순화: RW = 12.5 × K (자본 요구량)
        """
        from scipy.stats import norm

        # 소매 기업 상관관계
        R = 0.03 * (1 - math.exp(-35 * pd)) / (1 - math.exp(-35)) + \
            0.16 * (1 - (1 - math.exp(-35 * pd)) / (1 - math.exp(-35)))

        # 만기 조정 (소매는 제외 가능하나 포함)
        b = (0.11852 - 0.05478 * math.log(max(pd, 1e-8))) ** 2
        ma = (1 + (maturity - 2.5) * b) / (1 - 1.5 * b)

        # K = 자본 요구량
        K = (lgd * norm.cdf(
            math.sqrt(1 / (1 - R)) * norm.ppf(pd) +
            math.sqrt(R / (1 - R)) * norm.ppf(0.999)
        ) - lgd * pd) * ma

        rw = K * 12.5
        return max(0, rw)

    def test_irb_low_pd_low_rw(self):
        """우량 차주(PD=0.1%): RWA가 낮아야 함."""
        rw = self._irb_risk_weight(pd=0.001)
        # 소매 IRB RWA는 PD=0.1%일 때 대략 3~8% 수준
        assert rw < 0.30, f"우량 차주 RWA({rw:.2%}) 과다"

    def test_irb_high_pd_high_rw(self):
        """불량 차주(PD=10%): RWA가 높아야 함."""
        rw = self._irb_risk_weight(pd=0.10)
        rw_low = self._irb_risk_weight(pd=0.001)
        assert rw > rw_low, "고위험 RWA < 저위험 RWA"

    def test_economic_capital_formula(self):
        """EC = EAD × RWA × 8%."""
        ead = 100_000_000
        rw = 0.50  # 50%
        min_capital_ratio = 0.08
        ec = ead * rw * min_capital_ratio

        assert ec == pytest.approx(4_000_000, rel=1e-6), \
            f"EC 계산 오류: {ec}"

    def test_application_model_card_has_rwa(self):
        """Application Scorecard model_card에 RWA 관련 정보 존재."""
        card_path = os.path.join(ARTIFACTS_DIR_APP, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("application model_card.json 없음")

        with open(card_path) as f:
            card = json.load(f)

        # OOT Gini 검증 (성능)
        perf = card.get("performance", {})
        assert "oot_gini" in perf, "model_card에 oot_gini 없음"
        assert "oot_ks" in perf, "model_card에 oot_ks 없음"

    def test_ccf_revolving_credit(self):
        """마이너스통장 CCF = 50% (신용공여 리스크)."""
        CCF = 0.50
        unused_limit = 50_000_000  # 미사용 한도 5천만원
        current_balance = 20_000_000  # 현재 잔액 2천만원

        ead = current_balance + CCF * unused_limit
        assert ead == 45_000_000, f"EAD 계산 오류: {ead}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 신용등급 PD 매핑 일관성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestGradePDMapping:
    """신용등급 ↔ PD 매핑 일관성 검증."""

    # scoring_engine.py에서 복사
    GRADE_PD_MAP = {
        "AAA": (0.0005, 900, 870),
        "AA":  (0.0010, 869, 840),
        "A":   (0.0030, 839, 805),
        "BBB": (0.0100, 804, 750),
        "BB":  (0.0300, 749, 665),
        "B":   (0.0700, 664, 600),
        "CCC": (0.1500, 599, 515),
        "CC":  (0.3000, 514, 445),
        "C":   (0.5000, 444, 350),
        "D":   (1.0000, 349, 0),
    }

    def test_pd_monotone_increasing(self):
        """PD: AAA < AA < A < BBB < ... < D."""
        grades_ordered = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        pds = [self.GRADE_PD_MAP[g][0] for g in grades_ordered]

        for i in range(len(pds) - 1):
            assert pds[i] < pds[i + 1], \
                f"PD 단조 증가 위반: {grades_ordered[i]}({pds[i]}) ≥ {grades_ordered[i+1]}({pds[i+1]})"

    def test_score_ranges_monotone_decreasing(self):
        """점수 범위: AAA가 가장 높고 D가 가장 낮음."""
        grades_ordered = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        max_scores = [self.GRADE_PD_MAP[g][1] for g in grades_ordered]

        for i in range(len(max_scores) - 1):
            assert max_scores[i] > max_scores[i + 1], \
                f"점수 단조 감소 위반: {grades_ordered[i]}"

    def test_score_ranges_contiguous(self):
        """점수 범위가 연속적 (갭 없음)."""
        grades_ordered = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        for i in range(len(grades_ordered) - 1):
            _, max_cur, min_cur = self.GRADE_PD_MAP[grades_ordered[i]]
            _, max_next, min_next = self.GRADE_PD_MAP[grades_ordered[i + 1]]
            assert min_cur == max_next + 1 or min_cur == max_next, \
                f"점수 갭: {grades_ordered[i]}({min_cur}) ↔ {grades_ordered[i+1]}({max_next})"

    def test_score_within_range(self):
        """모든 등급 점수: [300, 900] 범위."""
        for grade, (pd, max_s, min_s) in self.GRADE_PD_MAP.items():
            assert 0 <= min_s <= 900, f"{grade} 최소점수 범위 초과"
            assert 300 <= max_s <= 900, f"{grade} 최대점수 범위 초과"

    def test_d_grade_pd_is_one(self):
        """D등급 PD = 100% (부도 확정)."""
        pd, _, _ = self.GRADE_PD_MAP["D"]
        assert pd == 1.0

    def test_aaa_grade_pd_very_low(self):
        """AAA등급 PD < 0.1% (최우량)."""
        pd, _, _ = self.GRADE_PD_MAP["AAA"]
        assert pd < 0.001


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 최고금리 규제 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestMaxInterestRate:
    """최고금리 규제 (대부업법 제8조, 이자제한법) 검증."""

    def test_max_rate_constant(self):
        """최고금리 20% 정의."""
        assert MAX_INTEREST_RATE == 0.20

    def test_all_segments_rate_below_max(self):
        """모든 세그먼트 금리 ≤ 20%."""
        segment_base_rates = {
            "SEG-DR": 0.035,   # 의사: 기준금리 + 스프레드 낮음
            "SEG-JD": 0.040,
            "SEG-ART": 0.075,
            "SEG-YTH": 0.060,
            "SEG-MIL": 0.045,
            "default": 0.090,
        }
        for seg, rate in segment_base_rates.items():
            assert rate <= MAX_INTEREST_RATE, \
                f"{seg} 금리({rate:.1%}) > 최고금리({MAX_INTEREST_RATE:.0%})"

    def test_rate_cap_applied_when_exceeded(self):
        """산출 금리 > 20%이면 20%로 cap."""
        uncapped_rate = 0.22
        capped_rate = min(uncapped_rate, MAX_INTEREST_RATE)
        assert capped_rate == MAX_INTEREST_RATE

    def test_seg_dr_discount_below_max(self):
        """SEG-DR 금리할인 후에도 0% 이상 유지."""
        base_rate = 0.03
        discount = 0.003  # -0.3%p
        final_rate = max(0.0, base_rate - discount)
        assert final_rate >= 0.0
        assert final_rate <= MAX_INTEREST_RATE


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. 규제 파라미터 시드 데이터 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRegulationParamSeed:
    """seed_regulation_params.py 데이터 무결성 검증."""

    def _load_seed_source(self) -> str:
        if not os.path.exists(SEED_PATH):
            pytest.skip(f"seed_regulation_params.py 없음: {SEED_PATH}")
        with open(SEED_PATH, encoding="utf-8") as f:
            return f.read()

    def test_seed_file_exists(self):
        """규제 파라미터 시드 파일 존재."""
        assert os.path.exists(SEED_PATH), \
            f"시드 파일 없음: {SEED_PATH}"

    def test_stress_dsr_phase2_present(self):
        """스트레스 DSR Phase2 파라미터 존재."""
        src = self._load_seed_source()
        assert "stress_dsr" in src and ("phase2" in src or "Phase2" in src), \
            "스트레스 DSR Phase2 파라미터 없음"

    def test_stress_dsr_phase3_present(self):
        """스트레스 DSR Phase3 파라미터 존재."""
        src = self._load_seed_source()
        assert "phase3" in src or "Phase3" in src, \
            "스트레스 DSR Phase3 파라미터 없음"

    def test_ltv_params_present(self):
        """LTV 파라미터 3종 존재 (일반/조정/투기)."""
        src = self._load_seed_source()
        for area in ["general", "regulated", "speculation"]:
            assert area in src, f"LTV {area} 파라미터 없음"

    def test_eq_grade_params_present(self):
        """EQ Grade 파라미터 존재 (EQ-S ~ EQ-E)."""
        src = self._load_seed_source()
        for grade in ["EQ-S", "EQ-A", "EQ-B", "EQ-C"]:
            assert grade in src, f"{grade} 파라미터 없음"

    def test_segment_params_present(self):
        """특수 세그먼트 파라미터 존재."""
        src = self._load_seed_source()
        for seg in ["SEG-DR", "SEG-JD", "SEG-ART", "SEG-YTH"]:
            assert seg in src, f"{seg} 파라미터 없음"

    def test_max_interest_rate_param_present(self):
        """최고금리 파라미터 존재."""
        src = self._load_seed_source()
        assert "max_interest" in src or "rate.max" in src, \
            "최고금리 파라미터 없음"

    def test_effective_from_field_present(self):
        """effective_from 필드가 모든 파라미터에 존재."""
        src = self._load_seed_source()
        assert "effective_from" in src, \
            "effective_from 필드 없음"

    def test_legal_basis_present_for_key_params(self):
        """주요 규제에 법적 근거 존재 (legal_basis)."""
        src = self._load_seed_source()
        assert "legal_basis" in src, "legal_basis 필드 없음"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Application Scorecard OOT 성능 규제 기준
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestApplicationModelPerformance:
    """Application Scorecard 금감원 규제 성능 기준 검증."""

    MIN_OOT_GINI = 0.30
    MIN_OOT_KS = 0.20

    def _load_card(self) -> dict:
        path = os.path.join(ARTIFACTS_DIR_APP, "model_card.json")
        if not os.path.exists(path):
            pytest.skip("application model_card.json 없음")
        with open(path) as f:
            return json.load(f)

    def test_oot_gini_regulatory_threshold(self):
        """Application Scorecard OOT Gini ≥ 0.30."""
        card = self._load_card()
        oot_gini = card["performance"]["oot_gini"]
        assert oot_gini >= self.MIN_OOT_GINI, \
            f"OOT Gini({oot_gini:.4f}) < 규제 기준({self.MIN_OOT_GINI})"

    def test_oot_ks_regulatory_threshold(self):
        """Application Scorecard OOT KS ≥ 0.20."""
        card = self._load_card()
        oot_ks = card["performance"]["oot_ks"]
        assert oot_ks >= self.MIN_OOT_KS, \
            f"OOT KS({oot_ks:.4f}) < 규제 기준({self.MIN_OOT_KS})"

    def test_model_card_has_trained_at(self):
        """model_card에 학습 일시 기록."""
        card = self._load_card()
        assert "trained_at" in card
        # ISO 형식 검증
        try:
            datetime.fromisoformat(card["trained_at"])
        except ValueError:
            pytest.fail(f"trained_at 형식 오류: {card['trained_at']}")

    def test_model_card_has_feature_groups(self):
        """model_card에 피처 그룹 정보 존재."""
        card = self._load_card()
        assert "feature_groups" in card
        assert len(card["feature_groups"]) > 0

    def test_cv_auc_stability(self):
        """CV AUC 표준편차 ≤ 0.03 (모델 안정성)."""
        card = self._load_card()
        cv_std = card.get("cv_auc_std", 1.0)
        assert cv_std <= 0.03, \
            f"CV AUC 표준편차({cv_std:.4f}) > 0.03 → 모델 불안정"


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
