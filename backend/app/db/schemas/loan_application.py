"""
대출 신청 테이블 (v1.1)
상품 유형별 (신용대출/주택담보대출/소액론) 정보 저장
v1.1 추가: owned_property_count, stress_dsr, EQ/IRG 적용값, shadow 점수, 비대면 채널 정보
"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.compat import JSONB, UUID


class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False
    )

    # ── 상품 유형 (라우팅 기준) ────────────────────────────────────
    product_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="credit(신용대출) | mortgage(주택담보대출) | micro(소액론) | credit_soho(개인사업자신용)"
    )

    # ── 신청 금액 정보 ─────────────────────────────────────────────
    requested_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False, comment="신청 금액 (원)")
    requested_term_months: Mapped[int | None] = mapped_column(Integer, comment="대출 기간 (월)")
    purpose: Mapped[str | None] = mapped_column(String(100), comment="대출 목적")

    # ── 주택담보대출 전용 필드 ────────────────────────────────────
    collateral_type: Mapped[str | None] = mapped_column(String(20), comment="담보 유형: apartment/house/commercial")
    collateral_value: Mapped[float | None] = mapped_column(Numeric(15, 2), comment="담보 시세 (원)")
    collateral_address: Mapped[str | None] = mapped_column(Text, comment="담보 주소 (가명처리)")
    is_regulated_area: Mapped[bool | None] = mapped_column(comment="규제지역 여부 (조정대상지역/투기과열지구)")
    is_speculation_area: Mapped[bool | None] = mapped_column(comment="투기과열지구 여부")
    owned_property_count: Mapped[int | None] = mapped_column(
        Integer, comment="보유 주택 수 (주담대 LTV 조건 분기용)"
    )

    # ── 스트레스 DSR (금감원 행정지도, Phase 2~3) ─────────────────
    stress_dsr_region: Mapped[str | None] = mapped_column(
        String(20), comment="스트레스 DSR 지역: metropolitan(수도권) | non_metropolitan(비수도권)"
    )
    stress_dsr_rate_applied: Mapped[float | None] = mapped_column(
        Numeric(6, 4), comment="실제 적용된 스트레스 금리 (%p)"
    )
    stress_dsr_phase: Mapped[str | None] = mapped_column(
        String(10), comment="적용된 스트레스 DSR 단계: phase1/phase2/phase3"
    )

    # ── 기존 부채 현황 (DSR 계산용) ──────────────────────────────
    existing_loan_monthly_payment: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="기존 대출 월 원리금 합계 (원)"
    )
    existing_credit_line: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="기존 마이너스통장 한도 합계 (CCF 계산용)"
    )
    existing_credit_balance: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="기존 마이너스통장 잔액"
    )

    # ── EQ Grade / IRG 적용값 ─────────────────────────────────────
    eq_grade_applied: Mapped[str | None] = mapped_column(
        String(5), comment="심사 시 적용된 EQ Grade (EQ-S/A/B/C/D/E)"
    )
    eq_limit_multiplier: Mapped[float | None] = mapped_column(
        Numeric(4, 2), comment="EQ Grade 한도 배수 (예: 2.0, 1.5, 1.0)"
    )
    irg_applied: Mapped[str | None] = mapped_column(
        String(5), comment="심사 시 적용된 IRG (L/M/H/VH)"
    )
    irg_pd_adjustment: Mapped[float | None] = mapped_column(
        Numeric(6, 4), comment="IRG에 따른 PD 조정값 (예: -0.10, +0.25)"
    )

    # ── 세그먼트 적용 정보 ────────────────────────────────────────
    segment_code_applied: Mapped[str | None] = mapped_column(
        String(30), comment="심사 시 적용된 특수 세그먼트 코드"
    )
    segment_benefit_json: Mapped[dict | None] = mapped_column(
        JSONB, comment="적용된 세그먼트 혜택 (한도배수, 금리우대 등)"
    )

    # ── Shadow 챌린저 모델 결과 ───────────────────────────────────
    shadow_challenger_score: Mapped[int | None] = mapped_column(
        Integer, comment="Shadow 모델 점수 (금소법 §19, 내부 분석용)"
    )
    shadow_challenger_decision: Mapped[str | None] = mapped_column(
        String(20), comment="Shadow 모델 의사결정 (내부 분석용)"
    )
    shadow_model_version: Mapped[str | None] = mapped_column(
        String(30), comment="Shadow 모델 버전"
    )

    # ── 비대면 디지털 신청 여정 ───────────────────────────────────
    channel_type: Mapped[str] = mapped_column(
        String(20), default="digital",
        comment="신청 채널: digital(비대면) | branch(영업점) | phone(전화)"
    )
    digital_channel: Mapped[str | None] = mapped_column(
        String(30), comment="디지털 채널: kakao/naver/bank_app/web"
    )
    session_id: Mapped[str | None] = mapped_column(
        String(64), comment="비대면 신청 세션 ID"
    )
    application_step: Mapped[str | None] = mapped_column(
        String(30),
        comment="신청 단계: identity_verify/consent/basic_info/financial_info/product_select/review/submit"
    )
    ocr_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="신분증 OCR 검증 완료 여부"
    )
    esign_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="전자서명 완료 여부"
    )

    # ── 심사 상태 ─────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending | under_review | approved | rejected | cancelled"
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(100), comment="수동 심사관 ID")
    reviewer_note: Mapped[str | None] = mapped_column(Text, comment="심사관 메모")
    auto_decision: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="자동 심사 여부 (True=자동, False=수동)"
    )

    # ── BRMS 정책 스냅샷 ──────────────────────────────────────────
    regulation_snapshot: Mapped[dict | None] = mapped_column(
        JSONB, comment="심사 시점 규제 파라미터 스냅샷 (감사 목적)"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ── ORM 관계 ─────────────────────────────────────────────────────
    applicant: Mapped["Applicant"] = relationship(  # noqa: F821
        "Applicant",
        back_populates="loan_applications",
        lazy="select",
    )
    credit_scores: Mapped[list["CreditScore"]] = relationship(  # noqa: F821
        "CreditScore",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="CreditScore.scored_at.desc()",
        lazy="select",
    )
