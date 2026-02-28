"""
주민등록번호 해시 유틸리티 (신용정보법 준수)
=============================================
주민등록번호는 원문을 저장하지 않고 HMAC-SHA256 해시로 저장.

운영 환경:  HashiCorp Vault에서 서명 키 조회
개발 환경:  RESIDENT_HASH_KEY 환경 변수 또는 기본 개발 키 사용

주의: 개발 키는 반드시 운영 배포 전 교체 필요.
"""
import hashlib
import hmac
import os

# 개발용 기본 키 (운영에서는 Vault 주입)
_DEV_KEY = b"kcs-dev-resident-hash-key-CHANGE-IN-PROD"


def _get_signing_key() -> bytes:
    """
    서명 키 조회 우선순위:
    1. RESIDENT_HASH_KEY 환경 변수 (운영/스테이징)
    2. Vault 클라이언트 (미래 확장)
    3. 개발용 기본 키
    """
    env_key = os.getenv("RESIDENT_HASH_KEY")
    if env_key:
        return env_key.encode()
    return _DEV_KEY


def hash_resident_number(resident_number: str) -> str:
    """
    주민등록번호 → HMAC-SHA256 해시 (hex 64자리).

    동일한 주민등록번호는 항상 같은 해시를 생성하므로
    신청 이력 조회 및 중복 방지에 사용 가능.

    Args:
        resident_number: 주민등록번호 (하이픈 포함/미포함 모두 허용)

    Returns:
        64자리 16진수 문자열
    """
    normalized = resident_number.replace("-", "").strip()
    key = _get_signing_key()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


def verify_resident_hash(resident_number: str, expected_hash: str) -> bool:
    """해시 일치 여부 확인 (타이밍 공격 방지: hmac.compare_digest 사용)."""
    actual = hash_resident_number(resident_number)
    return hmac.compare_digest(actual, expected_hash)
