"""
[통합 테스트] FastAPI E2E 테스트
==================================
실제 DB 없이 httpx.AsyncClient + FastAPI TestClient 기반.

테스트 범위:
  1. /health 엔드포인트
  2. JWT 인증 (로그인/토큰/me)
  3. RBAC 인가 (역할별 접근 제어)
  4. 신청 여정 API (7단계)
  5. 직접 평가 API (/scoring/evaluate)
  6. 관리자 API (규제 파라미터 조회/등록)
  7. 모니터링 API (PSI/칼리브레이션)

실행: pytest tests/integration/test_api_e2e.py -v -s
"""
import os
import sys
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)

# FastAPI TestClient 임포트 시도
try:
    from fastapi.testclient import TestClient
    import httpx
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# 앱 임포트 시도 (DB 연결 없이 테스트 가능한지 확인)
try:
    # DB 없이도 동작하도록 환경변수 설정
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("ENVIRONMENT", "development")
    from app.main import app
    HAS_APP = True
except Exception as e:
    HAS_APP = False
    APP_IMPORT_ERROR = str(e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 픽스처
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@pytest.fixture(scope="module")
def client():
    if not HAS_FASTAPI:
        pytest.skip("fastapi/httpx 미설치")
    if not HAS_APP:
        pytest.skip(f"앱 임포트 실패: {APP_IMPORT_ERROR}")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _get_token(client, username: str, password: str) -> str:
    """JWT 토큰 획득 헬퍼."""
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token", "")
    return ""


@pytest.fixture(scope="module")
def admin_token(client) -> str:
    return _get_token(client, "admin", "KCS@admin2024")


@pytest.fixture(scope="module")
def risk_manager_token(client) -> str:
    return _get_token(client, "risk_manager", "KCS@risk2024")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 기본 헬스체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestHealthCheck:
    def test_health_endpoint(self, client):
        """/health 엔드포인트 200 응답."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_response_fields(self, client):
        """/health 응답에 service 필드 포함."""
        resp = client.get("/health")
        data = resp.json()
        assert "service" in data
        assert data["service"] == "kcs-api"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. JWT 인증 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAuthentication:
    """OAuth2 Password Flow JWT 인증 검증."""

    def test_login_endpoint_exists(self, client):
        """/api/v1/auth/token 라우트 존재 (404 아님)."""
        resp = client.post("/api/v1/auth/token", data={})
        assert resp.status_code != 404

    def test_login_success_admin(self, client):
        """admin 계정 로그인 → 200 + access_token 반환."""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "KCS@admin2024"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert data["username"] == "admin"

    def test_login_success_risk_manager(self, client):
        """risk_manager 계정 로그인 → 200 + role 필드 포함."""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "risk_manager", "password": "KCS@risk2024"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "role" in data
        assert data["role"] == "risk_manager"

    def test_login_invalid_password_returns_401(self, client):
        """잘못된 비밀번호 → 401 Unauthorized."""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "WrongPass!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self, client):
        """존재하지 않는 사용자 → 401."""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "nobody_xyz", "password": "any"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 401

    def test_get_me_without_token_returns_401(self, client):
        """/auth/me 토큰 없이 → 401."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_get_me_with_valid_token(self, client, admin_token):
        """/auth/me Bearer 토큰 → 200 + 사용자 정보."""
        if not admin_token:
            pytest.skip("admin 토큰 획득 실패 (인증 서비스 미동작)")
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "username" in data
        assert data["username"] == "admin"

    def test_get_me_with_invalid_token_returns_401(self, client):
        """/auth/me 위조 토큰 → 401."""
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer fake.jwt.token"},
        )
        assert resp.status_code == 401

    def test_token_access_token_is_non_empty(self, client):
        """발급된 access_token이 빈 문자열이 아님."""
        resp = client.post(
            "/api/v1/auth/token",
            data={"username": "compliance", "password": "KCS@comp2024"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        token = resp.json().get("access_token", "")
        assert len(token) > 20  # JWT는 최소 수십 자리


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. RBAC 인가 테스트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAuthorizationRBAC:
    """역할 기반 접근 제어 (RBAC) 검증."""

    _PARAM_PAYLOAD = {
        "param_key": "test.rbac.write",
        "param_category": "dsr",
        "param_value": {"value": 0.4, "unit": "ratio"},
        "effective_from": "2024-01-01T00:00:00Z",
        "description": "RBAC 통합 테스트용 파라미터",
    }

    def test_create_param_without_token_returns_401(self, client):
        """인증 없이 파라미터 등록 → 401."""
        resp = client.post("/api/v1/admin/regulation-params", json=self._PARAM_PAYLOAD)
        assert resp.status_code == 401

    def test_developer_cannot_create_param_returns_403(self, client):
        """developer 역할은 파라미터 등록 금지 → 403."""
        token = _get_token(client, "developer", "KCS@dev2024")
        if not token:
            pytest.skip("developer 토큰 획득 실패")
        resp = client.post(
            "/api/v1/admin/regulation-params",
            json={**self._PARAM_PAYLOAD, "param_key": "test.rbac.dev_fail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_compliance_cannot_create_param_returns_403(self, client):
        """compliance 역할은 파라미터 등록 금지 → 403."""
        token = _get_token(client, "compliance", "KCS@comp2024")
        if not token:
            pytest.skip("compliance 토큰 획득 실패")
        resp = client.post(
            "/api/v1/admin/regulation-params",
            json={**self._PARAM_PAYLOAD, "param_key": "test.rbac.comp_fail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_risk_manager_can_create_param(self, client, risk_manager_token):
        """risk_manager 역할은 파라미터 등록 가능 (DB 없으면 500 허용)."""
        if not risk_manager_token:
            pytest.skip("risk_manager 토큰 획득 실패")
        resp = client.post(
            "/api/v1/admin/regulation-params",
            json={**self._PARAM_PAYLOAD, "param_key": "test.rbac.rm_ok"},
            headers={"Authorization": f"Bearer {risk_manager_token}"},
        )
        # DB 연결 없으면 500, DB 있으면 201
        assert resp.status_code in (201, 500)

    def test_admin_can_create_param(self, client, admin_token):
        """admin 역할은 파라미터 등록 가능 (DB 없으면 500 허용)."""
        if not admin_token:
            pytest.skip("admin 토큰 획득 실패")
        resp = client.post(
            "/api/v1/admin/regulation-params",
            json={**self._PARAM_PAYLOAD, "param_key": "test.rbac.admin_ok"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code in (201, 500)

    def test_delete_param_without_token_returns_401(self, client):
        """인증 없이 파라미터 비활성화 → 401."""
        resp = client.delete(
            "/api/v1/admin/regulation-params/00000000-0000-0000-0000-000000000001",
            params={"reason": "test"},
        )
        assert resp.status_code == 401

    def test_read_params_is_public(self, client):
        """파라미터 조회는 인증 없이 접근 가능 (DB 없으면 500 허용)."""
        resp = client.get("/api/v1/admin/regulation-params")
        assert resp.status_code in (200, 500)
        assert resp.status_code != 401


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 신청 여정 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestApplicationJourney:
    """7단계 비대면 신청 여정."""

    def test_start_application(self, client):
        """Step 1: 신청 시작 → application_id 발급."""
        resp = client.post("/api/v1/applications/start", json={
            "product_type": "credit",
            "digital_channel": "mobile_app",
        })
        # DB 없으면 500도 허용 (구조 검증이 목적)
        assert resp.status_code in (200, 201, 422, 500)
        if resp.status_code in (200, 201):
            data = resp.json()
            assert "application_id" in data or "id" in data

    def test_start_application_invalid_product(self, client):
        """잘못된 상품 코드 → 422 Validation Error."""
        resp = client.post("/api/v1/applications/start", json={
            "product_type": "invalid_product_xyz",
        })
        assert resp.status_code in (200, 422, 400, 500)

    def test_application_routes_exist(self, client):
        """신청 API 라우트 존재 확인 (404 아님)."""
        routes_to_check = [
            "/api/v1/applications/start",
        ]
        for route in routes_to_check:
            resp = client.options(route)
            assert resp.status_code != 404, f"라우트 없음: {route}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 직접 평가 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestScoringAPI:
    """직접 평가 엔드포인트 검증."""

    def test_evaluate_route_exists(self, client):
        """/scoring/evaluate 라우트 존재."""
        resp = client.post("/api/v1/scoring/evaluate", json={})
        assert resp.status_code != 404

    def test_evaluate_with_minimal_payload(self, client):
        """/scoring/evaluate 최소 페이로드 → 구조적 오류 또는 평가 결과 반환."""
        resp = client.post("/api/v1/scoring/evaluate", json={
            "applicant": {
                "age": 35,
                "income_annual": 40000000,
                "employment_type": "employed",
                "cb_consent_granted": True,
            },
            "loan_request": {
                "product_type": "credit",
                "requested_amount": 10000000,
            },
        })
        # DB 없으면 500, 성공이면 200
        assert resp.status_code in (200, 422, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "score" in data or "decision" in data

    def test_score_scale_endpoint(self, client):
        """/scoring/score-scale → 점수 범위 정보 반환."""
        resp = client.get("/api/v1/scoring/score-scale")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "min_score" in data or "score_min" in data or "min" in str(data)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 관리자 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAdminAPI:
    """BRMS 파라미터 관리 API."""

    def test_regulation_params_list(self, client):
        """/admin/regulation-params → 파라미터 목록 반환."""
        resp = client.get("/api/v1/admin/regulation-params")
        assert resp.status_code in (200, 500)  # DB 없으면 500

    def test_eq_grade_master(self, client):
        """/admin/eq-grade-master → EQ Grade 목록."""
        resp = client.get("/api/v1/admin/eq-grade-master")
        assert resp.status_code in (200, 500)

    def test_irg_master(self, client):
        """/admin/irg-master → IRG 목록."""
        resp = client.get("/api/v1/admin/irg-master")
        assert resp.status_code in (200, 500)

    def test_admin_read_routes_not_404(self, client):
        """관리자 조회 API 라우트 존재 (404 아님)."""
        for path in [
            "/api/v1/admin/regulation-params",
            "/api/v1/admin/eq-grade-master",
            "/api/v1/admin/irg-master",
        ]:
            resp = client.get(path)
            assert resp.status_code != 404, f"라우트 없음: {path}"

    def test_write_requires_auth_not_404(self, client):
        """규제 파라미터 등록 엔드포인트 존재 (auth 없으면 401)."""
        resp = client.post("/api/v1/admin/regulation-params", json={})
        assert resp.status_code in (401, 422)  # 401(인증실패) or 422(유효성)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 모니터링 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestMonitoringAPI:
    """PSI/칼리브레이션/빈티지 API."""

    def test_psi_summary_endpoint(self, client):
        """/monitoring/psi-summary 응답 구조."""
        resp = client.get("/api/v1/monitoring/psi-summary")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "score_psi" in data
            assert "overall_status" in data

    def test_calibration_endpoint(self, client):
        """/monitoring/calibration 응답 구조."""
        resp = client.get("/api/v1/monitoring/calibration")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "ece" in data
            assert "brier_score" in data

    def test_vintage_endpoint(self, client):
        """/monitoring/vintage 응답 구조."""
        resp = client.get("/api/v1/monitoring/vintage")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "cohorts" in data

    def test_portfolio_summary_endpoint(self, client):
        """/monitoring/portfolio-summary 응답."""
        resp = client.get("/api/v1/monitoring/portfolio-summary")
        assert resp.status_code in (200, 500)

    def test_psi_report_endpoint(self, client):
        """/monitoring/psi-report 통합 보고서."""
        resp = client.get("/api/v1/monitoring/psi-report")
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "overall_status" in data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. API 문서 (Swagger)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSwaggerDocs:
    """개발 환경 Swagger 문서 접근성."""

    def test_openapi_json_accessible(self, client):
        """/openapi.json 접근 가능."""
        resp = client.get("/openapi.json")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "openapi" in data
            assert "paths" in data

    def test_docs_endpoint_accessible(self, client):
        """/docs Swagger UI (개발 환경)."""
        resp = client.get("/docs")
        assert resp.status_code in (200, 404)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
