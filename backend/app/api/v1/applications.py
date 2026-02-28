"""
대출 신청 API (비대면 디지털 여정)
====================================
비대면 신청 흐름:
  1. POST /start          - 신청 세션 시작 (채널 식별)
  2. POST /{id}/consent   - CB 조회 동의 (신용정보법 §32)
  3. POST /{id}/applicant - 신청인 기본정보 입력
  4. POST /{id}/financial - 재무 정보 입력 (외부 API 조회)
  5. POST /{id}/product   - 상품/한도 선택
  6. POST /{id}/submit    - 최종 제출 → 자동 심사 실행
  7. GET  /{id}/result    - 심사 결과 조회
  8. POST /{id}/appeal    - 거절 이의제기 (신용정보법 §39의5)
"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.scoring_service import ScoringService

router = APIRouter()
logger = logging.getLogger(__name__)


# ── 요청/응답 모델 ──────────────────────────────────────────────

class ApplicationStartRequest(BaseModel):
    digital_channel: str = Field(
        ..., description="유입 채널: bank_app | kakao | naver | web"
    )
    product_type: str = Field(
        ..., description="상품 유형: credit | mortgage | micro | credit_soho"
    )

class ApplicationStartResponse(BaseModel):
    application_id: str
    session_id: str
    next_step: str = "consent"
    message: str = "CB 조회 동의 단계로 진행하세요."


class ConsentRequest(BaseModel):
    cb_consent: bool = Field(..., description="신용정보 조회 동의")
    alt_data_consent: bool = Field(False, description="대안데이터 활용 동의")
    mydata_consent: bool = Field(False, description="마이데이터 연동 동의")


class ApplicantInfoRequest(BaseModel):
    # 개인정보 (가명처리)
    resident_registration_hash: str = Field(
        ..., description="주민번호 HMAC-SHA256 해시 (클라이언트에서 처리)"
    )
    name_masked: str | None = Field(None, description="가명처리된 성명 (예: 홍*동)")

    # 인구통계
    age: int = Field(..., ge=19, le=80, description="나이")
    applicant_type: str = Field("individual", description="individual | self_employed")
    employment_type: str = Field(..., description="employed | self_employed | retired | student | unemployed")
    income_annual: float = Field(..., gt=0, description="연간 소득 (원)")

    # 특수 직역 (선택)
    occupation_code: str | None = Field(None, description="직종 코드 (예: MD001, JD001)")
    license_number: str | None = Field(None, description="면허 번호 (의사/변호사)")

    # 개인사업자 전용 (선택)
    business_registration_hash: str | None = None
    business_type: str | None = None
    business_duration_months: int | None = None


class FinancialInfoRequest(BaseModel):
    existing_loan_monthly_payment: float = Field(0.0, description="기존 대출 월 원리금 (원)")
    existing_credit_line: float = Field(0.0, description="마이너스통장 한도 합계 (원)")
    existing_credit_balance: float = Field(0.0, description="마이너스통장 잔액 (원)")

    # 주담대 전용
    collateral_value: float | None = Field(None, description="담보 시세 (원)")
    collateral_address: str | None = Field(None, description="담보 주소")
    is_regulated_area: bool = Field(False, description="조정대상지역 여부")
    is_speculation_area: bool = Field(False, description="투기과열지구 여부")
    owned_property_count: int = Field(0, description="보유 주택 수")


class ProductSelectRequest(BaseModel):
    requested_amount: float = Field(..., gt=0, description="신청 금액 (원)")
    requested_term_months: int = Field(..., ge=1, le=360, description="대출 기간 (월)")
    purpose: str | None = Field(None, description="대출 목적")


class SubmitRequest(BaseModel):
    esign_token: str = Field(..., description="전자서명 토큰")
    final_confirm: bool = Field(True, description="최종 확인")

    # 스트레스 DSR용 금리 유형
    rate_type: str = Field("variable", description="금리 유형: variable | mixed_short | mixed_long | fixed")
    stress_dsr_region: str = Field("metropolitan", description="스트레스 DSR 지역: metropolitan | non_metropolitan")


class ApplicationResultResponse(BaseModel):
    application_id: str
    status: str
    decision: str | None
    score: int | None
    grade: str | None
    approved_amount: float | None
    approved_rate: float | None
    rate_breakdown: dict | None
    dsr_ratio: float | None
    ltv_ratio: float | None
    rejection_reasons: list[str] | None
    top_positive_factors: list[dict] | None
    top_negative_factors: list[dict] | None
    appeal_deadline: str | None
    scored_at: str | None


class AppealRequest(BaseModel):
    appeal_reason: str = Field(..., description="이의제기 사유")
    supporting_documents: list[str] = Field(
        default_factory=list,
        description="첨부 서류 목록 (파일명)"
    )


# ── 핸들러 ───────────────────────────────────────────────────────

@router.post("/start", response_model=ApplicationStartResponse)
async def start_application(
    request: ApplicationStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    비대면 대출 신청 세션 시작.
    채널 식별 및 신청 ID 발급.
    """
    application_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    # DB에 pending 상태로 저장
    from app.db.schemas.loan_application import LoanApplication
    app_record = LoanApplication(
        id=uuid.UUID(application_id),
        applicant_id=uuid.uuid4(),  # 임시 (consent 단계에서 신청인 생성)
        product_type=request.product_type,
        requested_amount=0,         # 상품 선택 단계에서 입력
        channel_type="digital",
        digital_channel=request.digital_channel,
        session_id=session_id,
        application_step="consent",
        status="pending",
    )
    db.add(app_record)
    await db.commit()

    logger.info(f"신청 세션 시작: app_id={application_id}, channel={request.digital_channel}")

    return ApplicationStartResponse(
        application_id=application_id,
        session_id=session_id,
        next_step="consent",
        message="신용정보 조회 동의 단계로 진행하세요.",
    )


@router.post("/{application_id}/consent")
async def submit_consent(
    application_id: str,
    request: ConsentRequest,
    db: AsyncSession = Depends(get_db),
):
    """CB 조회 동의 제출 (신용정보법 §32)"""
    if not request.cb_consent:
        raise HTTPException(
            status_code=400,
            detail="신용정보 조회 동의가 필요합니다. (신용정보법 §32)"
        )

    from sqlalchemy import select
    from app.db.schemas.loan_application import LoanApplication
    stmt = select(LoanApplication).where(LoanApplication.id == uuid.UUID(application_id))
    result = await db.execute(stmt)
    app_record = result.scalar_one_or_none()

    if not app_record:
        raise HTTPException(status_code=404, detail="신청 정보를 찾을 수 없습니다.")

    app_record.application_step = "applicant_info"
    await db.commit()

    return {
        "application_id": application_id,
        "consent_recorded": True,
        "next_step": "applicant_info",
        "message": "동의가 완료되었습니다. 신청인 정보를 입력하세요.",
    }


@router.post("/{application_id}/applicant")
async def submit_applicant_info(
    application_id: str,
    request: ApplicantInfoRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    신청인 기본 정보 입력.
    특수 직역 자격 검증 (외부 API 호출 - Mock Server).
    """
    from sqlalchemy import select
    from app.db.schemas.applicant import Applicant
    from app.db.schemas.loan_application import LoanApplication

    # 기존 신청인 조회 (주민번호 해시 기준)
    stmt = select(Applicant).where(
        Applicant.resident_registration_hash == request.resident_registration_hash
    )
    result = await db.execute(stmt)
    applicant = result.scalar_one_or_none()

    if not applicant:
        # 신규 신청인 생성
        applicant = Applicant(
            id=uuid.uuid4(),
            resident_registration_hash=request.resident_registration_hash,
            name_masked=request.name_masked,
            age=request.age,
            age_band=_get_age_band(request.age),
            applicant_type=request.applicant_type,
            employment_type=request.employment_type,
            income_annual=request.income_annual,
            occupation_code=request.occupation_code,
            cb_consent_granted=True,
            cb_consent_date=datetime.utcnow(),
        )
        db.add(applicant)

    # 특수 세그먼트 자격 검증 (면허번호 있으면 외부 API 호출)
    segment_code = ""
    if request.occupation_code and request.license_number:
        segment_code = await _verify_segment(
            request.occupation_code, request.license_number, request.resident_registration_hash
        )
        applicant.segment_code = segment_code
        applicant.segment_verified = bool(segment_code)
        applicant.segment_verified_at = datetime.utcnow() if segment_code else None

    # 청년 세그먼트 자동 배정
    if not segment_code and 19 <= request.age <= 34:
        segment_code = "SEG-YTH"
        applicant.segment_code = segment_code

    # 신청서에 신청인 연결
    stmt2 = select(LoanApplication).where(LoanApplication.id == uuid.UUID(application_id))
    r2 = await db.execute(stmt2)
    app_record = r2.scalar_one_or_none()
    if app_record:
        app_record.applicant_id = applicant.id
        app_record.application_step = "financial_info"
        app_record.segment_code_applied = segment_code

    await db.commit()

    return {
        "application_id": application_id,
        "applicant_id": str(applicant.id),
        "segment_code": segment_code or None,
        "next_step": "financial_info",
        "message": "재무 정보를 입력하세요.",
    }


@router.post("/{application_id}/financial")
async def submit_financial_info(
    application_id: str,
    request: FinancialInfoRequest,
    db: AsyncSession = Depends(get_db),
):
    """재무 정보 입력 (기존 부채, 주담대 담보 정보)"""
    from sqlalchemy import select
    from app.db.schemas.loan_application import LoanApplication

    stmt = select(LoanApplication).where(LoanApplication.id == uuid.UUID(application_id))
    result = await db.execute(stmt)
    app_record = result.scalar_one_or_none()

    if not app_record:
        raise HTTPException(status_code=404, detail="신청 정보를 찾을 수 없습니다.")

    app_record.existing_loan_monthly_payment = request.existing_loan_monthly_payment
    app_record.existing_credit_line = request.existing_credit_line
    app_record.existing_credit_balance = request.existing_credit_balance
    app_record.collateral_value = request.collateral_value
    app_record.collateral_address = request.collateral_address
    app_record.is_regulated_area = request.is_regulated_area
    app_record.is_speculation_area = request.is_speculation_area
    app_record.owned_property_count = request.owned_property_count
    app_record.application_step = "product_select"

    await db.commit()

    return {
        "application_id": application_id,
        "next_step": "product_select",
        "message": "상품 및 희망 한도를 선택하세요.",
    }


@router.post("/{application_id}/product")
async def submit_product_selection(
    application_id: str,
    request: ProductSelectRequest,
    db: AsyncSession = Depends(get_db),
):
    """상품/한도/기간 선택"""
    from sqlalchemy import select
    from app.db.schemas.loan_application import LoanApplication

    stmt = select(LoanApplication).where(LoanApplication.id == uuid.UUID(application_id))
    result = await db.execute(stmt)
    app_record = result.scalar_one_or_none()

    if not app_record:
        raise HTTPException(status_code=404, detail="신청 정보를 찾을 수 없습니다.")

    app_record.requested_amount = request.requested_amount
    app_record.requested_term_months = request.requested_term_months
    app_record.purpose = request.purpose
    app_record.application_step = "review"

    await db.commit()

    return {
        "application_id": application_id,
        "next_step": "submit",
        "message": "신청 내용을 확인하고 최종 제출하세요.",
        "summary": {
            "product_type": app_record.product_type,
            "requested_amount": request.requested_amount,
            "requested_term_months": request.requested_term_months,
        },
    }


@router.post("/{application_id}/submit")
async def submit_application(
    application_id: str,
    request: SubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    최종 제출 → 자동 신용평가 실행.
    전자서명 검증 후 BRMS + ScoringEngine 실행.
    """
    if not request.final_confirm:
        raise HTTPException(status_code=400, detail="최종 확인이 필요합니다.")

    from sqlalchemy import select
    from app.db.schemas.loan_application import LoanApplication
    from app.db.schemas.applicant import Applicant
    from app.db.schemas.credit_score import CreditScore

    # 신청서 조회
    stmt = select(LoanApplication).where(LoanApplication.id == uuid.UUID(application_id))
    result = await db.execute(stmt)
    app_record = result.scalar_one_or_none()
    if not app_record:
        raise HTTPException(status_code=404, detail="신청 정보를 찾을 수 없습니다.")

    # 신청인 조회
    stmt2 = select(Applicant).where(Applicant.id == app_record.applicant_id)
    r2 = await db.execute(stmt2)
    applicant = r2.scalar_one_or_none()
    if not applicant:
        raise HTTPException(status_code=400, detail="신청인 정보가 없습니다. 신청인 정보를 먼저 입력하세요.")

    # 전자서명 완료 처리 (Mock: 토큰 유효성 체크)
    if not request.esign_token or len(request.esign_token) < 10:
        raise HTTPException(status_code=400, detail="전자서명이 유효하지 않습니다.")
    app_record.esign_completed = True
    app_record.application_step = "submit"
    app_record.status = "under_review"

    # 스트레스 DSR 지역 정보 저장
    app_record.stress_dsr_region = request.stress_dsr_region

    # ── 자동 신용평가 실행 ────────────────────────────────────────
    service = ScoringService(db)
    scoring_result = await service.evaluate(
        application=app_record,
        applicant=applicant,
        rate_type=request.rate_type,
        stress_dsr_region=request.stress_dsr_region,
    )

    # 결과 저장
    credit_score_record = CreditScore(
        id=uuid.uuid4(),
        application_id=app_record.id,
        score=scoring_result.score,
        grade=scoring_result.grade,
        pd_estimate=scoring_result.pd_estimate,
        lgd_estimate=scoring_result.lgd_estimate,
        ead_estimate=scoring_result.ead_estimate,
        risk_weight=scoring_result.risk_weight,
        economic_capital=scoring_result.economic_capital,
        decision=scoring_result.decision,
        approved_amount=scoring_result.approved_amount,
        approved_rate=scoring_result.rate_breakdown.final_rate,
        approved_term_months=scoring_result.approved_term_months,
        rate_breakdown=scoring_result.rate_breakdown.to_dict(),
        hurdle_rate_satisfied=scoring_result.rate_breakdown.hurdle_rate_satisfied,
        dsr_ratio=scoring_result.dsr_ratio,
        stress_dsr_ratio=scoring_result.stress_dsr_ratio,
        ltv_ratio=scoring_result.ltv_ratio,
        dsr_limit_breached=scoring_result.dsr_limit_breached,
        ltv_limit_breached=scoring_result.ltv_limit_breached,
        rejection_reason={"reasons": scoring_result.rejection_reasons},
        top_positive_factors={"factors": scoring_result.top_positive_factors},
        top_negative_factors={"factors": scoring_result.top_negative_factors},
        appeal_deadline=scoring_result.appeal_deadline,
        raw_probability=scoring_result.raw_probability,
        model_version=scoring_result.model_version,
        scorecard_type=scoring_result.scorecard_type,
    )
    db.add(credit_score_record)

    # 신청서 상태 업데이트
    app_record.status = scoring_result.decision
    app_record.auto_decision = True
    app_record.stress_dsr_rate_applied = scoring_result.stress_dsr_ratio - scoring_result.dsr_ratio
    app_record.eq_grade_applied = applicant.employer_eq_grade or "EQ-C"
    app_record.segment_code_applied = applicant.segment_code or ""

    await db.commit()

    logger.info(
        f"심사 완료: app_id={application_id}, "
        f"decision={scoring_result.decision}, "
        f"score={scoring_result.score}, "
        f"grade={scoring_result.grade}"
    )

    return {
        "application_id": application_id,
        "decision": scoring_result.decision,
        "score": scoring_result.score,
        "grade": scoring_result.grade,
        "approved_amount": scoring_result.approved_amount,
        "approved_rate": scoring_result.rate_breakdown.final_rate,
        "message": _decision_message(scoring_result.decision),
    }


@router.get("/{application_id}/result", response_model=ApplicationResultResponse)
async def get_result(
    application_id: str,
    db: AsyncSession = Depends(get_db),
):
    """심사 결과 상세 조회"""
    from sqlalchemy import select
    from app.db.schemas.credit_score import CreditScore

    stmt = select(CreditScore).where(
        CreditScore.application_id == uuid.UUID(application_id)
    ).order_by(CreditScore.scored_at.desc()).limit(1)
    result = await db.execute(stmt)
    cs = result.scalar_one_or_none()

    if not cs:
        raise HTTPException(status_code=404, detail="심사 결과를 찾을 수 없습니다.")

    return ApplicationResultResponse(
        application_id=application_id,
        status="completed",
        decision=cs.decision,
        score=cs.score,
        grade=cs.grade,
        approved_amount=cs.approved_amount,
        approved_rate=float(cs.approved_rate) if cs.approved_rate else None,
        rate_breakdown=cs.rate_breakdown,
        dsr_ratio=float(cs.dsr_ratio) if cs.dsr_ratio else None,
        ltv_ratio=float(cs.ltv_ratio) if cs.ltv_ratio else None,
        rejection_reasons=cs.rejection_reason.get("reasons") if cs.rejection_reason else None,
        top_positive_factors=cs.top_positive_factors.get("factors") if cs.top_positive_factors else None,
        top_negative_factors=cs.top_negative_factors.get("factors") if cs.top_negative_factors else None,
        appeal_deadline=cs.appeal_deadline.isoformat() if cs.appeal_deadline else None,
        scored_at=cs.scored_at.isoformat() if cs.scored_at else None,
    )


@router.post("/{application_id}/appeal")
async def submit_appeal(
    application_id: str,
    request: AppealRequest,
    db: AsyncSession = Depends(get_db),
):
    """이의제기 제출 (신용정보법 §39의5)"""
    from sqlalchemy import select
    from app.db.schemas.credit_score import CreditScore
    from datetime import datetime as dt

    stmt = select(CreditScore).where(
        CreditScore.application_id == uuid.UUID(application_id)
    ).order_by(CreditScore.scored_at.desc()).limit(1)
    result = await db.execute(stmt)
    cs = result.scalar_one_or_none()

    if not cs:
        raise HTTPException(status_code=404, detail="심사 결과를 찾을 수 없습니다.")

    if cs.decision != "rejected":
        raise HTTPException(status_code=400, detail="거절된 신청에 대해서만 이의제기가 가능합니다.")

    if cs.appeal_deadline and dt.utcnow() > cs.appeal_deadline:
        raise HTTPException(status_code=400, detail="이의제기 기한(30일)이 지났습니다.")

    # 이의제기 접수 처리 (감사 로그 기록 - 실제 환경에서 Kafka 발행)
    appeal_id = str(uuid.uuid4())
    logger.info(
        f"이의제기 접수: app_id={application_id}, "
        f"appeal_id={appeal_id}, reason={request.appeal_reason[:50]}"
    )

    return {
        "appeal_id": appeal_id,
        "application_id": application_id,
        "status": "received",
        "message": "이의제기가 접수되었습니다. 영업일 기준 7일 이내 검토 결과를 통보드립니다.",
        "review_deadline": (dt.utcnow().date().isoformat()),
    }


# ── 유틸리티 ─────────────────────────────────────────────────────

def _get_age_band(age: int) -> str:
    if age < 30: return "20s"
    if age < 40: return "30s"
    if age < 50: return "40s"
    if age < 60: return "50s"
    return "60+"


def _decision_message(decision: str) -> str:
    messages = {
        "approved":      "대출 승인이 완료되었습니다.",
        "rejected":      "심사 결과 거절되었습니다. 결과 조회에서 상세 사유를 확인하세요.",
        "manual_review": "추가 심사가 필요합니다. 영업일 기준 3일 이내 연락드립니다.",
    }
    return messages.get(decision, "심사가 완료되었습니다.")


async def _verify_segment(
    occupation_code: str, license_number: str, resident_hash: str
) -> str:
    """외부 API(Mock Server)에서 전문직 면허 검증 후 세그먼트 코드 반환"""
    import httpx
    import os

    mock_url = os.getenv("MOCK_SERVER_URL", "http://mock-server:8001")
    api_key = os.getenv("MOCK_API_KEY", "kcs-mock-api-key-dev")

    occ_to_type = {
        "MD001": "doctor", "MD002": "dentist", "MD003": "oriental_medicine",
        "JD001": "lawyer", "JD002": "legal_scrivener", "JD003": "cpa",
        "ART001": "artist",
    }
    license_type = occ_to_type.get(occupation_code)
    if not license_type:
        return ""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{mock_url}/api/profession/license",
                json={
                    "resident_hash": resident_hash,
                    "license_type": license_type,
                    "license_number": license_number,
                },
                headers={"X-API-Key": api_key},
            )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("segment_code") or ""
    except Exception as e:
        logger.warning(f"전문직 면허 검증 API 호출 실패: {e}")

    return ""
