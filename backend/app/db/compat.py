"""
DB 타입 호환 레이어
===================
PostgreSQL: JSONB (바이너리 JSON, GIN 인덱스 지원)
SQLite (테스트): JSON (동등한 시맨틱)

UUID: TypeDecorator 기반으로 SQLite/PostgreSQL 모두 문자열로 저장.
INET: PostgreSQL 전용, SQLite 폴백은 String(45).
"""
import os
import uuid as _uuid_mod

from sqlalchemy import String
from sqlalchemy import types as _sa_types
from sqlalchemy.dialects import postgresql as _pg

_db_url = os.getenv("DATABASE_URL", "postgresql://")
_is_postgres = _db_url.startswith("postgresql")


class UUID(_sa_types.TypeDecorator):
    """UUID → VARCHAR(36) TypeDecorator (SQLite/PostgreSQL 호환).

    PostgreSQL에서는 네이티브 UUID 컬럼으로, SQLite에서는 VARCHAR(36)으로 동작한다.
    Python 값은 항상 str 또는 uuid.UUID 모두 수용한다.
    """
    impl = String(36)
    cache_ok = True

    def __init__(self, *args, as_uuid: bool = True, **kwargs):
        self.as_uuid = as_uuid
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_pg.UUID(as_uuid=False))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if self.as_uuid:
            return _uuid_mod.UUID(str(value))
        return str(value)


if _is_postgres:
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401
    try:
        from sqlalchemy.dialects.postgresql import INET  # noqa: F401
    except ImportError:
        INET = String(45)  # type: ignore[assignment]
else:
    from sqlalchemy import JSON as JSONB  # noqa: F401
    INET = String(45)  # type: ignore[assignment]
