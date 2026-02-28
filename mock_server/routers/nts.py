"""
국세청 소득/사업자 정보 Mock API
=================================
근로소득/사업소득 확인, 사업자 현황 조회
실제 국세청 홈택스 API를 모사
"""
import random
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from mock_server.routers._fixture_loader import get_fixture_by_resident, get_fixture_by_employer

router = APIRouter()


class IncomeRequest(BaseModel):
    resident_hash: str
    tax_year: int = 2024
    consent_token: str


class IncomeResponse(BaseModel):
    resident_hash: str
    tax_year: int
    employment_income: float        # 근로소득 (원)
    business_income: float          # 사업소득 (원)
    other_income: float             # 기타소득 (원)
    total_income: float             # 합계
    income_verified: bool           # 소득 검증 여부
    employer_name: str | None       # 주된 근무처명 (마스킹)
    data_source: str = "NTS_MOCK"


class BusinessRequest(BaseModel):
    business_registration_hash: str
    resident_hash: str
    consent_token: str


class BusinessResponse(BaseModel):
    business_registration_hash: str
    business_name: str              # 상호 (마스킹)
    business_type: str              # 업태
    business_category: str         # 업종
    registration_date: str         # 개업일
    closure_date: str | None        # 폐업일 (None=영업중)
    is_active: bool
    annual_revenue: float           # 연매출액 (원)
    revenue_year: int
    tax_filing_count: int           # 최근 3년 확정신고 횟수
    data_source: str = "NTS_MOCK"


# 직업별 소득 분포
INCOME_BY_OCCUPATION = {
    "doctor":    {"mean": 180_000_000, "std": 60_000_000},
    "dentist":   {"mean": 150_000_000, "std": 50_000_000},
    "oriental":  {"mean": 100_000_000, "std": 40_000_000},
    "lawyer":    {"mean": 130_000_000, "std": 70_000_000},
    "accountant":{"mean": 90_000_000, "std": 40_000_000},
    "employed":  {"mean": 48_000_000, "std": 20_000_000},
    "self_employed": {"mean": 42_000_000, "std": 25_000_000},
    "artist":    {"mean": 22_000_000, "std": 15_000_000},
}

EMPLOYER_NAMES = [
    "삼성전자 주식회사", "현대자동차 주식회사", "LG전자 주식회사", "SK하이닉스 주식회사",
    "포스코홀딩스", "카카오 주식회사", "네이버 주식회사", "기아 주식회사",
    "한국전력공사", "국민은행", "신한은행", "하나은행", "우리은행", "IBK기업은행",
    "서울특별시청", "경기도청", "한국도로공사", "한국수자원공사",
    "중소기업 A사", "중소기업 B사", "스타트업 C사",
]


@router.post("/income", response_model=IncomeResponse)
async def get_income(
    request: IncomeRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """국세청 소득 정보 조회"""
    fixture = get_fixture_by_resident(request.resident_hash)
    if fixture:
        return IncomeResponse(**fixture["nts_income"])

    seed = int(request.resident_hash[:8], 16) % 10000
    rng = random.Random(seed)

    # 직종 결정 (해시 기반)
    occupation_weights = [
        ("employed", 0.58), ("self_employed", 0.20), ("artist", 0.03),
        ("doctor", 0.02), ("lawyer", 0.02), ("dentist", 0.01),
        ("accountant", 0.02), ("oriental", 0.01),
    ]
    occ_roll = rng.random()
    cumulative = 0
    occupation = "employed"
    for occ, weight in occupation_weights:
        cumulative += weight
        if occ_roll < cumulative:
            occupation = occ
            break

    params = INCOME_BY_OCCUPATION.get(occupation, INCOME_BY_OCCUPATION["employed"])
    base_income = max(10_000_000, rng.gauss(params["mean"], params["std"]))

    if occupation in ("employed", "doctor", "dentist", "lawyer", "accountant", "oriental"):
        employment_income = round(base_income, -4)
        business_income = 0.0
    else:
        employment_income = 0.0
        business_income = round(base_income, -4)

    other_income = round(rng.uniform(0, 5_000_000), -4)
    total = employment_income + business_income + other_income

    employer = rng.choice(EMPLOYER_NAMES) if employment_income > 0 else None
    # 마스킹: 앞 2글자만 표시
    if employer:
        employer = employer[:2] + "*" * max(1, len(employer) - 4) + employer[-1:]

    return IncomeResponse(
        resident_hash=request.resident_hash,
        tax_year=request.tax_year,
        employment_income=employment_income,
        business_income=business_income,
        other_income=other_income,
        total_income=total,
        income_verified=True,
        employer_name=employer,
    )


@router.post("/business", response_model=BusinessResponse)
async def get_business(
    request: BusinessRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """국세청 사업자 정보 조회 (개인사업자)"""
    fixture = get_fixture_by_employer(request.business_registration_hash)
    if fixture and fixture.get("nts_business"):
        return BusinessResponse(**fixture["nts_business"])

    seed = int(request.business_registration_hash[:8], 16) % 10000
    rng = random.Random(seed)

    business_types = [
        ("음식점업", "한식일반음식점"),
        ("도소매업", "전자상거래소매업"),
        ("서비스업", "경영컨설팅업"),
        ("제조업", "식료품제조업"),
        ("의료업", "일반의원"),
        ("법률서비스업", "변호사업"),
        ("예술활동업", "미술창작업"),
    ]
    btype, bcategory = rng.choice(business_types)

    start_year = rng.randint(2010, 2022)
    start_date = date(start_year, rng.randint(1, 12), rng.randint(1, 28))

    duration_years = 2024 - start_year
    is_active = rng.random() < 0.90
    revenue = rng.uniform(30_000_000, 500_000_000)

    return BusinessResponse(
        business_registration_hash=request.business_registration_hash,
        business_name=f"**** {btype[:2]}업체",
        business_type=btype,
        business_category=bcategory,
        registration_date=start_date.strftime("%Y-%m-%d"),
        closure_date=None if is_active else (start_date + timedelta(days=rng.randint(365, 3650))).strftime("%Y-%m-%d"),
        is_active=is_active,
        annual_revenue=round(revenue, -4),
        revenue_year=2023,
        tax_filing_count=min(3, duration_years),
    )
