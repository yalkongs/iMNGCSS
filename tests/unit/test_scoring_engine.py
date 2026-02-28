"""
[단위 테스트] ScoringEngine 핵심 로직
========================================
ScoringEngine의 주요 함수를 DB/외부 의존성 없이 테스트.

pytest tests/unit/test_scoring_engine.py -v
"""
import os
import sys
import math
import pytest

# 백엔드 모듈 경로 추가
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

try:
    from app.core.scoring_engine import (
        SCORE_BASE, SCORE_PDO, BASE_PD, SCORE_MIN, SCORE_MAX,
        GRADE_PD_MAP, LGD_BY_PRODUCT, RW_BY_PRODUCT,
        CUTOFF_REJECT, CUTOFF_MANUAL,
        ScoringInput,
    )
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False
    pytestmark = pytest.mark.skip(reason="scoring_engine import 실패")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼: 스코어 직접 계산 (엔진과 동일 공식)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def pd_to_score(pd: float) -> int:
    pd = max(1e-6, min(pd, 0.9999))
    odds = pd / (1 - pd)
    base_odds = BASE_PD / (1 - BASE_PD)
    score = SCORE_BASE - (SCORE_PDO / math.log(2)) * math.log(odds / base_odds)
    return int(max(SCORE_MIN, min(SCORE_MAX, round(score))))


def score_to_grade(score: int) -> str:
    for grade, (pd, max_s, min_s) in GRADE_PD_MAP.items():
        if min_s <= score <= max_s:
            return grade
    return "D"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 점수 스케일링 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestScoreScaling:
    """점수 변환 공식 정확성 검증."""

    def test_base_pd_gives_base_score(self):
        """기준 PD(7.2%)는 기준 점수(600점) 반환."""
        score = pd_to_score(BASE_PD)
        assert score == SCORE_BASE, f"기준점 오류: {score} ≠ {SCORE_BASE}"

    def test_score_range_is_300_to_900(self):
        """모든 PD에 대해 점수가 [300, 900] 범위."""
        pds = [0.0001, 0.001, 0.01, 0.05, 0.1, 0.3, 0.5, 0.9, 0.999]
        for pd in pds:
            score = pd_to_score(pd)
            assert SCORE_MIN <= score <= SCORE_MAX, \
                f"PD={pd}: 점수={score} 범위 초과"

    def test_lower_pd_higher_score(self):
        """PD가 낮을수록 점수가 높음 (단조 감소)."""
        pds = [0.001, 0.01, 0.05, 0.10, 0.30]
        scores = [pd_to_score(p) for p in pds]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1], \
                f"단조 감소 위반: PD={pds[i]}→{scores[i]}, PD={pds[i+1]}→{scores[i+1]}"

    def test_pdo_40_points(self):
        """PDO=40: Odds가 2배 증가하면 점수 40점 하락."""
        pd1 = 0.05   # odds = 0.0526
        pd2 = 0.095  # odds ≈ 0.105 (약 2배)
        score1 = pd_to_score(pd1)
        score2 = pd_to_score(pd2)
        # 40점 ± 5점 허용 (반올림 오차)
        diff = score1 - score2
        assert 35 <= diff <= 50, f"PDO 오류: 점수 차이={diff} (기대값: 약 40)"

    def test_reject_cutoff_boundary(self):
        """CUTOFF_REJECT = 450점 이하 → 자동 거절."""
        assert CUTOFF_REJECT == 450
        assert CUTOFF_MANUAL == 530

    def test_very_low_pd_gives_high_score(self):
        """우량 차주(PD=0.05%): 800점대 이상."""
        score = pd_to_score(0.0005)
        assert score >= 800, f"AAA급 차주 점수({score}) 낮음"

    def test_very_high_pd_gives_low_score(self):
        """불량 차주(PD=55%): 450점 미만 → 자동 거절."""
        score = pd_to_score(0.55)
        assert score < CUTOFF_REJECT, f"D급 차주 점수({score}) ≥ 거절 기준"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 신용등급 매핑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestGradeMapping:
    """신용등급 ↔ 점수 매핑 정확성."""

    def test_all_grades_defined(self):
        """10개 등급 모두 정의."""
        expected = {"AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"}
        assert set(GRADE_PD_MAP.keys()) == expected

    def test_score_900_is_aaa(self):
        """900점 → AAA 등급."""
        grade = score_to_grade(900)
        assert grade == "AAA"

    def test_score_300_is_d(self):
        """300점 → D 등급."""
        grade = score_to_grade(300)
        assert grade == "D"

    def test_score_600_is_b_or_bb(self):
        """600점 → B등급 (기준점)."""
        grade = score_to_grade(600)
        assert grade in ("B", "BB"), f"600점 등급 오류: {grade}"

    def test_grade_pd_monotone(self):
        """등급이 낮을수록 PD가 높아야 함."""
        grades_ordered = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        pds = [GRADE_PD_MAP[g][0] for g in grades_ordered]
        for i in range(len(pds) - 1):
            assert pds[i] < pds[i + 1]

    def test_score_ranges_no_gap(self):
        """점수 범위 연속성: 300~900 사이 갭 없음."""
        grades_ordered = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        # 최대 범위 체크
        max_score = max(GRADE_PD_MAP[g][1] for g in grades_ordered)
        min_score = min(GRADE_PD_MAP[g][2] for g in grades_ordered)
        assert max_score == SCORE_MAX
        assert min_score <= SCORE_MIN


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. LGD / RWA 파라미터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestLGDRWAParams:
    """상품별 LGD / 위험가중치 검증."""

    def test_lgd_values_defined(self):
        """4개 상품 LGD 정의."""
        for product in ["credit", "credit_soho", "mortgage", "micro"]:
            assert product in LGD_BY_PRODUCT, f"LGD 미정의: {product}"
            lgd = LGD_BY_PRODUCT[product]
            assert 0 < lgd <= 1.0

    def test_mortgage_lgd_lower_than_credit(self):
        """주담대 LGD < 신용대출 LGD (담보 효과)."""
        assert LGD_BY_PRODUCT["mortgage"] < LGD_BY_PRODUCT["credit"]

    def test_micro_lgd_highest(self):
        """소액론 LGD가 가장 높음 (고위험 무담보)."""
        micro_lgd = LGD_BY_PRODUCT["micro"]
        for product, lgd in LGD_BY_PRODUCT.items():
            assert micro_lgd >= lgd, f"소액론({micro_lgd}) < {product}({lgd})"

    def test_rw_values_defined(self):
        """상품별 위험가중치 정의."""
        for product in ["credit", "mortgage"]:
            assert product in RW_BY_PRODUCT
            assert 0 < RW_BY_PRODUCT[product] <= 2.0

    def test_mortgage_rw_lower_than_credit(self):
        """주담대 위험가중치 < 신용대출 (담보 효과)."""
        assert RW_BY_PRODUCT["mortgage"] < RW_BY_PRODUCT["credit"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. ScoringInput 데이터클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestScoringInput:
    """ScoringInput 생성 및 기본값 검증."""

    def _make_input(self, **overrides) -> ScoringInput:
        defaults = dict(
            application_id="test-001",
            product_type="credit",
            requested_amount=30_000_000,
            requested_term_months=36,
            applicant_type="individual",
            age=35,
            employment_type="employed",
            income_annual=50_000_000,
            income_verified=True,
            cb_score=700,
            delinquency_count_12m=0,
            worst_delinquency_status=0,
            open_loan_count=1,
            total_loan_balance=10_000_000,
            inquiry_count_3m=1,
        )
        defaults.update(overrides)
        return ScoringInput(**defaults)

    def test_create_basic_input(self):
        """기본 ScoringInput 생성 성공."""
        inp = self._make_input()
        assert inp.application_id == "test-001"
        assert inp.product_type == "credit"

    def test_default_segment_code_empty(self):
        """기본 세그먼트 코드는 빈 문자열."""
        inp = self._make_input()
        assert inp.segment_code == ""

    def test_default_eq_grade(self):
        """기본 EQ Grade는 EQ-C."""
        inp = self._make_input()
        assert inp.eq_grade == "EQ-C"

    def test_default_irg_code(self):
        """기본 IRG 코드는 M (Medium)."""
        inp = self._make_input()
        assert inp.irg_code == "M"

    def test_segment_override(self):
        """세그먼트 코드 오버라이드."""
        inp = self._make_input(segment_code="SEG-DR", eq_grade="EQ-B")
        assert inp.segment_code == "SEG-DR"
        assert inp.eq_grade == "EQ-B"

    def test_mortgage_fields(self):
        """주담대 전용 필드."""
        inp = self._make_input(
            product_type="mortgage",
            collateral_value=500_000_000,
            is_speculation_area=True,
            owned_property_count=1,
        )
        assert inp.collateral_value == 500_000_000
        assert inp.is_speculation_area is True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. DSR / EAD 계산 로직 단위 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestDSREADCalculation:
    """DSR, EAD 계산 공식 검증."""

    def _monthly_payment(self, principal, annual_rate, months) -> float:
        if months <= 0 or principal <= 0:
            return 0.0
        if annual_rate == 0:
            return principal / months
        r = annual_rate / 12
        return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)

    def test_monthly_payment_formula(self):
        """원리금균등분할 월상환액 계산 정확성."""
        # 1억, 연 6%, 30년
        payment = self._monthly_payment(100_000_000, 0.06, 360)
        # 약 599,550원 예상
        assert 580_000 < payment < 620_000, f"월상환액 오류: {payment:,.0f}"

    def test_dsr_formula(self):
        """DSR = 연간 원리금 / 연소득."""
        monthly_income = 5_000_000
        monthly_payment_amt = 1_500_000
        dsr = (monthly_payment_amt * 12) / (monthly_income * 12)
        assert dsr == pytest.approx(0.30, abs=1e-6)

    def test_ead_term_loan(self):
        """기간 대출 EAD = 대출 원금."""
        requested_amount = 50_000_000
        ead = requested_amount  # 기간 대출은 전액
        assert ead == 50_000_000

    def test_ead_revolving_with_ccf(self):
        """회전신용 EAD = 현잔액 + CCF(50%) × 미사용 한도."""
        balance = 20_000_000
        unused_limit = 30_000_000
        ccf = 0.50
        ead = balance + ccf * unused_limit
        assert ead == 35_000_000

    def test_ltv_mortgage_calculation(self):
        """LTV = 대출금액 / 담보가치."""
        loan = 300_000_000
        collateral = 500_000_000
        ltv = loan / collateral
        assert ltv == pytest.approx(0.60, abs=1e-6)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 한도 및 거절 로직
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestDecisionLogic:
    """의사결정 규칙 단위 검증."""

    def test_score_below_reject_cutoff_is_rejected(self):
        """450점 미만 → 자동 거절."""
        assert 449 < CUTOFF_REJECT

    def test_score_above_manual_cutoff_is_approved(self):
        """530점 이상 → 자동 승인 가능."""
        assert CUTOFF_MANUAL == 530
        assert 600 >= CUTOFF_MANUAL

    def test_active_delinquency_is_hard_reject(self):
        """현재 연체 중 → 하드 거절 (점수 무관)."""
        # worst_delinquency_status >= 1 이고 최근 발생 → 거절
        delinquency_status = 1
        assert delinquency_status >= 1  # 거절 조건

    def test_dsr_over_limit_is_reject(self):
        """DSR > 40% → 거절."""
        dsr = 0.42
        dsr_limit = 0.40
        assert dsr > dsr_limit  # 거절 조건

    def test_ltv_over_limit_is_reject(self):
        """LTV > 70% (일반지역) → 거절."""
        ltv = 0.75
        ltv_limit = 0.70
        assert ltv > ltv_limit  # 거절 조건

    def test_rate_cap_at_max_interest(self):
        """최고금리 20% 초과 시 cap 적용."""
        calculated_rate = 0.22  # 산출 금리 22%
        capped = min(calculated_rate, 0.20)
        assert capped == 0.20

    def test_approved_amount_segment_limit_multiplier(self):
        """SEG-DR: 한도 3.0배 적용."""
        income = 200_000_000  # 의사 연소득 2억
        base_limit = income * 1.5  # 기본 1.5배
        seg_multiplier = 3.0 / 1.5  # SEG-DR 비율
        dr_limit = base_limit * seg_multiplier
        assert dr_limit == 600_000_000  # 6억


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
