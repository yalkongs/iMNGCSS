"""
감사 로그 테이블
신용정보법: 신용정보 처리 이력 5년 보존 의무
금감원 모범규준: 모든 평가 이력 추적
"""
from datetime import datetime
from sqlalchemy import String, DateTime, BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 대상 엔티티
    entity_type: Mapped[str] = mapped_column(String(50), comment="credit_score|application|model_version|applicant")
    entity_id: Mapped[str | None] = mapped_column(String(36), comment="UUID 문자열")

    # 액션
    action: Mapped[str] = mapped_column(
        String(50), comment="score_created|application_approved|application_rejected|model_deployed|data_accessed"
    )

    # 행위자
    actor_id: Mapped[str | None] = mapped_column(String(100), comment="사용자 ID 또는 시스템 ID")
    actor_type: Mapped[str] = mapped_column(String(20), comment="user|api|system|batch")

    # 변경 내용
    changes: Mapped[dict | None] = mapped_column(JSONB, comment="변경 전후 데이터")
    ip_address: Mapped[str | None] = mapped_column(String(45), comment="IP 주소")
    user_agent: Mapped[str | None] = mapped_column(Text, comment="User-Agent")

    # 규제 관련 메모
    regulation_ref: Mapped[str | None] = mapped_column(String(100), comment="관련 법령 조항 (예: 신용정보법 §32)")

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
