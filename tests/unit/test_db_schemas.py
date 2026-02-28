"""
DB 스키마 단위 테스트
=====================
ORM 모델 정의, 관계(relationship), 제약조건(CheckConstraint)을 검증.
실제 DB 연결 없이 SQLAlchemy 메타데이터만 검사.
"""
import uuid
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.schemas import Applicant, LoanApplication, CreditScore, RegulationParam


# ──────────────────────────────────────────────────────────────────────────────
# SQLite 인메모리 DB (테스트 전용)
# ──────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as sess:
        yield sess
        sess.rollback()


# ──────────────────────────────────────────────────────────────────────────────
# 헬퍼 팩토리
# ──────────────────────────────────────────────────────────────────────────────
def _applicant(**kwargs) -> Applicant:
    defaults = dict(
        resident_registration_hash=f"hash_{uuid.uuid4().hex[:16]}",
        cb_consent_granted=True,
    )
    defaults.update(kwargs)
    return Applicant(**defaults)


def _loan_app(applicant_id: uuid.UUID, **kwargs) -> LoanApplication:
    defaults = dict(
        applicant_id=applicant_id,
        product_type="credit",
        requested_amount=10_000_000,
    )
    defaults.update(kwargs)
    return LoanApplication(**defaults)


def _credit_score(application_id: uuid.UUID, **kwargs) -> CreditScore:
    defaults = dict(
        application_id=application_id,
        score=650,
        grade="BB",
        decision="approved",
        pd_estimate=0.035,
    )
    defaults.update(kwargs)
    return CreditScore(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# 1. 테이블 메타데이터 검증
# ══════════════════════════════════════════════════════════════════════════════
class TestTableMetadata:
    """테이블 존재 여부 및 컬럼 수 검증 (DB 연결 없이 메타데이터 확인)."""

    def test_applicant_tablename(self):
        assert Applicant.__tablename__ == "applicants"

    def test_loan_application_tablename(self):
        assert LoanApplication.__tablename__ == "loan_applications"

    def test_credit_score_tablename(self):
        assert CreditScore.__tablename__ == "credit_scores"

    def test_applicant_has_required_columns(self):
        cols = {c.key for c in Applicant.__table__.columns}
        assert "id" in cols
        assert "resident_registration_hash" in cols
        assert "segment_code" in cols
        assert "employer_eq_grade" in cols

    def test_loan_application_has_foreign_key_to_applicant(self):
        fk_cols = {fk.column.table.name for fk in LoanApplication.__table__.foreign_keys}
        assert "applicants" in fk_cols

    def test_credit_score_has_foreign_key_to_loan_application(self):
        fk_cols = {fk.column.table.name for fk in CreditScore.__table__.foreign_keys}
        assert "loan_applications" in fk_cols

    def test_credit_score_has_check_constraints(self):
        constraint_names = {c.name for c in CreditScore.__table__.constraints}
        assert "chk_score_range" in constraint_names
        assert "chk_pd_range" in constraint_names


# ══════════════════════════════════════════════════════════════════════════════
# 2. ORM 관계(relationship) 정의 검증
# ══════════════════════════════════════════════════════════════════════════════
class TestOrmRelationships:
    """relationship 속성이 ORM 클래스에 올바르게 정의됐는지 검증."""

    def test_applicant_has_loan_applications_relationship(self):
        """Applicant → LoanApplication (1:N) 관계가 정의돼야 한다."""
        mapper = inspect(Applicant)
        rel_names = {r.key for r in mapper.relationships}
        assert "loan_applications" in rel_names

    def test_loan_application_has_applicant_relationship(self):
        """LoanApplication → Applicant (N:1) 관계가 정의돼야 한다."""
        mapper = inspect(LoanApplication)
        rel_names = {r.key for r in mapper.relationships}
        assert "applicant" in rel_names

    def test_loan_application_has_credit_scores_relationship(self):
        """LoanApplication → CreditScore (1:N) 관계가 정의돼야 한다."""
        mapper = inspect(LoanApplication)
        rel_names = {r.key for r in mapper.relationships}
        assert "credit_scores" in rel_names

    def test_credit_score_has_application_relationship(self):
        """CreditScore → LoanApplication (N:1) 관계가 정의돼야 한다."""
        mapper = inspect(CreditScore)
        rel_names = {r.key for r in mapper.relationships}
        assert "application" in rel_names

    def test_applicant_to_loan_application_is_one_to_many(self):
        """Applicant.loan_applications 는 리스트(컬렉션) 관계여야 한다."""
        mapper = inspect(Applicant)
        rel = mapper.relationships["loan_applications"]
        assert rel.uselist is True      # 컬렉션(1:N)

    def test_loan_application_to_applicant_is_many_to_one(self):
        """LoanApplication.applicant 는 단일 객체(M:1) 관계여야 한다."""
        mapper = inspect(LoanApplication)
        rel = mapper.relationships["applicant"]
        assert rel.uselist is False     # 단일 객체(N:1)

    def test_back_populates_bidirectional(self):
        """Applicant ↔ LoanApplication 관계가 양방향으로 연결돼야 한다."""
        app_mapper = inspect(Applicant)
        loan_mapper = inspect(LoanApplication)
        app_rel = app_mapper.relationships["loan_applications"]
        loan_rel = loan_mapper.relationships["applicant"]
        assert app_rel.back_populates == "applicant"
        assert loan_rel.back_populates == "loan_applications"

    def test_cascade_delete_orphan_on_loan_applications(self):
        """Applicant 삭제 시 LoanApplication 이 cascade 삭제돼야 한다."""
        mapper = inspect(Applicant)
        rel = mapper.relationships["loan_applications"]
        assert "delete-orphan" in str(rel.cascade)

    def test_cascade_delete_orphan_on_credit_scores(self):
        """LoanApplication 삭제 시 CreditScore 가 cascade 삭제돼야 한다."""
        mapper = inspect(LoanApplication)
        rel = mapper.relationships["credit_scores"]
        assert "delete-orphan" in str(rel.cascade)


# ══════════════════════════════════════════════════════════════════════════════
# 3. 실제 CRUD + 관계 탐색 테스트 (SQLite 인메모리 DB)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.skip(reason="JSONB 타입이 SQLite에서 지원되지 않음 (PostgreSQL 필요)")
class TestCrudAndNavigation:
    """실제 DB에 저장/조회 후 관계 탐색이 동작하는지 검증."""

    def test_create_applicant_and_navigate_to_loan(self, session):
        """Applicant → loan_applications 탐색이 가능해야 한다."""
        applicant = _applicant()
        session.add(applicant)
        session.flush()

        loan = _loan_app(applicant.id)
        session.add(loan)
        session.flush()

        # 관계 탐색
        assert len(applicant.loan_applications) == 1
        assert applicant.loan_applications[0].product_type == "credit"

    def test_navigate_from_loan_to_applicant(self, session):
        """LoanApplication → applicant 역탐색이 가능해야 한다."""
        applicant = _applicant()
        session.add(applicant)
        session.flush()

        loan = _loan_app(applicant.id)
        session.add(loan)
        session.flush()

        retrieved = session.get(LoanApplication, loan.id)
        assert retrieved.applicant is not None
        assert retrieved.applicant.id == applicant.id

    def test_create_credit_score_and_navigate(self, session):
        """CreditScore → application → applicant 체인 탐색이 가능해야 한다."""
        applicant = _applicant()
        session.add(applicant)
        session.flush()

        loan = _loan_app(applicant.id)
        session.add(loan)
        session.flush()

        score = _credit_score(loan.id, score=720, grade="A")
        session.add(score)
        session.flush()

        # CreditScore → LoanApplication
        assert score.application.product_type == "credit"
        # LoanApplication → CreditScore
        assert len(loan.credit_scores) == 1
        assert loan.credit_scores[0].score == 720

    def test_multiple_loans_per_applicant(self, session):
        """한 신청인이 여러 대출 신청을 할 수 있어야 한다."""
        applicant = _applicant()
        session.add(applicant)
        session.flush()

        for product in ["credit", "mortgage"]:
            session.add(_loan_app(applicant.id, product_type=product))
        session.flush()

        assert len(applicant.loan_applications) == 2
        product_types = {la.product_type for la in applicant.loan_applications}
        assert product_types == {"credit", "mortgage"}

    def test_cascade_delete_removes_loans(self, session):
        """Applicant 삭제 시 연관 LoanApplication 도 삭제돼야 한다."""
        applicant = _applicant()
        session.add(applicant)
        session.flush()

        loan = _loan_app(applicant.id)
        session.add(loan)
        session.flush()
        loan_id = loan.id

        session.delete(applicant)
        session.flush()

        assert session.get(LoanApplication, loan_id) is None

    def test_credit_score_range_constraint(self, session):
        """score < 300 이면 DB 제약조건 위반이 발생해야 한다 (SQLite skip)."""
        # SQLite는 CHECK constraint를 기본 비활성화하므로 이 테스트는 skipping
        # PostgreSQL에서는 실제로 IntegrityError가 발생
        pytest.skip("SQLite CHECK constraint 비활성화 (PostgreSQL 전용)")


# ══════════════════════════════════════════════════════════════════════════════
# 4. RegulationParam 스키마 검증
# ══════════════════════════════════════════════════════════════════════════════
class TestRegulationParamSchema:
    """RegulationParam 테이블 구조 검증."""

    def test_regulation_param_tablename(self):
        assert RegulationParam.__tablename__ == "regulation_params"

    def test_regulation_param_has_key_columns(self):
        cols = {c.key for c in RegulationParam.__table__.columns}
        for required in ["id", "param_key", "param_value", "param_category"]:
            assert required in cols, f"필수 컬럼 누락: {required}"

    def test_regulation_param_unique_key(self):
        """param_key 는 unique 제약이 있어야 한다."""
        unique_constraints = [
            c for c in RegulationParam.__table__.constraints
            if hasattr(c, "columns") and "param_key" in [col.name for col in c.columns]
        ]
        # unique index 또는 unique constraint 확인
        unique_indexes = [
            i for i in RegulationParam.__table__.indexes
            if i.unique and "param_key" in [c.name for c in i.columns]
        ]
        has_unique = len(unique_constraints) > 0 or len(unique_indexes) > 0
        assert has_unique, "param_key 에 unique 제약이 없음"
