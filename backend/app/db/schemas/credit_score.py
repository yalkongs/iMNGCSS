"""
신용평가 결과 테이블 (v1.1)
금융소비자보호법: 거절 사유 고지 의무 → rejection_reason JSONB
바젤III IRB: PD/LGD/EAD + RW + RAROC 저장
v1.1 추가: RAROC 금리 분해, 칼리브레이션 메타, EAD/CCF 구분
"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.compat import JSONB, UUID


class CreditScore(Base):
    __tablename__ = "credit_scores"

    __table_args__ = (
        CheckConstraint("score BETWEEN 300 AND 900", name="chk_score_range"),
        CheckConstraint("pd_estimate BETWEEN 0 AND 1", name="chk_pd_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id"), nullable=False
    )

    # ── 평가 점수 및 등급 ─────────────────────────────────────────
    score: Mapped[int] = mapped_column(Integer, nullable=False, comment="신용점수 300~900 (스케일링 기준점600/PDO40)")
    grade: Mapped[str] = mapped_column(
        String(5), nullable=False,
        comment="신용등급: AAA/AA/A/BBB/BB/B/CCC/CC/C/D"
    )
    scorecard_type: Mapped[str | None] = mapped_column(
        String(30), comment="application/behavioral/collection"
    )
    model_version: Mapped[str | None] = mapped_column(String(30), comment="사용된 모델 버전")

    # ── 바젤III IRB 리스크 파라미터 ──────────────────────────────
    pd_estimate: Mapped[float | None] = mapped_column(Numeric(8, 6), comment="부도확률 (PD)")
    lgd_estimate: Mapped[float | None] = mapped_column(Numeric(8, 6), comment="부도손실률 (LGD)")
    ead_estimate: Mapped[float | None] = mapped_column(Numeric(15, 2), comment="부도시 익스포져 (EAD)")
    ccf_applied: Mapped[float | None] = mapped_column(
        Numeric(6, 4), comment="CCF 적용값 (회전한도: ML모델 or 기본50%)"
    )
    risk_weight: Mapped[float | None] = mapped_column(
        Numeric(6, 4), comment="위험가중치 RW (무담보=0.75, 주담대=0.35)"
    )
    economic_capital: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="경제자본 = EAD×RW×8%"
    )

    # ── RAROC 기반 금리 분해 ──────────────────────────────────────
    rate_breakdown: Mapped[dict | None] = mapped_column(
        JSONB,
        comment=(
            "금리 분해표 JSONB: "
            "base_rate, credit_spread, funding_cost, operating_cost, "
            "eq_adjustment, relationship_discount, final_rate, raroc_at_final"
        )
    )
    hurdle_rate_satisfied: Mapped[bool | None] = mapped_column(
        Boolean, comment="허들금리(RAROC≥15%) 충족 여부"
    )

    # ── 승인 결과 ─────────────────────────────────────────────────
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="approved | rejected | manual_review"
    )
    approved_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), comment="승인 금액 (원)")
    approved_rate: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="최종 적용 금리 (%)")
    approved_term_months: Mapped[int | None] = mapped_column(Integer, comment="승인 기간 (월)")

    # ── 규제 비율 (은행업 감독규정) ──────────────────────────────
    dsr_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="DSR 비율 (%)")
    stress_dsr_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="스트레스DSR 비율 (%)")
    ltv_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="LTV 비율 % (주담대)")
    dti_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="DTI 비율 % (주담대)")
    dsr_limit_breached: Mapped[bool | None] = mapped_column(Boolean, comment="DSR 한도 초과 여부")
    ltv_limit_breached: Mapped[bool | None] = mapped_column(Boolean, comment="LTV 한도 초과 여부")

    # ── 설명가능성 (금융소비자보호법 §19, 신용정보법 §39의5) ────────
    rejection_reason: Mapped[dict | None] = mapped_column(
        JSONB, comment="거절 사유 목록 (한국어 3가지, 이의제기 고지 포함)"
    )
    shap_values: Mapped[dict | None] = mapped_column(JSONB, comment="SHAP 피처 기여도")
    top_positive_factors: Mapped[dict | None] = mapped_column(JSONB, comment="점수 상승 요인 3개 (한국어)")
    top_negative_factors: Mapped[dict | None] = mapped_column(JSONB, comment="점수 하락 요인 3개 (한국어)")
    appeal_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="이의제기 기한 (scored_at + 30일)"
    )

    # ── 칼리브레이션 메타 (FR-MON-005) ──────────────────────────
    calibration_bin: Mapped[int | None] = mapped_column(
        Integer, comment="ECE 계산용 확률 구간 번호 (1~10)"
    )
    raw_probability: Mapped[float | None] = mapped_column(
        Numeric(8, 6), comment="모델 출력 원시 확률 (ECE/Brier 계산용)"
    )

    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # ── ORM 관계 ─────────────────────────────────────────────────────
    application: Mapped["LoanApplication"] = relationship(  # noqa: F821
        "LoanApplication",
        back_populates="credit_scores",
        lazy="select",
    )
