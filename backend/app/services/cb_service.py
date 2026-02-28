"""
CB (Credit Bureau) 서비스
==========================
NICE CB / KCB CB 외부 API 연동.
Mock 서버(포트 8001) 또는 실제 CB API 호출.

NICE CB:  POST /cb/nice/score    (주 CB)
KCB  CB:  POST /cb/kcb/score     (회로 차단기 폴백)

회로 차단기 패턴:
  - NICE 오류 → KCB 폴백
  - 양쪽 모두 실패 → CachedScore 사용
  - 캐시 없으면 DefaultScore 반환 (보수적 700점)
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# ── CB 서버 설정 ─────────────────────────────────────────────
CB_MOCK_BASE_URL = os.getenv("CB_MOCK_BASE_URL", "http://mock-server:8001")
CB_TIMEOUT_SEC = float(os.getenv("CB_TIMEOUT_SEC", "3.0"))
CB_MAX_RETRIES = int(os.getenv("CB_MAX_RETRIES", "1"))

# CB 조회 불가 시 보수적 폴백 점수 (실제 운영에서는 수동 심사 전환)
CB_FALLBACK_SCORE = 700
CB_FALLBACK_GRADE = "BB"


@dataclass
class CBScore:
    """CB 조회 결과."""
    source: str                         # "nice" | "kcb" | "fallback" | "cached"
    cb_score: int                       # 신용점수 (1~1000 또는 300~900)
    credit_grade: str                   # 1~10등급 또는 AAA~D
    delinquency_count_12m: int = 0      # 12개월 연체 횟수
    worst_delinquency_status: int = 0   # 최악 연체 상태 (0=없음, 1=30일, 2=90일+)
    open_loan_count: int = 0            # 보유 대출 수
    total_loan_balance: int = 0         # 총 대출 잔액 (원)
    inquiry_count_3m: int = 0           # 최근 3개월 조회 수
    inquiry_count_6m: int = 0           # 최근 6개월 조회 수
    telecom_no_delinquency: bool = True  # 통신료 연체 없음
    queried_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    is_fallback: bool = False
    error_message: str | None = None


class CBService:
    """
    CB API 통합 서비스.

    사용법:
        async with CBService() as svc:
            cb = await svc.get_score(resident_hash)
    """

    def __init__(
        self,
        base_url: str = CB_MOCK_BASE_URL,
        timeout: float = CB_TIMEOUT_SEC,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        # 인메모리 캐시 (실제 운영: Redis 사용)
        self._cache: dict[str, tuple[CBScore, datetime]] = {}
        self._cache_ttl = timedelta(hours=1)

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _cache_key(self, resident_hash: str) -> str:
        return f"cb:{resident_hash[:16]}"

    def _get_cached(self, resident_hash: str) -> CBScore | None:
        key = self._cache_key(resident_hash)
        if key in self._cache:
            score, cached_at = self._cache[key]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                logger.debug(f"CB 캐시 히트: {key}")
                return score
        return None

    def _set_cache(self, resident_hash: str, score: CBScore) -> None:
        key = self._cache_key(resident_hash)
        self._cache[key] = (score, datetime.utcnow())

    async def get_score(
        self,
        resident_hash: str,
        applicant_name: str | None = None,
        include_detail: bool = True,
    ) -> CBScore:
        """
        CB 점수 조회 (NICE → KCB → 폴백 순).

        Args:
            resident_hash: 주민번호 HMAC-SHA256 해시
            applicant_name: 신청인 이름 (mock 서버 헤더용)
            include_detail: 상세 정보 포함 여부

        Returns:
            CBScore 객체
        """
        # 1. 캐시 확인
        cached = self._get_cached(resident_hash)
        if cached:
            cached.source = "cached"
            return cached

        # 2. NICE CB 시도
        try:
            score = await self._query_nice(resident_hash, applicant_name)
            self._set_cache(resident_hash, score)
            logger.info(f"NICE CB 조회 성공: score={score.cb_score}")
            return score
        except Exception as e:
            logger.warning(f"NICE CB 조회 실패, KCB 폴백 시도: {e}")

        # 3. KCB CB 폴백
        try:
            score = await self._query_kcb(resident_hash, applicant_name)
            self._set_cache(resident_hash, score)
            logger.info(f"KCB CB 폴백 성공: score={score.cb_score}")
            return score
        except Exception as e:
            logger.error(f"KCB CB 폴백도 실패: {e}")

        # 4. 최종 폴백 (보수적 점수)
        return self._fallback_score(reason="CB API 모두 불가")

    async def _query_nice(
        self, resident_hash: str, applicant_name: str | None = None
    ) -> CBScore:
        """NICE CB API 조회."""
        if not self._client:
            raise RuntimeError("CBService가 컨텍스트 매니저로 열리지 않음")

        payload = {"resident_hash": resident_hash}
        if applicant_name:
            payload["applicant_name"] = applicant_name

        resp = await self._client.post("/cb/nice/score", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return CBScore(
            source="nice",
            cb_score=data.get("credit_score", CB_FALLBACK_SCORE),
            credit_grade=data.get("credit_grade", CB_FALLBACK_GRADE),
            delinquency_count_12m=data.get("delinquency_count_12m", 0),
            worst_delinquency_status=data.get("worst_delinquency_status", 0),
            open_loan_count=data.get("open_loan_count", 0),
            total_loan_balance=data.get("total_loan_balance", 0),
            inquiry_count_3m=data.get("inquiry_count_3m", 0),
            inquiry_count_6m=data.get("inquiry_count_6m", 0),
            telecom_no_delinquency=data.get("telecom_no_delinquency", True),
            queried_at=data.get("queried_at", datetime.utcnow().isoformat()),
        )

    async def _query_kcb(
        self, resident_hash: str, applicant_name: str | None = None
    ) -> CBScore:
        """KCB CB API 조회 (회로 차단기 폴백)."""
        if not self._client:
            raise RuntimeError("CBService가 컨텍스트 매니저로 열리지 않음")

        payload = {"resident_hash": resident_hash}
        if applicant_name:
            payload["applicant_name"] = applicant_name

        resp = await self._client.post("/cb/kcb/score", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return CBScore(
            source="kcb",
            cb_score=data.get("credit_score", CB_FALLBACK_SCORE),
            credit_grade=data.get("credit_grade", CB_FALLBACK_GRADE),
            delinquency_count_12m=data.get("delinquency_count_12m", 0),
            worst_delinquency_status=data.get("worst_delinquency_status", 0),
            open_loan_count=data.get("open_loan_count", 0),
            total_loan_balance=data.get("total_loan_balance", 0),
            inquiry_count_3m=data.get("inquiry_count_3m", 0),
            inquiry_count_6m=data.get("inquiry_count_6m", 0),
            telecom_no_delinquency=data.get("telecom_no_delinquency", True),
            queried_at=datetime.utcnow().isoformat(),
        )

    def _fallback_score(self, reason: str = "") -> CBScore:
        """
        CB 조회 불가 시 보수적 폴백 점수 반환.
        실제 운영에서는 수동 심사 전환 트리거.
        """
        logger.error(f"CB 폴백 점수 사용: {reason}")
        return CBScore(
            source="fallback",
            cb_score=CB_FALLBACK_SCORE,
            credit_grade=CB_FALLBACK_GRADE,
            delinquency_count_12m=0,
            worst_delinquency_status=0,
            open_loan_count=0,
            total_loan_balance=0,
            inquiry_count_3m=0,
            is_fallback=True,
            error_message=reason,
        )

    async def get_dual_cb_score(
        self, resident_hash: str
    ) -> tuple[CBScore, CBScore | None]:
        """
        NICE + KCB 양방향 조회 (이중 검증).
        두 CB 점수 중 더 불리한 쪽을 사용하는 보수적 전략도 가능.

        Returns:
            (nice_score, kcb_score) — kcb는 실패 시 None
        """
        nice_score: CBScore | None = None
        kcb_score: CBScore | None = None

        try:
            nice_score = await self._query_nice(resident_hash)
        except Exception as e:
            logger.warning(f"이중 CB: NICE 실패 ({e})")

        try:
            kcb_score = await self._query_kcb(resident_hash)
        except Exception as e:
            logger.warning(f"이중 CB: KCB 실패 ({e})")

        if nice_score is None and kcb_score is None:
            nice_score = self._fallback_score("이중 CB 모두 실패")

        return (nice_score or kcb_score) or self._fallback_score("이중 CB 모두 실패"), kcb_score  # type: ignore[return-value]

    def conservative_score(self, nice: CBScore, kcb: CBScore | None) -> CBScore:
        """
        두 CB 점수 중 더 불리한(낮은) 점수 선택 (보수적 접근).
        바젤III 모범규준: 복수 데이터 소스 활용 시 보수적 추정.
        """
        if kcb is None or nice.is_fallback:
            return nice
        if kcb.is_fallback:
            return nice
        # 더 낮은 점수 선택
        return nice if nice.cb_score <= kcb.cb_score else kcb
