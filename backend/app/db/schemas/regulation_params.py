"""
규제 파라미터 테이블 (BRMS - ADR-001)
금감원/금융위 기준 규제값을 코드가 아닌 DB에서 관리.
effective_from/effective_to로 버전 이력 관리 (은행업감독규정 개정 대응).

핵심 원칙:
- 규제값 변경 시 코드 배포 없이 파라미터만 업데이트
- 모든 변경은 audit 추적
- Redis 캐시 (TTL 5분) + PostgreSQL JSONB
"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.compat import JSONB, UUID


class RegulationParam(Base):
    __tablename__ = "regulation_params"

    __table_args__ = (
        # 동일 파라미터 + 동일 기간 중복 방지
        UniqueConstraint("param_key", "effective_from", name="uq_param_key_effective_from"),
        # 조회 성능 최적화
        Index("idx_regulation_params_key_active", "param_key", "is_active"),
        Index("idx_regulation_params_category", "param_category"),
        Index("idx_regulation_params_effective", "effective_from", "effective_to"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── 파라미터 식별 ─────────────────────────────────────────────
    param_key: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment=(
            "파라미터 고유 키. 예:"
            " stress_dsr.metropolitan.variable.phase3"
            " | ltv.speculation_area"
            " | dsr.max_ratio"
            " | eq_grade.multiplier.EQ-S"
            " | irg.pd_adjustment.VH"
        )
    )
    param_category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="카테고리: dsr | ltv | dti | rate | limit | eq_grade | irg | segment | ccf"
    )
    phase_label: Mapped[str | None] = mapped_column(
        String(20), comment="정책 단계: phase1 | phase2 | phase3 (스트레스 DSR 등)"
    )

    # ── 파라미터 값 (JSONB - 복잡한 조건부 구조 지원) ──────────────
    param_value: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment=(
            "파라미터 값 JSONB. 예:"
            ' {"rate": 0.75, "unit": "percentage_point"}'
            ' {"max_ratio": 40.0, "unit": "percent"}'
            ' {"multiplier": 2.0, "rate_adjustment": -0.3}'
        )
    )

    # ── 적용 조건 (조건부 규제 지원) ─────────────────────────────
    condition_json: Mapped[dict | None] = mapped_column(
        JSONB,
        comment=(
            "적용 조건 JSONB. 예:"
            ' {"region": "metropolitan", "rate_type": "variable"}'
            ' {"product_type": "mortgage", "owned_count": ">1"}'
            ' {"segment": "SEG-DR"}'
        )
    )

    # ── 유효 기간 (버전 이력 관리) ───────────────────────────────
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="시행일 (예: 2024-02-01 for 스트레스DSR Phase2)"
    )
    effective_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="종료일 (null = 현재 유효)"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="현재 활성화 여부"
    )

    # ── 법령/근거 ─────────────────────────────────────────────────
    legal_basis: Mapped[str | None] = mapped_column(
        String(200), comment="법령 근거 (예: 은행업감독규정 §35의5, 대부업법 §11)"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="파라미터 설명")

    # ── 변경 관리 (감사 추적) ────────────────────────────────────
    created_by: Mapped[str | None] = mapped_column(String(50), comment="등록자 ID")
    approved_by: Mapped[str | None] = mapped_column(String(50), comment="승인자 ID (4-eyes 원칙)")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str | None] = mapped_column(Text, comment="변경 사유")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class EqGradeMaster(Base):
    """
    EQ Grade 마스터 테이블 (기업 신용도 등급)
    직장/회사별 EQ Grade → 한도 배수 및 금리 우대
    """
    __tablename__ = "eq_grade_master"

    __table_args__ = (
        Index("idx_eq_grade_employer", "employer_registration_no"),
        Index("idx_eq_grade_mou_code", "mou_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    employer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="기업명")
    employer_registration_no: Mapped[str | None] = mapped_column(
        String(20), comment="사업자등록번호 해시"
    )
    eq_grade: Mapped[str] = mapped_column(
        String(5), nullable=False,
        comment="EQ-S(2.0x) | EQ-A(1.8x) | EQ-B(1.5x) | EQ-C(1.2x) | EQ-D(1.0x) | EQ-E(0.7x)"
    )

    # ── EQ Grade 혜택 ────────────────────────────────────────────
    limit_multiplier: Mapped[float] = mapped_column(
        comment="한도 배수 (EQ-S=2.0, EQ-A=1.8, EQ-B=1.5, EQ-C=1.2, EQ-D=1.0, EQ-E=0.7)"
    )
    rate_adjustment: Mapped[float] = mapped_column(
        comment="금리 조정 (%p, EQ-S=-0.5, EQ-A=-0.3, EQ-B=-0.2, EQ-C=0, EQ-D=+0.2, EQ-E=+0.5)"
    )

    # ── MOU 협약 정보 ────────────────────────────────────────────
    mou_code: Mapped[str | None] = mapped_column(
        String(20), comment="MOU 협약 코드 (SEG-MOU-{code})"
    )
    mou_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mou_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mou_special_rate: Mapped[float | None] = mapped_column(
        comment="MOU 특별 금리 (%p 우대)"
    )

    # ── 관리 정보 ────────────────────────────────────────────────
    grade_source: Mapped[str | None] = mapped_column(
        String(30), comment="등급 출처: dart/nice_biz/manual"
    )
    grade_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="등급 산정일")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class IrgMaster(Base):
    """
    IRG 마스터 테이블 (산업 리스크 등급)
    KSIC 코드별 리스크 등급 → PD 조정값
    """
    __tablename__ = "irg_master"

    __table_args__ = (
        UniqueConstraint("ksic_code", name="uq_irg_ksic_code"),
        Index("idx_irg_master_grade", "irg_grade"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    ksic_code: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="한국표준산업분류 코드"
    )
    industry_name: Mapped[str] = mapped_column(String(100), comment="업종명")
    irg_grade: Mapped[str] = mapped_column(
        String(5), nullable=False,
        comment="L(Low) | M(Medium) | H(High) | VH(Very High)"
    )
    pd_adjustment: Mapped[float] = mapped_column(
        comment="PD 조정값 (L=-0.10, M=0.0, H=+0.15, VH=+0.30)"
    )
    limit_cap: Mapped[float | None] = mapped_column(
        comment="한도 상한 배수 (VH=0.5x 등 제한)"
    )

    review_year: Mapped[int | None] = mapped_column(comment="등급 검토 연도")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
