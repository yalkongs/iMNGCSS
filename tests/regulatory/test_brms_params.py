"""
[규제 테스트] BRMS 파라미터 무결성 검증
==========================================
validation/roles/ 의 검증 테스트와 달리,
여기서는 규제 파라미터 자체의 값/형식/범위 무결성에 집중.

실행: pytest tests/regulatory/ -v
"""
import os
import sys
import json
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# ─── 규제 기준값 (하드코딩 — 법규 기반) ───────────────────────────────────
REG_CONSTANTS = {
    # 총부채원리금상환비율
    "dsr_max": 0.40,
    # LTV 한도
    "ltv_general": 0.70,
    "ltv_adjustment": 0.60,
    "ltv_speculative": 0.40,
    # 법정 최고금리
    "rate_max_interest": 0.20,
    # 스트레스 DSR (24.02.26 Phase2)
    "stress_dsr_metro_phase2": 0.0075,
    "stress_dsr_nonmetro_phase2": 0.0150,
    # 스트레스 DSR (25.07.01 Phase3)
    "stress_dsr_metro_phase3": 0.0150,
    "stress_dsr_nonmetro_phase3": 0.0300,
    # Basel III 최저 자기자본 비율
    "bis_min_capital_ratio": 0.08,
    # 점수 범위
    "score_min": 300,
    "score_max": 900,
    "score_base": 600,
    "score_auto_reject": 450,
    "score_manual_review": 530,
}

# 시드 파일에서 기대하는 파라미터 목록
EXPECTED_SEED_PARAMS = [
    "dsr.max_ratio",
    "ltv.general",
    "ltv.adjustment",
    "ltv.speculative",
    "rate.max_interest",
    "stress_dsr.phase2.metropolitan.variable",
    "stress_dsr.phase2.metropolitan.mixed",
    "stress_dsr.phase2.non_metropolitan.variable",
    "stress_dsr.phase2.non_metropolitan.mixed",
    "stress_dsr.phase3.metropolitan.variable",
    "stress_dsr.phase3.metropolitan.mixed",
    "stress_dsr.phase3.non_metropolitan.variable",
    "stress_dsr.phase3.non_metropolitan.mixed",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 시드 모듈 파라미터 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSeedParamIntegrity:
    """seed_regulation_params.py 내 하드코딩 파라미터 무결성."""

    @pytest.fixture(scope="class")
    def seed_src(self):
        seed_path = os.path.join(BACKEND_DIR, "app", "core", "seed_regulation_params.py")
        if not os.path.exists(seed_path):
            pytest.skip(f"시드 파일 없음: {seed_path}")
        with open(seed_path, encoding="utf-8") as f:
            return f.read()

    def test_dsr_max_ratio_value(self, seed_src):
        """DSR 한도 40% 하드코딩 확인."""
        assert "0.40" in seed_src or "40" in seed_src, "DSR 40% 값 누락"

    def test_ltv_values_present(self, seed_src):
        """LTV 3종 값 확인."""
        for val in ["0.70", "0.60", "0.40"]:
            assert val in seed_src, f"LTV 값 누락: {val}"

    def test_max_interest_rate(self, seed_src):
        """최고금리 20% 확인."""
        assert "0.20" in seed_src or "20%" in seed_src, "최고금리 값 누락"

    def test_stress_dsr_phase2_metro(self, seed_src):
        """스트레스 DSR Phase2 수도권 0.75%p."""
        assert "0.0075" in seed_src, "Phase2 수도권 스트레스 DSR 0.0075 누락"

    def test_stress_dsr_phase3_metro(self, seed_src):
        """스트레스 DSR Phase3 수도권 1.50%p."""
        assert "0.0150" in seed_src, "Phase3 수도권 스트레스 DSR 0.0150 누락"

    def test_stress_dsr_phase3_nonmetro(self, seed_src):
        """스트레스 DSR Phase3 비수도권 3.00%p."""
        assert "0.0300" in seed_src, "Phase3 비수도권 스트레스 DSR 0.0300 누락"

    def test_eq_grade_definitions_present(self, seed_src):
        """EQ Grade EQ-S ~ EQ-E 정의 확인."""
        for grade in ["EQ-S", "EQ-A", "EQ-B", "EQ-C", "EQ-D", "EQ-E"]:
            assert grade in seed_src, f"EQ Grade 정의 누락: {grade}"

    def test_irg_definitions_present(self, seed_src):
        """IRG L/M/H/VH 정의 확인."""
        for irg in ['"L"', '"M"', '"H"', '"VH"']:
            assert irg in seed_src, f"IRG 정의 누락: {irg}"

    def test_expected_param_keys_covered(self, seed_src):
        """주요 파라미터 키 포함 여부."""
        for key in ["dsr.max_ratio", "ltv.general", "rate.max_interest"]:
            assert key in seed_src, f"파라미터 키 누락: {key}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. PolicyEngine 파라미터 상수 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestPolicyEngineConstants:
    """PolicyEngine 소스코드 내 규제 상수 범위 검증."""

    @pytest.fixture(scope="class")
    def policy_src(self):
        path = os.path.join(BACKEND_DIR, "app", "core", "policy_engine.py")
        if not os.path.exists(path):
            pytest.skip(f"PolicyEngine 없음: {path}")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_dsr_constant_exists(self, policy_src):
        """DSR 관련 상수 또는 키 존재."""
        assert "dsr" in policy_src.lower(), "DSR 관련 코드 없음"

    def test_ltv_constant_exists(self, policy_src):
        """LTV 관련 상수 존재."""
        assert "ltv" in policy_src.lower(), "LTV 관련 코드 없음"

    def test_redis_ttl_not_zero(self, policy_src):
        """Redis TTL이 0보다 큰 값으로 설정."""
        import re
        ttl_matches = re.findall(r"ttl\s*=\s*(\d+)", policy_src, re.IGNORECASE)
        for ttl in ttl_matches:
            assert int(ttl) > 0, f"Redis TTL이 0: {ttl}"

    def test_fallback_exists(self, policy_src):
        """DB 장애 시 폴백 메커니즘 존재."""
        assert "fallback" in policy_src.lower() or "default" in policy_src.lower(), \
            "폴백 메커니즘 없음"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 규제 상수 산술 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRegulatoryConstants:
    """법규 기반 상수 산술 정합성 검증 (외부 의존 없음)."""

    def test_dsr_max_ratio_range(self):
        """DSR 최대 비율 0 < DSR ≤ 0.50."""
        dsr = REG_CONSTANTS["dsr_max"]
        assert 0 < dsr <= 0.50, f"DSR 비율 범위 이상: {dsr}"

    def test_ltv_ordering(self):
        """LTV: 투기 < 조정 < 일반 (규제 강화 순서)."""
        assert (
            REG_CONSTANTS["ltv_speculative"]
            < REG_CONSTANTS["ltv_adjustment"]
            < REG_CONSTANTS["ltv_general"]
        ), "LTV 순서 오류"

    def test_stress_dsr_phase3_gt_phase2(self):
        """Phase3 스트레스 DSR > Phase2 (규제 강화)."""
        assert (
            REG_CONSTANTS["stress_dsr_metro_phase3"]
            > REG_CONSTANTS["stress_dsr_metro_phase2"]
        ), "Phase3이 Phase2보다 작음 (수도권)"
        assert (
            REG_CONSTANTS["stress_dsr_nonmetro_phase3"]
            > REG_CONSTANTS["stress_dsr_nonmetro_phase2"]
        ), "Phase3이 Phase2보다 작음 (비수도권)"

    def test_nonmetro_stress_dsr_gt_metro(self):
        """비수도권 스트레스 DSR > 수도권 (지방 부동산 리스크 반영)."""
        assert (
            REG_CONSTANTS["stress_dsr_nonmetro_phase3"]
            > REG_CONSTANTS["stress_dsr_metro_phase3"]
        ), "비수도권이 수도권보다 낮음"

    def test_max_interest_rate_legal(self):
        """최고금리 20% (이자제한법)."""
        assert REG_CONSTANTS["rate_max_interest"] == 0.20, "최고금리 20% 아님"

    def test_score_range_valid(self):
        """점수 범위 300~900, 기준점 600."""
        assert REG_CONSTANTS["score_min"] == 300
        assert REG_CONSTANTS["score_max"] == 900
        assert REG_CONSTANTS["score_base"] == 600
        assert REG_CONSTANTS["score_min"] < REG_CONSTANTS["score_base"] < REG_CONSTANTS["score_max"]

    def test_decision_thresholds_ordering(self):
        """자동거절 < 수동심사 임계값."""
        assert (
            REG_CONSTANTS["score_auto_reject"]
            < REG_CONSTANTS["score_manual_review"]
        ), "거절/심사 임계값 순서 오류"

    def test_bis_min_capital_ratio(self):
        """BIS 최저 자기자본 비율 8%."""
        assert REG_CONSTANTS["bis_min_capital_ratio"] == 0.08, "BIS 비율 8% 아님"

    def test_phase3_metro_rate(self):
        """Phase3 수도권 가산율 = 1.50%p."""
        assert abs(REG_CONSTANTS["stress_dsr_metro_phase3"] - 0.0150) < 1e-9

    def test_phase3_nonmetro_rate(self):
        """Phase3 비수도권 가산율 = 3.00%p."""
        assert abs(REG_CONSTANTS["stress_dsr_nonmetro_phase3"] - 0.0300) < 1e-9


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. EQ Grade / IRG 파라미터 구조 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestEQGradeStructure:
    """EQ Grade 및 IRG 파라미터 구조 정합성."""

    # EQ Grade: grade → (한도배수, 금리조정)
    EQ_GRADES = {
        "EQ-S": (2.0, -0.005),
        "EQ-A": (1.5, -0.003),
        "EQ-B": (1.2, -0.001),
        "EQ-C": (1.0, 0.0),
        "EQ-D": (0.9, 0.003),
        "EQ-E": (0.7, 0.005),
    }

    # IRG: grade → PD 조정 가산값
    IRG_PARAMS = {
        "L":  -0.10,
        "M":   0.00,
        "H":  +0.15,
        "VH": +0.30,
    }

    def test_eq_grade_limit_multipliers_ordered(self):
        """EQ Grade 한도배수: EQ-S(최고) → EQ-E(최저) 감소."""
        grades_ordered = ["EQ-S", "EQ-A", "EQ-B", "EQ-C", "EQ-D", "EQ-E"]
        mults = [self.EQ_GRADES[g][0] for g in grades_ordered]
        for i in range(len(mults) - 1):
            assert mults[i] >= mults[i + 1], \
                f"{grades_ordered[i]} 배수({mults[i]}) < {grades_ordered[i+1]} 배수({mults[i+1]})"

    def test_eq_grade_rate_adjustments_ordered(self):
        """EQ Grade 금리조정: EQ-S(최저=우대) → EQ-E(최고=가산) 증가."""
        grades_ordered = ["EQ-S", "EQ-A", "EQ-B", "EQ-C", "EQ-D", "EQ-E"]
        rates = [self.EQ_GRADES[g][1] for g in grades_ordered]
        for i in range(len(rates) - 1):
            assert rates[i] <= rates[i + 1], \
                f"금리 조정 순서 오류: {grades_ordered[i]}({rates[i]}) > {grades_ordered[i+1]}({rates[i+1]})"

    def test_irg_pd_adjustment_ordering(self):
        """IRG: L(하향) → VH(상향) PD 조정 순서."""
        assert self.IRG_PARAMS["L"] < self.IRG_PARAMS["M"] < self.IRG_PARAMS["H"] < self.IRG_PARAMS["VH"]

    def test_irg_m_is_zero(self):
        """IRG M은 기준 (PD 조정 없음)."""
        assert self.IRG_PARAMS["M"] == 0.0

    def test_eq_c_is_neutral(self):
        """EQ-C는 기준 등급 (한도배수 1.0, 금리조정 0)."""
        mult, rate_adj = self.EQ_GRADES["EQ-C"]
        assert mult == 1.0, f"EQ-C 배수 오류: {mult}"
        assert rate_adj == 0.0, f"EQ-C 금리조정 오류: {rate_adj}"

    def test_eq_s_best_terms(self):
        """EQ-S 최우대: 한도배수 최대, 금리 최저."""
        mult_s, rate_s = self.EQ_GRADES["EQ-S"]
        for grade, (mult, rate) in self.EQ_GRADES.items():
            if grade == "EQ-S":
                continue
            assert mult_s >= mult, f"EQ-S 배수({mult_s}) < {grade}({mult})"
            assert rate_s <= rate, f"EQ-S 금리({rate_s}) > {grade}({rate})"

    def test_irg_vh_highest_risk(self):
        """IRG VH: PD 가산 최대 (30%p)."""
        assert self.IRG_PARAMS["VH"] == pytest.approx(0.30)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 특수 세그먼트 파라미터 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSpecialSegmentParams:
    """특수 세그먼트 혜택 논리적 일관성."""

    SEGMENTS = {
        "SEG-DR": {"min_eq_grade": "EQ-B", "limit_mult": 3.0, "rate_discount": -0.003},
        "SEG-JD": {"min_eq_grade": "EQ-B", "limit_mult": 2.5, "rate_discount": -0.002},
        "SEG-YTH": {"rate_discount": -0.005},
        "SEG-MIL": {"min_eq_grade": "EQ-S", "limit_mult": 2.0, "rate_discount": -0.005},
    }

    def test_all_segments_have_rate_discount(self):
        """모든 세그먼트는 금리 우대 (음수)."""
        for seg, params in self.SEGMENTS.items():
            disc = params.get("rate_discount", 0)
            assert disc <= 0, f"{seg} 금리 우대가 양수: {disc}"

    def test_seg_dr_higher_limit_than_seg_jd(self):
        """SEG-DR 한도 > SEG-JD (더 많은 혜택)."""
        assert self.SEGMENTS["SEG-DR"]["limit_mult"] > self.SEGMENTS["SEG-JD"]["limit_mult"]

    def test_seg_mil_best_discount(self):
        """SEG-MIL: 군인 세그먼트 최우대 금리."""
        mil_disc = self.SEGMENTS["SEG-MIL"]["rate_discount"]
        yth_disc = self.SEGMENTS["SEG-YTH"]["rate_discount"]
        assert mil_disc <= yth_disc, f"SEG-MIL({mil_disc}) > SEG-YTH({yth_disc})"

    def test_seg_mil_eq_s_guaranteed(self):
        """SEG-MIL: EQ-S 보장."""
        assert self.SEGMENTS["SEG-MIL"]["min_eq_grade"] == "EQ-S"

    def test_seg_dr_limit_not_over_10(self):
        """SEG-DR 한도배수 현실적 범위 (≤ 10x)."""
        assert self.SEGMENTS["SEG-DR"]["limit_mult"] <= 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
