"""
KCS (Korea Credit Scoring System) FastAPI 메인 앱
=====================================================
비대면 핵심 채널 기반 신용평가 시스템
개인 + 개인사업자 대상
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1 import admin, applications, auth, monitoring, scoring
from app.config import settings
from app.db.base import Base
import app.db.schemas  # noqa: F401 - 모든 ORM 모델을 Base.metadata에 등록
from app.db.session import AsyncSessionLocal, engine
from app.middleware import LoggingMiddleware, RateLimitMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 이벤트"""
    # ── 시작 ─────────────────────────────────────────────────────
    logger.info(f"KCS API 서버 시작 (환경: {settings.ENVIRONMENT})")

    # DB 테이블 생성 (개발 환경)
    if settings.ENVIRONMENT == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB 테이블 생성 완료")

        # regulation_params 초기 시드
        from app.core.seed_regulation_params import seed_regulation_params
        async with AsyncSessionLocal() as db:
            inserted = await seed_regulation_params(db)
            if inserted > 0:
                logger.info(f"규제 파라미터 시드 완료: {inserted}건")

    yield

    # ── 종료 ─────────────────────────────────────────────────────
    await engine.dispose()
    logger.info("KCS API 서버 종료")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "한국 신용평가 시스템 (KCS) API\n\n"
        "## 지원 상품\n"
        "- 신용대출 (개인/개인사업자)\n"
        "- 주택담보대출\n"
        "- 소액마이크로론\n\n"
        "## 특수 세그먼트\n"
        "- SEG-DR: 의사/치과의사/한의사\n"
        "- SEG-JD: 변호사/법무사/회계사\n"
        "- SEG-ART: 예술인복지재단 등록 예술인\n"
        "- SEG-YTH: 청년(만 19-34세)\n"
        "- SEG-MOU: 협약기업 근로자\n"
    ),
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
)

# ── 미들웨어 등록 순서: 바깥쪽(먼저 실행)부터 안쪽 순 ──────────────

# 1. Gzip 압축 (1kb 이상 응답 압축)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 2. Rate Limiting (Redis 슬라이딩 윈도우)
app.add_middleware(RateLimitMiddleware)

# 3. 요청/응답 구조화 로깅 + Correlation ID
app.add_middleware(LoggingMiddleware)

# 4. CORS (개발: 전체 허용, 운영: 도메인 제한)
if settings.ENVIRONMENT == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    allowed_origins = [o.strip() for o in
                       __import__("os").getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

# API 라우터
app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["인증 (JWT)"],
)
app.include_router(
    applications.router,
    prefix=f"{settings.API_V1_PREFIX}/applications",
    tags=["대출 신청"],
)
app.include_router(
    scoring.router,
    prefix=f"{settings.API_V1_PREFIX}/scoring",
    tags=["신용평가"],
)
app.include_router(
    admin.router,
    prefix=f"{settings.API_V1_PREFIX}/admin",
    tags=["관리자 (규제 파라미터)"],
)
app.include_router(
    monitoring.router,
    prefix=f"{settings.API_V1_PREFIX}/monitoring",
    tags=["모니터링 (PSI/칼리브레이션)"],
)


@app.get("/health", tags=["시스템"])
async def health():
    return {"status": "ok", "service": "kcs-api", "version": "1.1.0"}


# ── Prometheus 메트릭 (/metrics) ──────────────────────────────────────────
# k8s annotation: prometheus.io/scrape=true, prometheus.io/path=/metrics
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,          # ENABLE_METRICS=true 로 활성화
    env_var_name="ENABLE_METRICS",
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app, include_in_schema=False, tags=["시스템"])
