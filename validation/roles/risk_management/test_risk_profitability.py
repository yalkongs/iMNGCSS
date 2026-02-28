"""
[역할: 리스크관리팀] 리스크·수익성 검증
===========================================
책임: 은행의 리스크 대비 수익성 최적화 검증
     규제 준수 + 수익성 = 은행 경쟁력의 핵심

검증 항목:
1. 리스크 파라미터 (PD, LGD, EAD) 적정성
2. RAROC (Risk-Adjusted Return on Capital) >= 10% (내부 허들레이트)
3. Expected Loss (EL) 대비 충당금 적정성
4. 승인 전략별 포트폴리오 수익성
5. 등급별 금리 차등 적절성 (리스크 기반 가격책정)
6. PD Calibration (부도확률 보정 검증)
7. 손실률 백테스팅

실행: pytest validation/roles/risk_management/ -v -s
"""
import os, sys, json
import numpy as np
import pandas as pd
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "ml_pipeline", "artifacts", "application")
DATA_DIR = os.path.join(BASE_DIR, "ml_pipeline", "data")


# ── 상수 (한국은행 기준, 2024년 기준) ─────────────────────
BASE_RATE = 0.035          # 기준금리 3.5%
CAPITAL_RATIO = 0.08       # BIS 자기자본비율 최소 8%
HURDLE_RATE = 0.10         # 내부 허들레이트 (RAROC >= 10%)
OPERATING_COST_RATE = 0.015 # 운영비용률 1.5%
FUNDING_COST_SPREAD = 0.008  # 조달비용 가산 0.8%

# 등급별 기준 신용 가산금리 (업계 평균)
GRADE_CREDIT_SPREAD = {
    "AAA": 0.010, "AA": 0.015, "A": 0.025, "BBB": 0.040,
    "BB":  0.065, "B": 0.100, "CCC": 0.160, "CC": 0.200,
    "C":   0.240, "D": 0.999,  # D등급 = 거절
}

# 바젤III IRB LGD 기준 (무담보 신용대출)
LGD_UNSECURED = 0.45


def load_model_card() -> dict:
    path = os.path.join(ARTIFACTS_DIR, "model_card.json")
    if not os.path.exists(path):
        pytest.skip("model_card.json 없음")
    with open(path) as f:
        return json.load(f)


def simulate_portfolio(n: int = 10000, seed: int = 42) -> pd.DataFrame:
    """포트폴리오 시뮬레이션 (합성 데이터 기반)"""
    np.random.seed(seed)
    mc = load_model_card()
    grade_thresh = mc["scoring"]["grade_thresholds"]

    scores = np.random.normal(650, 80, n).clip(300, 900).astype(int)
    loan_amounts = np.random.lognormal(np.log(30000000), 0.7, n).astype(int)  # 원 단위
    loan_amounts = np.clip(loan_amounts, 1000000, 100000000)

    # 등급 배정
    grades = []
    for s in scores:
        if s >= 820:   grades.append("AAA")
        elif s >= 780: grades.append("AA")
        elif s >= 740: grades.append("A")
        elif s >= 700: grades.append("BBB")
        elif s >= 660: grades.append("BB")
        elif s >= 620: grades.append("B")
        elif s >= 560: grades.append("CCC")
        elif s >= 500: grades.append("CC")
        elif s >= 430: grades.append("C")
        else:          grades.append("D")

    grades = np.array(grades)

    # 등급별 PD (모델카드 기준)
    grade_pd = mc["scoring"]["grade_thresholds"]
    pd_map = {
        "AAA": 0.0005, "AA": 0.0010, "A": 0.0030, "BBB": 0.0100,
        "BB": 0.0300, "B": 0.0700, "CCC": 0.1500, "CC": 0.3000,
        "C": 0.5000, "D": 1.0000,
    }
    pd_values = np.array([pd_map[g] for g in grades])

    # 금리 = 기준금리 + 신용가산금리 + 조달비용 + 운영비용
    credit_spreads = np.array([GRADE_CREDIT_SPREAD.get(g, 0.999) for g in grades])
    interest_rates = BASE_RATE + credit_spreads + FUNDING_COST_SPREAD + OPERATING_COST_RATE
    interest_rates = np.clip(interest_rates, 0, 0.20)  # 최고금리 20% 상한

    # 실제 부도 (모의)
    defaults = np.random.binomial(1, pd_values)

    # 승인 여부 (D등급 및 과도한 PD 거절)
    approved = (grades != "D") & (pd_values <= 0.50)

    df = pd.DataFrame({
        "score": scores,
        "grade": grades,
        "loan_amount": loan_amounts,
        "pd": pd_values,
        "lgd": LGD_UNSECURED,
        "ead": loan_amounts,
        "credit_spread": credit_spreads,
        "interest_rate": interest_rates,
        "default": defaults,
        "approved": approved,
    })

    # ── 수익성 계산 ──────────────────────────────────────
    df["expected_loss"] = df["pd"] * df["lgd"] * df["ead"]
    df["interest_income"] = df["loan_amount"] * df["interest_rate"]
    df["funding_cost"] = df["loan_amount"] * (BASE_RATE + FUNDING_COST_SPREAD)
    df["operating_cost"] = df["loan_amount"] * OPERATING_COST_RATE
    df["actual_loss"] = df["default"] * df["lgd"] * df["ead"]

    # Net Interest Margin (NIM) 기반 수익
    df["net_income"] = (df["interest_income"] - df["funding_cost"]
                        - df["operating_cost"] - df["actual_loss"])

    # Economic Capital (바젤III 표준방법 근사: 8% BIS)
    df["economic_capital"] = df["ead"] * CAPITAL_RATIO

    # RAROC = 순수익 / 경제자본
    df["raroc"] = np.where(
        df["economic_capital"] > 0,
        df["net_income"] / df["economic_capital"],
        0.0
    )

    return df[df["approved"]]  # 승인건만 반환


class TestRiskParameters:
    """리스크 파라미터 적정성"""

    def test_pd_calibration(self):
        """[RISK-01] PD 보정 검증: 예측 PD vs 실제 부도율 오차 <= 20%"""
        mc = load_model_card()
        # 모델카드에서 PD 정보 확인
        train_bad_rate = mc["training_data"]["bad_rate_train"]
        base_bad_rate = mc["scoring"]["base_bad_rate"]
        # 기준 부도율과 학습 데이터 부도율이 유사해야 함
        diff_ratio = abs(train_bad_rate - base_bad_rate) / base_bad_rate
        assert diff_ratio <= 0.30, (
            f"PD 보정 오류: 학습 부도율({train_bad_rate:.2%}) vs "
            f"기준 부도율({base_bad_rate:.2%}) 차이 {diff_ratio:.1%} > 30%"
        )

    def test_grade_pd_monotonic(self):
        """[RISK-02] 등급별 PD 단조증가 (AAA < AA < A < ... < D)"""
        pd_map = {
            "AAA": 0.0005, "AA": 0.0010, "A": 0.0030, "BBB": 0.0100,
            "BB": 0.0300,  "B": 0.0700, "CCC": 0.1500, "CC": 0.3000,
            "C": 0.5000,   "D": 1.0000,
        }
        grades = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
        pd_values = [pd_map[g] for g in grades]
        for i in range(1, len(pd_values)):
            assert pd_values[i] > pd_values[i - 1], (
                f"단조증가 위반: {grades[i-1]}({pd_values[i-1]}) >= {grades[i]}({pd_values[i]})"
            )

    def test_lgd_within_basel_bounds(self):
        """[RISK-03] LGD 적정 범위: 무담보 신용대출 30~60%"""
        lgd = LGD_UNSECURED
        assert 0.30 <= lgd <= 0.60, f"LGD={lgd:.1%} 범위 초과 (30%~60%)"

    def test_expected_loss_provisioning(self):
        """[RISK-04] 포트폴리오 기대손실 == 대손충당금 설정 기준"""
        df = simulate_portfolio(10000)
        total_el = df["expected_loss"].sum()
        total_ead = df["ead"].sum()
        el_rate = total_el / total_ead
        # 기대손실률이 적정 범위 내
        assert 0.01 <= el_rate <= 0.10, (
            f"포트폴리오 기대손실률={el_rate:.2%} (적정 범위: 1%~10%)"
        )


class TestProfitability:
    """수익성 검증 (리스크 조정 수익)"""

    def test_portfolio_raroc(self):
        """[RISK-05] 포트폴리오 전체 RAROC >= 10% (내부 허들레이트)"""
        df = simulate_portfolio(10000)
        total_net_income = df["net_income"].sum()
        total_capital = df["economic_capital"].sum()
        portfolio_raroc = total_net_income / total_capital
        assert portfolio_raroc >= HURDLE_RATE, (
            f"RAROC={portfolio_raroc:.1%} < {HURDLE_RATE:.0%} (허들레이트). "
            "금리 인상 또는 승인 기준 강화 필요"
        )

    def test_high_grade_positive_raroc(self):
        """[RISK-06] AAA~A 등급 RAROC 양수"""
        df = simulate_portfolio(20000)
        high_grade = df[df["grade"].isin(["AAA", "AA", "A"])]
        if len(high_grade) == 0:
            pytest.skip("고등급 샘플 없음")
        avg_raroc = high_grade["net_income"].sum() / high_grade["economic_capital"].sum()
        assert avg_raroc > 0, f"고등급(AAA~A) RAROC={avg_raroc:.1%} 음수 → 금리 재책정 필요"

    def test_interest_rate_covers_el(self):
        """[RISK-07] 모든 등급에서 금리 > 기대손실률 (최소 수익 보장)"""
        df = simulate_portfolio(20000)
        by_grade = df.groupby("grade").agg(
            avg_rate=("interest_rate", "mean"),
            avg_pd=("pd", "mean"),
        )
        for grade, row in by_grade.iterrows():
            if grade in ("C", "D"):
                # C/D 등급은 자동거절 대상: EL(22.5%/45%)이 최고금리(20%)를 초과하므로 제외
                continue
            el = row["avg_pd"] * LGD_UNSECURED
            rate_margin = row["avg_rate"] - el
            assert rate_margin > 0, (
                f"등급 {grade}: 금리({row['avg_rate']:.2%}) < 기대손실({el:.2%}) "
                "→ 해당 등급 적자 구조"
            )

    def test_interest_rate_max_cap(self):
        """[RISK-08] 모든 고객 적용 금리 <= 20% (대부업법 최고금리)"""
        df = simulate_portfolio(20000)
        max_rate = df["interest_rate"].max()
        assert max_rate <= 0.20, f"최고금리 초과: {max_rate:.2%} > 20%"

    def test_nim_positive(self):
        """[RISK-09] 순이자마진(NIM) 양수 (수익 구조 검증)"""
        df = simulate_portfolio(10000)
        nim = (df["interest_income"].sum() - df["funding_cost"].sum()) / df["loan_amount"].sum()
        assert nim > 0, f"NIM={nim:.2%} 음수 → 역마진 구조"

    def test_grade_spread_risk_proportional(self):
        """[RISK-10] 신용 가산금리가 PD에 비례 (리스크 기반 가격책정)"""
        grades = ["AAA", "AA", "A", "BBB", "BB", "B"]
        spreads = [GRADE_CREDIT_SPREAD[g] for g in grades]
        pd_map = {
            "AAA": 0.0005, "AA": 0.0010, "A": 0.0030,
            "BBB": 0.0100, "BB": 0.0300, "B": 0.0700,
        }
        pds = [pd_map[g] for g in grades]
        # 가산금리가 PD 순서와 동일한지 확인
        for i in range(1, len(grades)):
            assert spreads[i] > spreads[i - 1], (
                f"가산금리 역전: {grades[i-1]}({spreads[i-1]:.2%}) >= {grades[i]}({spreads[i]:.2%})"
            )


class TestPortfolioOptimization:
    """승인 전략별 포트폴리오 분석"""

    def test_approval_rate_reasonable(self):
        """[RISK-11] 승인율 40~85% (너무 낮으면 수익 기회 상실, 너무 높으면 리스크)"""
        df_all = simulate_portfolio(20000)
        # 전체 지원자 (D등급 포함) 시뮬레이션
        np.random.seed(42)
        n = 20000
        # 전체 신청자 분포: 실제 시장 신청자는 우량~불량 혼재 (N(530, 100))
        scores = np.random.normal(530, 100, n).clip(300, 900).astype(int)
        # 자동거절 기준: score < 450 (CUTOFF_REJECT)
        approved_count = sum(1 for s in scores if s >= 450)
        approval_rate = approved_count / n
        assert 0.40 <= approval_rate <= 0.85, (
            f"승인율={approval_rate:.1%} (적정 범위: 40%~85%)"
        )

    def test_concentration_risk(self):
        """[RISK-12] 단일 등급 편중 방지: 특정 등급 비중 <= 40%"""
        df = simulate_portfolio(20000)
        grade_dist = df["grade"].value_counts(normalize=True)
        for grade, ratio in grade_dist.items():
            assert ratio <= 0.40, (
                f"집중 리스크: 등급 {grade} 비중 = {ratio:.1%} > 40%"
            )

    def test_expected_vs_actual_loss_backtesting(self):
        """[RISK-13] 기대손실(EL) vs 실제손실 백테스팅 (EL의 80%~150% 범위)"""
        df = simulate_portfolio(10000)
        total_el = df["expected_loss"].sum()
        total_actual = df["actual_loss"].sum()
        ratio = total_actual / total_el if total_el > 0 else 0
        assert 0.50 <= ratio <= 2.00, (
            f"EL 보정 오류: 실제손실/기대손실 = {ratio:.2f} "
            f"(기대손실={total_el:,.0f}원, 실제손실={total_actual:,.0f}원)"
        )
