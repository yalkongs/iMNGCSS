"""
요청/응답 로깅 미들웨어
========================
- X-Request-ID 헤더로 Correlation ID 전파
- 요청 메서드·경로·상태코드·소요시간 구조화 로깅
- 헬스체크(/health)는 로깅 제외
"""
import time
import uuid
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("kcs.access")

# 로깅에서 제외할 경로
_SKIP_PATHS = frozenset(["/health", "/metrics", "/favicon.ico"])


class LoggingMiddleware(BaseHTTPMiddleware):
    """구조화된 요청/응답 로그 + Correlation ID 주입."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Correlation ID: 클라이언트 제공 → 없으면 생성
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # request.state 에 저장 (다운스트림 핸들러에서 접근 가능)
        request.state.request_id = request_id

        path = request.url.path
        skip = path in _SKIP_PATHS

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 응답 헤더에 Correlation ID 포함
        response.headers["X-Request-ID"] = request_id

        if not skip:
            logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed_ms, 2),
                    "client": request.client.host if request.client else "-",
                },
            )

            # 느린 응답 경고 (p95 SLA 500ms 초과 시)
            if elapsed_ms > 500:
                logger.warning(
                    "slow_request",
                    extra={
                        "request_id": request_id,
                        "path": path,
                        "duration_ms": round(elapsed_ms, 2),
                    },
                )

        return response
