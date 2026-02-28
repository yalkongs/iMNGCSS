"""
인증/인가 단위 테스트
=====================
JWT 토큰 생성/검증, RBAC 역할 계층 테스트.
외부 의존성 없음 (DB/Redis 불필요).
"""
import pytest
from datetime import timedelta

from app.core.auth import (
    authenticate_user,
    create_access_token,
    verify_password,
    _has_role,
    _decode_token,
    ROLE_ADMIN,
    ROLE_RISK_MANAGER,
    ROLE_COMPLIANCE,
    ROLE_DEVELOPER,
    ROLE_VIEWER,
)
from app.config import settings


# ── 비밀번호 검증 ──────────────────────────────────────────────────────────

class TestPasswordVerification:
    def test_authenticate_risk_manager_success(self):
        user = authenticate_user("risk_manager", "KCS@risk2024")
        assert user is not None
        assert user["role"] == ROLE_RISK_MANAGER

    def test_authenticate_admin_success(self):
        user = authenticate_user("admin", "KCS@admin2024")
        assert user is not None
        assert user["role"] == ROLE_ADMIN

    def test_authenticate_wrong_password(self):
        user = authenticate_user("risk_manager", "WrongPassword!")
        assert user is None

    def test_authenticate_unknown_user(self):
        user = authenticate_user("hacker", "any_password")
        assert user is None

    def test_all_demo_accounts_valid(self):
        """데모 계정 4종 전부 인증 성공."""
        accounts = [
            ("admin", "KCS@admin2024"),
            ("risk_manager", "KCS@risk2024"),
            ("compliance", "KCS@comp2024"),
            ("developer", "KCS@dev2024"),
        ]
        for username, password in accounts:
            user = authenticate_user(username, password)
            assert user is not None, f"{username} 인증 실패"


# ── JWT 토큰 발급/검증 ─────────────────────────────────────────────────────

class TestJwtToken:
    def test_create_and_decode_token(self):
        token = create_access_token("risk_manager", ROLE_RISK_MANAGER)
        payload = _decode_token(token)
        assert payload["sub"] == "risk_manager"
        assert payload["role"] == ROLE_RISK_MANAGER

    def test_token_has_exp_and_iat(self):
        token = create_access_token("admin", ROLE_ADMIN)
        payload = _decode_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_custom_expiry(self):
        token = create_access_token(
            "compliance", ROLE_COMPLIANCE,
            expires_delta=timedelta(minutes=5),
        )
        payload = _decode_token(token)
        assert payload["sub"] == "compliance"

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _decode_token("not.a.valid.jwt")
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises(self):
        from fastapi import HTTPException
        token = create_access_token("admin", ROLE_ADMIN)
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException):
            _decode_token(tampered)

    def test_expired_token_raises(self):
        from fastapi import HTTPException
        token = create_access_token(
            "developer", ROLE_DEVELOPER,
            expires_delta=timedelta(seconds=-1),  # 이미 만료
        )
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(token)
        assert exc_info.value.status_code == 401


# ── RBAC 역할 계층 ─────────────────────────────────────────────────────────

class TestRbacHierarchy:
    def test_admin_has_all_roles(self):
        """admin은 모든 역할을 포함한다."""
        for role in [ROLE_RISK_MANAGER, ROLE_COMPLIANCE, ROLE_DEVELOPER, ROLE_VIEWER]:
            assert _has_role(ROLE_ADMIN, role), f"admin은 {role} 역할을 포함해야 함"

    def test_admin_has_itself(self):
        assert _has_role(ROLE_ADMIN, ROLE_ADMIN)

    def test_risk_manager_has_viewer(self):
        assert _has_role(ROLE_RISK_MANAGER, ROLE_VIEWER)

    def test_risk_manager_not_compliance(self):
        assert not _has_role(ROLE_RISK_MANAGER, ROLE_COMPLIANCE)

    def test_compliance_has_viewer(self):
        assert _has_role(ROLE_COMPLIANCE, ROLE_VIEWER)

    def test_compliance_not_risk_manager(self):
        assert not _has_role(ROLE_COMPLIANCE, ROLE_RISK_MANAGER)

    def test_developer_has_viewer(self):
        assert _has_role(ROLE_DEVELOPER, ROLE_VIEWER)

    def test_viewer_no_other_roles(self):
        assert not _has_role(ROLE_VIEWER, ROLE_RISK_MANAGER)
        assert not _has_role(ROLE_VIEWER, ROLE_COMPLIANCE)
        assert not _has_role(ROLE_VIEWER, ROLE_DEVELOPER)

    def test_same_role_always_true(self):
        for role in [ROLE_RISK_MANAGER, ROLE_COMPLIANCE, ROLE_DEVELOPER, ROLE_VIEWER]:
            assert _has_role(role, role)


# ── 암호화 유틸리티 ────────────────────────────────────────────────────────

class TestCryptoUtils:
    def test_resident_hash_deterministic(self):
        """동일 입력 → 동일 해시."""
        from app.core.crypto import hash_resident_number
        h1 = hash_resident_number("901010-1234567")
        h2 = hash_resident_number("901010-1234567")
        assert h1 == h2

    def test_resident_hash_ignores_hyphen(self):
        """하이픈 유무 상관없이 동일 해시."""
        from app.core.crypto import hash_resident_number
        h1 = hash_resident_number("9010101234567")
        h2 = hash_resident_number("901010-1234567")
        assert h1 == h2

    def test_resident_hash_different_inputs(self):
        from app.core.crypto import hash_resident_number
        h1 = hash_resident_number("901010-1234567")
        h2 = hash_resident_number("901010-7654321")
        assert h1 != h2

    def test_resident_hash_length(self):
        """HMAC-SHA256 → 64자리 hex."""
        from app.core.crypto import hash_resident_number
        h = hash_resident_number("901010-1234567")
        assert len(h) == 64

    def test_verify_resident_hash(self):
        from app.core.crypto import hash_resident_number, verify_resident_hash
        number = "901010-1234567"
        h = hash_resident_number(number)
        assert verify_resident_hash(number, h)
        assert not verify_resident_hash("000000-0000000", h)
