"""
KCS API 부하 테스트 (Locust)
==============================
실제 사용자 행동 패턴 기반 부하 테스트.

설치: pip install locust
실행:
  # Web UI (http://localhost:8089)
  locust -f tests/performance/locustfile.py --host=http://localhost:8000

  # 헤드리스 (CI 용)
  locust -f tests/performance/locustfile.py \
    --host=http://localhost:8000 \
    --users=50 --spawn-rate=5 --run-time=60s \
    --headless --only-summary

목표 SLA (은행 인터넷뱅킹 기준):
  - p50  ≤  200ms
  - p95  ≤  500ms
  - p99  ≤ 1000ms
  - 에러율 < 1%
  - TPS  ≥  100 req/s (peak)
"""
import random
import json
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

# ── 데모 토큰 캐시 (로그인 오버헤드 최소화) ────────────────────────
_TOKEN_CACHE: dict[str, str] = {}

# ── 테스트 사용자 프로파일 풀 ──────────────────────────────────────
_CB_SCORES = [400, 450, 500, 550, 600, 650, 680, 720, 750, 800]
_INCOMES   = [2000, 2500, 3000, 3500, 4000, 5000, 6000, 8000]
_AMOUNTS   = [10_000_000, 20_000_000, 30_000_000, 50_000_000, 100_000_000]
_SEGMENTS  = [None, "SEG-DR", "SEG-JD", "SEG-YTH", "SEG-MOU-TECH"]


def _scoring_payload(
    cb_score: int | None = None,
    income: int | None = None,
    amount: int | None = None,
    segment: str | None = None,
) -> dict:
    """신용평가 요청 페이로드 생성."""
    cb = cb_score or random.choice(_CB_SCORES)
    inc = income or random.choice(_INCOMES)
    amt = amount or random.choice(_AMOUNTS)
    delinq = random.choices([0, 1, 2, 5], weights=[70, 15, 10, 5])[0]
    dsr = round(random.uniform(0.10, 0.50), 2)

    payload: dict = {
        "resident_hash": f"load_test_{random.randint(1, 100_000):06d}",
        "product_type": random.choice(["credit", "mortgage", "micro"]),
        "requested_amount": amt,
        "requested_term_months": random.choice([12, 24, 36, 60]),
        "cb_score": cb,
        "income_annual_wan": inc,
        "delinquency_count_12m": delinq,
        "employment_type": random.choice(["employed", "self_employed", "unemployed"]),
        "employment_duration_months": random.randint(0, 120),
        "existing_loan_monthly_payment": random.randint(0, 1_500_000),
        "open_loan_count": random.randint(0, 10),
        "total_loan_balance": random.randint(0, 100_000_000),
        "inquiry_count_3m": random.randint(0, 10),
        "worst_delinquency_status": random.choice([0, 0, 0, 1, 2, 3]),
        "age": random.randint(20, 65),
        "dsr_ratio": dsr,
    }
    if segment:
        payload["segment_code"] = segment
    return payload


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 일반 사용자 (대출 신청자)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class BorrowerUser(HttpUser):
    """일반 차주: 신용 조회 + 신청 여정 (가장 많은 트래픽)."""

    wait_time = between(1, 3)   # 사용자 간 대기 시간 1~3초
    weight = 70                 # 전체 가상 사용자 중 70%

    def on_start(self):
        """세션 시작: 헬스체크로 서버 준비 확인."""
        self.client.get("/health")

    @task(50)
    def direct_scoring(self):
        """직접 신용평가 (가장 빈번한 요청)."""
        payload = _scoring_payload()
        with self.client.post(
            "/api/v1/scoring/evaluate",
            json=payload,
            name="/api/v1/scoring/evaluate [general]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if "score" not in data:
                    resp.failure("응답에 score 없음")
                elif not (300 <= data["score"] <= 900):
                    resp.failure(f"점수 범위 이상: {data['score']}")
            elif resp.status_code == 422:
                resp.failure(f"Validation 오류: {resp.text[:100]}")

    @task(20)
    def good_borrower_scoring(self):
        """우량 차주 평가 (CB 700+)."""
        payload = _scoring_payload(cb_score=random.randint(700, 850), income=5000)
        self.client.post(
            "/api/v1/scoring/evaluate",
            json=payload,
            name="/api/v1/scoring/evaluate [good]",
        )

    @task(10)
    def risky_borrower_scoring(self):
        """고위험 차주 평가 (CB 500 미만)."""
        payload = _scoring_payload(cb_score=random.randint(350, 500), income=2000)
        payload["delinquency_count_12m"] = random.randint(2, 8)
        self.client.post(
            "/api/v1/scoring/evaluate",
            json=payload,
            name="/api/v1/scoring/evaluate [risky]",
        )

    @task(10)
    def special_segment_scoring(self):
        """특수 세그먼트 평가 (의사/변호사 등)."""
        seg = random.choice(["SEG-DR", "SEG-JD", "SEG-YTH"])
        payload = _scoring_payload(
            cb_score=random.randint(650, 780),
            income=random.randint(6000, 12000),
            segment=seg,
        )
        self.client.post(
            "/api/v1/scoring/evaluate",
            json=payload,
            name=f"/api/v1/scoring/evaluate [{seg}]",
        )

    @task(5)
    def application_start(self):
        """대출 신청 세션 시작."""
        self.client.post(
            "/api/v1/applications/start",
            json={
                "product_type": random.choice(["credit", "mortgage"]),
                "channel": random.choice(["mobile_app", "web", "branch"]),
            },
            name="/api/v1/applications/start",
        )

    @task(3)
    def health_check(self):
        """헬스체크 (모니터링 시스템)."""
        self.client.get("/health", name="/health")

    @task(2)
    def check_regulation_params(self):
        """규제 파라미터 조회 (읽기 전용)."""
        cat = random.choice(["dsr", "ltv", "rate"])
        self.client.get(
            f"/api/v1/admin/regulation-params?category={cat}",
            name="/api/v1/admin/regulation-params [read]",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 심사 담당자 (내부 사용자)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class UnderwriterUser(HttpUser):
    """심사 담당자: 모니터링 조회 + 배치 심사 (낮은 빈도)."""

    wait_time = between(3, 8)   # 업무 처리 대기 3~8초
    weight = 20                 # 전체 가상 사용자 중 20%

    def on_start(self):
        """로그인하여 토큰 획득."""
        self._token = self._get_token("risk_manager", "KCS@risk2024")
        self._headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def _get_token(self, username: str, password: str) -> str:
        """JWT 토큰 획득."""
        if username in _TOKEN_CACHE:
            return _TOKEN_CACHE[username]
        resp = self.client.post(
            "/api/v1/auth/token",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/api/v1/auth/token",
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            _TOKEN_CACHE[username] = token
            return token
        return ""

    @task(40)
    def view_psi_monitoring(self):
        """PSI 모니터링 대시보드 조회."""
        self.client.get(
            "/api/v1/monitoring/psi-summary",
            name="/api/v1/monitoring/psi-summary",
        )

    @task(30)
    def view_calibration(self):
        """모델 칼리브레이션 지표 조회."""
        self.client.get(
            "/api/v1/monitoring/calibration",
            name="/api/v1/monitoring/calibration",
        )

    @task(20)
    def view_vintage_analysis(self):
        """빈티지 분석 조회."""
        self.client.get(
            "/api/v1/monitoring/vintage",
            name="/api/v1/monitoring/vintage",
        )

    @task(10)
    def shadow_mode_scoring(self):
        """Shadow Mode (챌린저 모델) 평가."""
        payload = _scoring_payload(cb_score=random.randint(600, 750))
        payload["shadow_mode"] = True
        self.client.post(
            "/api/v1/scoring/evaluate",
            json=payload,
            name="/api/v1/scoring/evaluate [shadow]",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 시스템 관리자 (BRMS 관리)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class AdminUser(HttpUser):
    """관리자: BRMS 파라미터 조회 + 규제 정보 열람 (매우 낮은 빈도)."""

    wait_time = between(10, 30)  # 관리 작업 대기 10~30초
    weight = 10                  # 전체 가상 사용자 중 10%

    def on_start(self):
        """관리자 토큰 획득."""
        resp = self.client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "KCS@admin2024"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="/api/v1/auth/token [admin]",
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            self._headers = {"Authorization": f"Bearer {token}"}
        else:
            self._headers = {}

    @task(50)
    def list_all_regulation_params(self):
        """전체 규제 파라미터 목록 조회."""
        self.client.get(
            "/api/v1/admin/regulation-params",
            name="/api/v1/admin/regulation-params [all]",
        )

    @task(20)
    def list_eq_grade_master(self):
        """EQ Grade 마스터 조회."""
        self.client.get(
            "/api/v1/admin/eq-grade-master",
            name="/api/v1/admin/eq-grade-master",
        )

    @task(20)
    def list_irg_master(self):
        """IRG 마스터 조회."""
        self.client.get(
            "/api/v1/admin/irg-master",
            name="/api/v1/admin/irg-master",
        )

    @task(10)
    def get_current_user_info(self):
        """현재 사용자 정보 조회."""
        self.client.get(
            "/api/v1/auth/me",
            headers=self._headers,
            name="/api/v1/auth/me",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 이벤트 훅: 부하 테스트 결과 커스텀 출력
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """부하 테스트 종료 시 SLA 기준 통과 여부 출력."""
    stats = environment.runner.stats
    total = stats.total

    print("\n" + "=" * 60)
    print("KCS 부하 테스트 결과 요약")
    print("=" * 60)
    print(f"  총 요청: {total.num_requests:,}")
    print(f"  실패: {total.num_failures:,} ({total.fail_ratio * 100:.1f}%)")
    print(f"  평균 응답: {total.avg_response_time:.0f}ms")
    print(f"  p50:  {total.get_response_time_percentile(0.5):.0f}ms")
    print(f"  p95:  {total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  p99:  {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  RPS:  {total.current_rps:.1f}")
    print()

    # SLA 기준 검사
    p95 = total.get_response_time_percentile(0.95)
    fail_rate = total.fail_ratio

    sla_pass = True
    if p95 > 500:
        print(f"  ❌ SLA 실패: p95={p95:.0f}ms > 500ms")
        sla_pass = False
    else:
        print(f"  ✅ SLA 통과: p95={p95:.0f}ms ≤ 500ms")

    if fail_rate > 0.01:
        print(f"  ❌ 에러율 초과: {fail_rate * 100:.1f}% > 1%")
        sla_pass = False
    else:
        print(f"  ✅ 에러율 정상: {fail_rate * 100:.1f}% ≤ 1%")

    print("=" * 60)

    if not sla_pass:
        environment.process_exit_code = 1
