"""
Alembic 환경 설정
=================
AsyncSQLAlchemy (asyncpg) 지원을 위해 동기 마이그레이션 실행 방식 사용.
SQLAlchemy 2.0 + asyncpg 환경에서 Alembic은 동기 방식으로 실행.

실행:
  docker compose exec api alembic upgrade head
  docker compose exec api alembic revision --autogenerate -m "description"
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── alembic.ini 로거 설정 ─────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── ORM 메타데이터 임포트 ─────────────────────────────────────────────────
# Base.metadata를 임포트해야 autogenerate가 모든 테이블을 감지함
from app.db.base import Base  # noqa: E402
import app.db.schemas  # noqa: E402,F401 — 모든 ORM 모델 등록

target_metadata = Base.metadata

# ── DATABASE_URL 환경변수 오버라이드 ──────────────────────────────────────
# asyncpg URL → 동기 psycopg2 URL로 변환 (alembic은 동기 엔진 사용)
_db_url = os.environ.get(
    "DATABASE_URL",
    config.get_main_option("sqlalchemy.url", ""),
)
# asyncpg → psycopg2 드라이버 전환
_sync_url = (
    _db_url
    .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    .replace("postgresql+aiosqlite:///", "sqlite:///")
)
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    """
    오프라인 모드 (DB 연결 없이 SQL 파일만 생성).
    실행: alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # PostgreSQL JSONB/UUID 렌더링 지원
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    온라인 모드 (실제 DB에 마이그레이션 적용).
    실행: alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,        # 컬럼 타입 변경 감지
            compare_server_default=True,  # 서버 기본값 변경 감지
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
