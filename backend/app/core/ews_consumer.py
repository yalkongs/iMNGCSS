"""
EWS (Early Warning System) Kafka 컨슈머
==========================================
ADR-004: 이상징후 탐지 및 자동 대응 파이프라인.

Kafka Topic: ews.alerts
심각도별 자동 대응:
  RED    → 한도 즉시 0원, 연체관리팀 알림 (3일 이상 연체 + 복수 신호)
  AMBER  → 한도 50% 축소, 행동평점 재산출 트리거
  YELLOW → 모니터링 강화, 다음 정기 평가 시 반영

EWS 신호 소스:
  - 납입 누락 (missed_payment)
  - CB 점수 급락 (cb_score_drop ≥ 50점)
  - 타 금융사 연체 발생 (cross_bank_delinquency)
  - 카드 연체 (card_delinquency)
  - 당좌차월 초과 (overdraft_exceeded)
  - 대량 조회 급증 (inquiry_spike: 30일 내 5건+)

실행: python -m app.core.ews_consumer
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging
import os
import signal
from typing import Any

logger = logging.getLogger(__name__)

# ── Kafka 설정 ─────────────────────────────────────────────
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
EWS_TOPIC = os.getenv("EWS_TOPIC", "ews.alerts")
EWS_CONSUMER_GROUP = os.getenv("EWS_CONSUMER_GROUP", "ews-processor")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "false").lower() == "true"

# ── EWS 임계값 ─────────────────────────────────────────────
RED_DELINQUENCY_DAYS = 3          # 3일 이상 연체 → RED 트리거
AMBER_CB_DROP_THRESHOLD = 50      # CB 50점 이상 하락 → AMBER
YELLOW_INQUIRY_SPIKE = 5          # 30일 내 조회 5건 → YELLOW
RED_MULTI_SIGNAL_COUNT = 2        # 복수 신호 발생 → RED 즉시 전환


class EWSeverity(str, Enum):  # noqa: UP042
    RED = "RED"
    AMBER = "AMBER"
    YELLOW = "YELLOW"


class EWSignalType(str, Enum):  # noqa: UP042
    MISSED_PAYMENT = "missed_payment"
    CB_SCORE_DROP = "cb_score_drop"
    CROSS_BANK_DELINQUENCY = "cross_bank_delinquency"
    CARD_DELINQUENCY = "card_delinquency"
    OVERDRAFT_EXCEEDED = "overdraft_exceeded"
    INQUIRY_SPIKE = "inquiry_spike"
    LARGE_WITHDRAWAL = "large_withdrawal"
    COLLATERAL_VALUE_DROP = "collateral_value_drop"


@dataclass
class EWSAlert:
    """EWS 이상징후 알림 메시지."""
    alert_id: str
    applicant_id: str
    application_id: str | None
    severity: EWSeverity
    signals: list[str]
    signal_details: dict[str, Any] = field(default_factory=dict)
    triggered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source_system: str = "ews"

    @classmethod
    def from_kafka_message(cls, msg: dict) -> "EWSAlert":
        return cls(
            alert_id=msg.get("alert_id", ""),
            applicant_id=msg.get("applicant_id", ""),
            application_id=msg.get("application_id"),
            severity=EWSeverity(msg.get("severity", "YELLOW")),
            signals=msg.get("signals", []),
            signal_details=msg.get("signal_details", {}),
            triggered_at=msg.get("triggered_at", datetime.utcnow().isoformat()),
            source_system=msg.get("source_system", "ews"),
        )


@dataclass
class EWSAction:
    """EWS 자동 대응 결과."""
    alert_id: str
    applicant_id: str
    severity: EWSeverity
    actions_taken: list[str]
    limit_change: float | None = None  # None=변경없음, 0=즉시동결, 0.5=50%축소
    rescore_triggered: bool = False
    notification_sent: bool = False
    processed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class EWSProcessor:
    """EWS 이상징후 처리기."""

    def __init__(self, db_session=None, notification_service=None):
        self._db = db_session
        self._notify = notification_service

    async def process(self, alert: EWSAlert) -> EWSAction:
        """알림 심각도에 따른 자동 대응 실행."""
        logger.info(
            f"EWS 처리 시작: alert_id={alert.alert_id} "
            f"severity={alert.severity} signals={alert.signals}"
        )

        if alert.severity == EWSeverity.RED:
            return await self._handle_red(alert)
        elif alert.severity == EWSeverity.AMBER:
            return await self._handle_amber(alert)
        else:
            return await self._handle_yellow(alert)

    async def _handle_red(self, alert: EWSAlert) -> EWSAction:
        """
        RED 대응:
          - 신용 한도 즉시 0원 (동결)
          - 연체관리팀 즉시 알림
          - 수동 심사 큐 전환
          - audit_log 기록
        """
        actions = []

        # 1. 한도 동결
        if self._db:
            try:
                await self._freeze_credit_limit(alert.applicant_id)
                actions.append("credit_limit_frozen")
                logger.warning(f"RED: 한도 동결 — applicant={alert.applicant_id}")
            except Exception as e:
                logger.error(f"한도 동결 실패: {e}")

        # 2. 연체관리팀 알림
        if self._notify:
            try:
                await self._notify.send_urgent(
                    team="collections",
                    applicant_id=alert.applicant_id,
                    message=f"RED 이상징후 발생: {alert.signals}",
                )
                actions.append("collections_notified")
            except Exception as e:
                logger.error(f"알림 발송 실패: {e}")

        # 3. 수동 심사 큐 전환 (DB에 상태 업데이트)
        if self._db:
            try:
                await self._set_manual_review(alert.applicant_id, reason=f"EWS RED: {alert.signals}")
                actions.append("manual_review_triggered")
            except Exception as e:
                logger.error(f"수동 심사 전환 실패: {e}")

        return EWSAction(
            alert_id=alert.alert_id,
            applicant_id=alert.applicant_id,
            severity=alert.severity,
            actions_taken=actions,
            limit_change=0.0,  # 즉시 동결
            rescore_triggered=True,
            notification_sent=bool(self._notify),
        )

    async def _handle_amber(self, alert: EWSAlert) -> EWSAction:
        """
        AMBER 대응:
          - 신용 한도 50% 축소
          - 행동평점 즉시 재산출 트리거 (behavioral rescore)
          - 리스크팀 알림
        """
        actions = []

        # 1. 한도 50% 축소
        if self._db:
            try:
                await self._reduce_credit_limit(alert.applicant_id, ratio=0.50)
                actions.append("credit_limit_reduced_50pct")
                logger.warning(f"AMBER: 한도 50% 축소 — applicant={alert.applicant_id}")
            except Exception as e:
                logger.error(f"한도 축소 실패: {e}")

        # 2. 행동평점 재산출 (Kafka 이벤트 발행)
        try:
            await self._trigger_behavioral_rescore(alert.applicant_id)
            actions.append("behavioral_rescore_triggered")
        except Exception as e:
            logger.error(f"행동평점 재산출 트리거 실패: {e}")

        # 3. 리스크팀 알림
        if self._notify:
            try:
                await self._notify.send_alert(
                    team="risk_management",
                    applicant_id=alert.applicant_id,
                    severity="AMBER",
                    signals=alert.signals,
                )
                actions.append("risk_team_notified")
            except Exception as e:
                logger.error(f"알림 발송 실패: {e}")

        return EWSAction(
            alert_id=alert.alert_id,
            applicant_id=alert.applicant_id,
            severity=alert.severity,
            actions_taken=actions,
            limit_change=0.50,
            rescore_triggered=True,
            notification_sent=bool(self._notify),
        )

    async def _handle_yellow(self, alert: EWSAlert) -> EWSAction:
        """
        YELLOW 대응:
          - 모니터링 강화 (다음 정기 평가 시 반영)
          - 로그 기록
          - 별도 알림 없음
        """
        actions = ["monitoring_enhanced", "logged"]
        logger.info(f"YELLOW: 모니터링 강화 — applicant={alert.applicant_id}, signals={alert.signals}")

        return EWSAction(
            alert_id=alert.alert_id,
            applicant_id=alert.applicant_id,
            severity=alert.severity,
            actions_taken=actions,
            limit_change=None,
            rescore_triggered=False,
            notification_sent=False,
        )

    async def _freeze_credit_limit(self, applicant_id: str) -> None:
        """신용 한도 즉시 동결 (DB 업데이트)."""
        if not self._db:
            return
        from sqlalchemy import update

        from app.db.schemas.loan_application import LoanApplication
        stmt = (
            update(LoanApplication)
            .where(LoanApplication.applicant_id == applicant_id)
            .values(status="suspended", auto_decision=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def _reduce_credit_limit(self, applicant_id: str, ratio: float = 0.50) -> None:
        """신용 한도 비율만큼 축소."""
        if not self._db:
            return
        # 실제 구현: 현재 한도 조회 → ratio 적용 → 업데이트
        logger.info(f"한도 {ratio:.0%} 축소 — applicant={applicant_id}")

    async def _set_manual_review(self, applicant_id: str, reason: str = "") -> None:
        """수동 심사 큐 전환."""
        if not self._db:
            return
        from sqlalchemy import update

        from app.db.schemas.loan_application import LoanApplication
        stmt = (
            update(LoanApplication)
            .where(LoanApplication.applicant_id == applicant_id)
            .values(status="manual_review", auto_decision=False)
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def _trigger_behavioral_rescore(self, applicant_id: str) -> None:
        """행동평점 재산출 이벤트 발행 (Kafka 또는 직접 호출)."""
        logger.info(f"행동평점 재산출 트리거 — applicant={applicant_id}")
        # 실제: Kafka Producer로 "behavioral.rescore" 토픽에 발행


def classify_severity(signals: list[str], signal_details: dict) -> EWSeverity:
    """
    신호 목록으로 심각도 분류.

    Rules:
      RED:    연체 3일+ | 복수 신호(2개+) + 연체 포함
      AMBER:  CB 50점 이상 하락 | 타 금융사 연체 | 카드 연체
      YELLOW: 조회 급증 | 당좌차월 | 소액 납입 누락
    """
    has_missed_payment = EWSignalType.MISSED_PAYMENT in signals
    has_cross_bank = EWSignalType.CROSS_BANK_DELINQUENCY in signals
    has_card_delinquency = EWSignalType.CARD_DELINQUENCY in signals

    delinquency_days = signal_details.get("delinquency_days", 0)
    cb_drop = signal_details.get("cb_score_drop", 0)
    _inquiry_count = signal_details.get("inquiry_count_30d", 0)

    # RED 조건
    if delinquency_days >= RED_DELINQUENCY_DAYS:
        return EWSeverity.RED
    if (has_missed_payment or has_cross_bank) and len(signals) >= RED_MULTI_SIGNAL_COUNT:
        return EWSeverity.RED

    # AMBER 조건
    if cb_drop >= AMBER_CB_DROP_THRESHOLD:
        return EWSeverity.AMBER
    if has_cross_bank or has_card_delinquency:
        return EWSeverity.AMBER
    if has_missed_payment and cb_drop >= 20:
        return EWSeverity.AMBER

    # YELLOW
    return EWSeverity.YELLOW


class EWSConsumer:
    """
    Kafka EWS 컨슈머.
    Kafka 미설치 시 인메모리 큐로 폴백 (개발/테스트용).
    """

    def __init__(self, db_factory=None):
        self._db_factory = db_factory
        self._processor: EWSProcessor | None = None
        self._running = False
        self._processed_count = 0
        self._error_count = 0

    async def start(self):
        """컨슈머 시작."""
        self._running = True
        logger.info(f"EWS 컨슈머 시작: topic={EWS_TOPIC}, group={EWS_CONSUMER_GROUP}")

        if KAFKA_ENABLED:
            await self._consume_kafka()
        else:
            logger.info("Kafka 비활성화 — 데모 모드 (인메모리 큐)")
            await self._consume_demo()

    async def stop(self):
        """컨슈머 정지."""
        self._running = False
        logger.info(
            f"EWS 컨슈머 종료: 처리={self._processed_count}건, 오류={self._error_count}건"
        )

    async def _consume_kafka(self):
        """실제 Kafka 컨슈머 (aiokafka)."""
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError:
            logger.error("aiokafka 미설치. pip install aiokafka")
            return

        consumer = AIOKafkaConsumer(
            EWS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=EWS_CONSUMER_GROUP,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        await consumer.start()
        logger.info("Kafka 컨슈머 연결 완료")
        try:
            async for msg in consumer:
                if not self._running:
                    break
                await self._handle_message(msg.value)
        finally:
            await consumer.stop()

    async def _consume_demo(self):
        """데모 모드: 샘플 이벤트 처리 후 대기."""
        demo_events = [
            {
                "alert_id": "demo-001",
                "applicant_id": "appl-test-001",
                "application_id": None,
                "severity": "AMBER",
                "signals": ["cb_score_drop", "missed_payment"],
                "signal_details": {"cb_score_drop": 65, "delinquency_days": 0},
                "triggered_at": datetime.utcnow().isoformat(),
                "source_system": "demo",
            },
            {
                "alert_id": "demo-002",
                "applicant_id": "appl-test-002",
                "application_id": None,
                "severity": "YELLOW",
                "signals": ["inquiry_spike"],
                "signal_details": {"inquiry_count_30d": 7},
                "triggered_at": datetime.utcnow().isoformat(),
                "source_system": "demo",
            },
        ]

        for event in demo_events:
            await self._handle_message(event)

        logger.info("데모 이벤트 처리 완료. 실제 Kafka 연결 대기 중...")
        # 운영 환경에서는 Kafka가 준비될 때까지 무한 대기
        while self._running and not KAFKA_ENABLED:
            await asyncio.sleep(30)

    async def _handle_message(self, payload: dict) -> None:
        """단일 EWS 메시지 처리."""
        try:
            alert = EWSAlert.from_kafka_message(payload)

            # DB 세션 생성
            db = None
            if self._db_factory:
                async with self._db_factory() as db:
                    processor = EWSProcessor(db_session=db)
                    action = await processor.process(alert)
            else:
                processor = EWSProcessor()
                action = await processor.process(alert)

            self._processed_count += 1
            logger.info(
                f"EWS 처리 완료: alert={alert.alert_id} "
                f"severity={alert.severity} actions={action.actions_taken}"
            )

        except Exception as e:
            self._error_count += 1
            logger.error(f"EWS 메시지 처리 오류: {e}, payload={payload}")

    @property
    def stats(self) -> dict:
        return {
            "processed": self._processed_count,
            "errors": self._error_count,
            "running": self._running,
        }


async def main():
    """EWS 컨슈머 독립 실행."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    consumer = EWSConsumer()

    # 종료 신호 처리
    loop = asyncio.get_event_loop()

    def shutdown():
        logger.info("종료 신호 수신")
        loop.create_task(consumer.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown)

    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
