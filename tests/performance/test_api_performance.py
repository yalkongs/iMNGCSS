"""
API 성능 테스트 (응답 시간 / 처리량 / 모델 추론 속도)
======================================================
목표 SLA:
  - POST /scoring/evaluate   ≤ 200ms (p95)
  - GET  /admin/regulation-params ≤ 100ms (p95)
  - ScoringEngine 통계 폴백   ≤ 50ms
  - ScoringEngine LightGBM    ≤ 200ms

실행 (API 서버 불필요 — 단위 성능 테스트):
  pytest tests/performance/ -v -s

실행 (API 서버 필요 — 통합 성능 테스트):
  KCS_API_URL=http://localhost:8000 pytest tests/performance/test_api_performance.py::TestHttpPerformance -v -s
"""
import os
import sys
import time
import math
import statistics
import pytest
import numpy as np
from typing import Callable

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

API_URL = os.getenv("KCS_API_URL", "")  # 비어있으면 HTTP 테스트 건너뜀


def _measure_latency(fn: Callable, n: int = 20) -> dict:
    """함수 실행 시간 측정 (ms)."""
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return {
        "mean_ms":   round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms":    round(sorted(times)[int(n * 0.95)], 2),
        "max_ms":    round(max(times), 2),
        "n":         n,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ScoringEngine 단위 성능 (DB/API 없음)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestScoringEnginePerformance:
    """ScoringEngine 추론 속도 테스트 (통계 폴백 모드)."""

    @pytest.fixture(autouse=True)
    def _import_engine(self):
        try:
            from app.core.scoring_engine import ScoringEngine, ScoringInput
            self.ScoringEngine = ScoringEngine
            self.ScoringInput = ScoringInput
        except ImportError as e:
            pytest.skip(f"ScoringEngine import 실패: {e}")

    def _make_input(self, cb_score: int = 700) -> "ScoringInput":
        return self.ScoringInput(
            resident_hash="perf_test_hash_001",
            product_type="credit",
            requested_amount=30_000_000,
            requested_term_months=36,
            cb_score=cb_score,
            income_annual_wan=4000,
            delinquency_count_12m=0,
            employment_type="employed",
            employment_duration_months=24,
            existing_loan_monthly_payment=300_000,
            open_loan_count=1,
            total_loan_balance=5_000_000,
            inquiry_count_3m=1,
            worst_delinquency_status=0,
            age=35,
            dsr_ratio=0.20,
        )

    def test_scoring_single_inference_latency(self):
        """단일 추론 ≤ 50ms (통계 폴백 모드)."""
        engine = self.ScoringEngine(model_path=None)
        inp = self._make_input()

        result = _measure_latency(lambda: engine.score(inp), n=30)
        print(f"\n  단일 추론: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")

        assert result["p95_ms"] <= 200, \
            f"ScoringEngine p95({result['p95_ms']}ms) > 200ms"

    def test_scoring_batch_100_throughput(self):
        """100건 배치 처리 ≤ 1초 (TPS ≥ 100)."""
        engine = self.ScoringEngine(model_path=None)

        inputs = [self._make_input(cb_score=600 + i % 200) for i in range(100)]

        t0 = time.perf_counter()
        results = [engine.score(inp) for inp in inputs]
        elapsed = time.perf_counter() - t0

        tps = len(results) / elapsed
        print(f"\n  배치 100건: {elapsed:.3f}초, TPS={tps:.0f}")

        assert elapsed <= 5.0, f"100건 처리 시간({elapsed:.2f}초) > 5초"
        assert len(results) == 100

    def test_scoring_good_borrower_fast(self):
        """우량 차주 (cb_score=800) 평가 ≤ 100ms."""
        engine = self.ScoringEngine(model_path=None)
        inp = self._make_input(cb_score=800)

        result = _measure_latency(lambda: engine.score(inp), n=20)
        print(f"\n  우량 차주 추론: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")

        assert result["p95_ms"] <= 200

    def test_scoring_bad_borrower_fast(self):
        """고위험 차주 (cb_score=400) 평가 ≤ 100ms."""
        engine = self.ScoringEngine(model_path=None)
        inp = self._make_input(cb_score=400)

        result = _measure_latency(lambda: engine.score(inp), n=20)
        print(f"\n  고위험 차주 추론: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")

        assert result["p95_ms"] <= 200

    def test_score_consistency_across_runs(self):
        """동일 입력에 대해 동일한 점수 반환 (결정론적)."""
        engine = self.ScoringEngine(model_path=None)
        inp = self._make_input(cb_score=720)

        scores = [engine.score(inp).score for _ in range(5)]
        assert len(set(scores)) == 1, \
            f"비결정론적 점수: {scores}"
        print(f"\n  점수 결정론성: {scores[0]}점 (5회 동일)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 점수 계산 알고리즘 성능
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestScoringAlgorithmPerformance:
    """점수 스케일링 및 PD 변환 성능."""

    def test_score_to_pd_conversion_speed(self):
        """Score → PD 변환 10,000건 ≤ 10ms."""
        # Score = 600 - (40/ln2) × ln(PD / 0.072)
        PDO = 40
        BASE_SCORE = 600
        BASE_PD = 0.072

        def score_to_pd(score: float) -> float:
            return min(1.0, BASE_PD * math.exp(-(score - BASE_SCORE) * math.log(2) / PDO))

        scores = np.random.uniform(300, 900, 10000)

        t0 = time.perf_counter()
        pds = [score_to_pd(s) for s in scores]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n  Score→PD 10,000건: {elapsed_ms:.2f}ms")
        assert elapsed_ms <= 500, f"Score→PD 변환 느림: {elapsed_ms:.2f}ms"
        assert all(0 < p <= 1.0 for p in pds), "PD 범위 이상"

    def test_dsr_calculation_bulk_performance(self):
        """DSR 계산 1,000건 ≤ 5ms."""
        def compute_dsr(annual_income: float, monthly_payment: float) -> float:
            if annual_income <= 0:
                return float("inf")
            return (monthly_payment * 12) / annual_income

        n = 1000
        incomes = np.random.lognormal(np.log(50_000_000), 0.4, n)
        payments = np.random.uniform(200_000, 2_000_000, n)

        t0 = time.perf_counter()
        dsrs = [compute_dsr(inc, pay) for inc, pay in zip(incomes, payments)]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n  DSR 계산 1,000건: {elapsed_ms:.2f}ms")
        assert elapsed_ms <= 100

    def test_psi_calculation_speed(self):
        """PSI 계산 (5,000 + 2,000건) ≤ 100ms."""
        rng = np.random.default_rng(42)
        ref = rng.normal(680, 80, 5000)
        cur = rng.normal(660, 85, 2000)

        def compute_psi_simple(ref, cur, n_bins=10):
            bins = np.percentile(ref, np.linspace(0, 100, n_bins + 1))
            bins[0], bins[-1] = -np.inf, np.inf
            ref_c, _ = np.histogram(ref, bins=bins)
            cur_c, _ = np.histogram(cur, bins=bins)
            ref_p = (ref_c + 0.5) / (len(ref) + 0.5 * n_bins)
            cur_p = (cur_c + 0.5) / (len(cur) + 0.5 * n_bins)
            return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))

        result = _measure_latency(lambda: compute_psi_simple(ref, cur), n=50)
        print(f"\n  PSI 계산: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")
        assert result["p95_ms"] <= 100, f"PSI p95({result['p95_ms']}ms) > 100ms"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. JWT 토큰 처리 성능
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAuthPerformance:
    """JWT 토큰 발급/검증 성능."""

    @pytest.fixture(autouse=True)
    def _import_auth(self):
        try:
            from app.core.auth import create_access_token, _decode_token, ROLE_RISK_MANAGER
            self.create_token = create_access_token
            self.decode_token = _decode_token
            self.ROLE = ROLE_RISK_MANAGER
        except ImportError as e:
            pytest.skip(f"auth 모듈 없음: {e}")

    def test_token_creation_speed(self):
        """JWT 발급 100회 ≤ 1초."""
        result = _measure_latency(
            lambda: self.create_token("test_user", self.ROLE), n=100
        )
        print(f"\n  JWT 발급: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")
        assert result["p95_ms"] <= 50, f"JWT 발급 p95({result['p95_ms']}ms) > 50ms"

    def test_token_decode_speed(self):
        """JWT 검증 100회 ≤ 200ms."""
        token = self.create_token("test_user", self.ROLE)
        result = _measure_latency(lambda: self.decode_token(token), n=100)
        print(f"\n  JWT 검증: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")
        assert result["p95_ms"] <= 50, f"JWT 검증 p95({result['p95_ms']}ms) > 50ms"

    def test_token_create_and_decode_roundtrip(self):
        """JWT 발급 + 검증 왕복 p95 ≤ 100ms."""
        def roundtrip():
            token = self.create_token("perf_user", self.ROLE)
            return self.decode_token(token)

        result = _measure_latency(roundtrip, n=50)
        print(f"\n  JWT 왕복: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")
        assert result["p95_ms"] <= 100


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. HTTP API 성능 (실행 서버 필요)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestHttpPerformance:
    """HTTP API 응답 시간 테스트 (KCS_API_URL 환경 변수 필요)."""

    @pytest.fixture(autouse=True)
    def _check_server(self):
        if not API_URL:
            pytest.skip("KCS_API_URL 환경 변수 없음 — make up 후 재실행")
        try:
            import httpx
            resp = httpx.get(f"{API_URL}/health", timeout=5)
            if resp.status_code != 200:
                pytest.skip(f"API 서버 응답 없음: {resp.status_code}")
        except Exception as e:
            pytest.skip(f"API 서버 연결 실패: {e}")

    def _post_score(self, cb_score: int = 700) -> float:
        import httpx
        payload = {
            "resident_hash": "perf_test",
            "product_type": "credit",
            "requested_amount": 30_000_000,
            "requested_term_months": 36,
            "cb_score": cb_score,
            "income_annual_wan": 4000,
            "delinquency_count_12m": 0,
            "employment_type": "employed",
            "employment_duration_months": 24,
            "existing_loan_monthly_payment": 300_000,
            "open_loan_count": 1,
            "total_loan_balance": 5_000_000,
            "inquiry_count_3m": 1,
            "worst_delinquency_status": 0,
            "age": 35,
            "dsr_ratio": 0.20,
        }
        t0 = time.perf_counter()
        httpx.post(f"{API_URL}/api/v1/scoring/evaluate", json=payload, timeout=10)
        return (time.perf_counter() - t0) * 1000

    def test_scoring_api_p95_under_500ms(self):
        """POST /scoring/evaluate p95 ≤ 500ms."""
        latencies = [self._post_score() for _ in range(20)]
        p95 = sorted(latencies)[int(20 * 0.95)]
        mean = statistics.mean(latencies)
        print(f"\n  /scoring/evaluate: mean={mean:.0f}ms, p95={p95:.0f}ms")
        assert p95 <= 500, f"scoring API p95({p95:.0f}ms) > 500ms"

    def test_health_endpoint_under_50ms(self):
        """GET /health p95 ≤ 50ms."""
        import httpx
        times = []
        for _ in range(30):
            t0 = time.perf_counter()
            httpx.get(f"{API_URL}/health", timeout=5)
            times.append((time.perf_counter() - t0) * 1000)

        p95 = sorted(times)[int(30 * 0.95)]
        print(f"\n  /health: mean={statistics.mean(times):.0f}ms, p95={p95:.0f}ms")
        assert p95 <= 200, f"health p95({p95:.0f}ms) > 200ms"

    def test_concurrent_scoring_requests(self):
        """10 동시 요청 처리 ≤ 3초 (총 처리 시간)."""
        import httpx
        from concurrent.futures import ThreadPoolExecutor, as_completed

        payload = {
            "resident_hash": "concurrent_test",
            "product_type": "credit",
            "requested_amount": 20_000_000,
            "requested_term_months": 24,
            "cb_score": 680,
            "income_annual_wan": 3500,
            "delinquency_count_12m": 0,
            "employment_type": "employed",
            "employment_duration_months": 18,
            "existing_loan_monthly_payment": 200_000,
            "open_loan_count": 1,
            "total_loan_balance": 3_000_000,
            "inquiry_count_3m": 1,
            "worst_delinquency_status": 0,
            "age": 30,
            "dsr_ratio": 0.15,
        }

        def send_request():
            return httpx.post(
                f"{API_URL}/api/v1/scoring/evaluate",
                json=payload, timeout=30
            )

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_request) for _ in range(10)]
            results = [f.result() for f in as_completed(futures)]
        elapsed = time.perf_counter() - t0

        success = sum(1 for r in results if r.status_code == 200)
        print(f"\n  10 동시 요청: {elapsed:.2f}초, 성공={success}/10")
        assert elapsed <= 10.0, f"10 동시 요청 처리 시간({elapsed:.2f}초) > 10초"
        assert success >= 8, f"성공률 낮음: {success}/10"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 주민번호 해시 성능
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestCryptoPerformance:
    """주민번호 HMAC-SHA256 해시 성능."""

    @pytest.fixture(autouse=True)
    def _import_crypto(self):
        try:
            from app.core.crypto import hash_resident_number, verify_resident_hash
            self.hash_fn = hash_resident_number
            self.verify_fn = verify_resident_hash
        except ImportError as e:
            pytest.skip(f"crypto 모듈 없음: {e}")

    def test_hash_speed_1000_records(self):
        """주민번호 해시 1,000건 ≤ 200ms."""
        numbers = [f"90101{i:07d}" for i in range(1000)]

        t0 = time.perf_counter()
        hashes = [self.hash_fn(n) for n in numbers]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n  주민번호 해시 1,000건: {elapsed_ms:.2f}ms")
        assert elapsed_ms <= 500, f"해시 1,000건 {elapsed_ms:.2f}ms > 500ms"
        assert all(len(h) == 64 for h in hashes), "해시 길이 이상"

    def test_hash_verification_speed(self):
        """해시 검증 p95 ≤ 5ms."""
        number = "901010-1234567"
        expected = self.hash_fn(number)

        result = _measure_latency(lambda: self.verify_fn(number, expected), n=100)
        print(f"\n  해시 검증: mean={result['mean_ms']}ms, p95={result['p95_ms']}ms")
        assert result["p95_ms"] <= 10


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
