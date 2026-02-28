"""
신청인 기본 정보 테이블 (v1.1)
개인정보 보호법: 주민번호는 해시값만 저장, 성명은 가명처리
v1.1 추가: applicant_type(개인/개인사업자), EQ Grade, IRG, OSI Score, 특수직역 세그먼트, SOHO 필드
"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.compat import UUID


class Applicant(Base):
    __tablename__ = "applicants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── 신청인 유형 (개인 vs 개인사업자 이중 구조) ──────────────────
    applicant_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="individual",
        comment="individual(개인) | self_employed(개인사업자)"
    )

    # ── 개인정보 - 가명처리 (개인정보 보호법 §28의2) ──────────────
    resident_registration_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
        comment="주민번호 HMAC-SHA256 해시 (Vault KMS 키 관리)"
    )
    name_masked: Mapped[str | None] = mapped_column(String(10), comment="가명처리된 성명 (예: 홍*동)")

    # ── 인구통계 변수 ─────────────────────────────────────────────
    age: Mapped[int | None] = mapped_column(Integer, comment="나이")
    age_band: Mapped[str | None] = mapped_column(String(10), comment="연령대 (20s/30s/40s/50s/60+)")
    employment_type: Mapped[str | None] = mapped_column(
        String(20),
        comment="직업유형: employed/self_employed/unemployed/retired/student"
    )
    employment_duration_months: Mapped[int | None] = mapped_column(Integer, comment="현 직장 근속월수")
    income_annual: Mapped[float | None] = mapped_column(Numeric(15, 2), comment="연간 소득 (원)")
    income_verified: Mapped[bool] = mapped_column(Boolean, default=False, comment="소득 검증 여부 (건보료 등)")
    residence_type: Mapped[str | None] = mapped_column(
        String(20), comment="거주형태: own/rent/family/public"
    )
    education_level: Mapped[str | None] = mapped_column(
        String(20), comment="학력: high_school/college/university/graduate"
    )

    # ── 직종 및 직장 정보 ─────────────────────────────────────────
    occupation_code: Mapped[str | None] = mapped_column(
        String(10), comment="직종 코드 (예: MD001=의사, JD001=변호사, ART001=예술인)"
    )
    employer_name: Mapped[str | None] = mapped_column(String(100), comment="직장명 (가명처리)")
    employer_registration_no: Mapped[str | None] = mapped_column(
        String(20), comment="사업자등록번호 해시 (EQ Grade 조회 키)"
    )

    # ── EQ Grade (기업 신용등급 연동) ─────────────────────────────
    employer_eq_grade: Mapped[str | None] = mapped_column(
        String(5), comment="EQ Grade: EQ-S/A/B/C/D/E (직장 신용도 기반 한도배수)"
    )
    eq_grade_source: Mapped[str | None] = mapped_column(
        String(20), comment="EQ Grade 출처: dart/nice_biz/manual/mou_list"
    )
    eq_grade_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── IRG (산업 리스크 등급) ────────────────────────────────────
    irg_code: Mapped[str | None] = mapped_column(
        String(5), comment="Industry Risk Grade: L/M/H/VH"
    )
    ksic_code: Mapped[str | None] = mapped_column(
        String(10), comment="한국표준산업분류 코드 (KSIC)"
    )

    # ── OSI Score (On-site 면접/현장 검증 점수, 개인사업자용) ────────
    osi_score: Mapped[float | None] = mapped_column(
        Numeric(6, 2), comment="현장심사 점수 0~100 (개인사업자 대면심사시)"
    )

    # ── 특수 직역 세그먼트 ────────────────────────────────────────
    segment_code: Mapped[str | None] = mapped_column(
        String(30),
        comment=(
            "특수 세그먼트: "
            "SEG-DR(의사/치과의사/한의사) | "
            "SEG-JD(변호사/법무사/회계사) | "
            "SEG-ART(예술인) | "
            "SEG-YTH(청년 19-34세) | "
            "SEG-MIL(군인/공무원) | "
            "SEG-MOU-{code}(협약기업 근로자)"
        )
    )
    segment_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="세그먼트 자격 검증 여부"
    )
    segment_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── 디지털 채널 정보 ──────────────────────────────────────────
    digital_channel: Mapped[str | None] = mapped_column(
        String(30), comment="유입 채널: kakao/naver/bank_app/web/branch"
    )

    # ── CB 동의 여부 (신용정보법 §32) ──────────────────────────────
    cb_consent_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    cb_consent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alt_data_consent_granted: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="대안데이터(통신/공공) 활용 동의"
    )
    mydata_consent_granted: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="마이데이터 연동 동의"
    )

    # ── SOHO/개인사업자 전용 필드 ─────────────────────────────────
    business_registration_no: Mapped[str | None] = mapped_column(
        String(20), comment="사업자등록번호 해시 (개인사업자)"
    )
    business_type: Mapped[str | None] = mapped_column(
        String(50), comment="업종 (예: 음식업/도소매업/서비스업)"
    )
    business_duration_months: Mapped[int | None] = mapped_column(
        Integer, comment="사업 영위 기간 (월)"
    )
    revenue_annual: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="연간 매출액 (원, 개인사업자)"
    )
    operating_income: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="영업이익 (원, 개인사업자)"
    )
    business_credit_score: Mapped[int | None] = mapped_column(
        Integer, comment="사업자 CB 점수 (NICE/KCB 사업자 신용정보)"
    )
    tax_filing_count: Mapped[int | None] = mapped_column(
        Integer, comment="최근 3년 확정신고 횟수 (국세청 조회)"
    )
    revenue_growth_rate: Mapped[float | None] = mapped_column(
        Numeric(8, 4), comment="전년비 매출 성장률 (%)"
    )

    # ── 예술인 소득 평활화 (SEG-ART 전용) ────────────────────────
    art_income_12m_avg: Mapped[float | None] = mapped_column(
        Numeric(15, 2), comment="12개월 평균 소득 (예술인 소득 변동성 완화)"
    )
    art_fund_registered: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="예술인복지재단 등록 여부"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # ── ORM 관계 ─────────────────────────────────────────────────────
    loan_applications: Mapped[list["LoanApplication"]] = relationship(  # noqa: F821
        "LoanApplication",
        back_populates="applicant",
        cascade="all, delete-orphan",
        lazy="select",
    )
