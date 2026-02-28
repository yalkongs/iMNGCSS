"""
Redis 슬라이딩 윈도우 Rate Limiting 미들웨어
=============================================
- IP 기반 기본 제한 (RATE_LIMIT_PER_MINUTE, 기본 60)
- /api/v1/scoring/evaluate 는 별도 강화 제한 (기본 30/분)
- 초과 시 HTTP 429 반환 + Retry-After 헤더
- Redis 미연결 시 Rate Limiting 우회 (Fail-Open)
"""
import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("kcs.ratelimit")

# 환경 변수로 제한값 조정 가능
_DEFAULT_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
_SCORING_LIMIT = int(os.getenv("RATE_LIMIT_SCORING_PER_MINUTE", "30"))
_WINDOW_SECONDS = 60

# Redis 연결 (선택적 — 없으면 Fail-Open)
try:
    import redis.asyncio as aioredis

    _redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    _redis: aioredis.Redis | None = aioredis.from_url(_redis_url, decode_responses=True)
except ImportError:
    _redis = None


def _get_client_key(request: Request) -> str:
    """클라이언트 식별자: Authorization 토큰 우선, 없으면 IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        # 토큰의 마지막 16자만 사용 (전체 저장 방지)
        return f"rl:token:{auth[-16:]}"
    client_ip = request.client.host if request.client else "unknown"
    return f"rl:ip:{client_ip}"


async def _check_rate_limit(key: str, limit: int) -> tuple[bool, int, int]:
    """
    슬라이딩 윈도우 Rate Limit 확인.

    Returns:
        (allowed, remaining, retry_after_seconds)
    """
    if _redis is None:
        return True, limit, 0

    try:
        now = time.time()
        window_start = now - _WINDOW_SECONDS

        pipe = _redis.pipeline()
        # 만료된 항목 제거 → 현재 윈도우 요청 추가 → 카운트 조회
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, _WINDOW_SECONDS + 1)
        results = await pipe.execute()

        count: int = results[2]
        remaining = max(0, limit - count)
        allowed = count <= limit

        retry_after = 0
        if not allowed:
            # 가장 오래된 항목이 만료되는 시간 계산
            oldest = await _redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(_WINDOW_SECONDS - (now - oldest[0][1])))

        return allowed, remaining, retry_after

    except Exception as exc:
        logger.warning("rate_limit_redis_error: %s — Fail-Open 적용", exc)
        return True, limit, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis 슬라이딩 윈도우 Rate Limiter."""

    # Rate Limit 적용 제외 경로
    _EXEMPT = frozenset(["/health", "/metrics", "/docs", "/redoc", "/openapi.json"])

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if path in self._EXEMPT:
            return await call_next(request)

        # 평가 엔드포인트는 더 엄격한 제한
        limit = _SCORING_LIMIT if path.startswith("/api/v1/scoring") else _DEFAULT_LIMIT
        key = _get_client_key(request)

        allowed, remaining, retry_after = await _check_rate_limit(key, limit)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                extra={
                    "key": key,
                    "path": path,
                    "limit": limit,
                    "retry_after": retry_after,
                },
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"요청 한도 초과 ({limit}회/분). {retry_after}초 후 재시도하세요.",
                    "limit": limit,
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
