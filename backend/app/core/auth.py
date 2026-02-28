"""
JWT 인증 및 RBAC (역할 기반 접근 제어)
========================================
python-jose + passlib 기반 JWT 토큰 발급/검증.

역할 체계:
  risk_manager  - 규제 파라미터 등록/비활성화 (BRMS 변경 권한)
  compliance    - 모니터링 결과 조회, 공정성 감사
  developer     - 모델 카드 조회, 성능 지표
  viewer        - 읽기 전용 (규제 파라미터 조회)
  admin         - 모든 권한 포함

데모 계정 (운영에서는 DB 기반으로 교체):
  risk_manager / KCS@risk2024
  compliance   / KCS@comp2024
  developer    / KCS@dev2024
  admin        / KCS@admin2024
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# ── 비밀번호 해시 ──────────────────────────────────────────────
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 Bearer 스키마 ───────────────────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# ── 역할 상수 ─────────────────────────────────────────────────
ROLE_ADMIN = "admin"
ROLE_RISK_MANAGER = "risk_manager"
ROLE_COMPLIANCE = "compliance"
ROLE_DEVELOPER = "developer"
ROLE_VIEWER = "viewer"

# 역할 포함 관계: admin은 모든 역할을 포함
_ROLE_HIERARCHY: dict[str, set[str]] = {
    ROLE_ADMIN: {ROLE_RISK_MANAGER, ROLE_COMPLIANCE, ROLE_DEVELOPER, ROLE_VIEWER},
    ROLE_RISK_MANAGER: {ROLE_VIEWER},
    ROLE_COMPLIANCE: {ROLE_VIEWER},
    ROLE_DEVELOPER: {ROLE_VIEWER},
    ROLE_VIEWER: set(),
}

# ── 데모 사용자 DB (운영: PostgreSQL users 테이블로 교체) ──────
_DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "hashed_password": _pwd_ctx.hash("KCS@admin2024"),
        "role": ROLE_ADMIN,
        "full_name": "시스템 관리자",
    },
    "risk_manager": {
        "username": "risk_manager",
        "hashed_password": _pwd_ctx.hash("KCS@risk2024"),
        "role": ROLE_RISK_MANAGER,
        "full_name": "리스크 관리자",
    },
    "compliance": {
        "username": "compliance",
        "hashed_password": _pwd_ctx.hash("KCS@comp2024"),
        "role": ROLE_COMPLIANCE,
        "full_name": "준법감시 담당자",
    },
    "developer": {
        "username": "developer",
        "hashed_password": _pwd_ctx.hash("KCS@dev2024"),
        "role": ROLE_DEVELOPER,
        "full_name": "개발자",
    },
}


# ── 비밀번호 검증 ──────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = _DEMO_USERS.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


# ── JWT 발급 ───────────────────────────────────────────────────

def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ── JWT 검증 ───────────────────────────────────────────────────

def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err


# ── FastAPI 의존성 ──────────────────────────────────────────────

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    """현재 인증된 사용자 정보 반환."""
    payload = _decode_token(token)
    username: str | None = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰에 사용자 정보가 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = _DEMO_USERS.get(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 토큰의 역할과 DB 역할 일치 확인 (역할 변경 후 구 토큰 차단)
    if payload.get("role") != user["role"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰 역할이 변경되었습니다. 재로그인하세요.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _has_role(user_role: str, required_role: str) -> bool:
    """역할 포함 관계 확인 (admin은 모든 역할 보유)."""
    if user_role == required_role:
        return True
    return required_role in _ROLE_HIERARCHY.get(user_role, set())


def require_role(*roles: str):
    """
    RBAC 의존성 팩토리.

    사용 예:
        @router.post("/sensitive")
        async def endpoint(user = Depends(require_role("risk_manager"))):
            ...
    """
    async def _check(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        user_role = user.get("role", "")
        for required in roles:
            if _has_role(user_role, required):
                return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"권한이 부족합니다. 필요 역할: {' 또는 '.join(roles)}",
        )
    return _check
