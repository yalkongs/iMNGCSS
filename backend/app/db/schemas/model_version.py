"""
모델 버전 관리 테이블
금감원 신용위험 모범규준: 모델 문서화, 검증 이력 유지
"""
from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.compat import JSONB, UUID


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="모델명 (예: application_v2)")
    scorecard_type: Mapped[str] = mapped_column(String(30), comment="application|behavioral|collection")
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(500), comment="모델 파일 경로")

    # 성능 지표 (금감원 모범규준 검증 지표)
    gini_train: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="학습 데이터 Gini 계수")
    gini_test: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="검증 데이터 Gini 계수")
    gini_oot: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="OOT(Out-of-Time) Gini 계수")
    ks_statistic: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="KS 통계량")
    auc_roc: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="AUC-ROC")

    # 공정성 지표 (금융위 AI 가이드라인)
    fairness_metrics: Mapped[dict | None] = mapped_column(JSONB, comment="성별/연령대별 Gini 차이")
    fairness_passed: Mapped[bool | None] = mapped_column(comment="공정성 기준 통과 여부")

    # 승인 워크플로우 (금감원 모범규준: 거버넌스)
    status: Mapped[str] = mapped_column(
        String(20), default="draft",
        comment="draft | validated | champion | retired"
    )
    is_champion: Mapped[bool] = mapped_column(Boolean, default=False, comment="현재 운영 모델 여부")
    approved_by: Mapped[str | None] = mapped_column(String(100), comment="승인자 (리스크관리위원회)")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 문서화
    training_data_period: Mapped[str | None] = mapped_column(String(50), comment="학습 데이터 기간 (예: 2021-01 ~ 2023-12)")
    feature_count: Mapped[int | None] = mapped_column(comment="사용된 피처 수")
    training_sample_count: Mapped[int | None] = mapped_column(comment="학습 샘플 수")
    bad_rate_train: Mapped[float | None] = mapped_column(Numeric(6, 4), comment="학습 데이터 불량률")
    notes: Mapped[str | None] = mapped_column(Text, comment="개발자 노트")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
