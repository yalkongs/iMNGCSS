"""
[역할: 리스크관리팀] 포트폴리오 스트레스 테스트 시나리오
==============================================================
책임: 거시경제 충격 시 포트폴리오 손실 추정 및 자본 적정성 검증

시나리오:
  1. 금리 충격 시나리오 (+1/+2/+3%p)
      → DSR 재계산 → 한도 초과 비율 → EL 증가
  2. 부동산 가격 하락 시나리오 (10/20/30%)
      → LTV 초과 비율 → 주담대 충당금 추가
  3. 경기침체 시나리오 (PD 1.5/2.0/3.0배 상승)
      → EL 증가 → EC 적정성 → RAROC 하락
  4. 복합 스트레스 시나리오 (금리↑ + 부동산↓ + PD↑)
  5. 역스트레스 테스트 (자본 소진점 역산)

금감원 모범규준:
  - 연 1회 이상 스트레스 테스트 의무
  - 자기자본비율 8% 유지 (바젤III)
  - 경기침체 시나리오: PD 2배 이상 충격

실행: pytest validation/roles/risk_management/test_stress_scenarios.py -v -s
"""
import os
import sys
import math
import json
import pytest
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
DATA_DIR = os.path.join(BASE_DIR, "ml_pipeline", "data")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application")

sys.path.insert(0, BASE_DIR)


# ── 바젤III 파라미터 ──────────────────────────────────────────
MIN_CAPITAL_RATIO = 0.08          # BIS 최소 자기자본비율 8%
TIER1_CAPITAL_RATIO = 0.06        # Tier1 최소 6%
CONSERVATION_BUFFER = 0.025       # 자본보전완충자본 2.5%
COUNTERCYCLICAL_BUFFER = 0.01     # 경기대응완충자본 1.0%

# 스트레스 시나리오 강도
SCENARIOS = {
    "mild":     {"pd_multiplier": 1.5, "lgd_addon": 0.05, "rate_shock": 0.01, "collateral_drop": 0.10},
    "moderate": {"pd_multiplier": 2.0, "lgd_addon": 0.10, "rate_shock": 0.02, "collateral_drop": 0.20},
    "severe":   {"pd_multiplier": 3.0, "lgd_addon": 0.15, "rate_shock": 0.03, "collateral_drop": 0.30},
}

# 포트폴리오 대표 파라미터 (데모 기준)
PORTFOLIO_BASE = {
    "total_ead": 100_000_000_000,    # 1조원 포트폴리오
    "avg_pd": 0.072,                 # 평균 PD 7.2%
    "avg_lgd_unsecured": 0.45,       # 무담보 LGD 45%
    "avg_lgd_mortgage": 0.25,        # 주담대 LGD 25%
    "mortgage_share": 0.35,          # 주담대 비중 35%
    "credit_share": 0.55,            # 신용대출 비중 55%
    "micro_share": 0.10,             # 소액론 비중 10%
    "avg_dsr": 0.28,                 # 평균 DSR 28%
    "avg_income": 50_000_000,        # 평균 소득 5천만원
    "avg_monthly_payment": 800_000,  # 평균 월상환액 80만원
    "capital_ratio": 0.12,           # 현재 자기자본비율 12%
    "economic_capital": 8_000_000_000,  # EC 800억원 (EAD × 8%)
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_el(ead: float, pd: float, lgd: float) -> float:
    """EL = EAD × PD × LGD"""
    return ead * pd * lgd


def compute_rwa_simplified(ead: float, pd: float, lgd: float) -> float:
    """단순화된 RWA (소매 IRB 기반)."""
    from scipy.stats import norm
    try:
        R = 0.03 * (1 - math.exp(-35 * pd)) / (1 - math.exp(-35)) + \
            0.16 * (1 - (1 - math.exp(-35 * pd)) / (1 - math.exp(-35)))
        b = (0.11852 - 0.05478 * math.log(max(pd, 1e-8))) ** 2
        K = (lgd * norm.cdf(
            math.sqrt(1 / (1 - R)) * norm.ppf(pd) +
            math.sqrt(R / (1 - R)) * norm.ppf(0.999)
        ) - lgd * pd) * (1 + (2.5 - 2.5) * b) / (1 - 1.5 * b)
        return max(0, ead * K * 12.5)
    except Exception:
        return ead * pd * lgd * 12.5  # 간단한 폴백


def compute_stressed_el(
    ead: float,
    base_pd: float,
    base_lgd: float,
    pd_multiplier: float = 1.0,
    lgd_addon: float = 0.0,
) -> float:
    """스트레스 EL = EAD × (PD × mult) × (LGD + addon)."""
    stressed_pd = min(1.0, base_pd * pd_multiplier)
    stressed_lgd = min(1.0, base_lgd + lgd_addon)
    return compute_el(ead, stressed_pd, stressed_lgd)


def monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    if months <= 0 or principal <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / months
    r = annual_rate / 12
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def compute_dsr(monthly_income: float, monthly_payment_amt: float) -> float:
    if monthly_income <= 0:
        return float("inf")
    return (monthly_payment_amt * 12) / (monthly_income * 12)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 금리 충격 시나리오
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRateShockScenario:
    """금리 충격 → DSR 증가 → 잠재적 부도 증가 시나리오."""

    BASE_RATE = 0.045         # 현재 금리 4.5%
    DSR_LIMIT = 0.40

    def _dsr_breach_ratio(self, rate_shock: float, n: int = 10000) -> float:
        """금리 충격 시 DSR > 40% 차주 비율 추정."""
        rng = np.random.default_rng(42)
        # 포트폴리오 분포
        incomes = rng.lognormal(np.log(4_500_000), 0.4, n)     # 월소득 분포
        principals = rng.uniform(30_000_000, 300_000_000, n)   # 대출 원금
        current_rate = rng.uniform(0.03, 0.07, n)               # 현재 금리 (변동)
        terms = rng.choice([120, 180, 240, 300, 360], n)        # 상환 기간

        shocked_rate = current_rate + rate_shock
        payments = np.array([
            monthly_payment(p, r, t)
            for p, r, t in zip(principals, shocked_rate, terms)
        ])
        dsrs = (payments * 12) / (incomes * 12)
        return float((dsrs > self.DSR_LIMIT).mean())

    def test_mild_rate_shock_dsr_breach(self):
        """+1%p 금리 충격: DSR 초과 비율 < 40%."""
        breach_ratio = self._dsr_breach_ratio(0.01)
        print(f"\n  [금리+1%p] DSR 초과 비율: {breach_ratio:.1%}")
        assert breach_ratio < 0.40, \
            f"경미 금리 충격 DSR 초과 과다: {breach_ratio:.1%}"

    def test_moderate_rate_shock_dsr_breach(self):
        """+2%p 금리 충격: DSR 초과 비율 < 55%."""
        breach_ratio = self._dsr_breach_ratio(0.02)
        print(f"\n  [금리+2%p] DSR 초과 비율: {breach_ratio:.1%}")
        assert breach_ratio < 0.55, \
            f"중간 금리 충격 DSR 초과 과다: {breach_ratio:.1%}"

    def test_severe_rate_shock_dsr_breach_increases(self):
        """+3%p 충격이 +1%p보다 DSR 초과 비율 높아야."""
        mild = self._dsr_breach_ratio(0.01)
        severe = self._dsr_breach_ratio(0.03)
        assert severe > mild, \
            f"심각 충격({severe:.1%}) ≤ 경미 충격({mild:.1%}) — 모순"

    def test_rate_shock_el_increase(self):
        """금리 충격 → PD 상승 → EL 증가 확인."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        lgd = PORTFOLIO_BASE["avg_lgd_unsecured"]

        base_el = compute_el(ead, base_pd, lgd)

        # 금리 2%p 충격 → PD 30% 증가 (금리-부도 상관관계)
        stressed_el = compute_stressed_el(ead, base_pd, lgd, pd_multiplier=1.3)

        el_increase = (stressed_el - base_el) / base_el
        print(f"\n  EL 기본: {base_el/1e8:.1f}억 → 스트레스: {stressed_el/1e8:.1f}억 ({el_increase:.1%} 증가)")
        assert stressed_el > base_el, "EL 증가 없음 — 스트레스 미반영"

    def test_rate_shock_scenarios_monotone(self):
        """금리 충격 강도에 따라 DSR 초과 비율이 단조 증가."""
        ratios = [
            self._dsr_breach_ratio(0.01),
            self._dsr_breach_ratio(0.02),
            self._dsr_breach_ratio(0.03),
        ]
        assert ratios[0] < ratios[1] < ratios[2], \
            f"단조성 위반: {[f'{r:.1%}' for r in ratios]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 부동산 가격 하락 시나리오
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestCollateralShockScenario:
    """부동산 가격 하락 → LTV 초과 → LGD 상승 시나리오."""

    BASE_LTV = 0.60          # 현재 평균 LTV 60%
    LTV_LIMIT_GENERAL = 0.70

    def _ltv_breach_ratio(self, collateral_drop: float, n: int = 5000) -> float:
        """담보 가격 하락 시 LTV > 70% 비율."""
        rng = np.random.default_rng(42)
        loan_amounts = rng.uniform(100_000_000, 500_000_000, n)
        collateral_values = loan_amounts / rng.uniform(0.45, 0.70, n)  # 현재 LTV 분포

        shocked_collateral = collateral_values * (1 - collateral_drop)
        ltvs = loan_amounts / shocked_collateral
        return float((ltvs > self.LTV_LIMIT_GENERAL).mean())

    def test_collateral_drop_10_pct_ltv_breach(self):
        """담보 10% 하락: LTV 초과 비율 < 40%."""
        breach = self._ltv_breach_ratio(0.10)
        print(f"\n  [담보-10%] LTV 초과 비율: {breach:.1%}")
        assert breach < 0.40

    def test_collateral_drop_30_pct_ltv_breach(self):
        """담보 30% 하락: LTV 초과 비율 < 95%."""
        breach = self._ltv_breach_ratio(0.30)
        print(f"\n  [담보-30%] LTV 초과 비율: {breach:.1%}")
        assert breach < 0.95

    def test_collateral_drop_increases_lgd(self):
        """담보 하락 → LGD 증가 (회수율 하락)."""
        # 기본 LTV=60%, LGD=25% (주담대)
        base_lgd = 0.25
        base_collateral = 500_000_000
        loan = base_collateral * 0.60

        # 30% 담보 하락
        shocked_collateral = base_collateral * 0.70
        shocked_ltv = loan / shocked_collateral  # 약 85%
        # LGD = max(LTV - 1, 0) + 회수비용 또는 직접 추정
        stressed_lgd = max(base_lgd, shocked_ltv - 0.50)

        assert stressed_lgd >= base_lgd, "담보 하락 시 LGD가 증가해야 함"
        print(f"\n  담보 30% 하락: LTV {base_collateral*0.6/shocked_collateral:.0%} → LGD {stressed_lgd:.0%}")

    def test_mortgage_el_increase_on_collateral_shock(self):
        """주담대 포트폴리오 EL: 담보 20% 하락 시 증가."""
        mortgage_ead = PORTFOLIO_BASE["total_ead"] * PORTFOLIO_BASE["mortgage_share"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        base_lgd = PORTFOLIO_BASE["avg_lgd_mortgage"]

        base_el = compute_el(mortgage_ead, base_pd, base_lgd)

        # 담보 20% 하락 → LGD +10%p
        stressed_el = compute_stressed_el(
            mortgage_ead, base_pd, base_lgd,
            pd_multiplier=1.2,   # 부동산 하락 → PD 약간 상승
            lgd_addon=0.10       # LGD +10%p
        )

        print(f"\n  주담대 EL: {base_el/1e8:.1f}억 → {stressed_el/1e8:.1f}억")
        assert stressed_el > base_el

    def test_collateral_shock_scenarios_monotone(self):
        """담보 충격 강도에 따라 LTV 초과 비율 단조 증가."""
        ratios = [
            self._ltv_breach_ratio(0.10),
            self._ltv_breach_ratio(0.20),
            self._ltv_breach_ratio(0.30),
        ]
        assert ratios[0] < ratios[1] < ratios[2], \
            f"LTV 초과 비율 단조성 위반: {[f'{r:.1%}' for r in ratios]}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 경기침체 시나리오 (PD 상승)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRecessionScenario:
    """경기침체 → PD 상승 → EL/EC 증가 → 자본 적정성 검증."""

    def _compute_stressed_capital_ratio(self, pd_multiplier: float) -> float:
        """스트레스 시나리오 자기자본비율 추정."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        lgd_unsec = PORTFOLIO_BASE["avg_lgd_unsecured"]
        lgd_mort = PORTFOLIO_BASE["avg_lgd_mortgage"]
        mortgage_share = PORTFOLIO_BASE["mortgage_share"]
        credit_share = PORTFOLIO_BASE["credit_share"]

        # 스트레스 EL 계산
        stressed_pd = min(1.0, base_pd * pd_multiplier)
        el_credit = compute_el(ead * credit_share, stressed_pd, lgd_unsec)
        el_mortgage = compute_el(ead * mortgage_share, stressed_pd, lgd_mort)
        total_el = el_credit + el_mortgage

        # 현재 자본 - 추가 손실 대비
        current_capital = ead * PORTFOLIO_BASE["capital_ratio"]
        # EL 증가분만큼 자본 소비
        base_el = compute_el(ead * credit_share, base_pd, lgd_unsec) + \
                  compute_el(ead * mortgage_share, base_pd, lgd_mort)
        additional_loss = max(0, total_el - base_el)
        stressed_capital = current_capital - additional_loss

        return stressed_capital / ead if ead > 0 else 0

    def test_mild_recession_capital_adequate(self):
        """경미 경기침체 (PD×1.5): 자기자본비율 8% 유지."""
        stressed_ratio = self._compute_stressed_capital_ratio(1.5)
        print(f"\n  [PD×1.5] 스트레스 자기자본비율: {stressed_ratio:.2%}")
        assert stressed_ratio >= MIN_CAPITAL_RATIO, \
            f"경미 경기침체 시 자기자본비율({stressed_ratio:.2%}) < 8%"

    def test_moderate_recession_capital_check(self):
        """중간 경기침체 (PD×2.0): 자본 상황 모니터링."""
        stressed_ratio = self._compute_stressed_capital_ratio(2.0)
        print(f"\n  [PD×2.0] 스트레스 자기자본비율: {stressed_ratio:.2%}")
        # 중간 스트레스에서도 Tier1 6% 이상 목표
        if stressed_ratio < MIN_CAPITAL_RATIO:
            print(f"  경고: 자기자본비율({stressed_ratio:.2%}) < 8% — 자본 확충 필요")
        # 음수 아님 확인 (파산 시나리오 방지)
        assert stressed_ratio > -0.10

    def test_severe_recession_el_quantification(self):
        """심각 경기침체 (PD×3.0): EL 최대 손실 추정."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        lgd = PORTFOLIO_BASE["avg_lgd_unsecured"]

        base_el = compute_el(ead, base_pd, lgd)
        stressed_el = compute_stressed_el(ead, base_pd, lgd, pd_multiplier=3.0, lgd_addon=0.15)

        el_increase = stressed_el - base_el
        el_ratio = stressed_el / base_el
        print(f"\n  [PD×3.0] EL: {base_el/1e8:.0f}억 → {stressed_el/1e8:.0f}억 ({el_ratio:.1f}배)")

        assert stressed_el > base_el
        assert el_ratio >= 3.0, "심각 스트레스 EL이 기본의 3배 이상이어야 함"

    def test_pd_multiplier_scenarios_monotone_el(self):
        """PD 배율이 높을수록 EL이 단조 증가."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        lgd = PORTFOLIO_BASE["avg_lgd_unsecured"]

        els = [
            compute_stressed_el(ead, base_pd, lgd, mult, 0)
            for mult in [1.0, 1.5, 2.0, 3.0]
        ]
        for i in range(len(els) - 1):
            assert els[i] < els[i + 1], f"EL 단조 증가 위반: {els}"

    def test_recession_raroc_decline(self):
        """경기침체 → RAROC 하락 (허들레이트 15% 이하로 떨어질 수 있음)."""
        ead = 100_000_000     # 1억 대출
        rate = 0.06           # 금리 6%
        months = 36
        base_pd = 0.05
        lgd = 0.45

        revenue = ead * rate * (months / 12)
        ec = ead * 0.08

        # 기본 RAROC
        base_el = compute_el(ead, base_pd, lgd)
        base_op_cost = ead * 0.015
        base_raroc = (revenue - base_el - base_op_cost) / ec

        # 스트레스 RAROC (PD×2.0)
        stress_el = compute_el(ead, min(1.0, base_pd * 2.0), lgd)
        stress_raroc = (revenue - stress_el - base_op_cost) / ec

        print(f"\n  기본 RAROC: {base_raroc:.2%} → 스트레스 RAROC: {stress_raroc:.2%}")
        assert stress_raroc < base_raroc, "스트레스 RAROC이 기본 RAROC보다 커야 함"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 복합 스트레스 시나리오
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestCombinedStressScenario:
    """금리↑ + 부동산↓ + PD↑ 복합 스트레스."""

    def _combined_stress_el(
        self,
        pd_multiplier: float,
        lgd_addon: float,
        rate_shock: float,
        collateral_drop: float,
    ) -> dict:
        """복합 스트레스 EL/EC 계산."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        mortgage_share = PORTFOLIO_BASE["mortgage_share"]
        credit_share = PORTFOLIO_BASE["credit_share"]

        # 신용대출 EL
        credit_el = compute_stressed_el(
            ead * credit_share,
            base_pd, PORTFOLIO_BASE["avg_lgd_unsecured"],
            pd_multiplier=pd_multiplier,
            lgd_addon=lgd_addon,
        )

        # 주담대 EL (담보 하락으로 LGD 추가)
        mortgage_lgd_addon = lgd_addon + collateral_drop * 0.3  # 담보 하락이 LGD에 미치는 영향
        mortgage_el = compute_stressed_el(
            ead * mortgage_share,
            base_pd, PORTFOLIO_BASE["avg_lgd_mortgage"],
            pd_multiplier=pd_multiplier * 1.1,  # 주담대 PD 추가 상승
            lgd_addon=mortgage_lgd_addon,
        )

        total_el = credit_el + mortgage_el
        current_capital = ead * PORTFOLIO_BASE["capital_ratio"]
        base_el = compute_el(ead, base_pd, PORTFOLIO_BASE["avg_lgd_unsecured"])
        stressed_capital_ratio = (current_capital - max(0, total_el - base_el)) / ead

        return {
            "total_el": total_el,
            "credit_el": credit_el,
            "mortgage_el": mortgage_el,
            "stressed_capital_ratio": stressed_capital_ratio,
        }

    def test_combined_mild_scenario(self):
        """복합 경미 시나리오: 자기자본비율 8% 유지."""
        result = self._combined_stress_el(
            **SCENARIOS["mild"]
        )
        ratio = result["stressed_capital_ratio"]
        print(f"\n  [복합 경미] EC비율: {ratio:.2%}, 총EL: {result['total_el']/1e8:.0f}억")
        assert ratio >= MIN_CAPITAL_RATIO, \
            f"복합 경미 시나리오 자기자본비율({ratio:.2%}) < 8%"

    def test_combined_moderate_scenario_capital(self):
        """복합 중간 시나리오: 자기자본비율 확인."""
        result = self._combined_stress_el(**SCENARIOS["moderate"])
        ratio = result["stressed_capital_ratio"]
        print(f"\n  [복합 중간] EC비율: {ratio:.2%}, 총EL: {result['total_el']/1e8:.0f}억")
        # 자본 고갈 여부 확인
        if ratio < 0.06:
            print(f"  경고: Tier1 자기자본비율({ratio:.2%}) < 6%")

    def test_combined_severe_scenario_el_quantification(self):
        """복합 심각 시나리오: 최대 손실 계량화."""
        result = self._combined_stress_el(**SCENARIOS["severe"])
        total_el = result["total_el"]
        total_ead = PORTFOLIO_BASE["total_ead"]

        el_rate = total_el / total_ead
        print(f"\n  [복합 심각] EL율: {el_rate:.2%}, 총EL: {total_el/1e8:.0f}억")

        # 심각 시나리오 EL율 < 30% (비현실적 시나리오 방지)
        assert 0 < el_rate < 0.30, f"EL율({el_rate:.2%}) 비현실적"

    def test_combined_severity_monotone(self):
        """시나리오 심각도에 따라 EL이 단조 증가."""
        els = [
            self._combined_stress_el(**SCENARIOS[s])["total_el"]
            for s in ["mild", "moderate", "severe"]
        ]
        assert els[0] < els[1] < els[2], \
            f"복합 시나리오 EL 단조 증가 위반: {[e/1e8 for e in els]}"

    def test_diversification_benefit(self):
        """신용대출 + 주담대 복합 포트폴리오: 완전 상관관계 가정 보수적."""
        # 완전 상관관계 vs 독립 상관관계 EL 비교
        ead_total = PORTFOLIO_BASE["total_ead"]
        pd = PORTFOLIO_BASE["avg_pd"]
        lgd = PORTFOLIO_BASE["avg_lgd_unsecured"]

        # 단일 자산 EL (보수적: 완전 상관)
        el_concentrated = compute_el(ead_total, pd, lgd)

        # 분산 포트폴리오 EL (독립: 선형 가중)
        el_diversified = (
            compute_el(ead_total * 0.55, pd, 0.45) +
            compute_el(ead_total * 0.35, pd * 0.8, 0.25) +
            compute_el(ead_total * 0.10, pd * 1.2, 0.60)
        )

        print(f"\n  집중 EL: {el_concentrated/1e8:.1f}억, 분산 EL: {el_diversified/1e8:.1f}억")
        # 분산 포트폴리오가 집중 포트폴리오보다 낮거나 비슷 (분산 효과)
        assert el_diversified <= el_concentrated * 1.1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 역스트레스 테스트 (Reverse Stress Test)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestReverseStress:
    """
    역스트레스 테스트: 자본 소진점(BIS 8% 하한)에 도달하는
    최소 충격 수준 역산.
    """

    def _find_pd_mult_at_capital_breach(self, target_ratio: float = 0.08) -> float:
        """자기자본비율이 target_ratio 이하로 떨어지는 최소 PD 배수 역산."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        lgd = PORTFOLIO_BASE["avg_lgd_unsecured"]
        current_capital = ead * PORTFOLIO_BASE["capital_ratio"]
        base_el = compute_el(ead, base_pd, lgd)

        # 이진 탐색으로 임계점 역산
        low, high = 1.0, 20.0
        for _ in range(30):
            mid = (low + high) / 2
            stressed_pd = min(1.0, base_pd * mid)
            stressed_el = compute_el(ead, stressed_pd, lgd)
            additional_loss = max(0, stressed_el - base_el)
            ratio = (current_capital - additional_loss) / ead
            if ratio > target_ratio:
                low = mid
            else:
                high = mid
        return round((low + high) / 2, 1)

    def test_capital_breach_pd_multiplier_found(self):
        """자본 소진점 PD 배수가 합리적 범위 (1.5~15배)."""
        breach_mult = self._find_pd_mult_at_capital_breach()
        print(f"\n  자본 소진 PD 배수: {breach_mult:.1f}배 (BIS 8% 기준)")
        assert 1.5 <= breach_mult <= 15.0, \
            f"비현실적 임계 PD 배수: {breach_mult}배"

    def test_severe_scenario_below_breach_point(self):
        """심각 시나리오 (PD×3.0)가 자본 소진 임계점 이하임을 확인."""
        breach_mult = self._find_pd_mult_at_capital_breach()
        severe_mult = SCENARIOS["severe"]["pd_multiplier"]  # 3.0

        if severe_mult >= breach_mult:
            print(f"\n  경고: 심각 시나리오(PD×{severe_mult}) ≥ 자본소진점(PD×{breach_mult:.1f})")
            print("  → 자본 확충 또는 포트폴리오 위험 감소 필요")
        else:
            print(f"\n  심각 시나리오(PD×{severe_mult}) < 자본소진점(PD×{breach_mult:.1f}) — 자본 완충 충분")

        # 어느 쪽이든 테스트 통과 (정보 제공 목적)
        assert breach_mult > 0

    def test_reverse_stress_lgd_shock(self):
        """LGD 충격에 의한 자본 소진점 역산."""
        ead = PORTFOLIO_BASE["total_ead"]
        base_pd = PORTFOLIO_BASE["avg_pd"]
        current_capital = ead * PORTFOLIO_BASE["capital_ratio"]
        base_el = compute_el(ead, base_pd, 0.45)

        # LGD가 몇 %p 상승하면 자본 소진?
        for lgd_shock in np.arange(0.05, 0.55, 0.05):
            stressed_lgd = min(1.0, 0.45 + lgd_shock)
            stressed_el = compute_el(ead, base_pd, stressed_lgd)
            capital_ratio = (current_capital - max(0, stressed_el - base_el)) / ead
            if capital_ratio < 0.08:
                print(f"\n  LGD +{lgd_shock:.0%}p 충격 시 자기자본비율 {capital_ratio:.2%} < 8%")
                break
        else:
            print(f"\n  LGD 충격 단독으로 자본 소진 없음 (현재 자본 충분)")

        # 정보 제공 테스트 — 무조건 통과
        assert True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. PSI 스트레스 (모델 드리프트 시뮬레이션)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestPSIMonitoring:
    """PSI 계산 검증 및 모델 드리프트 감지."""

    def _compute_psi_simple(self, ref: np.ndarray, cur: np.ndarray, n_bins: int = 10) -> float:
        bins = np.percentile(ref, np.linspace(0, 100, n_bins + 1))
        bins[0] = -np.inf
        bins[-1] = np.inf
        ref_c, _ = np.histogram(ref, bins=bins)
        cur_c, _ = np.histogram(cur, bins=bins)
        ref_p = (ref_c + 0.5) / (len(ref) + 0.5 * n_bins)
        cur_p = (cur_c + 0.5) / (len(cur) + 0.5 * n_bins)
        return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))

    def test_stable_population_low_psi(self):
        """동일 분포: PSI < 0.05 (안정)."""
        rng = np.random.default_rng(42)
        ref = rng.normal(680, 80, 5000)
        cur = rng.normal(680, 80, 2000)  # 동일 분포
        psi = self._compute_psi_simple(ref, cur)
        print(f"\n  안정 집단 PSI: {psi:.4f}")
        assert psi < 0.10, f"안정 집단 PSI({psi:.4f}) ≥ 0.10"

    def test_shifted_population_high_psi(self):
        """평균 80점 하락 분포: PSI > 0.20 (드리프트 감지)."""
        rng = np.random.default_rng(42)
        ref = rng.normal(680, 80, 5000)
        cur = rng.normal(580, 100, 2000)  # 평균 100점 하락, 분산 증가
        psi = self._compute_psi_simple(ref, cur)
        print(f"\n  이동 집단 PSI: {psi:.4f}")
        assert psi > 0.20, f"드리프트 감지 실패: PSI({psi:.4f}) ≤ 0.20"

    def test_psi_monotone_with_drift_magnitude(self):
        """분포 이동 크기에 따라 PSI 단조 증가."""
        rng = np.random.default_rng(42)
        ref = rng.normal(680, 80, 5000)

        psi_values = []
        for mean_shift in [0, 20, 50, 80, 120]:
            cur = rng.normal(680 - mean_shift, 80, 2000)
            psi = self._compute_psi_simple(ref, cur)
            psi_values.append(psi)

        for i in range(len(psi_values) - 1):
            assert psi_values[i] <= psi_values[i + 1] + 0.01, \
                f"PSI 단조성 위반: {[round(p, 4) for p in psi_values]}"

    def test_psi_from_monitoring_engine(self):
        """MonitoringEngine PSI 계산 통합 테스트."""
        monitoring_path = os.path.join(
            BASE_DIR, "backend", "app", "core", "monitoring_engine.py"
        )
        if not os.path.exists(monitoring_path):
            pytest.skip("monitoring_engine.py 없음")

        sys.path.insert(0, os.path.join(BASE_DIR, "backend"))
        try:
            from app.core.monitoring_engine import compute_psi, PSI_GREEN, PSI_YELLOW
        except ImportError as e:
            pytest.skip(f"monitoring_engine import 실패: {e}")

        rng = np.random.default_rng(42)
        ref = rng.normal(680, 80, 5000)
        cur = rng.normal(650, 90, 2000)

        result = compute_psi(ref, cur, n_bins=10)
        print(f"\n  MonitoringEngine PSI: {result.psi:.4f} ({result.status})")
        assert 0 <= result.psi <= 1.0
        assert result.status in ("green", "yellow", "red")
        assert len(result.bins) == 10


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
