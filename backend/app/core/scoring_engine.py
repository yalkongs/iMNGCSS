"""
스코어링 엔진 (Application Scorecard)
======================================
LightGBM 모델 로드 → 피처 전처리 → 점수 산출 → SHAP 설명 → 신용등급 변환

점수 스케일링:
  - 범위: 300~900
  - 기준점: 600점 = Base PD 7.2%
  - PDO (Points to Double Odds): 40점
  - 공식: Score = Base - (PDO/log2) × log(PD/(1-PD))

바젤III IRB 파라미터:
  - PD: 모델 출력 확률 (IRG 조정 포함)
  - LGD: 신용대출 45%, 주담대 25%, 소액론 60%
  - EAD: 기간별 원금 + CCF × 미사용 한도

의사결정 규칙 (BRMS 연동):
  - DSR > 40% → 거절
  - LTV 초과 → 거절
  - 연체중 → 거절 (하드 컷오프)
  - 점수 < 400 → 거절
  - 400 ≤ 점수 < 500 → 수동 심사
"""
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# 점수 스케일링 파라미터
SCORE_BASE = 600
SCORE_PDO = 40
BASE_PD = 0.072
SCORE_MIN = 300
SCORE_MAX = 900

# 신용등급 → PD 매핑 (바젤III IRB 내부 기준)
GRADE_PD_MAP = {
    "AAA": (0.0005, 900, 870),
    "AA":  (0.0010, 869, 840),
    "A":   (0.0030, 839, 805),
    "BBB": (0.0100, 804, 750),
    "BB":  (0.0300, 749, 665),
    "B":   (0.0700, 664, 600),
    "CCC": (0.1500, 599, 515),
    "CC":  (0.3000, 514, 445),
    "C":   (0.5000, 444, 351),
    "D":   (1.0000, 350, 0),
}

# LGD 기본값
LGD_BY_PRODUCT = {
    "credit":       0.45,
    "credit_soho":  0.50,
    "mortgage":     0.25,
    "micro":        0.60,
}

# 위험가중치 (Basel III Standard)
RW_BY_PRODUCT = {
    "credit":       0.75,
    "credit_soho":  0.75,
    "mortgage":     0.35,
    "micro":        1.00,
}

# 의사결정 점수 컷오프
CUTOFF_REJECT = 450         # 이 미만: 자동 거절
CUTOFF_MANUAL = 530         # 이 미만~거절초과: 수동 심사
CUTOFF_APPROVE = 530        # 이 이상: 자동 승인

# 수동 심사 상향 가능 점수 (세그먼트 혜택 반영 후)
MANUAL_REVIEW_SCORE_RANGE = (CUTOFF_REJECT, CUTOFF_MANUAL)


@dataclass
class ScoringInput:
    """스코어링 입력 데이터"""
    # 신청 정보
    application_id: str = ""
    product_type: str = "credit"        # credit | mortgage | micro | credit_soho
    requested_amount: float = 0.0       # 원
    requested_term_months: int = 12

    # 신청인 정보
    applicant_type: str = "individual"  # individual | self_employed
    age: int = 0
    employment_type: str = ""
    income_annual: float = 0.0          # 원
    income_verified: bool = True

    # CB 정보
    cb_score: int = 0                   # NICE/KCB 점수 (300~1000)
    delinquency_count_12m: int = 0
    worst_delinquency_status: int = 0   # 0~3
    open_loan_count: int = 0
    total_loan_balance: float = 0.0     # 원
    inquiry_count_3m: int = 0

    # 세그먼트/EQ/IRG
    segment_code: str = ""
    eq_grade: str = "EQ-C"
    irg_code: str = "M"
    irg_pd_adjustment: float = 0.0

    # 주담대 전용
    collateral_value: float = 0.0
    is_regulated_area: bool = False
    is_speculation_area: bool = False
    owned_property_count: int = 0

    # 기존 부채
    existing_monthly_payment: float = 0.0
    existing_credit_line: float = 0.0
    existing_credit_balance: float = 0.0

    # 대안 데이터
    telecom_no_delinquency: int = 1
    health_insurance_paid_months_12m: int = 12
    national_pension_paid_months_24m: int = 24

    # 개인사업자 전용
    business_duration_months: int = 0
    revenue_annual: float = 0.0
    operating_income: float = 0.0
    tax_filing_count: int = 0

    # 외부 연동 / 성능 테스트 호환 alias 필드
    resident_hash: str = ""                       # application_id 대안 (주민등록 해시)
    income_annual_wan: float = 0.0                # 만원 단위 소득 (income_annual 대안)
    employment_duration_months: int = 0           # 재직 기간 (월)
    existing_loan_monthly_payment: float = 0.0    # existing_monthly_payment 대안
    dsr_ratio: float = 0.0                        # 외부 DSR 직접 입력


@dataclass
class RateBreakdown:
    """RAROC 기반 금리 분해표"""
    base_rate: float            # 기준금리 (한국은행)
    credit_spread: float        # 신용 스프레드 (PD × LGD 기반)
    funding_cost: float         # 조달 비용
    operating_cost: float       # 운영 비용
    eq_adjustment: float        # EQ Grade 조정
    segment_discount: float     # 세그먼트 우대
    relationship_discount: float # 거래관계 우대
    final_rate: float           # 최종 적용 금리
    rate_capped: bool           # 최고금리 캡 적용 여부
    raroc_at_final_rate: float  # 최종금리에서의 RAROC
    hurdle_rate_satisfied: bool # RAROC ≥ 허들금리(15%)

    def to_dict(self) -> dict:
        return {
            "base_rate": round(self.base_rate, 4),
            "credit_spread": round(self.credit_spread, 4),
            "funding_cost": round(self.funding_cost, 4),
            "operating_cost": round(self.operating_cost, 4),
            "eq_adjustment": round(self.eq_adjustment, 4),
            "segment_discount": round(self.segment_discount, 4),
            "relationship_discount": round(self.relationship_discount, 4),
            "final_rate": round(self.final_rate, 4),
            "rate_capped": self.rate_capped,
            "raroc_at_final_rate": round(self.raroc_at_final_rate, 4),
            "hurdle_rate_satisfied": self.hurdle_rate_satisfied,
        }


@dataclass
class ScoringResult:
    """스코어링 결과"""
    # 점수 및 등급
    score: int                  # 300~900
    grade: str                  # AAA~D
    raw_probability: float      # 모델 원시 확률
    pd_estimate: float          # IRG 조정 후 최종 PD
    lgd_estimate: float
    ead_estimate: float
    risk_weight: float
    economic_capital: float

    # 의사결정
    decision: str               # approved | rejected | manual_review
    approved_amount: float
    approved_term_months: int

    # 금리
    rate_breakdown: RateBreakdown

    # 규제 비율
    dsr_ratio: float
    stress_dsr_ratio: float
    ltv_ratio: float
    dsr_limit_breached: bool
    ltv_limit_breached: bool

    # 거절 사유 (금소법 §19)
    rejection_reasons: list[str] = field(default_factory=list)
    top_positive_factors: list[dict] = field(default_factory=list)
    top_negative_factors: list[dict] = field(default_factory=list)

    # 이의제기 (신용정보법 §39의5)
    appeal_deadline: datetime | None = None

    # 모델 메타
    model_version: str = "v1.0"
    scorecard_type: str = "application"


class ScoringEngine:
    """
    Application Scorecard 스코어링 엔진.
    모델 파일이 없으면 통계 기반 추정 모드로 동작 (데모 환경).
    """

    def __init__(self, artifacts_path: str = "./artifacts", policy_engine=None, model_path=None):
        self._artifacts_path = artifacts_path
        self._policy_engine = policy_engine
        self._model = None
        self._model_version = "demo-v1.0"
        self._load_model()

    def _load_model(self) -> None:
        """LightGBM 모델 로드. 파일 없으면 통계 기반 폴백."""
        model_path = os.path.join(self._artifacts_path, "application_scorecard.lgb")
        if os.path.exists(model_path):
            try:
                import lightgbm as lgb
                self._model = lgb.Booster(model_file=model_path)
                logger.info(f"LightGBM 모델 로드 완료: {model_path}")
            except Exception as e:
                logger.warning(f"모델 로드 실패, 통계 폴백 모드: {e}")
        else:
            logger.info("모델 파일 없음 - 통계 기반 추정 모드 (데모)")

    def _estimate_pd_statistical(self, inp: ScoringInput) -> float:
        """
        모델 없을 때 통계 기반 PD 추정 (데모 환경 폴백).
        로지스틱 회귀 근사.
        """
        log_odds = -3.5

        # CB 점수 효과
        log_odds += (inp.cb_score - 700) / 100 * (-1.8)

        # 연체 이력
        log_odds += inp.delinquency_count_12m * 0.6
        log_odds += inp.worst_delinquency_status * 0.8

        # DSR 초과
        income_monthly = inp.income_annual / 12
        new_monthly = inp.requested_amount * 0.005
        total_monthly = inp.existing_monthly_payment + new_monthly
        dsr = (total_monthly / income_monthly * 100) if income_monthly > 0 else 999
        dsr_excess = max(0, dsr - 40)
        log_odds += dsr_excess * 0.03

        # 소득 억제 효과
        log_odds += math.log1p(50000 / max(inp.income_annual, 1)) * 0.5

        # 조회 수
        log_odds += inp.inquiry_count_3m * 0.3

        # 대안 데이터
        log_odds -= inp.telecom_no_delinquency * 0.3
        log_odds -= (inp.health_insurance_paid_months_12m / 12) * 0.4

        # 개인사업자 추가 위험
        if inp.applicant_type == "self_employed":
            log_odds += 0.3
            if inp.business_duration_months < 24:
                log_odds += 0.4
            if inp.tax_filing_count < 2:
                log_odds += 0.3

        pd_raw = 1 / (1 + math.exp(-log_odds))

        # IRG 조정
        pd_adjusted = pd_raw * (1 + inp.irg_pd_adjustment)

        return float(np.clip(pd_adjusted, 0.001, 0.999))

    @staticmethod
    def pd_to_score(pd: float) -> int:
        """PD → 스코어 변환 (300~900)"""
        if pd <= 0 or pd >= 1:
            return SCORE_MIN if pd >= 1 else SCORE_MAX
        odds = pd / (1 - pd)
        score = SCORE_BASE - (SCORE_PDO / math.log(2)) * math.log(odds / (BASE_PD / (1 - BASE_PD)))
        return int(np.clip(round(score), SCORE_MIN, SCORE_MAX))

    @staticmethod
    def score_to_grade(score: int) -> str:
        """스코어 → 신용등급"""
        for grade, (pd_val, upper, lower) in GRADE_PD_MAP.items():
            if lower <= score <= upper:
                return grade
        return "D"

    def _compute_dsr(
        self, inp: ScoringInput, stress_rate: float = 0.0
    ) -> tuple[float, float]:
        """DSR 및 스트레스 DSR 계산"""
        income_monthly = inp.income_annual / 12
        if income_monthly <= 0:
            return 999.0, 999.0

        new_monthly = inp.requested_amount * 0.005  # 5%, 20년 상환 근사
        total_monthly = inp.existing_monthly_payment + new_monthly
        dsr = total_monthly / income_monthly * 100

        # 스트레스 DSR: 스트레스 가산금리 반영
        stressed_rate = 0.05 + stress_rate / 100  # 연이율
        stressed_monthly = inp.requested_amount * (stressed_rate / 12) / (
            1 - (1 + stressed_rate / 12) ** (-inp.requested_term_months)
        ) if inp.requested_term_months > 0 else new_monthly
        stress_total = inp.existing_monthly_payment + stressed_monthly
        stress_dsr = stress_total / income_monthly * 100

        return round(dsr, 4), round(stress_dsr, 4)

    def _compute_ltv(self, inp: ScoringInput) -> float:
        """LTV 계산 (주담대 전용)"""
        if inp.product_type != "mortgage" or inp.collateral_value <= 0:
            return 0.0
        return round(inp.requested_amount / inp.collateral_value * 100, 4)

    def _compute_ead(self, inp: ScoringInput) -> float:
        """EAD 계산 (CCF 포함)"""
        if inp.product_type in ("credit", "mortgage", "micro", "credit_soho"):
            # 기간부 대출: EAD = 신청금액 (실행 기준)
            ead = inp.requested_amount
        else:
            # 회전한도: EAD = 잔액 + CCF × 미사용한도
            ccf = 0.50
            unused = max(0, inp.existing_credit_line - inp.existing_credit_balance)
            ead = inp.existing_credit_balance + ccf * unused

        return ead

    def _compute_rate_breakdown(
        self,
        pd: float,
        lgd: float,
        ead: float,
        rw: float,
        eq_grade: str,
        segment_code: str,
        base_rate: float = 3.5,
        max_rate: float = 20.0,
    ) -> RateBreakdown:
        """
        RAROC 기반 금리 분해 계산.
        final_rate = base_rate + credit_spread + funding_cost + operating_cost + EQ조정 + 세그먼트우대
        """
        # 신용 스프레드: EL = PD × LGD (위험 프리미엄)
        el = pd * lgd
        credit_spread = round(el * 100 * 2.5, 4)   # EL → 금리 스프레드 환산 (승수 2.5)

        funding_cost = 1.2   # 조달 비용 (평균 예금금리 근사)
        operating_cost = 0.8  # 운영 비용 (판관비/대출 비율 근사)

        # EQ Grade 금리 조정
        eq_adj_map = {
            "EQ-S": -0.5, "EQ-A": -0.3, "EQ-B": -0.2,
            "EQ-C": 0.0,  "EQ-D":  0.2, "EQ-E":  0.5,
        }
        eq_adjustment = eq_adj_map.get(eq_grade, 0.0)

        # 세그먼트 우대
        seg_discount_map = {
            "SEG-DR":  -0.3,
            "SEG-JD":  -0.2,
            "SEG-YTH": -0.5,
            "SEG-MIL": -0.5,
            "SEG-ART":  0.0,
        }
        seg_prefix = segment_code.split("-")[0] + "-" + segment_code.split("-")[1] if "-" in segment_code else segment_code
        seg_discount = seg_discount_map.get(segment_code, seg_discount_map.get(seg_prefix, 0.0))
        if segment_code.startswith("SEG-MOU-"):
            seg_discount = -0.3  # MOU 기본 우대

        relationship_discount = 0.0  # 거래관계 우대 (추후 확장)

        raw_rate = (
            base_rate
            + credit_spread
            + funding_cost
            + operating_cost
            + eq_adjustment
            + seg_discount
            + relationship_discount
        )

        rate_capped = raw_rate > max_rate
        final_rate = min(raw_rate, max_rate)
        final_rate = max(final_rate, base_rate + 0.5)  # 최저금리 보장

        # RAROC 계산: (Net Interest Income - EL) / Economic Capital
        net_interest = final_rate / 100 * ead
        el_amount = el * ead
        economic_capital = ead * rw * 0.08
        raroc = (net_interest - el_amount) / economic_capital if economic_capital > 0 else 0.0

        return RateBreakdown(
            base_rate=base_rate,
            credit_spread=credit_spread,
            funding_cost=funding_cost,
            operating_cost=operating_cost,
            eq_adjustment=eq_adjustment,
            segment_discount=seg_discount,
            relationship_discount=relationship_discount,
            final_rate=round(final_rate, 4),
            rate_capped=rate_capped,
            raroc_at_final_rate=round(raroc, 4),
            hurdle_rate_satisfied=raroc >= 0.15,
        )

    def _make_rejection_reasons(
        self,
        inp: ScoringInput,
        score: int,
        dsr: float,
        dsr_limit: float,
        ltv: float,
        ltv_limit: float,
    ) -> list[str]:
        """거절 사유 생성 (금소법 §19 - 한국어 3가지)"""
        reasons = []

        if inp.worst_delinquency_status >= 1:
            reasons.append("현재 연체 기록이 있어 대출이 불가합니다.")

        if score < CUTOFF_REJECT:
            reasons.append(
                f"신용평가 점수({score}점)가 최저 기준({CUTOFF_REJECT}점)에 미달합니다."
            )

        if dsr > dsr_limit:
            reasons.append(
                f"총부채원리금상환비율(DSR)이 {dsr:.1f}%로 한도({dsr_limit:.0f}%)를 초과합니다."
            )

        if ltv > ltv_limit:
            reasons.append(
                f"담보인정비율(LTV)이 {ltv:.1f}%로 한도({ltv_limit:.0f}%)를 초과합니다."
            )

        if inp.income_annual < 12_000_000:
            reasons.append("연소득이 최저 기준(1,200만원)에 미달합니다.")

        # 최대 3개
        return reasons[:3]

    def score(
        self,
        inp: ScoringInput,
        dsr_limit: float = 40.0,
        stress_dsr_rate: float = 0.0,
        ltv_limit: float = 70.0,
        max_rate: float = 20.0,
        base_rate: float = 3.5,
    ) -> ScoringResult:
        """
        신용 스코어링 메인 로직.

        Args:
            inp: 스코어링 입력 데이터
            dsr_limit: DSR 한도 (BRMS에서 조회)
            stress_dsr_rate: 스트레스 DSR 가산금리 (BRMS에서 조회)
            ltv_limit: LTV 한도 (BRMS에서 조회, 주담대)
            max_rate: 최고금리 (BRMS에서 조회)
            base_rate: 기준금리
        """
        # ── 1. PD 추정 ─────────────────────────────────────────────
        if self._model is not None:
            # LightGBM 모델 사용
            features = self._build_feature_vector(inp)
            pd_raw = float(self._model.predict([features])[0])
        else:
            # 통계 기반 추정 (데모)
            pd_raw = self._estimate_pd_statistical(inp)

        # IRG 추가 조정
        pd_final = float(np.clip(pd_raw * (1 + inp.irg_pd_adjustment), 0.001, 0.999))

        # ── 2. 점수 및 등급 변환 ──────────────────────────────────
        score = self.pd_to_score(pd_final)
        grade = self.score_to_grade(score)

        # ── 3. 리스크 파라미터 ────────────────────────────────────
        lgd = LGD_BY_PRODUCT.get(inp.product_type, 0.45)
        rw = RW_BY_PRODUCT.get(inp.product_type, 0.75)
        ead = self._compute_ead(inp)
        economic_capital = ead * rw * 0.08

        # ── 4. 규제 비율 계산 ─────────────────────────────────────
        dsr, stress_dsr = self._compute_dsr(inp, stress_dsr_rate)
        ltv = self._compute_ltv(inp)

        dsr_breached = dsr > dsr_limit
        ltv_breached = ltv > ltv_limit

        # ── 5. 의사결정 ───────────────────────────────────────────
        rejection_reasons = []
        is_hard_reject = (
            inp.worst_delinquency_status >= 2   # 2개월+ 연체: 하드 컷오프
            or score < CUTOFF_REJECT
            or dsr_breached
            or ltv_breached
            or inp.income_annual < 12_000_000
        )

        if is_hard_reject:
            decision = "rejected"
            rejection_reasons = self._make_rejection_reasons(
                inp, score, dsr, dsr_limit, ltv, ltv_limit
            )
            approved_amount = 0.0
        elif score < CUTOFF_MANUAL:
            decision = "manual_review"
            approved_amount = inp.requested_amount
        else:
            decision = "approved"
            approved_amount = inp.requested_amount

        # ── 6. 한도 조정 (EQ Grade 배수) ──────────────────────────
        if decision == "approved":
            eq_multiplier_map = {
                "EQ-S": 2.0, "EQ-A": 1.8, "EQ-B": 1.5,
                "EQ-C": 1.2, "EQ-D": 1.0, "EQ-E": 0.7,
            }
            eq_mult = eq_multiplier_map.get(inp.eq_grade, 1.0)
            # 소득 배수 한도 (신용대출)
            if inp.product_type in ("credit", "credit_soho"):
                income_cap = inp.income_annual * 1.5 * eq_mult
                approved_amount = min(approved_amount, income_cap)

        # ── 7. 금리 분해 ──────────────────────────────────────────
        rate_breakdown = self._compute_rate_breakdown(
            pd=pd_final, lgd=lgd, ead=ead, rw=rw,
            eq_grade=inp.eq_grade,
            segment_code=inp.segment_code,
            base_rate=base_rate,
            max_rate=max_rate,
        )

        # ── 8. 설명 요인 (SHAP 없을 때 휴리스틱) ─────────────────
        pos_factors, neg_factors = self._generate_explanation_factors(inp, score, pd_final)

        # ── 9. 이의제기 기한 (거절/수동심사 시) ──────────────────
        appeal_deadline = None
        if decision in ("rejected", "manual_review"):
            appeal_deadline = datetime.utcnow() + timedelta(days=30)

        return ScoringResult(
            score=score,
            grade=grade,
            raw_probability=round(pd_raw, 6),
            pd_estimate=round(pd_final, 6),
            lgd_estimate=round(lgd, 6),
            ead_estimate=round(ead, 2),
            risk_weight=round(rw, 4),
            economic_capital=round(economic_capital, 2),
            decision=decision,
            approved_amount=round(approved_amount, 0),
            approved_term_months=inp.requested_term_months,
            rate_breakdown=rate_breakdown,
            dsr_ratio=dsr,
            stress_dsr_ratio=stress_dsr,
            ltv_ratio=ltv,
            dsr_limit_breached=dsr_breached,
            ltv_limit_breached=ltv_breached,
            rejection_reasons=rejection_reasons,
            top_positive_factors=pos_factors,
            top_negative_factors=neg_factors,
            appeal_deadline=appeal_deadline,
            model_version=self._model_version,
        )

    @staticmethod
    def _generate_explanation_factors(
        inp: ScoringInput, score: int, pd: float
    ) -> tuple[list[dict], list[dict]]:
        """
        SHAP 없을 때 휴리스틱 설명 인자 생성.
        실제 환경에서는 SHAP 값으로 대체.
        """
        pos = []
        neg = []

        # 긍정 요인
        if inp.cb_score >= 750:
            pos.append({"factor": "신용점수 우수", "detail": f"CB 점수 {inp.cb_score}점 (상위권)", "impact": "high"})
        if inp.delinquency_count_12m == 0:
            pos.append({"factor": "최근 연체 없음", "detail": "최근 12개월 연체 기록 없음", "impact": "medium"})
        if inp.income_verified:
            pos.append({"factor": "소득 검증 완료", "detail": "건강보험 납부로 소득 확인됨", "impact": "medium"})
        if inp.telecom_no_delinquency == 1:
            pos.append({"factor": "통신료 성실 납부", "detail": "통신료 납부 이력 양호", "impact": "low"})
        if inp.segment_code in ("SEG-DR", "SEG-JD", "SEG-MIL"):
            pos.append({"factor": "전문직/안정직종", "detail": f"세그먼트 {inp.segment_code} 해당", "impact": "high"})

        # 부정 요인
        income_monthly = inp.income_annual / 12
        new_monthly = inp.requested_amount * 0.005
        dsr_approx = (inp.existing_monthly_payment + new_monthly) / income_monthly * 100 if income_monthly > 0 else 999
        if dsr_approx > 30:
            neg.append({"factor": "DSR 비율 높음", "detail": f"원리금상환비율 {dsr_approx:.0f}%", "impact": "high"})
        if inp.inquiry_count_3m >= 3:
            neg.append({"factor": "최근 조회 많음", "detail": f"최근 3개월 {inp.inquiry_count_3m}회 조회", "impact": "medium"})
        if inp.open_loan_count >= 4:
            neg.append({"factor": "보유 대출 많음", "detail": f"현재 {inp.open_loan_count}건 대출 보유", "impact": "medium"})
        if inp.applicant_type == "self_employed" and inp.business_duration_months < 24:
            neg.append({"factor": "사업기간 짧음", "detail": f"사업 영위 {inp.business_duration_months}개월", "impact": "medium"})

        return pos[:3], neg[:3]

    def _build_feature_vector(self, inp: ScoringInput) -> list:
        """LightGBM 입력용 피처 벡터 생성"""
        # 실제 훈련된 모델의 피처 순서와 일치해야 함
        # 여기서는 기본 피처만 나열 (실제 환경에서 feature_names.json 참조)
        return [
            inp.cb_score,
            inp.delinquency_count_12m,
            inp.worst_delinquency_status,
            inp.open_loan_count,
            inp.total_loan_balance / 1_000_000,  # 백만원 단위
            inp.inquiry_count_3m,
            inp.income_annual / 1_000_000,
            inp.requested_amount / 1_000_000,
            inp.age,
            1 if inp.employment_type == "employed" else 0,
            1 if inp.applicant_type == "self_employed" else 0,
            inp.telecom_no_delinquency,
            inp.health_insurance_paid_months_12m,
        ]
