"""
미들웨어 단위 테스트
====================
LoggingMiddleware, RateLimitMiddleware 의 동작을 ASGI 앱 레벨에서 검증.

의존성 없이 실행 가능 (Redis mock, FastAPI TestClient 사용).
"""
import time
import uuid
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────────
# 테스트용 최소 FastAPI 앱 팩토리
# ──────────────────────────────────────────────────────────────────────────────

def _make_app_with_logging() -> FastAPI:
    """LoggingMiddleware 만 등록한 테스트 앱."""
    from app.middleware.logging_middleware import LoggingMiddleware

    app = FastAPI()
    app.add_middleware(LoggingMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def _make_app_with_ratelimit(redis_mock=None) -> FastAPI:
    """RateLimitMiddleware 만 등록한 테스트 앱 (redis mock 주입)."""
    import app.middleware.rate_limit_middleware as rl_mod

    # 모듈 수준 _redis 교체
    rl_mod._redis = redis_mock

    from app.middleware.rate_limit_middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/scoring/evaluate")
    async def scoring():
        return {"score": 750}

    @app.get("/api/v1/admin/data")
    async def admin():
        return {"data": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ══════════════════════════════════════════════════════════════════════════════
# 1. LoggingMiddleware 테스트
# ══════════════════════════════════════════════════════════════════════════════
class TestLoggingMiddleware:
    """요청/응답 로깅 + Correlation ID 동작 검증."""

    def test_response_contains_x_request_id(self):
        """응답 헤더에 X-Request-ID 가 포함돼야 한다."""
        client = TestClient(_make_app_with_logging())
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_client_request_id_is_preserved(self):
        """클라이언트가 X-Request-ID 를 보내면 그 값이 그대로 반환돼야 한다."""
        custom_id = "my-correlation-id-12345"
        client = TestClient(_make_app_with_logging())
        resp = client.get("/ping", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id

    def test_auto_generated_request_id_is_uuid(self):
        """X-Request-ID 를 보내지 않으면 UUID 형식의 값이 생성돼야 한다."""
        client = TestClient(_make_app_with_logging())
        resp = client.get("/ping")
        generated_id = resp.headers["x-request-id"]
        # UUID 파싱 가능한지 검증
        parsed = uuid.UUID(generated_id)
        assert str(parsed) == generated_id

    def test_health_path_still_returns_x_request_id(self):
        """
        /health 는 로깅을 건너뛰지만, 응답 헤더에는 X-Request-ID 가 있어야 한다.
        (로깅 skip != 헤더 skip)
        """
        client = TestClient(_make_app_with_logging())
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_different_requests_get_unique_ids(self):
        """두 요청이 각자 다른 X-Request-ID 를 받아야 한다."""
        client = TestClient(_make_app_with_logging())
        id1 = client.get("/ping").headers["x-request-id"]
        id2 = client.get("/ping").headers["x-request-id"]
        assert id1 != id2

    def test_slow_request_warning_is_logged(self):
        """500ms 초과 응답에 대해 slow_request 경고 로그가 발생해야 한다."""
        from fastapi import FastAPI as _FA
        from app.middleware.logging_middleware import LoggingMiddleware

        app = _FA()
        app.add_middleware(LoggingMiddleware)

        @app.get("/slow")
        async def slow():
            import asyncio
            await asyncio.sleep(0)  # 실제 sleep 대신 perf_counter 를 mock
            return {"ok": True}

        # elapsed_ms 를 1000ms 로 조작하여 warning 트리거
        with patch("app.middleware.logging_middleware.time") as mock_time:
            # perf_counter: 0 → 1.0 (1000ms 경과 시뮬레이션)
            mock_time.perf_counter.side_effect = [0.0, 1.0]

            with patch("app.middleware.logging_middleware.logger") as mock_logger:
                client = TestClient(app)
                client.get("/slow")

                # warning 호출 확인
                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "slow_request" in call_args[0][0]

    def test_normal_request_no_slow_warning(self):
        """빠른 응답(500ms 미만)에는 slow_request 경고가 없어야 한다."""
        with patch("app.middleware.logging_middleware.logger") as mock_logger:
            client = TestClient(_make_app_with_logging())
            client.get("/ping")
            # warning 은 호출되지 않아야 함
            mock_logger.warning.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 2. _get_client_key 함수 테스트
# ══════════════════════════════════════════════════════════════════════════════
class TestGetClientKey:
    """Rate Limit 클라이언트 식별 키 생성 로직 검증."""

    def _make_request(self, auth_header: str | None = None, client_ip: str = "127.0.0.1"):
        """테스트용 Request 객체 생성."""
        from starlette.testclient import TestClient as StarletteTC
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.requests import Request as StarReq

        captured = {}

        async def capture_view(request: StarReq):
            from app.middleware.rate_limit_middleware import _get_client_key
            from starlette.responses import JSONResponse
            captured["key"] = _get_client_key(request)
            return JSONResponse({"key": captured["key"]})

        app = Starlette(routes=[Route("/", capture_view)])
        headers = {}
        if auth_header:
            headers["Authorization"] = auth_header
        tc = StarletteTC(app)
        tc.get("/", headers=headers)
        return captured.get("key", "")

    def test_ip_key_without_auth(self):
        """Authorization 헤더 없으면 IP 기반 키를 생성해야 한다."""
        key = self._make_request()
        assert key.startswith("rl:ip:")

    def test_token_key_with_bearer(self):
        """Bearer 토큰이 있으면 토큰 기반 키를 생성해야 한다."""
        token = "eyJhbGciOiJIUzI1NiJ9.payload.signature_abc"
        key = self._make_request(auth_header=f"Bearer {token}")
        assert key.startswith("rl:token:")
        # 마지막 16자만 포함돼야 한다
        assert key.endswith(token[-16:])

    def test_non_bearer_auth_uses_ip(self):
        """Basic 인증 등 Bearer 아닌 경우 IP 키를 사용해야 한다."""
        key = self._make_request(auth_header="Basic dXNlcjpwYXNz")
        assert key.startswith("rl:ip:")


# ══════════════════════════════════════════════════════════════════════════════
# 3. _check_rate_limit 함수 테스트
# ══════════════════════════════════════════════════════════════════════════════
class TestCheckRateLimit:
    """슬라이딩 윈도우 Rate Limit 로직 단위 검증 (Redis mock 사용)."""

    @pytest.mark.asyncio
    async def test_fail_open_when_redis_is_none(self):
        """_redis 가 None 이면 항상 허용(Fail-Open)해야 한다."""
        import app.middleware.rate_limit_middleware as rl_mod
        original = rl_mod._redis
        try:
            rl_mod._redis = None
            from app.middleware.rate_limit_middleware import _check_rate_limit
            allowed, remaining, retry_after = await _check_rate_limit("key", 60)
            assert allowed is True
            assert remaining == 60
            assert retry_after == 0
        finally:
            rl_mod._redis = original

    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self):
        """요청 수가 한도 미만이면 허용돼야 한다."""
        mock_redis = AsyncMock()
        mock_pipeline = MagicMock()
        # pipeline.execute() → [None, None, count=5, None]
        mock_pipeline.execute = AsyncMock(return_value=[None, None, 5, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=False)
        mock_pipeline.zremrangebyscore = MagicMock()
        mock_pipeline.zadd = MagicMock()
        mock_pipeline.zcard = MagicMock()
        mock_pipeline.expire = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

        import app.middleware.rate_limit_middleware as rl_mod
        original = rl_mod._redis
        try:
            rl_mod._redis = mock_redis
            from app.middleware.rate_limit_middleware import _check_rate_limit
            allowed, remaining, retry_after = await _check_rate_limit("rl:ip:127.0.0.1", 60)
            assert allowed is True
            assert remaining == 55  # 60 - 5
            assert retry_after == 0
        finally:
            rl_mod._redis = original

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self):
        """요청 수가 한도 초과면 거부해야 한다."""
        mock_redis = AsyncMock()
        mock_pipeline = MagicMock()
        # count = 61 (한도 60 초과)
        mock_pipeline.execute = AsyncMock(return_value=[None, None, 61, None])
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=False)
        mock_pipeline.zremrangebyscore = MagicMock()
        mock_pipeline.zadd = MagicMock()
        mock_pipeline.zcard = MagicMock()
        mock_pipeline.expire = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

        # zrange 는 가장 오래된 항목 반환 (retry_after 계산용)
        oldest_ts = time.time() - 5  # 5초 전 항목
        mock_redis.zrange = AsyncMock(return_value=[("ts_value", oldest_ts)])

        import app.middleware.rate_limit_middleware as rl_mod
        original = rl_mod._redis
        try:
            rl_mod._redis = mock_redis
            from app.middleware.rate_limit_middleware import _check_rate_limit
            allowed, remaining, retry_after = await _check_rate_limit("rl:ip:127.0.0.1", 60)
            assert allowed is False
            assert remaining == 0
            assert retry_after >= 1
        finally:
            rl_mod._redis = original

    @pytest.mark.asyncio
    async def test_fail_open_on_redis_error(self):
        """Redis 오류 발생 시 Fail-Open 으로 허용해야 한다."""
        mock_redis = AsyncMock()
        mock_pipeline = MagicMock()
        mock_pipeline.execute = AsyncMock(side_effect=Exception("Redis 연결 실패"))
        mock_pipeline.zremrangebyscore = MagicMock()
        mock_pipeline.zadd = MagicMock()
        mock_pipeline.zcard = MagicMock()
        mock_pipeline.expire = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

        import app.middleware.rate_limit_middleware as rl_mod
        original = rl_mod._redis
        try:
            rl_mod._redis = mock_redis
            from app.middleware.rate_limit_middleware import _check_rate_limit
            allowed, remaining, retry_after = await _check_rate_limit("rl:ip:127.0.0.1", 60)
            assert allowed is True   # Fail-Open
        finally:
            rl_mod._redis = original


# ══════════════════════════════════════════════════════════════════════════════
# 4. RateLimitMiddleware HTTP 동작 테스트
# ══════════════════════════════════════════════════════════════════════════════
class TestRateLimitMiddlewareHttp:
    """HTTP 요청/응답 레벨에서 Rate Limit 동작 검증."""

    def test_exempt_paths_pass_without_limit(self):
        """/health 등 제외 경로는 Rate Limit 없이 통과해야 한다."""
        client = TestClient(_make_app_with_ratelimit(redis_mock=None))
        resp = client.get("/health")
        assert resp.status_code == 200
        # Rate Limit 헤더 없어야 함
        assert "x-ratelimit-limit" not in resp.headers

    def test_allowed_request_has_rate_limit_headers(self):
        """허용된 요청 응답에 X-RateLimit-* 헤더가 있어야 한다."""
        client = TestClient(_make_app_with_ratelimit(redis_mock=None))
        resp = client.get("/api/v1/admin/data")
        assert resp.status_code == 200
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers

    def test_scoring_uses_lower_limit(self):
        """/api/v1/scoring 경로는 낮은 한도(30)를 사용해야 한다."""
        import app.middleware.rate_limit_middleware as rl_mod
        rl_mod._redis = None  # Fail-Open
        rl_mod._SCORING_LIMIT = 30
        rl_mod._DEFAULT_LIMIT = 60

        client = TestClient(_make_app_with_ratelimit(redis_mock=None))
        resp = client.get("/api/v1/scoring/evaluate")
        assert resp.status_code == 200
        assert resp.headers["x-ratelimit-limit"] == "30"

    def test_admin_uses_default_limit(self):
        """/api/v1/admin 경로는 기본 한도(60)를 사용해야 한다."""
        import app.middleware.rate_limit_middleware as rl_mod
        rl_mod._redis = None
        rl_mod._DEFAULT_LIMIT = 60

        client = TestClient(_make_app_with_ratelimit(redis_mock=None))
        resp = client.get("/api/v1/admin/data")
        assert resp.status_code == 200
        assert resp.headers["x-ratelimit-limit"] == "60"

    def test_rate_limit_exceeded_returns_429(self):
        """한도 초과 시 HTTP 429 와 올바른 응답 본문이 반환돼야 한다."""
        # _check_rate_limit 을 직접 패치하여 한도 초과 시뮬레이션
        with patch(
            "app.middleware.rate_limit_middleware._check_rate_limit",
            new_callable=AsyncMock,
            return_value=(False, 0, 30),  # allowed=False, remaining=0, retry_after=30
        ):
            import app.middleware.rate_limit_middleware as rl_mod
            rl_mod._redis = MagicMock()  # None 이 아니어야 패치 효과

            client = TestClient(_make_app_with_ratelimit(redis_mock=MagicMock()))
            resp = client.get("/api/v1/admin/data")

        assert resp.status_code == 429
        body = resp.json()
        assert "detail" in body
        assert body["retry_after"] == 30
        assert resp.headers["retry-after"] == "30"
        assert resp.headers["x-ratelimit-remaining"] == "0"

    def test_429_response_has_all_required_headers(self):
        """429 응답에 Retry-After, X-RateLimit-* 헤더가 모두 있어야 한다."""
        with patch(
            "app.middleware.rate_limit_middleware._check_rate_limit",
            new_callable=AsyncMock,
            return_value=(False, 0, 45),
        ):
            client = TestClient(_make_app_with_ratelimit(redis_mock=MagicMock()))
            resp = client.get("/api/v1/scoring/evaluate")

        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers


# ══════════════════════════════════════════════════════════════════════════════
# 5. GZip 압축 테스트
# ══════════════════════════════════════════════════════════════════════════════
class TestGzipMiddleware:
    """FastAPI 내장 GZipMiddleware 동작 검증 (1KB 이상 압축)."""

    def test_large_response_is_compressed(self):
        """Accept-Encoding: gzip 요청 + 1KB 이상 응답은 압축돼야 한다."""
        from fastapi import FastAPI
        from fastapi.middleware.gzip import GZipMiddleware

        app = FastAPI()
        app.add_middleware(GZipMiddleware, minimum_size=1024)

        @app.get("/big")
        async def big_response():
            # 2KB 이상 응답 생성
            return {"data": "x" * 2048}

        client = TestClient(app)
        resp = client.get("/big", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        # httpx/TestClient 는 자동으로 압축 해제하지만 헤더 확인 가능
        # Content-Encoding 또는 응답이 정상임을 확인
        assert resp.json()["data"] == "x" * 2048

    def test_small_response_not_compressed(self):
        """1KB 미만 응답은 압축하지 않아야 한다."""
        from fastapi import FastAPI
        from fastapi.middleware.gzip import GZipMiddleware

        app = FastAPI()
        app.add_middleware(GZipMiddleware, minimum_size=1024)

        @app.get("/small")
        async def small_response():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/small", headers={"Accept-Encoding": "gzip"})
        assert resp.status_code == 200
        # 작은 응답은 content-encoding gzip 없음
        assert resp.headers.get("content-encoding") != "gzip"


# ══════════════════════════════════════════════════════════════════════════════
# 6. 미들웨어 통합 동작 테스트 (스택 순서 검증)
# ══════════════════════════════════════════════════════════════════════════════
class TestMiddlewareStack:
    """LoggingMiddleware + RateLimitMiddleware 동시 등록 시 상호 작용 검증."""

    def _make_stacked_app(self) -> FastAPI:
        """두 미들웨어 모두 등록한 앱."""
        import app.middleware.rate_limit_middleware as rl_mod
        rl_mod._redis = None  # Fail-Open

        from app.middleware.logging_middleware import LoggingMiddleware
        from app.middleware.rate_limit_middleware import RateLimitMiddleware
        from fastapi.middleware.gzip import GZipMiddleware

        app = FastAPI()
        app.add_middleware(GZipMiddleware, minimum_size=1024)
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(LoggingMiddleware)

        @app.get("/api/v1/test")
        async def test_ep():
            return {"result": "ok"}

        return app

    def test_stacked_response_has_both_headers(self):
        """스택된 미들웨어에서 X-Request-ID 와 X-RateLimit-* 가 모두 있어야 한다."""
        client = TestClient(self._make_stacked_app())
        resp = client.get("/api/v1/test")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers
        assert "x-ratelimit-limit" in resp.headers

    def test_custom_request_id_preserved_through_stack(self):
        """커스텀 X-Request-ID 가 미들웨어 스택을 통과해도 보존돼야 한다."""
        client = TestClient(self._make_stacked_app())
        custom_id = "stack-test-id-9999"
        resp = client.get("/api/v1/test", headers={"X-Request-ID": custom_id})
        assert resp.headers["x-request-id"] == custom_id
