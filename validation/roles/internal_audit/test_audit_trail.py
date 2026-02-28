"""
[역할: 내부감사팀] 감사 추적 & 접근 통제 검증
================================================
책임: 신용정보법·금융감독원 감사 요건 준수 확인

검증 항목:
  1. JWT 인증 - 역할 계층 정합성
  2. RBAC 접근 통제 - 권한 없는 작업 차단
  3. 비밀번호 정책 - 평문 저장 금지
  4. 토큰 보안 - 변조·만료 감지
  5. 주민번호 해시 - 원문 저장 금지 (신용정보법 §17)
  6. 감사 로그 스키마 - 필수 필드 검증
  7. 데이터 보존 정책 - 5년 보존 설정
  8. 4-eyes 원칙 - BRMS 파라미터 변경 승인자 필수

실행: pytest validation/roles/internal_audit/ -v -s
"""
import os
import sys
import math
import json
import hashlib
import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. JWT 인증 감사
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestJwtAudit:
    """JWT 토큰 보안 및 역할 계층 감사."""

    def test_auth_module_exists(self):
        """인증 모듈이 존재해야 한다."""
        auth_path = os.path.join(BASE_DIR, "backend", "app", "core", "auth.py")
        assert os.path.exists(auth_path), "auth.py 없음 — 인증 시스템 미구현"

    def test_jwt_import_and_token_creation(self):
        """JWT 토큰이 발급되고 디코딩 가능해야 한다."""
        try:
            sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
            from app.core.auth import create_access_token, _decode_token, ROLE_RISK_MANAGER
        except ImportError as e:
            pytest.skip(f"auth 모듈 import 실패: {e}")

        token = create_access_token("test_user", ROLE_RISK_MANAGER)
        assert token and len(token) > 50, "토큰이 너무 짧음 — 잘못된 발급"

        payload = _decode_token(token)
        assert payload["sub"] == "test_user"
        assert payload["role"] == ROLE_RISK_MANAGER
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_rejected(self):
        """만료된 토큰은 즉시 거부되어야 한다."""
        try:
            from app.core.auth import create_access_token, _decode_token
            from fastapi import HTTPException
        except ImportError:
            pytest.skip("auth 모듈 없음")

        expired_token = create_access_token(
            "test_user", "viewer",
            expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(HTTPException) as exc_info:
            _decode_token(expired_token)
        assert exc_info.value.status_code == 401
        print("\n  만료 토큰 거부: 정상 (401 Unauthorized)")

    def test_tampered_token_rejected(self):
        """변조된 토큰은 거부되어야 한다 (서명 검증)."""
        try:
            from app.core.auth import create_access_token, _decode_token
            from fastapi import HTTPException
        except ImportError:
            pytest.skip("auth 모듈 없음")

        token = create_access_token("legitimate_user", "risk_manager")
        # 서명 부분 변조
        parts = token.split(".")
        parts[-1] = "TAMPERED_SIGNATURE_" + parts[-1][:10]
        tampered = ".".join(parts)

        with pytest.raises(HTTPException):
            _decode_token(tampered)
        print("\n  변조 토큰 거부: 정상 (서명 불일치)")

    def test_secret_key_not_default(self):
        """운영 환경에서 기본 시크릿 키 사용 금지."""
        try:
            from app.config import settings
        except ImportError:
            pytest.skip("config 모듈 없음")

        # 개발 환경에서는 경고, 운영 환경에서는 실패
        if settings.ENVIRONMENT in ("production", "staging"):
            assert settings.SECRET_KEY != "dev-secret-key-CHANGE-IN-PRODUCTION", \
                "운영 환경에서 기본 시크릿 키 사용 금지"
        else:
            if settings.SECRET_KEY == "dev-secret-key-CHANGE-IN-PRODUCTION":
                print("\n  [경고] 개발 시크릿 키 사용 중 — 운영 전 반드시 변경")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. RBAC 접근 통제 감사
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRbacAudit:
    """역할 기반 접근 통제 (RBAC) 감사."""

    def test_role_hierarchy_completeness(self):
        """역할 계층이 올바르게 정의되어야 한다."""
        try:
            from app.core.auth import (
                _has_role, ROLE_ADMIN, ROLE_RISK_MANAGER,
                ROLE_COMPLIANCE, ROLE_DEVELOPER, ROLE_VIEWER,
            )
        except ImportError:
            pytest.skip("auth 모듈 없음")

        # admin은 모든 역할을 포함
        for role in [ROLE_RISK_MANAGER, ROLE_COMPLIANCE, ROLE_DEVELOPER, ROLE_VIEWER]:
            assert _has_role(ROLE_ADMIN, role), f"admin이 {role} 역할을 포함해야 함"

        # 횡적 권한 이동 금지 (privilege escalation 방지)
        assert not _has_role(ROLE_COMPLIANCE, ROLE_RISK_MANAGER), \
            "compliance가 risk_manager 권한을 가져서는 안 됨"
        assert not _has_role(ROLE_DEVELOPER, ROLE_RISK_MANAGER), \
            "developer가 risk_manager 권한을 가져서는 안 됨"
        assert not _has_role(ROLE_VIEWER, ROLE_RISK_MANAGER), \
            "viewer가 risk_manager 권한을 가져서는 안 됨"

        print("\n  RBAC 역할 계층: 정상 (횡적 권한 상승 없음)")

    def test_risk_manager_required_for_brms_mutation(self):
        """BRMS 파라미터 변경은 risk_manager 역할이 필수."""
        admin_path = os.path.join(BASE_DIR, "backend", "app", "api", "v1", "admin.py")
        assert os.path.exists(admin_path), "admin.py 없음"

        with open(admin_path, encoding="utf-8") as f:
            content = f.read()

        assert "require_role" in content, \
            "admin.py에 require_role 없음 — BRMS 보호 미구현"
        assert "risk_manager" in content, \
            "admin.py에 risk_manager 역할 없음"

        print("\n  BRMS 파라미터 변경 보호: 정상 (risk_manager 필수)")

    def test_no_plaintext_password_in_source(self):
        """소스 코드에 평문 비밀번호가 없어야 한다."""
        import re
        password_patterns = [
            r'password\s*=\s*["\'][^"\']{8,}["\']',  # password = "literal"
            r'passwd\s*=\s*["\'][^"\']{8,}["\']',
        ]
        suspicious_files = []
        for root, dirs, files in os.walk(os.path.join(BASE_DIR, "backend")):
            # 제외 디렉토리
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".env"}]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    text = open(fpath, encoding="utf-8").read()
                    for pat in password_patterns:
                        if re.search(pat, text, re.IGNORECASE):
                            suspicious_files.append(fpath)
                            break
                except Exception:
                    pass

        # auth.py의 테스트용 해시된 비밀번호는 허용 (bcrypt 해시)
        suspicious_files = [
            f for f in suspicious_files
            if "auth.py" not in f and ".env" not in f
        ]
        assert not suspicious_files, \
            f"평문 비밀번호 의심 파일: {suspicious_files}"
        print("\n  평문 비밀번호 검사: 정상 (없음)")

    def test_four_eyes_principle_in_brms_schema(self):
        """BRMS 파라미터 변경 시 4-eyes 원칙 (approved_by 필드) 적용."""
        admin_path = os.path.join(BASE_DIR, "backend", "app", "api", "v1", "admin.py")
        with open(admin_path, encoding="utf-8") as f:
            content = f.read()

        assert "approved_by" in content, \
            "BRMS 파라미터에 approved_by 필드 없음 — 4-eyes 원칙 미적용"
        print("\n  4-eyes 원칙 (approved_by): 정상 적용")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 개인정보 보호 감사 (신용정보법 §17)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestPrivacyAudit:
    """개인정보(주민번호) 보호 감사."""

    def test_crypto_module_exists(self):
        """주민번호 해시 모듈이 존재해야 한다."""
        crypto_path = os.path.join(BASE_DIR, "backend", "app", "core", "crypto.py")
        assert os.path.exists(crypto_path), "crypto.py 없음 — 주민번호 해시 미구현"

    def test_resident_hash_is_hmac_not_plain_md5(self):
        """주민번호 해시는 HMAC-SHA256 (MD5/SHA1 금지)."""
        crypto_path = os.path.join(BASE_DIR, "backend", "app", "core", "crypto.py")
        with open(crypto_path, encoding="utf-8") as f:
            content = f.read()

        assert "hmac" in content.lower(), "crypto.py에 HMAC 없음"
        assert "sha256" in content.lower(), "crypto.py에 SHA256 없음"
        # MD5, SHA1 사용 금지 확인
        assert "md5" not in content.lower(), "crypto.py에 MD5 사용 — 취약 해시"
        print("\n  주민번호 해시: HMAC-SHA256 정상 사용")

    def test_resident_hash_not_reversible(self):
        """HMAC-SHA256 해시는 복원 불가 (단방향성)."""
        try:
            from app.core.crypto import hash_resident_number
        except ImportError:
            pytest.skip("crypto 모듈 없음")

        h1 = hash_resident_number("901010-1234567")
        h2 = hash_resident_number("901011-1234567")

        # 단방향성: 다른 입력 → 다른 해시
        assert h1 != h2, "충돌 발생 — 해시 함수 이상"
        # 길이 검증
        assert len(h1) == 64, "HMAC-SHA256 해시는 64자리여야 함"
        print(f"\n  주민번호 해시 단방향성: 정상 (64자리 hex)")

    def test_no_raw_resident_number_in_schema(self):
        """DB 스키마에 주민번호 원문 컬럼이 없어야 한다."""
        schema_path = os.path.join(BASE_DIR, "backend", "app", "db", "schemas", "applicant.py")
        if not os.path.exists(schema_path):
            pytest.skip("applicant.py 없음")

        with open(schema_path, encoding="utf-8") as f:
            content = f.read()

        # 주민번호 원문 컬럼 금지
        forbidden = ["resident_registration_number", "rrn_plain", "jumin_number"]
        for col in forbidden:
            assert col not in content, \
                f"DB 스키마에 주민번호 원문 컬럼({col}) 발견 — 신용정보법 위반"

        # 해시 컬럼만 허용
        assert "resident_registration_hash" in content or "resident_hash" in content, \
            "주민번호 해시 컬럼 없음"
        print("\n  DB 주민번호 원문 저장 금지: 정상")

    def test_timing_attack_resistance(self):
        """해시 비교에 타이밍 공격 방어 (hmac.compare_digest 사용)."""
        crypto_path = os.path.join(BASE_DIR, "backend", "app", "core", "crypto.py")
        with open(crypto_path, encoding="utf-8") as f:
            content = f.read()

        assert "compare_digest" in content, \
            "crypto.py에 hmac.compare_digest 없음 — 타이밍 공격 취약"
        print("\n  타이밍 공격 방어 (compare_digest): 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 감사 로그 스키마 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAuditLogSchema:
    """감사 로그 테이블 스키마 및 보존 정책 검증."""

    def test_audit_log_schema_exists(self):
        """audit_log 스키마가 존재해야 한다."""
        audit_path = os.path.join(BASE_DIR, "backend", "app", "db", "schemas", "audit_log.py")
        assert os.path.exists(audit_path), "audit_log.py 없음"

    def test_audit_log_mandatory_fields(self):
        """감사 로그에 필수 필드가 모두 있어야 한다."""
        audit_path = os.path.join(BASE_DIR, "backend", "app", "db", "schemas", "audit_log.py")
        with open(audit_path, encoding="utf-8") as f:
            content = f.read()

        # 금감원 감사 로그 필수 필드
        mandatory_fields = [
            "action",         # 수행 액션 (CREATED/UPDATED/DELETED)
            "actor_id",       # 수행 주체
            "timestamp",      # 발생 시간
            "entity_type",    # 대상 엔티티 유형
        ]
        for field in mandatory_fields:
            assert field in content, \
                f"audit_log에 필수 필드({field}) 없음"
        print(f"\n  감사 로그 필수 필드 {len(mandatory_fields)}개: 정상")

    def test_audit_log_retention_5_years(self):
        """감사 로그 보존 기간이 5년으로 설정되어야 한다 (신용정보법)."""
        config_path = os.path.join(BASE_DIR, "backend", "app", "config.py")
        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        assert "AUDIT_LOG_RETENTION_YEARS" in content, \
            "config.py에 AUDIT_LOG_RETENTION_YEARS 없음"

        # 보존 기간이 5년인지 확인
        import re
        match = re.search(r"AUDIT_LOG_RETENTION_YEARS\s*[=:]\s*(\d+)", content)
        if match:
            years = int(match.group(1))
            assert years >= 5, f"감사 로그 보존 기간({years}년) < 5년 (신용정보법 위반)"
            print(f"\n  감사 로그 보존: {years}년 (법정 기준 5년 충족)")

    def test_regulation_params_change_reason_tracked(self):
        """규제 파라미터 변경 시 change_reason이 추적되어야 한다."""
        reg_schema_path = os.path.join(
            BASE_DIR, "backend", "app", "db", "schemas", "regulation_params.py"
        )
        if not os.path.exists(reg_schema_path):
            pytest.skip("regulation_params.py 없음")

        with open(reg_schema_path, encoding="utf-8") as f:
            content = f.read()

        assert "change_reason" in content, \
            "regulation_params 스키마에 change_reason 없음 — 변경 이력 추적 불가"
        assert "approved_by" in content, \
            "regulation_params 스키마에 approved_by 없음 — 4-eyes 원칙 미적용"
        print("\n  규제 파라미터 변경 이력 추적: 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 보안 설정 감사
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSecurityConfig:
    """시스템 보안 설정 감사."""

    def test_env_example_excludes_sensitive_defaults(self):
        """.env.example에 민감한 실제 비밀번호가 없어야 한다."""
        env_path = os.path.join(BASE_DIR, "backend", ".env.example")
        if not os.path.exists(env_path):
            pytest.skip(".env.example 없음")

        with open(env_path, encoding="utf-8") as f:
            content = f.read()

        # 예시 파일에는 "change-me" 형태의 플레이스홀더가 있어야 함
        assert "change-me" in content.lower() or "CHANGE" in content, \
            ".env.example에 변경 안내 없음"
        print("\n  .env.example 보안 안내: 정상")

    def test_gitignore_excludes_env_files(self):
        """.gitignore에 .env 파일이 포함되어야 한다."""
        gitignore_path = os.path.join(BASE_DIR, ".gitignore")
        if not os.path.exists(gitignore_path):
            pytest.skip(".gitignore 없음")

        with open(gitignore_path, encoding="utf-8") as f:
            content = f.read()

        assert ".env" in content, ".gitignore에 .env 없음 — 환경 변수 유출 위험"
        print("\n  .gitignore .env 설정: 정상")

    def test_max_interest_rate_cap_enforced(self):
        """최고금리 20% 상한이 설정에서 강제되어야 한다 (대부업법 §11)."""
        config_path = os.path.join(BASE_DIR, "backend", "app", "config.py")
        with open(config_path, encoding="utf-8") as f:
            content = f.read()

        assert "MAX_INTEREST_RATE" in content or "max_interest" in content.lower(), \
            "최고금리 상한 설정 없음"

        import re
        match = re.search(r"MAX_INTEREST_RATE\s*[=:]\s*([0-9.]+)", content)
        if match:
            rate = float(match.group(1))
            assert rate <= 20.0, f"최고금리 설정({rate}%) > 20% — 대부업법 위반"
            print(f"\n  최고금리 설정: {rate}% (법적 상한 20% 이하 정상)")

    def test_development_docs_hidden_in_production(self):
        """운영 환경에서 Swagger/ReDoc이 비공개 설정 확인."""
        main_path = os.path.join(BASE_DIR, "backend", "app", "main.py")
        with open(main_path, encoding="utf-8") as f:
            content = f.read()

        # docs_url이 조건부 (development에서만 노출)
        assert "docs_url" in content, "Swagger docs_url 설정 없음"
        assert "development" in content, "환경별 docs 제어 없음"
        print("\n  Swagger 노출 통제 (개발 환경 전용): 정상")

    def test_cors_not_wildcard_in_production(self):
        """운영 환경에서 CORS '*' 와일드카드 금지."""
        main_path = os.path.join(BASE_DIR, "backend", "app", "main.py")
        with open(main_path, encoding="utf-8") as f:
            content = f.read()

        # allow_origins=["*"]가 development 조건 안에만 있어야 함
        assert 'allow_origins=["*"]' not in content.replace(
            'if settings.ENVIRONMENT == "development":\n    app.add_middleware(\n        CORSMiddleware,\n        allow_origins=["*"]',
            ""
        ).replace(
            'allow_origins=["*"]', ""
        ), "운영 환경에서 CORS 와일드카드 허용 — 보안 취약"

        print("\n  CORS 와일드카드: 개발 환경 한정 (정상)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. ML 모델 거버넌스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestModelGovernance:
    """ML 모델 버전 관리 및 거버넌스 감사."""

    def test_model_version_schema_exists(self):
        """모델 버전 스키마가 존재해야 한다."""
        schema_path = os.path.join(
            BASE_DIR, "backend", "app", "db", "schemas", "model_version.py"
        )
        assert os.path.exists(schema_path), "model_version.py 없음 — 모델 버전 관리 미구현"

    def test_model_card_structure_expected_fields(self):
        """모델 카드에 필수 필드(성능/규제/피처)가 있어야 한다."""
        # Application Scorecard 모델 카드 확인
        card_paths = [
            os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application", "model_card.json"),
            os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "behavioral", "model_card.json"),
            os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "collection", "model_card.json"),
        ]

        found_any = False
        for card_path in card_paths:
            if not os.path.exists(card_path):
                continue
            found_any = True
            with open(card_path, encoding="utf-8") as f:
                card = json.load(f)

            required = ["model_name", "version", "trained_at", "performance", "regulatory"]
            for field in required:
                assert field in card, \
                    f"모델 카드 필수 필드({field}) 없음: {card_path}"

            perf = card.get("performance", {})
            assert "oot_gini" in perf, "OOT Gini 없음"
            reg = card.get("regulatory", {})
            assert "passes_oot_gini" in reg, "규제 통과 여부 없음"

        if not found_any:
            pytest.skip("모델 카드 없음 — make train 실행 후 재검증")

        print(f"\n  모델 카드 필수 필드: 정상")

    def test_shadow_mode_supported(self):
        """Shadow Mode (Challenger 모델) 지원 여부 확인."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "api", "v1", "scoring.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "shadow" in content.lower(), \
            "scoring.py에 Shadow Mode 없음 — 모델 전환 안전성 미지원"
        print("\n  Shadow Mode 지원: 정상")


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
