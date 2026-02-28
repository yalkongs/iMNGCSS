"""
SQLAlchemy ORM 스키마 모듈
모든 테이블 클래스를 임포트하여 Base.metadata에 등록
"""
from app.db.schemas.applicant import Applicant
from app.db.schemas.loan_application import LoanApplication
from app.db.schemas.credit_score import CreditScore
from app.db.schemas.model_version import ModelVersion
from app.db.schemas.audit_log import AuditLog
from app.db.schemas.regulation_params import RegulationParam, EqGradeMaster, IrgMaster

__all__ = [
    "Applicant",
    "LoanApplication",
    "CreditScore",
    "ModelVersion",
    "AuditLog",
    "RegulationParam",
    "EqGradeMaster",
    "IrgMaster",
]
