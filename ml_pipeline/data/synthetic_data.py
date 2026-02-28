"""
한국 은행 개인/개인사업자 대출 합성 데이터 생성기 (v1.1)
============================================================
실제 한국 금융 통계 기반:
- 나이스/KCB 신용등급 분포
- 통계청 가계소득 분포 (2023년 기준)
- 금감원 은행 여신 연체율 통계
- 부도율: ~7% (일반 신용대출 기준)

v1.1 추가:
- applicant_type: 개인 / 개인사업자 이원 구조
- 특수 세그먼트: SEG-DR(의사), SEG-JD(변호사), SEG-ART(예술인), SEG-YTH(청년), SEG-MOU(협약기업)
- EQ Grade (직장/기업 신용도) + IRG (산업 리스크 등급)
- 개인사업자 전용 필드 (매출, 영업이익, 사업기간 등)
- 총 10만건 생성

출력: ml_pipeline/data/ 하위 parquet 파일
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import warnings
warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = BASE_DIR
np.random.seed(42)


# ── 한국 금융 통계 기반 분포 상수 ───────────────────────────
CB_SCORE_DIST = {
    "mean": 680, "std": 120, "min": 300, "max": 1000
}
INCOME_DIST_BY_JOB = {
    "employed":      {"mean": 4800, "std": 2000, "min": 1800},  # 단위: 만원/년
    "self_employed": {"mean": 4200, "std": 2500, "min": 1200},
    "retired":       {"mean": 2400, "std": 1000, "min": 800},
    "student":       {"mean": 1000, "std": 500,  "min": 400},
    "unemployed":    {"mean": 1600, "std": 800,  "min": 600},
    # 특수 직역 (높은 소득)
    "doctor":        {"mean": 18000, "std": 6000, "min": 8000},
    "dentist":       {"mean": 15000, "std": 5000, "min": 7000},
    "oriental_md":   {"mean": 10000, "std": 4000, "min": 5000},
    "lawyer":        {"mean": 13000, "std": 7000, "min": 5000},
    "accountant":    {"mean": 9000,  "std": 4000, "min": 4000},
    "artist":        {"mean": 2200,  "std": 1500, "min": 600},
    "military":      {"mean": 4500,  "std": 1500, "min": 2400},
}
AGE_DIST = {
    "20s": (20, 29, 0.15),
    "30s": (30, 39, 0.28),
    "40s": (40, 49, 0.27),
    "50s": (50, 59, 0.20),
    "60+": (60, 75, 0.10),
}
# 일반 직업 분포 (비특수직역)
JOB_DIST = {
    "employed":      0.58,
    "self_employed": 0.20,
    "retired":       0.10,
    "student":       0.05,
    "unemployed":    0.07,
}
# 특수직역 인구 비중 (전체 중 %)
SPECIAL_SEGMENT_DIST = {
    "SEG-DR":  0.020,   # 2.0% - 의사/치과의사/한의사
    "SEG-JD":  0.015,   # 1.5% - 변호사/법무사/회계사
    "SEG-ART": 0.010,   # 1.0% - 예술인복지재단 등록 예술인
    "SEG-YTH": 0.100,   # 10.0% - 청년(만 19-34세, 연령 조건)
    "SEG-MIL": 0.025,   # 2.5% - 군인/공무원
    "SEG-MOU": 0.080,   # 8.0% - 협약기업(MOU) 근로자
}
BAD_RATE_TARGET = 0.072   # 한국 신용대출 평균 부도율 약 7.2%

# EQ Grade 분포 (직장/기업 신용도)
EQ_GRADE_DIST = {
    "EQ-S": (0.03, 2.0, -0.5),   # (비율, 한도배수, 금리조정)
    "EQ-A": (0.10, 1.8, -0.3),
    "EQ-B": (0.20, 1.5, -0.2),
    "EQ-C": (0.40, 1.2,  0.0),
    "EQ-D": (0.20, 1.0,  0.2),
    "EQ-E": (0.07, 0.7,  0.5),
}

# IRG (산업 리스크 등급) 분포
IRG_DIST = {
    "L":  (0.15, -0.10),   # (비율, PD 조정)
    "M":  (0.50,  0.00),
    "H":  (0.25,  0.15),
    "VH": (0.10,  0.30),
}

# MOU 기업 코드 목록
MOU_CODES = ["MOU-SEC001", "MOU-HMC001", "MOU-KKO001", "MOU-NVR001", "MOU-GOV001",
             "MOU-LGE001", "MOU-SKH001", "MOU-POS001", "MOU-KEB001", "MOU-IBK001"]


def generate_special_segments(
    age: np.ndarray, employment: np.ndarray, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    특수 세그먼트 코드 및 직종 코드 생성.
    연령/직업 조건을 반영하여 현실적 분포 생성.

    Returns:
        (segment_code_arr, occupation_type_arr)
    """
    segment_codes = np.array([""] * n, dtype=object)
    occupation_types = employment.copy().astype(object)

    # SEG-YTH: 청년 (19-34세) - 연령 조건 자동 적용
    youth_mask = (age >= 19) & (age <= 34)
    # SEG-YTH는 다른 세그먼트와 중복 가능하지만 기본 배정은 연령 기반
    yth_rollout = np.random.random(n) < 0.60  # 청년 중 60%가 SEG-YTH 신청
    segment_codes[youth_mask & yth_rollout] = "SEG-YTH"

    # SEG-DR: 의사/치과의사/한의사 (직장인 중 일부)
    dr_pool = (employment == "employed") & (age >= 28) & (age <= 65)
    dr_mask = dr_pool & (np.random.random(n) < (SPECIAL_SEGMENT_DIST["SEG-DR"] / dr_pool.mean() if dr_pool.mean() > 0 else 0))
    segment_codes[dr_mask] = "SEG-DR"
    occ_types = np.random.choice(["doctor", "dentist", "oriental_md"], size=dr_mask.sum())
    occupation_types[dr_mask] = occ_types

    # SEG-JD: 변호사/법무사/회계사
    jd_pool = (employment == "employed") & (age >= 27) & (age <= 65)
    jd_mask = jd_pool & (np.random.random(n) < (SPECIAL_SEGMENT_DIST["SEG-JD"] / jd_pool.mean() if jd_pool.mean() > 0 else 0))
    jd_mask = jd_mask & (segment_codes == "")  # 중복 방지
    segment_codes[jd_mask] = "SEG-JD"
    occ_types_jd = np.random.choice(["lawyer", "legal_scrivener", "accountant"], size=jd_mask.sum())
    occupation_types[jd_mask] = occ_types_jd

    # SEG-ART: 예술인 (특수 고용 형태)
    art_pool = age <= 60
    art_mask = art_pool & (np.random.random(n) < SPECIAL_SEGMENT_DIST["SEG-ART"]) & (segment_codes == "")
    segment_codes[art_mask] = "SEG-ART"
    occupation_types[art_mask] = "artist"

    # SEG-MIL: 군인/공무원
    mil_pool = (employment == "employed") & (age >= 22) & (age <= 60)
    mil_mask = mil_pool & (np.random.random(n) < (SPECIAL_SEGMENT_DIST["SEG-MIL"] / mil_pool.mean() if mil_pool.mean() > 0 else 0))
    mil_mask = mil_mask & (segment_codes == "")
    segment_codes[mil_mask] = "SEG-MIL"
    occupation_types[mil_mask] = "military"

    # SEG-MOU: 협약기업 근로자
    mou_pool = employment == "employed"
    mou_mask = mou_pool & (np.random.random(n) < SPECIAL_SEGMENT_DIST["SEG-MOU"]) & (segment_codes == "")
    segment_codes[mou_mask] = "SEG-MOU-" + np.random.choice(MOU_CODES, size=mou_mask.sum())

    return segment_codes, occupation_types


def generate_eq_irg(employment: np.ndarray, segment_codes: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """
    EQ Grade (기업 신용도) 및 IRG (산업 리스크 등급) 생성.
    특수 세그먼트는 최소 보장 EQ Grade 적용.
    """
    eq_grades = np.array(["EQ-C"] * n, dtype=object)
    irg_codes = np.array(["M"] * n, dtype=object)

    # 일반 직장인 EQ Grade 확률적 배정
    employed_mask = employment == "employed"
    eq_choices = list(EQ_GRADE_DIST.keys())
    eq_probs = [v[0] for v in EQ_GRADE_DIST.values()]
    eq_grades[employed_mask] = np.random.choice(
        eq_choices, size=employed_mask.sum(), p=eq_probs
    )

    # 특수 세그먼트 최소 EQ Grade 보장
    seg_eq_guarantee = {
        "SEG-DR":  "EQ-B",   # 의료전문직 최소 EQ-B
        "SEG-JD":  "EQ-B",   # 법무전문직 최소 EQ-B
        "SEG-MIL": "EQ-S",   # 군인/공무원 EQ-S
    }
    eq_order = ["EQ-S", "EQ-A", "EQ-B", "EQ-C", "EQ-D", "EQ-E"]
    for seg, min_grade in seg_eq_guarantee.items():
        seg_mask = np.char.startswith(segment_codes.astype(str), seg.split("-")[0] + "-" + seg.split("-")[1] if "-" in seg else seg)
        # 정확한 매칭
        exact_mask = segment_codes == seg
        if exact_mask.any():
            min_idx = eq_order.index(min_grade)
            for i in np.where(exact_mask)[0]:
                cur_idx = eq_order.index(eq_grades[i]) if eq_grades[i] in eq_order else 5
                if cur_idx > min_idx:
                    eq_grades[i] = min_grade

    # IRG 배정 (개인사업자 업종별)
    irg_choices = list(IRG_DIST.keys())
    irg_probs = [v[0] for v in IRG_DIST.values()]
    irg_codes[:] = np.random.choice(irg_choices, size=n, p=irg_probs)

    return eq_grades, irg_codes


def generate_soho_fields(employment: np.ndarray, income_annual: np.ndarray, n: int) -> pd.DataFrame:
    """
    개인사업자(SOHO) 전용 필드 생성.
    일반 직장인은 NaN 처리.
    """
    soho_mask = employment == "self_employed"
    k = soho_mask.sum()

    business_duration = np.where(
        soho_mask,
        np.random.exponential(72, n).clip(1, 360).astype(int),
        0
    )
    revenue_annual = np.where(
        soho_mask,
        np.clip(income_annual * np.random.uniform(1.5, 4.0, n), 1000, 200000) * 10000,
        0
    ).astype(int)
    operating_income = np.where(
        soho_mask,
        revenue_annual * np.random.uniform(0.05, 0.25, n),
        0
    ).astype(int)
    revenue_growth = np.where(
        soho_mask,
        np.random.normal(0.05, 0.20, n),
        0.0
    ).round(4)
    tax_filing_count = np.where(
        soho_mask,
        np.random.randint(1, 4, n),
        0
    )

    business_types = np.array([""] * n, dtype=object)
    btype_choices = ["음식점업", "도소매업", "서비스업", "제조업", "건설업", "운수업", "정보통신업", "부동산업"]
    business_types[soho_mask] = np.random.choice(btype_choices, size=k)

    return pd.DataFrame({
        "business_duration_months": business_duration,
        "revenue_annual": revenue_annual,
        "operating_income": operating_income,
        "revenue_growth_rate": revenue_growth,
        "tax_filing_count": tax_filing_count,
        "business_type": business_types,
    })


def generate_age(n: int) -> np.ndarray:
    """통계청 경제활동인구 연령 분포 기반"""
    ages = []
    for band, (lo, hi, prob) in AGE_DIST.items():
        count = int(n * prob)
        ages.extend(np.random.randint(lo, hi + 1, count).tolist())
    remaining = n - len(ages)
    ages.extend(np.random.randint(30, 50, remaining).tolist())
    result = np.array(ages[:n])
    np.random.shuffle(result)
    return result


def generate_employment(n: int) -> np.ndarray:
    jobs = list(JOB_DIST.keys())
    probs = list(JOB_DIST.values())
    return np.random.choice(jobs, size=n, p=probs)


def generate_income(jobs: np.ndarray) -> np.ndarray:
    incomes = np.zeros(len(jobs))
    for job, params in INCOME_DIST_BY_JOB.items():
        mask = jobs == job
        count = mask.sum()
        if count > 0:
            raw = np.random.normal(params["mean"], params["std"], count)
            incomes[mask] = np.clip(raw, params["min"], None)
    return np.round(incomes, 0)


def generate_cb_features(n: int, income_annual: np.ndarray) -> pd.DataFrame:
    """
    CB(신용조회회사) 제공 신용 변수 생성
    - KCB/NICE 신용점수 분포 기반
    - 소득과 신용도의 상관관계 반영
    """
    # 기본 CB 점수 (소득 수준과 양의 상관관계)
    income_normalized = (income_annual - income_annual.min()) / (income_annual.max() - income_annual.min() + 1)
    cb_base = np.random.normal(CB_SCORE_DIST["mean"], CB_SCORE_DIST["std"], n)
    cb_base += income_normalized * 80  # 소득 효과
    cb_score = np.clip(cb_base, CB_SCORE_DIST["min"], CB_SCORE_DIST["max"]).astype(int)

    # 연체 이력 (CB 점수와 역상관)
    delinq_prob_base = 1 / (1 + np.exp((cb_score - 600) / 80))  # logistic
    delinq_12m = np.random.binomial(5, delinq_prob_base * 0.3)
    delinq_24m = delinq_12m + np.random.binomial(3, delinq_prob_base * 0.2)

    # 보유 대출 건수
    open_loans = np.random.poisson(2.1, n).clip(0, 10)

    # 총 부채 잔액 (소득 대비)
    debt_ratio = np.random.beta(2, 5, n) * 3.0  # 0~3 배수
    total_loan_balance = (income_annual * debt_ratio * 10000).astype(int)  # 원 단위

    # 최근 3/6개월 조회 수 (많을수록 위험)
    inquiry_3m = np.random.poisson(1.2, n).clip(0, 10)
    inquiry_6m = inquiry_3m + np.random.poisson(0.8, n).clip(0, 5)

    # 신용카드 보유 수
    card_count = np.random.poisson(2.3, n).clip(0, 8)

    # 최악 연체 상태 (0=정상, 1=1개월, 2=2개월, 3=3개월+)
    worst_delinq = np.zeros(n, dtype=int)
    mask_1m = delinq_24m > 0
    mask_2m = delinq_24m > 2
    mask_3m = delinq_24m > 4
    worst_delinq[mask_1m] = 1
    worst_delinq[mask_2m] = 2
    worst_delinq[mask_3m] = 3

    return pd.DataFrame({
        "cb_score": cb_score,
        "delinquency_count_12m": delinq_12m,
        "delinquency_count_24m": delinq_24m,
        "open_loan_count": open_loans,
        "total_loan_balance": total_loan_balance,
        "inquiry_count_3m": inquiry_3m,
        "inquiry_count_6m": inquiry_6m,
        "credit_card_count": card_count,
        "worst_delinquency_status": worst_delinq,
    })


def generate_financial_ratios(income_annual: np.ndarray, total_loan_balance: np.ndarray,
                               requested_amount: np.ndarray) -> pd.DataFrame:
    """DSR, DTI, 부채비율 등 재무 비율 생성"""
    income_monthly = income_annual * 10000 / 12  # 원 단위 월소득

    # 기존 부채 월 원리금 (총 부채 기준 추정)
    existing_monthly_payment = total_loan_balance * 0.008  # 금리 4.5%, 20년 상환 가정

    # 신청 대출 월 원리금
    new_monthly_payment = requested_amount * 0.005  # 금리 5%, 20년 상환 가정

    dsr_ratio = np.where(
        income_monthly > 0,
        (existing_monthly_payment + new_monthly_payment) / income_monthly * 100,
        999.0
    )

    debt_to_income = np.where(
        income_annual > 0,
        total_loan_balance / (income_annual * 10000),
        999.0
    )

    loan_to_income = np.where(
        income_annual > 0,
        requested_amount / (income_annual * 10000),
        999.0
    )

    return pd.DataFrame({
        "dsr_ratio": np.clip(dsr_ratio, 0, 300).round(2),
        "debt_to_income": np.clip(debt_to_income, 0, 10).round(4),
        "loan_to_income": np.clip(loan_to_income, 0, 5).round(4),
        "existing_monthly_payment": existing_monthly_payment.astype(int),
    })


def generate_transaction_behavior(income_annual: np.ndarray, cb_score: np.ndarray) -> pd.DataFrame:
    """계좌 거래 행동 변수 생성 (오픈뱅킹 기반)"""
    income_monthly = income_annual * 10000 / 12

    # 월 입금액 (소득과 유사하나 노이즈 포함)
    avg_inflow = income_monthly * np.random.normal(1.05, 0.2, len(income_annual))
    avg_inflow = np.clip(avg_inflow, 300000, None)

    # 지출 패턴 (소득 대비 지출 비율)
    expense_ratio = np.random.beta(3, 2, len(income_annual)) * 0.95
    avg_expense = avg_inflow * expense_ratio

    # 저축률
    savings_rate = np.clip((avg_inflow - avg_expense) / avg_inflow, 0, 0.8)

    # 카드 사용 비율 (고신용자일수록 높은 경향)
    card_usage_rate = np.clip(
        (cb_score - 400) / 600 * 0.7 + np.random.normal(0, 0.1, len(cb_score)),
        0, 1
    )

    # 당좌차월 발생 건수 (연간)
    overdraft_prob = 1 - cb_score / 1100
    overdraft_count = np.random.poisson(np.clip(overdraft_prob * 3, 0, 8))

    return pd.DataFrame({
        "avg_monthly_inflow": avg_inflow.round(0).astype(int),
        "avg_monthly_expense": avg_expense.round(0).astype(int),
        "savings_rate": savings_rate.round(4),
        "card_usage_rate": card_usage_rate.round(4),
        "overdraft_count_annual": overdraft_count,
    })


def generate_alternative_data(income_annual: np.ndarray, n: int) -> pd.DataFrame:
    """
    대안 데이터 (동의 기반, 신용정보법 §32)
    - 통신료 납부 이력 (이동통신 연체)
    - 건강보험료 납부 이력 (소득 검증 연동)
    - 국민연금 납부 이력 (직장 안정성)
    """
    # 통신료 연체 없음 비율 (소득과 양의 상관)
    telecom_ok_prob = np.clip(0.85 + income_annual / 100000 * 0.1, 0.6, 0.98)
    telecom_no_delinquency = np.random.binomial(1, telecom_ok_prob)

    # 건보료 납부 월 수 (최근 12개월)
    health_ins_months = np.where(
        np.isin(np.arange(n) % 5, [0, 1, 2]),  # 60% 직장가입자
        np.random.randint(10, 13, n),
        np.random.randint(6, 13, n)
    )

    # 국민연금 납부 월 수 (최근 24개월)
    pension_months = np.where(
        income_annual > 3000,
        np.random.randint(18, 25, n),
        np.random.randint(8, 24, n)
    )

    return pd.DataFrame({
        "telecom_no_delinquency": telecom_no_delinquency,
        "health_insurance_paid_months_12m": np.clip(health_ins_months, 0, 12),
        "national_pension_paid_months_24m": np.clip(pension_months, 0, 24),
    })


def compute_default_probability(df: pd.DataFrame) -> np.ndarray:
    """
    실제 은행 부도 예측 로직 근사 (logistic 함수 기반)
    - CB 점수 (가장 중요)
    - 연체 이력
    - DSR 비율
    - 소득 수준
    목표 부도율: ~7.2%
    """
    log_odds = -3.5  # 절편 (기준 부도율 약 3%)

    # CB 점수 효과 (가장 강력)
    log_odds += (df["cb_score"] - 700) / 100 * (-1.8)

    # 연체 이력
    log_odds += df["delinquency_count_12m"] * 0.6
    log_odds += df["worst_delinquency_status"] * 0.8

    # 재무 비율
    dsr_excess = np.clip(df["dsr_ratio"] - 40, 0, None)
    log_odds += dsr_excess * 0.03

    # 부채비율
    log_odds += np.clip(df["debt_to_income"] - 2.0, 0, None) * 0.4

    # 소득 효과 (억제 요인)
    log_odds += np.log1p(50000 / np.clip(df["income_annual"] * 10000, 1, None)) * 0.5

    # 대출 조회 수 (위험 신호)
    log_odds += df["inquiry_count_3m"] * 0.3

    # 대안 데이터 (긍정적 효과)
    log_odds -= df["telecom_no_delinquency"] * 0.3
    log_odds -= (df["health_insurance_paid_months_12m"] / 12) * 0.4

    pd_raw = 1 / (1 + np.exp(-log_odds))

    # 스케일 조정 → 목표 부도율 달성
    current_mean = pd_raw.mean()
    scale_factor = BAD_RATE_TARGET / current_mean
    pd_adjusted = np.clip(pd_raw * scale_factor, 0.001, 0.999)

    return pd_adjusted


def generate_dataset(n: int = 50000, product_type: str = "credit") -> pd.DataFrame:
    """
    전체 데이터셋 생성 (v1.1 - 특수 세그먼트, EQ Grade, IRG, SOHO 포함)

    Args:
        n: 레코드 수
        product_type: credit | mortgage | micro | credit_soho
    Returns:
        DataFrame with all features + target (default_12m)
    """
    print(f"[데이터 생성] {n:,}건 합성 데이터 생성 중... (상품: {product_type})")

    # ── 기본 인구통계 ──────────────────────────────────────────────
    age = generate_age(n)
    age_band = pd.cut(age, bins=[0, 29, 39, 49, 59, 100],
                      labels=["20s", "30s", "40s", "50s", "60+"])

    employment = generate_employment(n)

    # ── 특수 세그먼트 및 직종 배정 ──────────────────────────────────
    segment_codes, occupation_types = generate_special_segments(age, employment, n)

    # 특수직역의 소득 분포는 별도 처리
    income_annual = np.zeros(n)
    # 일반 직업군 소득
    for job, params in INCOME_DIST_BY_JOB.items():
        if job in ("doctor", "dentist", "oriental_md", "lawyer", "accountant", "artist", "military"):
            continue
        mask = (occupation_types == job)
        count = mask.sum()
        if count > 0:
            raw = np.random.normal(params["mean"], params["std"], count)
            income_annual[mask] = np.clip(raw, params["min"], None)
    # 특수직역 소득
    for job in ("doctor", "dentist", "oriental_md", "lawyer", "accountant", "artist", "military"):
        params = INCOME_DIST_BY_JOB[job]
        mask = (occupation_types == job)
        count = mask.sum()
        if count > 0:
            raw = np.random.normal(params["mean"], params["std"], count)
            income_annual[mask] = np.clip(raw, params["min"], None)
    # 미배정 직종 기본값
    zero_mask = income_annual == 0
    if zero_mask.sum() > 0:
        income_annual[zero_mask] = np.clip(
            np.random.normal(INCOME_DIST_BY_JOB["employed"]["mean"],
                             INCOME_DIST_BY_JOB["employed"]["std"], zero_mask.sum()),
            INCOME_DIST_BY_JOB["employed"]["min"], None
        )
    income_annual = np.round(income_annual, 0)

    # ── EQ Grade / IRG 배정 ─────────────────────────────────────────
    eq_grades, irg_codes = generate_eq_irg(employment, segment_codes, n)

    # ── 개인사업자 여부 및 applicant_type ──────────────────────────
    applicant_type = np.where(employment == "self_employed", "self_employed", "individual")

    # ── SOHO 전용 필드 ─────────────────────────────────────────────
    soho_df = generate_soho_fields(employment, income_annual, n)

    # ── 거주 형태 ──────────────────────────────────────────────────
    residence_type = np.random.choice(
        ["own", "rent", "family", "public"],
        size=n, p=[0.42, 0.38, 0.16, 0.04]
    )

    # ── 근속 기간 (개월) ───────────────────────────────────────────
    employment_duration = np.where(
        employment == "employed",
        np.random.exponential(60, n).clip(1, 360).astype(int),
        np.where(employment == "self_employed",
                 soho_df["business_duration_months"].values, 0)
    )

    # ── CB 피처 ────────────────────────────────────────────────────
    cb_df = generate_cb_features(n, income_annual)

    # 특수직역(SEG-DR/JD)은 CB 점수 보정 (높은 소득 → 높은 신용도)
    dr_jd_mask = np.isin(segment_codes, ["SEG-DR", "SEG-JD", "SEG-MIL"])
    if dr_jd_mask.sum() > 0:
        boost = np.random.randint(30, 80, dr_jd_mask.sum())
        cb_df.loc[dr_jd_mask, "cb_score"] = np.clip(
            cb_df.loc[dr_jd_mask, "cb_score"] + boost, 300, 1000
        )

    # ── 신청 금액 (상품별) ─────────────────────────────────────────
    if product_type == "credit":
        # 특수직역은 더 높은 한도 신청
        base_amount = np.random.lognormal(np.log(3000), 0.8, n)
        seg_bonus = np.where(np.isin(segment_codes, ["SEG-DR"]), 3.0,
                   np.where(np.isin(segment_codes, ["SEG-JD"]), 2.5,
                   np.where(np.isin(segment_codes, ["SEG-MIL"]), 2.0, 1.0)))
        requested_amount_wan = np.clip(base_amount * seg_bonus, 100, 30000)
        collateral_value = np.zeros(n)
        ltv_ratio = np.zeros(n)
    elif product_type == "mortgage":
        requested_amount_wan = np.clip(
            np.random.lognormal(np.log(30000), 0.6, n), 5000, 100000
        )
        collateral_value_wan = requested_amount_wan / np.random.uniform(0.4, 0.75, n)
        collateral_value = collateral_value_wan
        ltv_ratio = (requested_amount_wan / collateral_value_wan * 100).round(2)
    elif product_type == "credit_soho":
        soho_only = employment == "self_employed"
        requested_amount_wan = np.where(
            soho_only,
            np.clip(np.random.lognormal(np.log(2000), 0.7, n), 300, 20000),
            np.clip(np.random.lognormal(np.log(3000), 0.8, n), 100, 10000)
        )
        collateral_value = np.zeros(n)
        ltv_ratio = np.zeros(n)
    else:  # micro
        requested_amount_wan = np.clip(
            np.random.lognormal(np.log(500), 0.5, n), 50, 3000
        )
        collateral_value = np.zeros(n)
        ltv_ratio = np.zeros(n)

    requested_amount = (requested_amount_wan * 10000).astype(int)  # 원 단위

    # ── 재무 비율 ──────────────────────────────────────────────────
    fin_df = generate_financial_ratios(income_annual, cb_df["total_loan_balance"].values, requested_amount)

    # ── 거래 행동 ──────────────────────────────────────────────────
    tx_df = generate_transaction_behavior(income_annual, cb_df["cb_score"].values)

    # ── 대안 데이터 ────────────────────────────────────────────────
    alt_df = generate_alternative_data(income_annual, n)

    # ── 전체 데이터프레임 조립 ─────────────────────────────────────
    df = pd.DataFrame({
        "applicant_id":            [f"APP{i:07d}" for i in range(1, n + 1)],
        "applicant_type":          applicant_type,
        "age":                     age,
        "age_band":                age_band.astype(str),
        "employment_type":         employment,
        "occupation_type":         occupation_types,
        "employment_duration_months": employment_duration,
        "income_annual_wan":       income_annual,        # 만원 단위
        "income_annual":           (income_annual * 10000).astype(int),  # 원 단위
        "residence_type":          residence_type,
        "segment_code":            segment_codes,
        "eq_grade":                eq_grades,
        "irg_code":                irg_codes,
        "product_type":            product_type,
        "requested_amount":        requested_amount,
        "collateral_value":        collateral_value.astype(int),
        "ltv_ratio":               ltv_ratio,
        # 디지털 채널 (비대면 주력)
        "digital_channel": np.random.choice(
            ["bank_app", "kakao", "naver", "web", "branch"],
            size=n, p=[0.40, 0.25, 0.15, 0.12, 0.08]
        ),
    })
    df = pd.concat([df, cb_df, fin_df, tx_df, alt_df, soho_df], axis=1)

    # ── IRG PD 조정 반영 ───────────────────────────────────────────
    irg_adj_map = {"L": -0.10, "M": 0.0, "H": 0.15, "VH": 0.30}
    df["irg_pd_adjustment"] = df["irg_code"].map(irg_adj_map).fillna(0.0)

    # ── 부도 여부 (12개월 내, Target) ──────────────────────────────
    pd_prob = compute_default_probability(df)
    # IRG 반영: VH 업종은 PD 증가, L 업종은 PD 감소
    pd_prob = np.clip(pd_prob * (1 + df["irg_pd_adjustment"].values), 0.001, 0.999)
    # 특수직역(SEG-DR/JD)은 부도율 낮게
    seg_pd_discount = np.where(np.isin(segment_codes, ["SEG-DR"]), 0.4,
                     np.where(np.isin(segment_codes, ["SEG-JD"]), 0.5,
                     np.where(np.isin(segment_codes, ["SEG-MIL"]), 0.3, 1.0)))
    pd_prob = np.clip(pd_prob * seg_pd_discount, 0.001, 0.999)

    df["default_12m"] = np.random.binomial(1, pd_prob)
    df["default_probability_true"] = pd_prob.round(6)

    # ── 관측 일자 (시계열 검증용) ──────────────────────────────────
    start_date = datetime(2021, 1, 1)
    observation_dates = [
        (start_date + timedelta(days=np.random.randint(0, 1095))).strftime("%Y-%m-%d")
        for _ in range(n)
    ]
    df["observation_date"] = observation_dates
    df["is_oot"] = pd.to_datetime(df["observation_date"]) >= "2023-07-01"

    print(f"  → 총 {n:,}건 생성 완료")
    print(f"  → 부도율: {df['default_12m'].mean():.2%}")
    print(f"  → CB 점수 평균: {df['cb_score'].mean():.0f} (std: {df['cb_score'].std():.0f})")
    print(f"  → DSR > 40% 비율: {(df['dsr_ratio'] > 40).mean():.1%}")
    print(f"  → 특수 세그먼트 비율: {(df['segment_code'] != '').mean():.1%}")
    print(f"  → 개인사업자 비율: {(df['applicant_type'] == 'self_employed').mean():.1%}")
    print(f"  → OOT 비율: {df['is_oot'].mean():.1%}")

    return df


def generate_behavioral_dataset(n: int = 20000) -> pd.DataFrame:
    """
    행동평점 데이터셋 (기존 대출 고객 모니터링)
    관측 기간: 대출 실행 후 3~24개월
    """
    print(f"\n[행동평점 데이터] {n:,}건 생성 중...")

    df = generate_dataset(n, product_type="credit")

    # 추가: 상환 행동 변수
    df["months_since_origination"] = np.random.randint(3, 25, n)
    df["payment_on_time_rate"] = np.clip(
        np.random.beta(8, 2, n), 0, 1
    ).round(4)
    df["outstanding_balance_ratio"] = np.clip(
        np.random.beta(4, 3, n), 0, 1
    ).round(4)
    df["prepayment_amount"] = np.random.exponential(500000, n).astype(int)
    df["missed_payment_count"] = np.random.poisson(0.3, n).clip(0, 12)

    # 행동 기반 부도 재추정 (상환 패턴 반영)
    behavior_adjustment = -df["payment_on_time_rate"] * 1.5 + df["missed_payment_count"] * 0.8
    pd_adjusted = 1 / (1 + np.exp(-(np.log(df["default_probability_true"] / (1 - df["default_probability_true"])) + behavior_adjustment)))
    df["default_12m"] = np.random.binomial(1, pd_adjusted.clip(0.001, 0.999))

    print(f"  → 부도율: {df['default_12m'].mean():.2%}")
    return df


def generate_collection_dataset(n: int = 5000) -> pd.DataFrame:
    """
    추심평점 데이터셋 (연체 발생 후 회수 예측)
    """
    print(f"\n[추심평점 데이터] {n:,}건 생성 중...")

    df = generate_dataset(n, product_type="credit")

    # 추심 전용 변수 (이미 연체 발생)
    df["delinquency_days"] = np.random.exponential(45, n).astype(int).clip(1, 360)
    df["delinquency_amount"] = np.random.exponential(2000000, n).astype(int)
    df["contact_attempt_count"] = np.random.poisson(3, n).clip(0, 20)
    df["last_payment_amount"] = np.where(
        np.random.random(n) > 0.6,
        np.random.exponential(500000, n).astype(int),
        0
    )
    df["has_asset"] = np.random.binomial(1, 0.35, n)  # 담보 자산 보유 여부

    # 회수 가능성 (target: 1=회수 성공, 0=부실 전환)
    recovery_prob = np.clip(
        0.6 - df["delinquency_days"] / 500 + df["has_asset"] * 0.2
        - df["delinquency_amount"] / 20000000 * 0.3,
        0.05, 0.95
    )
    df["recovery_success"] = np.random.binomial(1, recovery_prob)
    df["default_12m"] = 1 - df["recovery_success"]  # 회수 실패 = 부도 처리

    print(f"  → 회수 성공률: {df['recovery_success'].mean():.2%}")
    return df


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("KCS 합성 데이터 생성 v1.1")
    print("개인 + 개인사업자 / 특수 세그먼트 포함")
    print("=" * 60)

    # 1. Application Scorecard 데이터 (신용대출) - 메인 데이터셋
    df_credit = generate_dataset(n=60000, product_type="credit")
    df_credit.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_credit_loan.parquet"), index=False)
    print(f"\n저장: synthetic_credit_loan.parquet ({len(df_credit):,}건)")

    # 2. 개인사업자 신용대출 데이터 (SOHO 전용)
    df_soho = generate_dataset(n=20000, product_type="credit_soho")
    df_soho.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_credit_soho.parquet"), index=False)
    print(f"저장: synthetic_credit_soho.parquet ({len(df_soho):,}건)")

    # 3. 주택담보대출 데이터
    df_mortgage = generate_dataset(n=20000, product_type="mortgage")
    df_mortgage.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_mortgage.parquet"), index=False)
    print(f"저장: synthetic_mortgage.parquet ({len(df_mortgage):,}건)")

    # 4. 소액마이크로론 데이터
    df_micro = generate_dataset(n=10000, product_type="micro")
    df_micro.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_micro_loan.parquet"), index=False)
    print(f"저장: synthetic_micro_loan.parquet ({len(df_micro):,}건)")

    # 5. Behavioral Scorecard 데이터
    df_behavioral = generate_behavioral_dataset(n=20000)
    df_behavioral.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_behavioral.parquet"), index=False)
    print(f"저장: synthetic_behavioral.parquet ({len(df_behavioral):,}건)")

    # 6. Collection Scorecard 데이터
    df_collection = generate_collection_dataset(n=5000)
    df_collection.to_parquet(os.path.join(OUTPUT_DIR, "synthetic_collection.parquet"), index=False)
    print(f"저장: synthetic_collection.parquet ({len(df_collection):,}건)")

    # 데이터 통계 요약 저장 (검증 보고서용)
    total_records = len(df_credit) + len(df_soho) + len(df_mortgage) + len(df_micro) + len(df_behavioral) + len(df_collection)
    summary = {
        "generated_at": datetime.now().isoformat(),
        "version": "v1.1",
        "datasets": {
            "credit_loan":   {"records": len(df_credit),    "bad_rate": round(df_credit["default_12m"].mean(), 4)},
            "credit_soho":   {"records": len(df_soho),      "bad_rate": round(df_soho["default_12m"].mean(), 4)},
            "mortgage":      {"records": len(df_mortgage),  "bad_rate": round(df_mortgage["default_12m"].mean(), 4)},
            "micro_loan":    {"records": len(df_micro),     "bad_rate": round(df_micro["default_12m"].mean(), 4)},
            "behavioral":    {"records": len(df_behavioral),"bad_rate": round(df_behavioral["default_12m"].mean(), 4)},
            "collection":    {"records": len(df_collection),"bad_rate": round(df_collection["default_12m"].mean(), 4)},
        },
        "feature_list": list(df_credit.columns),
        "total_records": total_records,
        "special_segments": {
            seg: int((df_credit["segment_code"].str.startswith(seg.replace("SEG-MOU", "SEG-MOU"))).sum())
            for seg in ["SEG-DR", "SEG-JD", "SEG-ART", "SEG-YTH", "SEG-MIL"]
        },
        "mou_count": int(df_credit["segment_code"].str.startswith("SEG-MOU-").sum()),
    }
    with open(os.path.join(OUTPUT_DIR, "data_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n=== 데이터 생성 완료 ===")
    print(f"총 {total_records:,}건")
    print(f"부도율(신용대출): {summary['datasets']['credit_loan']['bad_rate']:.2%}")
    print(f"특수 세그먼트: { {k: v for k, v in summary['special_segments'].items()} }")
    print(f"MOU 기업 근로자: {summary['mou_count']:,}건")
