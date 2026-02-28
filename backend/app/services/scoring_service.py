"""
ScoringService
===============
PolicyEngine (BRMS) + ScoringEngine 통합 서비스.
신청/신청인 데이터 → 규제 파라미터 조회 → 스코어링 → 결과 반환.
"""
import logging
import os
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.policy_engine import PolicyEngine
from app.core.scoring_engine import ScoringEngine, ScoringInput, ScoringResult
from app.services.cb_service import CBService

logger = logging.getLogger(__name__)


class ScoringService:
    """
    신용평가 서비스.
    PolicyEngine으로 규제 파라미터 조회 후 ScoringEngine 실행.
    """

    def __init__(self, db: AsyncSession, redis_client=None):
        self._db = db
        self._policy_engine = PolicyEngine(db, redis_client)
        self._scoring_engine = ScoringEngine(
            artifacts_path=os.getenv("MODEL_ARTIFACTS_PATH", "./artifacts"),
            policy_engine=self._policy_engine,
        )
        self._cb_base_url = os.getenv("CB_MOCK_BASE_URL", "http://mock-server:8001")

    async def evaluate(
        self,
        application,       # LoanApplication ORM 객체
        applicant,         # Applicant ORM 객체
        rate_type: str = "variable",
        stress_dsr_region: str = "metropolitan",
    ) -> ScoringResult:
        """
        전체 신용평가 실행.

        1. BRMS에서 규제 파라미터 조회
        2. ScoringEngine 실행
        3. 결과 반환
        """
        eff_date = datetime.utcnow()

        # ── 1. BRMS 규제 파라미터 조회 ──────────────────────────
        # 스트레스 DSR
        stress_rate = await self._policy_engine.get_stress_dsr_rate(
            region=stress_dsr_region,
            rate_type=rate_type,
            effective_date=eff_date,
        )

        # DSR 한도
        dsr_limit = await self._policy_engine.get_dsr_limit(
            product_type=application.product_type,
            effective_date=eff_date,
        )

        # LTV 한도 (주담대)
        if application.product_type == "mortgage":
            area_type = "speculation_area" if application.is_speculation_area else \
                        "regulated" if application.is_regulated_area else "general"
            ltv_limit = await self._policy_engine.get_ltv_limit(
                area_type=area_type,
                owned_count=application.owned_property_count or 0,
                effective_date=eff_date,
            )
        else:
            ltv_limit = 100.0  # 신용대출은 LTV 무관

        # 최고금리
        max_rate = await self._policy_engine.get_max_interest_rate(eff_date)

        # EQ Grade 혜택 (세그먼트 또는 직장 신용도)
        eq_grade = applicant.employer_eq_grade or "EQ-C"
        segment_code = applicant.segment_code or ""

        # 세그먼트에 최소 EQ Grade 보장
        if segment_code:
            seg_benefit = await self._policy_engine.get_segment_benefit(segment_code, eff_date)
            guaranteed_eq = seg_benefit.get("guaranteed_eq_grade")
            if guaranteed_eq:
                eq_order = ["EQ-S", "EQ-A", "EQ-B", "EQ-C", "EQ-D", "EQ-E"]
                current_idx = eq_order.index(eq_grade) if eq_grade in eq_order else 5
                guaranteed_idx = eq_order.index(guaranteed_eq) if guaranteed_eq in eq_order else 5
                if guaranteed_idx < current_idx:
                    eq_grade = guaranteed_eq

        # IRG PD 조정
        irg_code = applicant.irg_code or "M"
        irg_adjustment = await self._policy_engine.get_irg_pd_adjustment(irg_code, eff_date)

        # 기준금리 (config 기본값 사용)
        from app.config import settings
        base_rate = settings.BASE_RATE

        # ── 2. CB API 조회 ───────────────────────────────────────
        async with CBService(base_url=self._cb_base_url) as cb_svc:
            cb_result = await cb_svc.get_score(
                resident_hash=applicant.resident_registration_hash,
                applicant_name=applicant.name if hasattr(applicant, "name") else None,
            )

        logger.info(
            f"CB 조회: source={cb_result.source} score={cb_result.cb_score} "
            f"delinquency={cb_result.delinquency_count_12m}"
        )

        # ── 3. ScoringInput 조립 ─────────────────────────────────
        inp = ScoringInput(
            application_id=str(application.id),
            product_type=application.product_type,
            requested_amount=float(application.requested_amount or 0),
            requested_term_months=int(application.requested_term_months or 36),

            applicant_type=applicant.applicant_type or "individual",
            age=applicant.age or 30,
            employment_type=applicant.employment_type or "employed",
            income_annual=float(applicant.income_annual or 0),
            income_verified=bool(applicant.income_verified),

            # CB API 실제 조회 결과
            cb_score=cb_result.cb_score,
            delinquency_count_12m=cb_result.delinquency_count_12m,
            worst_delinquency_status=cb_result.worst_delinquency_status,
            open_loan_count=cb_result.open_loan_count,
            total_loan_balance=cb_result.total_loan_balance,
            inquiry_count_3m=cb_result.inquiry_count_3m,

            segment_code=segment_code,
            eq_grade=eq_grade,
            irg_code=irg_code,
            irg_pd_adjustment=irg_adjustment,

            collateral_value=float(application.collateral_value or 0),
            is_regulated_area=bool(application.is_regulated_area),
            is_speculation_area=bool(application.is_speculation_area),
            owned_property_count=int(application.owned_property_count or 0),

            existing_monthly_payment=float(application.existing_loan_monthly_payment or 0),
            existing_credit_line=float(application.existing_credit_line or 0),
            existing_credit_balance=float(application.existing_credit_balance or 0),

            # 개인사업자 필드
            business_duration_months=int(applicant.business_duration_months or 0),
            revenue_annual=float(applicant.revenue_annual or 0),
            operating_income=float(applicant.operating_income or 0),
            tax_filing_count=int(applicant.tax_filing_count or 0),
        )

        # ── 4. ScoringEngine 실행 ─────────────────────────────────
        result = self._scoring_engine.score(
            inp=inp,
            dsr_limit=dsr_limit,
            stress_dsr_rate=stress_rate,
            ltv_limit=ltv_limit,
            max_rate=max_rate,
            base_rate=base_rate,
        )

        # ── 5. regulation_snapshot 저장 (감사 목적) ──────────────
        application.regulation_snapshot = {
            "effective_date": eff_date.isoformat(),
            "stress_dsr_rate": stress_rate,
            "stress_dsr_region": stress_dsr_region,
            "rate_type": rate_type,
            "dsr_limit": dsr_limit,
            "ltv_limit": ltv_limit,
            "max_rate": max_rate,
            "eq_grade": eq_grade,
            "irg_code": irg_code,
            "irg_adjustment": irg_adjustment,
            "cb_source": cb_result.source,
            "cb_score": cb_result.cb_score,
            "cb_is_fallback": cb_result.is_fallback,
        }

        return result

    async def batch_score(self, application_ids: list[str]) -> dict[str, ScoringResult]:
        """배치 스코어링 (포트폴리오 리뷰용)"""
        results = {}
        for app_id in application_ids:
            try:
                # 각 신청서 조회 및 평가
                from sqlalchemy import select
                from app.db.schemas.loan_application import LoanApplication
                from app.db.schemas.applicant import Applicant

                stmt = select(LoanApplication).where(LoanApplication.id == app_id)
                r = await self._db.execute(stmt)
                app = r.scalar_one_or_none()
                if not app:
                    continue

                stmt2 = select(Applicant).where(Applicant.id == app.applicant_id)
                r2 = await self._db.execute(stmt2)
                appl = r2.scalar_one_or_none()
                if not appl:
                    continue

                result = await self.evaluate(app, appl)
                results[app_id] = result
            except Exception as e:
                logger.error(f"배치 스코어링 실패 (app_id={app_id}): {e}")

        return results
