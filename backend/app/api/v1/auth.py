"""
인증 API (/api/v1/auth)
========================
JWT 토큰 발급 (OAuth2 Password Flow).

Swagger UI에서 직접 로그인 테스트 가능:
  - POST /api/v1/auth/token  →  username + password → access_token
  - GET  /api/v1/auth/me     →  현재 사용자 정보

데모 계정:
  risk_manager / KCS@risk2024   ← 규제 파라미터 등록/삭제 권한
  compliance   / KCS@comp2024   ← 모니터링 조회 권한
  developer    / KCS@dev2024    ← 모델 성능 지표 조회
  admin        / KCS@admin2024  ← 전체 권한
"""
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.config import settings
from app.core.auth import authenticate_user, create_access_token, get_current_user

router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 초
    role: str
    username: str


class UserInfoResponse(BaseModel):
    username: str
    role: str
    full_name: str


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="로그인 (JWT 발급)",
    description=(
        "OAuth2 Password Flow로 JWT 액세스 토큰을 발급합니다.\n\n"
        "**데모 계정:**\n"
        "- `risk_manager` / `KCS@risk2024` — 규제 파라미터 관리\n"
        "- `compliance` / `KCS@comp2024` — 모니터링/감사\n"
        "- `developer` / `KCS@dev2024` — 모델 성능 조회\n"
        "- `admin` / `KCS@admin2024` — 전체 권한\n"
    ),
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expire_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    token = create_access_token(
        subject=user["username"],
        role=user["role"],
        expires_delta=timedelta(seconds=expire_seconds),
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expire_seconds,
        role=user["role"],
        username=user["username"],
    )


@router.get(
    "/me",
    response_model=UserInfoResponse,
    summary="현재 사용자 정보",
)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UserInfoResponse:
    return UserInfoResponse(
        username=current_user["username"],
        role=current_user["role"],
        full_name=current_user["full_name"],
    )
