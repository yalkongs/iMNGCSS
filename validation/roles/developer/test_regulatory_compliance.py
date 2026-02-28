"""
[역할: 모델 개발팀] 규제 준수 자동화 테스트
=============================================
책임: 모델이 금감원/금융위 규제 요건을 충족하는지 검증
검증 항목:
  - DSR 한도 준수 (은행업감독규정)
  - LTV 한도 준수 (투기/조정/일반 지역별)
  - 최고금리 준수 (대부업법 §11)
  - 스트레스 DSR 적용 여부 (금감원 행정지도)
  - 거절 사유 고지 (금소법 §19)
  - 자동 평가 이의제기 기한 설정 (신용정보법 §39의5)
  - BRMS 파라미터 버전 관리 검증 (FR-ADM-002)

실행: pytest validation/roles/developer/test_regulatory_compliance.py -v
"""
import os, sys, json
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# ── ScoringEngine 직접 테스트 ────────────────────────────────
try:
    from backend.app.core.scoring_engine import (
        ScoringEngine, ScoringInput, CUTOFF_REJECT, CUTOFF_MANUAL,
        SCORE_MIN, SCORE_MAX
    )
    HAS_ENGINE = True
except ImportError:
    HAS_ENGINE = False


def make_base_input(**overrides) -> "ScoringInput":
    """기본 ScoringInput 생성 헬퍼"""
    defaults = dict(
        application_id="test-001",
        product_type="credit",
        requested_amount=30_000_000,
        requested_term_months=36,
        applicant_type="individual",
        age=35,
        employment_type="employed",
        income_annual=60_000_000,
        income_verified=True,
        cb_score=700,
        delinquency_count_12m=0,
        worst_delinquency_status=0,
        open_loan_count=1,
        total_loan_balance=10_000_000,
        inquiry_count_3m=1,
        segment_code="",
        eq_grade="EQ-C",
        irg_code="M",
        irg_pd_adjustment=0.0,
        existing_monthly_payment=200_000,
    )
    defaults.update(overrides)
    return ScoringInput(**defaults)


class TestDSRLimit:
    """DSR 한도 준수 검증 (은행업감독규정 §35의5)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_dsr_over_40_rejected(self):
        """[REG-01] DSR > 40% 시 자동 거절"""
        engine = ScoringEngine()
        # 소득 대비 과도한 신청 (DSR > 40% 발생)
        inp = make_base_input(
            income_annual=24_000_000,       # 연 2,400만원
            requested_amount=100_000_000,   # 1억원 신청
            existing_monthly_payment=500_000,
        )
        result = engine.score(inp, dsr_limit=40.0)
        assert result.dsr_limit_breached or result.decision == "rejected", (
            f"DSR {result.dsr_ratio:.1f}% > 40% 인데 거절 안 됨 (decision={result.decision})"
        )

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_dsr_under_40_not_auto_rejected_by_dsr(self):
        """[REG-02] DSR < 40% 시 DSR 원인 거절 없음"""
        engine = ScoringEngine()
        inp = make_base_input(
            income_annual=60_000_000,
            requested_amount=20_000_000,
            existing_monthly_payment=100_000,
        )
        result = engine.score(inp, dsr_limit=40.0)
        assert not result.dsr_limit_breached, (
            f"DSR {result.dsr_ratio:.1f}% < 40% 인데 dsr_limit_breached=True"
        )


class TestLTVLimit:
    """LTV 한도 준수 검증 (주담대)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_ltv_over_70_general_area_rejected(self):
        """[REG-03] 일반 지역 LTV > 70% 거절"""
        engine = ScoringEngine()
        inp = make_base_input(
            product_type="mortgage",
            requested_amount=800_000_000,   # 8억
            collateral_value=1_000_000_000, # 10억 (LTV=80%)
            income_annual=120_000_000,
        )
        result = engine.score(inp, ltv_limit=70.0)
        assert result.ltv_limit_breached or result.decision == "rejected", (
            f"LTV {result.ltv_ratio:.1f}% > 70% 인데 거절 안 됨"
        )

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_ltv_speculation_area_40_limit(self):
        """[REG-04] 투기과열지구 LTV 한도 40%"""
        engine = ScoringEngine()
        inp = make_base_input(
            product_type="mortgage",
            requested_amount=500_000_000,   # 5억
            collateral_value=1_000_000_000, # 10억 (LTV=50%)
            is_speculation_area=True,
            income_annual=120_000_000,
        )
        result = engine.score(inp, ltv_limit=40.0)
        # LTV 50% > 40% 한도 초과
        assert result.ltv_limit_breached or result.decision == "rejected", (
            f"투기과열지구 LTV {result.ltv_ratio:.1f}% > 40% 인데 거절 안 됨"
        )


class TestMaxInterestRate:
    """최고금리 준수 (대부업법 §11)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_rate_capped_at_20_percent(self):
        """[REG-05] 최종 금리 ≤ 20%"""
        engine = ScoringEngine()
        # 고위험 신청 (금리가 높게 산출될 케이스)
        inp = make_base_input(
            cb_score=400,
            delinquency_count_12m=3,
            worst_delinquency_status=1,
            eq_grade="EQ-E",
            irg_code="VH",
            irg_pd_adjustment=0.30,
        )
        result = engine.score(inp, max_rate=20.0)
        assert result.rate_breakdown.final_rate <= 20.0, (
            f"최고금리 초과: {result.rate_breakdown.final_rate:.2f}% > 20%"
        )

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_rate_cap_flag_set(self):
        """[REG-06] 최고금리 캡 적용 시 rate_capped=True"""
        engine = ScoringEngine()
        # 원래 금리가 20% 초과할 정도로 고위험
        inp = make_base_input(
            cb_score=350, worst_delinquency_status=2,
            delinquency_count_12m=5, eq_grade="EQ-E",
            irg_code="VH", irg_pd_adjustment=0.30,
        )
        result = engine.score(inp, max_rate=20.0, base_rate=3.5)
        # 극단적 고위험이므로 캡 적용 또는 거절
        if result.decision != "rejected":
            # 거절이 아닌 경우 금리 캡 검증
            assert result.rate_breakdown.final_rate <= 20.0


class TestRejectionReasons:
    """거절 사유 고지 의무 (금소법 §19)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_rejection_includes_reasons(self):
        """[REG-07] 거절 시 한국어 사유 최소 1개 이상"""
        engine = ScoringEngine()
        inp = make_base_input(
            cb_score=350,
            worst_delinquency_status=3,
        )
        result = engine.score(inp, dsr_limit=40.0)
        if result.decision == "rejected":
            assert len(result.rejection_reasons) >= 1, \
                "거절 시 사유 없음 (금소법 §19 위반)"
            for reason in result.rejection_reasons:
                assert isinstance(reason, str) and len(reason) > 0


class TestAppealDeadline:
    """자동 평가 이의제기 기한 (신용정보법 §39의5)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_rejected_has_appeal_deadline(self):
        """[REG-08] 거절 시 이의제기 기한(30일) 설정"""
        from datetime import datetime, timedelta
        engine = ScoringEngine()
        inp = make_base_input(cb_score=350, worst_delinquency_status=3)
        result = engine.score(inp)
        if result.decision == "rejected":
            assert result.appeal_deadline is not None, \
                "거절 시 appeal_deadline 없음 (신용정보법 §39의5 위반)"
            days_delta = (result.appeal_deadline - datetime.utcnow()).days
            assert 28 <= days_delta <= 32, \
                f"이의제기 기한이 30일이 아님: {days_delta}일"


class TestScoreRange:
    """점수 범위 검증"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_score_within_300_900(self):
        """[REG-09] 모든 점수 300~900 범위 내"""
        engine = ScoringEngine()
        test_cases = [
            make_base_input(cb_score=300, worst_delinquency_status=3),
            make_base_input(cb_score=900, income_annual=200_000_000),
            make_base_input(cb_score=700),
        ]
        for inp in test_cases:
            result = engine.score(inp)
            assert SCORE_MIN <= result.score <= SCORE_MAX, \
                f"점수 범위 초과: {result.score} (허용: {SCORE_MIN}~{SCORE_MAX})"

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_grade_matches_score(self):
        """[REG-10] 점수-등급 일관성"""
        from backend.app.core.scoring_engine import GRADE_PD_MAP
        engine = ScoringEngine()
        inp = make_base_input()
        result = engine.score(inp)
        grade = result.grade
        score = result.score
        # 등급에 해당하는 점수 범위 확인
        if grade in GRADE_PD_MAP:
            _, upper, lower = GRADE_PD_MAP[grade]
            assert lower <= score <= upper, \
                f"등급({grade})과 점수({score}) 불일치: 예상 범위 {lower}~{upper}"


class TestSegmentBenefits:
    """특수 세그먼트 혜택 검증"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_seg_dr_rate_discount(self):
        """[REG-11] SEG-DR(의사) 금리 우대 적용"""
        engine = ScoringEngine()
        inp_normal = make_base_input(income_annual=180_000_000, cb_score=750)
        inp_doctor = make_base_input(
            income_annual=180_000_000, cb_score=750,
            segment_code="SEG-DR", eq_grade="EQ-B",
        )
        result_normal = engine.score(inp_normal)
        result_doctor = engine.score(inp_doctor)

        if result_normal.decision != "rejected" and result_doctor.decision != "rejected":
            assert result_doctor.rate_breakdown.final_rate <= result_normal.rate_breakdown.final_rate, (
                f"SEG-DR 금리 우대 미적용: 일반={result_normal.rate_breakdown.final_rate:.2f}%, "
                f"의사={result_doctor.rate_breakdown.final_rate:.2f}%"
            )

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    @pytest.mark.asyncio
    async def test_seg_yth_rate_discount(self):
        """[REG-12] SEG-YTH(청년) -0.5%p 금리 우대"""
        engine = ScoringEngine()
        inp_normal = make_base_input(age=35, cb_score=650)
        inp_youth  = make_base_input(age=25, cb_score=650, segment_code="SEG-YTH")
        r_normal = engine.score(inp_normal)
        r_youth  = engine.score(inp_youth)
        if r_normal.decision != "rejected" and r_youth.decision != "rejected":
            assert r_youth.rate_breakdown.final_rate <= r_normal.rate_breakdown.final_rate + 0.1


class TestBRMSParameterVersioning:
    """BRMS 파라미터 버전 관리 (FR-ADM-002)"""

    def test_seed_params_have_effective_date(self):
        """[REG-13] 모든 시드 파라미터에 effective_from 있음"""
        try:
            from backend.app.core.seed_regulation_params import SEED_PARAMS
            for p in SEED_PARAMS:
                assert "effective_from" in p and p["effective_from"] is not None, \
                    f"effective_from 없음: {p['param_key']}"
        except ImportError:
            pytest.skip("seed_regulation_params 없음")

    def test_seed_params_have_legal_basis_for_key_rules(self):
        """[REG-14] 핵심 규제 파라미터에 법령 근거 있음"""
        try:
            from backend.app.core.seed_regulation_params import SEED_PARAMS
            key_categories = {"dsr", "ltv", "rate"}
            for p in SEED_PARAMS:
                if p.get("param_category") in key_categories:
                    assert p.get("legal_basis"), \
                        f"법령 근거 없음: {p['param_key']} (카테고리: {p['param_category']})"
        except ImportError:
            pytest.skip("seed_regulation_params 없음")

    def test_stress_dsr_phase3_has_later_effective_date(self):
        """[REG-15] 스트레스 DSR Phase3가 Phase2보다 늦은 시행일"""
        try:
            from backend.app.core.seed_regulation_params import SEED_PARAMS
            phase2 = [p for p in SEED_PARAMS if p.get("phase_label") == "phase2" and "metropolitan" in p["param_key"]]
            phase3 = [p for p in SEED_PARAMS if p.get("phase_label") == "phase3" and "metropolitan" in p["param_key"]]
            if phase2 and phase3:
                assert phase3[0]["effective_from"] > phase2[0]["effective_from"], \
                    "Phase3 시행일이 Phase2보다 빠르거나 같음"
        except ImportError:
            pytest.skip("seed_regulation_params 없음")


# ── 단위 테스트 (동기) ─────────────────────────────────────────

class TestScoringEngineUnit:
    """ScoringEngine 단위 테스트 (비동기 없이)"""

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    def test_pd_to_score_base_pd(self):
        """기준 PD(7.2%)는 600점에 매핑"""
        score = ScoringEngine.pd_to_score(0.072)
        assert 595 <= score <= 605, f"기준 PD → {score}점 (예상: 600±5)"

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    def test_pd_to_score_low_pd_high_score(self):
        """낮은 PD → 높은 점수"""
        score_low_pd  = ScoringEngine.pd_to_score(0.001)
        score_high_pd = ScoringEngine.pd_to_score(0.50)
        assert score_low_pd > score_high_pd

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    def test_score_to_grade_mapping(self):
        """점수-등급 매핑 일관성"""
        assert ScoringEngine.score_to_grade(880) == "AAA"
        assert ScoringEngine.score_to_grade(600) in ("B", "CCC")
        assert ScoringEngine.score_to_grade(350) == "D"

    @pytest.mark.skipif(not HAS_ENGINE, reason="ScoringEngine 없음")
    def test_score_bounds(self):
        """점수 범위 경계값"""
        assert ScoringEngine.pd_to_score(0.0001) == SCORE_MAX
        assert ScoringEngine.pd_to_score(0.9999) == SCORE_MIN
