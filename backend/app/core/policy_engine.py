"""
BRMS PolicyEngine (ADR-001)
================================
규제 파라미터를 코드가 아닌 DB(regulation_params)에서 조회.
Redis 캐시(TTL 5분) + PostgreSQL JSONB fallback.

핵심 원칙:
- 스트레스 DSR, LTV, DSR 한도 등 모든 규제값은 이 엔진을 통해 조회
- 코드에 직접 숫자 하드코딩 금지
- 규제 변경 → DB 업데이트만으로 즉시 반영 (배포 불필요)

사용 예:
    engine = PolicyEngine(db_session, redis_client)
    stress_rate = await engine.get_stress_dsr_rate("metropolitan", "variable", effective_date)
    ltv_limit = await engine.get_ltv_limit("speculation_area")
    eq_benefit = await engine.get_eq_grade_benefit("EQ-S")
"""
import json
import logging
from datetime import datetime, date
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Redis 캐시 TTL (초)
CACHE_TTL = 300  # 5분


class PolicyEngine:
    """
    규제 파라미터 조회 엔진.
    Redis 캐시 우선, miss 시 PostgreSQL 조회.
    """

    def __init__(self, db: AsyncSession, redis_client=None):
        self._db = db
        self._redis = redis_client

    # ── 내부 캐시 유틸리티 ──────────────────────────────────────

    async def _get_cached(self, cache_key: str) -> Any | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(cache_key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis 조회 실패 (cache_key={cache_key}): {e}")
        return None

    async def _set_cached(self, cache_key: str, value: Any) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.setex(cache_key, CACHE_TTL, json.dumps(value, default=str))
        except Exception as e:
            logger.warning(f"Redis 저장 실패 (cache_key={cache_key}): {e}")

    async def _query_param(
        self,
        param_key: str,
        condition_match: dict | None = None,
        effective_date: datetime | None = None,
    ) -> dict | None:
        """
        regulation_params 테이블에서 파라미터 조회.
        effective_date 기준 활성화된 파라미터 반환.
        condition_match가 있으면 condition_json 서브셋 매칭.
        """
        from app.db.schemas.regulation_params import RegulationParam

        eff = effective_date or datetime.utcnow()

        stmt = (
            select(RegulationParam)
            .where(
                and_(
                    RegulationParam.param_key == param_key,
                    RegulationParam.is_active == True,  # noqa: E712
                    RegulationParam.effective_from <= eff,
                    (RegulationParam.effective_to == None)  # noqa: E711
                    | (RegulationParam.effective_to >= eff),
                )
            )
            .order_by(RegulationParam.effective_from.desc())
            .limit(1)
        )

        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            return None

        # condition_match 필터링 (조건이 있는 경우)
        if condition_match and row.condition_json:
            for k, v in condition_match.items():
                if row.condition_json.get(k) != v:
                    return None

        return row.param_value

    # ── 스트레스 DSR 조회 ────────────────────────────────────────

    async def get_stress_dsr_rate(
        self,
        region: str,
        rate_type: str,
        effective_date: datetime | None = None,
        phase: str | None = None,
    ) -> float:
        """
        스트레스 DSR 가산금리 조회.

        Args:
            region: metropolitan(수도권) | non_metropolitan(비수도권)
            rate_type: variable(변동) | mixed_short(혼합단기<5년) | mixed_long(혼합장기≥5년) | fixed(고정)
            effective_date: 기준 날짜 (None=현재)
            phase: phase1 | phase2 | phase3 (None=현재 시행 중인 최신)

        Returns:
            스트레스 금리 (%p). 고정금리=0.0
        """
        if rate_type == "fixed":
            return 0.0

        cache_key = f"stress_dsr:{region}:{rate_type}:{phase or 'latest'}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return float(cached)

        param_key = f"stress_dsr.{region}.{rate_type}"
        eff = effective_date or datetime.utcnow()

        value = await self._query_param(param_key, effective_date=eff)

        if value is None:
            # DB에 없으면 fallback: 기본값 (수도권 변동 phase2 = 0.75%p)
            fallback_map = {
                ("metropolitan", "variable"): 0.75,
                ("metropolitan", "mixed_short"): 0.75,
                ("metropolitan", "mixed_long"): 0.375,
                ("non_metropolitan", "variable"): 1.50,
                ("non_metropolitan", "mixed_short"): 1.50,
                ("non_metropolitan", "mixed_long"): 0.75,
            }
            rate = fallback_map.get((region, rate_type), 0.0)
            logger.warning(
                f"stress_dsr param not found in DB (key={param_key}), using fallback={rate}"
            )
        else:
            rate = float(value.get("rate", 0.0))

        await self._set_cached(cache_key, rate)
        return rate

    # ── LTV 한도 조회 ────────────────────────────────────────────

    async def get_ltv_limit(
        self,
        area_type: str,
        owned_count: int = 0,
        effective_date: datetime | None = None,
    ) -> float:
        """
        LTV 한도 조회.

        Args:
            area_type: general | regulated | speculation_area
            owned_count: 보유 주택 수 (1주택 이상이면 추가 규제)
            effective_date: 기준 날짜

        Returns:
            LTV 최대 비율 (%). 예: 70.0, 60.0, 40.0
        """
        cache_key = f"ltv:{area_type}:owned{owned_count}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return float(cached)

        param_key = f"ltv.{area_type}"
        eff = effective_date or datetime.utcnow()
        value = await self._query_param(param_key, effective_date=eff)

        if value is None:
            fallback_map = {
                "general": 70.0,
                "regulated": 60.0,
                "speculation_area": 40.0,
            }
            limit = fallback_map.get(area_type, 70.0)
            logger.warning(f"ltv param not found (key={param_key}), fallback={limit}")
        else:
            limit = float(value.get("max_ratio", 70.0))
            # 다주택자 추가 규제 (보유 주택 2채 이상)
            if owned_count >= 2 and "multi_owner_deduction" in value:
                limit -= float(value["multi_owner_deduction"])

        await self._set_cached(cache_key, limit)
        return limit

    # ── DSR 한도 조회 ────────────────────────────────────────────

    async def get_dsr_limit(
        self,
        product_type: str = "credit",
        effective_date: datetime | None = None,
    ) -> float:
        """
        DSR 한도 조회.

        Args:
            product_type: credit | mortgage | micro
            effective_date: 기준 날짜

        Returns:
            DSR 최대 비율 (%). 기본 40.0%
        """
        cache_key = f"dsr:limit:{product_type}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return float(cached)

        value = await self._query_param("dsr.max_ratio", effective_date=effective_date)
        limit = float(value.get("max_ratio", 40.0)) if value else 40.0

        await self._set_cached(cache_key, limit)
        return limit

    # ── EQ Grade 혜택 조회 ───────────────────────────────────────

    async def get_eq_grade_benefit(
        self,
        eq_grade: str,
        effective_date: datetime | None = None,
    ) -> dict:
        """
        EQ Grade 혜택 조회 (한도 배수 + 금리 조정).

        Returns:
            {"limit_multiplier": 1.5, "rate_adjustment": -0.2}
        """
        cache_key = f"eq_grade:{eq_grade}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        param_key = f"eq_grade.benefit.{eq_grade}"
        value = await self._query_param(param_key, effective_date=effective_date)

        if value is None:
            # 하드코딩 fallback (DB 미등록 시)
            fallback = {
                "EQ-S": {"limit_multiplier": 2.0, "rate_adjustment": -0.5},
                "EQ-A": {"limit_multiplier": 1.8, "rate_adjustment": -0.3},
                "EQ-B": {"limit_multiplier": 1.5, "rate_adjustment": -0.2},
                "EQ-C": {"limit_multiplier": 1.2, "rate_adjustment": 0.0},
                "EQ-D": {"limit_multiplier": 1.0, "rate_adjustment": 0.2},
                "EQ-E": {"limit_multiplier": 0.7, "rate_adjustment": 0.5},
            }
            benefit = fallback.get(eq_grade, {"limit_multiplier": 1.0, "rate_adjustment": 0.0})
            logger.warning(f"eq_grade param not found (grade={eq_grade}), using fallback")
        else:
            benefit = value

        await self._set_cached(cache_key, benefit)
        return benefit

    # ── IRG PD 조정값 조회 ───────────────────────────────────────

    async def get_irg_pd_adjustment(
        self,
        irg_code: str,
        effective_date: datetime | None = None,
    ) -> float:
        """
        IRG에 따른 PD 조정값 조회.

        Returns:
            PD 조정값 (비율). L=-0.10, M=0.0, H=+0.15, VH=+0.30
        """
        cache_key = f"irg:pd_adjustment:{irg_code}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return float(cached)

        param_key = f"irg.pd_adjustment.{irg_code}"
        value = await self._query_param(param_key, effective_date=effective_date)

        if value is None:
            fallback = {"L": -0.10, "M": 0.0, "H": 0.15, "VH": 0.30}
            adj = fallback.get(irg_code, 0.0)
        else:
            adj = float(value.get("adjustment", 0.0))

        await self._set_cached(cache_key, adj)
        return adj

    # ── 세그먼트 혜택 조회 ───────────────────────────────────────

    async def get_segment_benefit(
        self,
        segment_code: str,
        effective_date: datetime | None = None,
    ) -> dict:
        """
        특수 세그먼트 혜택 조회.

        Returns:
            {
              "guaranteed_eq_grade": "EQ-B",
              "limit_multiplier": 3.0,
              "rate_discount": -0.3,
              "income_smoothing_months": 12  # SEG-ART
            }
        """
        cache_key = f"segment:{segment_code}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return cached

        # SEG-MOU-{code} 패턴 처리
        param_key = segment_code if not segment_code.startswith("SEG-MOU-") else "SEG-MOU"
        value = await self._query_param(
            f"segment.benefit.{param_key}", effective_date=effective_date
        )

        if value is None:
            fallback = {
                "SEG-DR":  {"guaranteed_eq_grade": "EQ-B", "limit_multiplier": 3.0, "rate_discount": -0.3},
                "SEG-JD":  {"guaranteed_eq_grade": "EQ-B", "limit_multiplier": 2.5, "rate_discount": -0.2},
                "SEG-ART": {"income_smoothing_months": 12, "rate_discount": 0.0, "guarantee_link": True},
                "SEG-YTH": {"rate_discount": -0.5, "limit_multiplier": 1.0},
                "SEG-MIL": {"guaranteed_eq_grade": "EQ-S", "limit_multiplier": 2.0, "rate_discount": -0.5},
                "SEG-MOU": {"rate_discount": -0.3, "limit_multiplier": 1.5},
            }
            benefit = fallback.get(segment_code.split("-MOU-")[0] + ("-MOU" if "-MOU-" in segment_code else ""), {})
            logger.warning(f"segment param not found (segment={segment_code}), using fallback")
        else:
            benefit = value

        await self._set_cached(cache_key, benefit)
        return benefit

    # ── 최고금리 조회 ────────────────────────────────────────────

    async def get_max_interest_rate(self, effective_date: datetime | None = None) -> float:
        """최고금리 조회 (대부업법 기준). 기본 20%"""
        cache_key = "rate:max_interest"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            return float(cached)

        value = await self._query_param("rate.max_interest", effective_date=effective_date)
        rate = float(value.get("max_rate", 20.0)) if value else 20.0

        await self._set_cached(cache_key, rate)
        return rate

    # ── 신용대출 소득배수 조회 ───────────────────────────────────

    async def get_credit_loan_income_multiplier(
        self,
        employment_type: str = "employed",
        segment_code: str | None = None,
        effective_date: datetime | None = None,
    ) -> float:
        """
        신용대출 소득배수 한도 조회.

        Returns:
            소득배수 (예: 1.5 = 연소득 1.5배)
        """
        cache_key = f"credit_loan:income_multiplier:{employment_type}"
        cached = await self._get_cached(cache_key)
        if cached is not None:
            base_multiplier = float(cached)
        else:
            value = await self._query_param(
                f"credit_loan.income_multiplier.{employment_type}",
                effective_date=effective_date,
            )
            base_multiplier = float(value.get("multiplier", 1.5)) if value else 1.5
            await self._set_cached(cache_key, base_multiplier)

        # 세그먼트 EQ 혜택 추가 적용
        if segment_code:
            seg_benefit = await self.get_segment_benefit(segment_code, effective_date)
            seg_multiplier = seg_benefit.get("limit_multiplier", 1.0)
            return base_multiplier * seg_multiplier

        return base_multiplier

    # ── 캐시 무효화 (규제 업데이트 시 호출) ─────────────────────

    async def invalidate_cache(self, param_key: str | None = None) -> None:
        """Redis 캐시 무효화. param_key=None이면 전체 무효화."""
        if self._redis is None:
            return
        try:
            if param_key:
                pattern = f"*{param_key}*"
                keys = await self._redis.keys(pattern)
                if keys:
                    await self._redis.delete(*keys)
            else:
                # regulation_params 관련 키 전체 삭제
                for pattern in ["stress_dsr:*", "ltv:*", "dsr:*", "eq_grade:*", "irg:*", "segment:*", "rate:*", "credit_loan:*"]:
                    keys = await self._redis.keys(pattern)
                    if keys:
                        await self._redis.delete(*keys)
            logger.info(f"PolicyEngine 캐시 무효화 완료 (key={param_key or 'ALL'})")
        except Exception as e:
            logger.error(f"캐시 무효화 실패: {e}")
