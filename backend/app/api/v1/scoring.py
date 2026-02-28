"""
신용평가 API (직접 평가 엔드포인트)
======================================
내부 심사 시스템 연동용 (Batch 평가, Shadow 모드)
"""
import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scoring_engine import ScoringEngine, ScoringInput
from app.db.session import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


class DirectScoreRequest(BaseModel):
    """직접 평가 요청 (내부 시스템용)"""
    product_type: str = Field(..., description="credit | mortgage | micro | credit_soho")
    requested_amount: float = Field(..., gt=0)
    requested_term_months: int = Field(36, ge=1, le=360)

    applicant_type: str = Field("individual")
    age: int = Field(..., ge=19, le=80)
    employment_type: str = Field("employed")
    income_annual: float = Field(..., gt=0)
    income_verified: bool = Field(False)

    cb_score: int = Field(..., ge=300, le=1000)
    delinquency_count_12m: int = Field(0, ge=0)
    worst_delinquency_status: int = Field(0, ge=0, le=3)
    open_loan_count: int = Field(0, ge=0)
    total_loan_balance: float = Field(0.0, ge=0)
    inquiry_count_3m: int = Field(0, ge=0)

    segment_code: str = Field("")
    eq_grade: str = Field("EQ-C")
    irg_code: str = Field("M")

    existing_monthly_payment: float = Field(0.0, ge=0)
    collateral_value: float = Field(0.0, ge=0)
    is_regulated_area: bool = Field(False)
    is_speculation_area: bool = Field(False)
    owned_property_count: int = Field(0, ge=0)

    telecom_no_delinquency: int = Field(1, ge=0, le=1)
    health_insurance_paid_months_12m: int = Field(12, ge=0, le=12)

    # Shadow 모드 여부
    shadow_mode: bool = Field(False, description="True면 결과 저장 안 함 (내부 분석용)")


@router.post("/evaluate")
async def direct_evaluate(
    request: DirectScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    직접 신용평가 (내부 시스템/데모용).
    shadow_mode=True이면 결과를 DB에 저장하지 않음.
    """

    # ScoringInput 조립
    inp = ScoringInput(
        application_id=str(uuid.uuid4()),
        product_type=request.product_type,
        requested_amount=request.requested_amount,
        requested_term_months=request.requested_term_months,
        applicant_type=request.applicant_type,
        age=request.age,
        employment_type=request.employment_type,
        income_annual=request.income_annual,
        income_verified=request.income_verified,
        cb_score=request.cb_score,
        delinquency_count_12m=request.delinquency_count_12m,
        worst_delinquency_status=request.worst_delinquency_status,
        open_loan_count=request.open_loan_count,
        total_loan_balance=request.total_loan_balance,
        inquiry_count_3m=request.inquiry_count_3m,
        segment_code=request.segment_code,
        eq_grade=request.eq_grade,
        irg_code=request.irg_code,
        existing_monthly_payment=request.existing_monthly_payment,
        collateral_value=request.collateral_value,
        is_regulated_area=request.is_regulated_area,
        is_speculation_area=request.is_speculation_area,
        owned_property_count=request.owned_property_count,
        telecom_no_delinquency=request.telecom_no_delinquency,
        health_insurance_paid_months_12m=request.health_insurance_paid_months_12m,
    )

    # PolicyEngine에서 파라미터 조회
    from datetime import datetime

    from app.config import settings
    from app.core.policy_engine import PolicyEngine

    pe = PolicyEngine(db)
    eff = datetime.utcnow()

    dsr_limit = await pe.get_dsr_limit(request.product_type, eff)
    ltv_limit = await pe.get_ltv_limit(
        "speculation_area" if request.is_speculation_area else
        "regulated" if request.is_regulated_area else "general",
        request.owned_property_count, eff
    )
    max_rate = await pe.get_max_interest_rate(eff)
    irg_adj = await pe.get_irg_pd_adjustment(request.irg_code, eff)
    inp.irg_pd_adjustment = irg_adj

    engine = ScoringEngine(artifacts_path=settings.MODEL_ARTIFACTS_PATH)
    result = engine.score(
        inp=inp,
        dsr_limit=dsr_limit,
        ltv_limit=ltv_limit,
        max_rate=max_rate,
        base_rate=settings.BASE_RATE,
    )

    response = {
        "score": result.score,
        "grade": result.grade,
        "pd_estimate": result.pd_estimate,
        "lgd_estimate": result.lgd_estimate,
        "ead_estimate": result.ead_estimate,
        "economic_capital": result.economic_capital,
        "decision": result.decision,
        "approved_amount": result.approved_amount,
        "rate_breakdown": result.rate_breakdown.to_dict(),
        "dsr_ratio": result.dsr_ratio,
        "stress_dsr_ratio": result.stress_dsr_ratio,
        "ltv_ratio": result.ltv_ratio,
        "dsr_limit_breached": result.dsr_limit_breached,
        "ltv_limit_breached": result.ltv_limit_breached,
        "rejection_reasons": result.rejection_reasons,
        "top_positive_factors": result.top_positive_factors,
        "top_negative_factors": result.top_negative_factors,
        "model_version": result.model_version,
        "shadow_mode": request.shadow_mode,
    }

    if not request.shadow_mode:
        logger.info(f"평가 완료: score={result.score}, decision={result.decision}")

    return response


@router.get("/score-scale")
async def get_score_scale():
    """신용점수 스케일 정보 조회"""
    from app.core.scoring_engine import BASE_PD, GRADE_PD_MAP, SCORE_BASE, SCORE_PDO
    return {
        "scale": {"min": 300, "max": 900, "base": SCORE_BASE, "pdo": SCORE_PDO, "base_pd": BASE_PD},
        "grade_ranges": {
            grade: {"pd": pd, "score_range": f"{lower}~{upper}"}
            for grade, (pd, upper, lower) in GRADE_PD_MAP.items()
        },
        "cutoffs": {
            "auto_reject_below": 450,
            "manual_review_below": 530,
            "auto_approve_above": 530,
        },
    }
