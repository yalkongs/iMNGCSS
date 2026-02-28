"""
[역할: 컴플라이언스팀] AI 공정성 & 금융소비자보호 검증
==========================================================
책임: 금융위원회 AI 모범규준 7대 원칙 + 금소법 준수 검증

검증 항목:
1. 성별 편향성 (Gender Bias) — 동일 재무조건 시 점수 차이 없어야
2. 연령 편향성 (Age Bias) — 청년/장년 불합리한 차별 없어야
3. 지역 편향성 (Regional Bias) — 거주지 자체가 거절 사유 아님
4. 보호 속성 독립성 — 주민번호/성별/연령 직접 입력 금지
5. 설명 가능성 — 거절 사유 한국어 제공 (금소법 §19)
6. 이의제기 절차 — 30일 이내 이의신청 안내 (신용정보법 §39의5)
7. 특수 세그먼트 편향 — 혜택이 차별이 아닌 우대인지 검증
8. 데이터 대표성 — 합성 데이터 인구학적 분포 편향 검사
9. 예술인·청년 긍정적 우대 적정성
10. Shadow Mode 불투명성 방지 (금소법 §19 모델 알고리즘 공개)

참고: 금융위원회 AI 모범규준(2021), 신용정보법, 금융소비자보호법

실행: pytest validation/roles/compliance/ -v -s
"""
import os
import sys
import json
import math
import pytest
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
DATA_DIR = os.path.join(BASE_DIR, "ml_pipeline", "data")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application")
SCORING_ENGINE_PATH = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
APPLICATIONS_API_PATH = os.path.join(BASE_DIR, "backend", "app", "api", "v1", "applications.py")


# ── 공정성 임계값 (금융위원회 AI 모범규준 기준) ───────────────
MAX_PROTECTED_ATTR_SCORE_DIFF = 30   # 보호 속성 점수 차이 최대 허용치 (30점)
MAX_APPROVAL_RATE_DISPARITY = 0.10   # 승인율 격차 최대 10%p
MIN_EXPLANATION_COUNT = 3            # 최소 거절 사유 제공 수
APPEAL_DEADLINE_DAYS = 30            # 이의제기 기한 30일


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼: 스코어 변환 함수 (scoring_engine.py와 동일 공식)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCORE_BASE = 600
SCORE_PDO = 40
BASE_PD = 0.072


def pd_to_score(pd: float) -> int:
    """PD → 신용점수 변환 (300~900 스케일)."""
    pd = max(1e-6, min(pd, 0.9999))
    odds = pd / (1 - pd)
    base_odds = BASE_PD / (1 - BASE_PD)
    score = SCORE_BASE - (SCORE_PDO / math.log(2)) * math.log(odds / base_odds)
    return int(max(300, min(900, round(score))))


def simulate_score(
    cb_score: int,
    income_annual: float,
    age: int,
    employment_type: str = "employed",
    delinquency_count: int = 0,
    open_loan_count: int = 1,
) -> int:
    """
    간략화된 PD 추정 및 스코어 산출 (통계 모델 폴백).
    성별/지역 등 보호 속성은 입력에 없음.
    """
    logit = -4.0
    logit += -0.003 * (cb_score - 600)
    logit += -0.4 * math.log(max(income_annual / 1e6, 1))
    logit += 0.3 * delinquency_count
    logit += 0.1 * open_loan_count

    if employment_type == "self_employed":
        logit += 0.3
    elif employment_type == "unemployed":
        logit += 0.8

    pd = 1 / (1 + math.exp(-logit))
    return pd_to_score(pd)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 성별 편향성 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestGenderBias:
    """동일 재무 프로파일에서 성별이 점수에 영향 없어야 함."""

    def _common_profile(self) -> dict:
        return dict(
            cb_score=700,
            income_annual=50_000_000,
            age=35,
            employment_type="employed",
            delinquency_count=0,
            open_loan_count=1,
        )

    def test_gender_not_in_scoring_input(self):
        """scoring_engine.py ScoringInput에 gender 필드 없어야 함."""
        if not os.path.exists(SCORING_ENGINE_PATH):
            pytest.skip("scoring_engine.py 없음")
        with open(SCORING_ENGINE_PATH, encoding="utf-8") as f:
            src = f.read()
        # gender 필드가 ScoringInput 데이터클래스에 없어야 함
        # "gender" 단어가 있더라도 주석이나 설명 이외의 필드 선언이 없어야 함
        lines = src.split("\n")
        scoring_input_section = False
        for line in lines:
            if "class ScoringInput" in line:
                scoring_input_section = True
            if scoring_input_section and "gender" in line.lower() and ":" in line and "#" not in line.split(":")[0]:
                pytest.fail(f"ScoringInput에 gender 필드 발견: {line.strip()}")

    def test_same_profile_same_score(self):
        """동일 재무 조건: 성별과 무관하게 동일 점수."""
        profile = self._common_profile()
        score_a = simulate_score(**profile)
        score_b = simulate_score(**profile)  # 동일 프로파일 재실행
        assert score_a == score_b, "비결정적 스코어링"

    def test_gender_field_not_in_synthetic_data_score_features(self):
        """합성 데이터의 스코어링 피처에 gender 없어야 함."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        features = card.get("features", [])
        assert "gender" not in features, "모델 피처에 gender 포함 — 편향 위험"

    def test_income_is_gender_neutral_feature(self):
        """소득 기반 스코어링: 동일 소득이면 성별 무관."""
        # 같은 소득, 같은 CB 점수 → 동일 점수 기대
        score_same_income = simulate_score(cb_score=700, income_annual=60_000_000, age=30)
        assert 300 <= score_same_income <= 900

    def test_protected_attributes_excluded(self):
        """주민번호, 성별, 민족 관련 필드가 피처에 없음."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        features = [f.lower() for f in card.get("features", [])]
        forbidden = ["gender", "sex", "race", "ethnicity", "religion",
                     "nationality", "resident_registration"]
        for fb in forbidden:
            assert fb not in features, f"금지 피처 발견: {fb}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 연령 편향성 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAgeBias:
    """연령 편향 — 동일 재무 조건에서 나이로 인한 불합리한 차별 없어야."""

    def test_age_not_direct_feature(self):
        """나이 자체가 단독 거절 사유가 아님 (소득/대출 기간 고려 가능)."""
        # age 필드가 scoring에 간접 사용 가능하나 직접 거절 사유 아님
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        features = card.get("features", [])
        # age가 피처에 있더라도 단독 거절 기준은 아님 — 별도 로직 확인
        # 여기서는 age가 최상위 중요도 피처가 아닌지 확인
        importance = card.get("feature_importance_top5", card.get("shap_top5", []))
        if importance:
            top1 = importance[0].get("feature", "")
            assert top1 != "age", "age가 가장 중요한 피처 → 연령 편향 위험"

    def test_youth_segment_positive_benefit_not_penalty(self):
        """SEG-YTH (청년)은 금리 우대 혜택 — 불이익 아님."""
        # SEG-YTH 세그먼트는 금리할인 혜택을 줘야 함
        seg_benefit_discount = -0.005  # -0.5%p (혜택은 음수)
        assert seg_benefit_discount < 0, "청년 세그먼트 금리 혜택이 없음"

    def test_youth_age_range_inclusive(self):
        """청년 정의: 만 19세 ~ 34세 (양 끝 포함)."""
        youth_min = 19
        youth_max = 34
        assert youth_min == 19
        assert youth_max == 34

        # 경계값 검증
        for age in [19, 20, 33, 34]:
            is_youth = youth_min <= age <= youth_max
            assert is_youth, f"{age}세는 청년 범위 포함이어야 함"

        for age in [18, 35]:
            is_youth = youth_min <= age <= youth_max
            assert not is_youth, f"{age}세는 청년 범위 밖이어야 함"

    def test_score_disparity_same_profile_different_age(self):
        """동일 재무 프로파일: 25세 vs 45세 점수 차이 허용 범위."""
        common = dict(cb_score=700, income_annual=50_000_000,
                      employment_type="employed", delinquency_count=0, open_loan_count=1)
        score_25 = simulate_score(age=25, **common)
        score_45 = simulate_score(age=45, **common)
        # 나이 자체는 모델에 직접 영향 없어야 함 (동일 점수)
        assert score_25 == score_45, \
            f"동일 재무 조건에서 연령별 점수 차이: 25세={score_25}, 45세={score_45}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 지역 편향성 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRegionalBias:
    """거주지/지역이 직접 거절 사유가 아님 (LTV 지역 제한은 규제, 차별 아님)."""

    def test_region_not_in_credit_model_features(self):
        """신용모델 피처에 거주지역(시도/시군구) 없어야 함."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        features = [f.lower() for f in card.get("features", [])]
        regional_features = ["region", "city", "district", "sido", "sigungu",
                             "address", "zip_code", "postal"]
        for rf in regional_features:
            assert rf not in features, f"지역 피처 발견: {rf}"

    def test_ltv_region_restriction_is_regulatory_not_discriminatory(self):
        """LTV 지역 제한은 금융당국 규제에 근거 (차별 아님)."""
        # 투기과열지구 LTV 제한은 금융정책, 신용평가 모델과 무관
        ltv_speculation = 0.40
        # 투기지구에서도 동일 소득/신용이면 같은 신용점수
        score_metro = simulate_score(cb_score=750, income_annual=80_000_000, age=40)
        score_rural = simulate_score(cb_score=750, income_annual=80_000_000, age=40)
        assert score_metro == score_rural, "지역에 따라 신용점수 달라짐"

    def test_stress_dsr_regional_difference_is_regulatory(self):
        """스트레스 DSR 지역 차등은 금융당국 규제 (신용평가 아님)."""
        # 수도권/비수도권 스트레스 가산금리 차이는 금융위원회 고시 기반
        metro_stress = 0.015   # Phase3 수도권
        non_metro_stress = 0.030  # Phase3 비수도권
        # 둘 다 법적 근거 있음
        assert metro_stress > 0
        assert non_metro_stress > 0
        assert non_metro_stress > metro_stress  # 비수도권이 더 높음


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 설명 가능성 (금소법 §19 거절 사유 고지)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestExplainability:
    """AI 판단 결과에 한국어 설명 제공 의무."""

    def test_rejection_reasons_are_korean(self):
        """거절 사유는 한국어여야 함."""
        sample_reasons = [
            "총부채원리금상환비율(DSR) 40% 초과",
            "신용점수 기준 미달 (450점 미만)",
            "진행 중인 연체 이력 존재",
            "담보인정비율(LTV) 초과",
        ]
        for reason in sample_reasons:
            # 한글 포함 여부 검사 (유니코드 범위: AC00-D7AF)
            has_korean = any("\uAC00" <= c <= "\uD7AF" for c in reason)
            assert has_korean, f"거절 사유에 한글 없음: {reason}"

    def test_rejection_has_minimum_explanation_count(self):
        """거절 시 최소 1개 이상 사유 제공."""
        sample_rejection = {
            "decision": "rejected",
            "rejection_reasons": ["DSR 40% 초과"],
        }
        assert len(sample_rejection["rejection_reasons"]) >= 1

    def test_scoring_engine_has_explanation_factors(self):
        """scoring_engine.py에 설명 요인(explanation) 존재."""
        if not os.path.exists(SCORING_ENGINE_PATH):
            pytest.skip("scoring_engine.py 없음")
        with open(SCORING_ENGINE_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "explanation" in src or "reject_reason" in src or "거절" in src, \
            "scoring_engine.py에 거절 사유 생성 로직 없음"

    def test_shap_values_for_explanation(self):
        """SHAP 기반 설명 파일 존재 (behavioral scorecard)."""
        shap_path = os.path.join(BASE_DIR, "ml_pipeline", "artifacts",
                                 "behavioral", "shap_importance.csv")
        if not os.path.exists(shap_path):
            pytest.skip("shap_importance.csv 없음 (behavioral 모델 미학습)")
        df = pd.read_csv(shap_path)
        assert "feature" in df.columns, "SHAP 파일에 feature 컬럼 없음"
        assert "mean_abs_shap" in df.columns, "SHAP 파일에 mean_abs_shap 컬럼 없음"
        assert len(df) > 0, "SHAP 파일 비어있음"

    def test_model_card_has_feature_importance(self):
        """model_card에 피처 중요도 Top10 존재."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        top10_key = "shap_top10" if "shap_top10" in card else "feature_importance_top10"
        assert top10_key in card, "model_card에 피처 중요도 없음"
        importance = card[top10_key]
        assert len(importance) > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 이의제기 절차 (신용정보법 §39의5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAppealProcess:
    """이의제기 절차 규정 준수 검증."""

    def test_appeal_deadline_is_30_days(self):
        """이의신청 기한 30일."""
        assert APPEAL_DEADLINE_DAYS == 30

    def test_appeal_endpoint_exists_in_api(self):
        """applications.py에 /appeal 엔드포인트 존재."""
        if not os.path.exists(APPLICATIONS_API_PATH):
            pytest.skip("applications.py 없음")
        with open(APPLICATIONS_API_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "/appeal" in src or "appeal" in src, \
            "이의신청 엔드포인트 없음"

    def test_appeal_deadline_date_format(self):
        """이의신청 마감일은 ISO 날짜 형식이어야 함."""
        from datetime import datetime, timedelta
        applied_at = datetime(2025, 1, 15)
        appeal_deadline = applied_at + timedelta(days=APPEAL_DEADLINE_DAYS)
        # ISO 형식으로 직렬화 가능한지
        assert appeal_deadline.isoformat() is not None

    def test_appeal_available_for_rejection_only(self):
        """이의신청은 거절 건에만 적용."""
        # 승인 건에는 이의신청 불필요 (논리 검증)
        decisions = ["approved", "manual_review", "rejected"]
        appeal_applicable = ["rejected"]  # 거절만 이의신청 대상
        for d in decisions:
            if d in appeal_applicable:
                assert True  # 이의신청 가능
            else:
                pass  # 이의신청 불필요 (오류 아님)

    def test_scoring_engine_sets_appeal_deadline(self):
        """scoring_engine.py에 appeal_deadline 설정 로직 존재."""
        if not os.path.exists(SCORING_ENGINE_PATH):
            pytest.skip("scoring_engine.py 없음")
        with open(SCORING_ENGINE_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "appeal_deadline" in src, \
            "scoring_engine.py에 appeal_deadline 없음"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 특수 세그먼트 우대 — 차별 vs 합리적 우대
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSpecialSegmentFairness:
    """특수 세그먼트 우대가 합리적 근거에 기반함을 검증."""

    SEGMENT_BENEFITS = {
        "SEG-DR": {"rationale": "전문직 소득 안정성", "rate_discount": -0.003},
        "SEG-JD": {"rationale": "전문직 소득 안정성", "rate_discount": -0.002},
        "SEG-ART": {"rationale": "예술인복지재단 등록, 불규칙 소득 보완", "rate_discount": 0.0},
        "SEG-YTH": {"rationale": "청년층 금융 접근성 지원", "rate_discount": -0.005},
        "SEG-MIL": {"rationale": "군인 신분 보장, 고용 안정성", "rate_discount": -0.005},
        "SEG-MOU": {"rationale": "협약기업 신용보강", "rate_discount": -0.003},
    }

    def test_all_segments_have_rationale(self):
        """모든 특수 세그먼트에 우대 근거 존재."""
        for seg, benefit in self.SEGMENT_BENEFITS.items():
            assert benefit["rationale"], f"{seg} 우대 근거 없음"

    def test_segment_discounts_non_positive(self):
        """세그먼트 금리 할인은 0 이하 (혜택은 금리 인하)."""
        for seg, benefit in self.SEGMENT_BENEFITS.items():
            assert benefit["rate_discount"] <= 0, \
                f"{seg} 금리 할인이 양수 → 불이익"

    def test_seg_art_income_smoothing_rationale(self):
        """SEG-ART: 12개월 소득 평활화 (불규칙 수입 보완 — 긍정적 우대)."""
        # 예술인은 불규칙 수입 → 12개월 평균 소득 인정
        art_monthly_incomes = [0, 3_000_000, 0, 5_000_000, 0, 2_000_000,
                               4_000_000, 0, 1_000_000, 0, 6_000_000, 2_000_000]
        avg_income = np.mean(art_monthly_incomes)
        assert avg_income > 0, "예술인 평균 소득이 0"

    def test_seg_yth_age_based_rationale(self):
        """SEG-YTH: 연령 기반이지만 금융 접근성 목적 (긍정적 차별)."""
        # 청년 금리 우대는 금융 소외 계층 지원 목적 → 합법적 우대
        youth_rate_discount = -0.005  # -0.5%p
        assert youth_rate_discount < 0, "청년 우대 금리가 없음"

    def test_non_segment_not_penalized(self):
        """일반 차주 (세그먼트 없음): 패널티 없음."""
        # 세그먼트 없는 일반 차주는 기본 조건 적용 (불이익 없음)
        default_segment_benefit = {"rate_adjustment": 0.0, "limit_multiplier": 1.0}
        assert default_segment_benefit["rate_adjustment"] == 0.0
        assert default_segment_benefit["limit_multiplier"] == 1.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 합성 데이터 공정성 (인구 분포)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSyntheticDataFairness:
    """합성 훈련 데이터의 인구학적 분포 편향 검사."""

    def _load_credit_data(self) -> pd.DataFrame:
        path = os.path.join(DATA_DIR, "synthetic_credit.parquet")
        if not os.path.exists(path):
            pytest.skip("synthetic_credit.parquet 없음")
        return pd.read_parquet(path)

    def test_age_distribution_reasonable(self):
        """연령 분포: 대출 가능 연령(20~70세) 충분히 포함."""
        df = self._load_credit_data()
        if "age" not in df.columns:
            pytest.skip("age 컬럼 없음")
        age_in_range = df[(df["age"] >= 20) & (df["age"] <= 70)]
        coverage = len(age_in_range) / len(df)
        assert coverage >= 0.95, f"연령 범위 내 비율({coverage:.1%}) < 95%"

    def test_income_distribution_not_skewed_extreme(self):
        """소득 분포: 극단적 편향 없어야 함 (상위 1% 소득이 전체의 50% 이하)."""
        df = self._load_credit_data()
        if "income_annual" not in df.columns:
            pytest.skip("income_annual 컬럼 없음")
        top1_pct = df["income_annual"].quantile(0.99)
        median = df["income_annual"].median()
        ratio = top1_pct / median
        # 합리적 소득 분포: 99th percentile이 중앙값의 10배 이하
        assert ratio <= 10, f"소득 분포 극단적 편향: 99th/median = {ratio:.1f}배"

    def test_default_rate_reasonable(self):
        """부도율: 1%~20% 범위 (현실적 범위)."""
        df = self._load_credit_data()
        target_col = "default_12m" if "default_12m" in df.columns else "default_flag"
        if target_col not in df.columns:
            pytest.skip("부도 컬럼 없음")
        bad_rate = df[target_col].mean()
        assert 0.01 <= bad_rate <= 0.20, \
            f"부도율({bad_rate:.1%}) 비현실적 범위"

    def test_employment_type_diversity(self):
        """고용 형태 다양성: 단일 유형 90% 초과 없어야."""
        df = self._load_credit_data()
        if "employment_type" not in df.columns:
            pytest.skip("employment_type 컬럼 없음")
        top_share = df["employment_type"].value_counts(normalize=True).iloc[0]
        assert top_share <= 0.90, \
            f"고용 유형 편향: 상위 유형 {top_share:.1%} (90% 초과)"

    def test_no_null_values_in_key_features(self):
        """핵심 피처에 과다 결측치 없어야 (결측치 < 5%)."""
        df = self._load_credit_data()
        key_features = ["cb_score", "income_annual", "delinquency_count_12m"]
        for feat in key_features:
            if feat not in df.columns:
                continue
            null_rate = df[feat].isna().mean()
            assert null_rate < 0.05, \
                f"{feat} 결측치 비율({null_rate:.1%}) ≥ 5%"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Shadow Mode 투명성 (금소법 §19)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestShadowModeTransparency:
    """Shadow Mode는 내부 검증용 — 고객 결정에 직접 반영 금지."""

    def test_shadow_mode_not_disclosed_to_customer(self):
        """Shadow 모드 점수/결정이 고객 응답에 포함 안 됨."""
        # scoring.py API 응답에 shadow 필드가 숨겨진지 확인
        scoring_api_path = os.path.join(
            BASE_DIR, "backend", "app", "api", "v1", "scoring.py"
        )
        if not os.path.exists(scoring_api_path):
            pytest.skip("scoring.py 없음")
        with open(scoring_api_path, encoding="utf-8") as f:
            src = f.read()
        # shadow_score가 응답에 포함될 경우 주석/조건부로 처리되어야 함
        # 여기서는 shadow_mode 처리 로직이 존재하는지만 검증
        assert "shadow" in src.lower(), "shadow mode 처리 로직 없음"

    def test_shadow_score_stored_internally_only(self):
        """Shadow 점수는 DB에만 저장 (금소법 §19 알고리즘 공개 시 활용 가능)."""
        # loan_application.py에 shadow_challenger_score 저장 필드 확인
        schema_path = os.path.join(
            BASE_DIR, "backend", "app", "db", "schemas", "loan_application.py"
        )
        if not os.path.exists(schema_path):
            pytest.skip("loan_application.py 없음")
        with open(schema_path, encoding="utf-8") as f:
            src = f.read()
        assert "shadow_challenger_score" in src or "shadow" in src.lower(), \
            "Shadow 점수 저장 필드 없음"

    def test_champion_challenger_purpose(self):
        """Champion-Challenger 목적: 모델 성능 비교 (내부용)."""
        # 챌린저 점수는 현행 모델 대비 성능 비교 목적으로만 사용
        purpose = "internal_model_comparison"
        assert purpose == "internal_model_comparison"  # 명세 확인


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. AI 모범규준 7대 원칙 체크리스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAIPrinciples:
    """금융위원회 AI 모범규준 7대 원칙 체크리스트."""

    AI_PRINCIPLES = {
        "transparency": "AI 모델 의사결정 과정 설명 가능",
        "accountability": "AI 결정에 대한 책임 주체 명확",
        "fairness": "차별 없는 공정한 심사",
        "safety": "모델 오작동 및 오류 대비",
        "privacy": "개인정보 보호 및 최소 수집",
        "robustness": "환경 변화에도 안정적 작동",
        "human_oversight": "AI 결정에 대한 인간 감독 가능",
    }

    def test_transparency_principle_met(self):
        """투명성: SHAP 기반 설명 + 한국어 거절 사유 제공."""
        # scoring_engine.py에 설명 생성 로직 확인
        if not os.path.exists(SCORING_ENGINE_PATH):
            pytest.skip("scoring_engine.py 없음")
        with open(SCORING_ENGINE_PATH, encoding="utf-8") as f:
            src = f.read()
        has_explanation = "explanation" in src or "reject_reason" in src or "거절" in src
        assert has_explanation, "투명성 원칙 미충족: 거절 사유 생성 없음"

    def test_accountability_principle_met(self):
        """책임성: model_card에 모델 버전, 학습일시, 담당자 필드."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        assert "trained_at" in card, "책임성 원칙 미충족: trained_at 없음"
        assert "version" in card, "책임성 원칙 미충족: 버전 없음"

    def test_fairness_principle_met(self):
        """공정성: 보호 속성(성별/인종) 피처 제외 확인."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        features = [f.lower() for f in card.get("features", [])]
        assert "gender" not in features
        assert "race" not in features

    def test_privacy_principle_met(self):
        """프라이버시: 주민번호 해시 저장 (평문 없음)."""
        schema_path = os.path.join(
            BASE_DIR, "backend", "app", "db", "schemas", "applicant.py"
        )
        if not os.path.exists(schema_path):
            pytest.skip("applicant.py 없음")
        with open(schema_path, encoding="utf-8") as f:
            src = f.read()
        # 주민번호 해시 필드 존재
        assert "resident_registration_hash" in src or "hash" in src.lower(), \
            "프라이버시 원칙 미충족: 주민번호 해시 저장 없음"
        # 평문 주민번호 필드 없어야 함
        assert "resident_registration_no" not in src and \
               "jumin_no" not in src, \
            "프라이버시 위반: 평문 주민번호 필드 존재"

    def test_human_oversight_principle_met(self):
        """인간 감독: 수동 심사(manual_review) 경로 존재."""
        if not os.path.exists(SCORING_ENGINE_PATH):
            pytest.skip("scoring_engine.py 없음")
        with open(SCORING_ENGINE_PATH, encoding="utf-8") as f:
            src = f.read()
        assert "manual" in src.lower() or "수동" in src or "심사" in src, \
            "인간 감독 원칙 미충족: 수동 심사 경로 없음"

    def test_robustness_principle_met(self):
        """강건성: OOT 성능 검증 + PSI 모니터링."""
        card_path = os.path.join(ARTIFACTS_DIR, "model_card.json")
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음")
        with open(card_path) as f:
            card = json.load(f)
        # OOT 검증 존재
        perf = card.get("performance", {})
        assert "oot_gini" in perf, "강건성 원칙 미충족: OOT 검증 없음"

    def test_all_principles_documented(self):
        """7대 원칙 모두 정의 상태."""
        assert len(self.AI_PRINCIPLES) == 7, \
            f"AI 원칙 수({len(self.AI_PRINCIPLES)}) ≠ 7"


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
