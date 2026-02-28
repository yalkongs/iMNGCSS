"""
건강보험공단 소득/가입자 정보 Mock API
=============================================
보험료 납부 이력을 통한 소득 검증 (직장가입자/지역가입자)
"""
import random
from datetime import datetime
from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter()


class NhisIncomeResponse(BaseModel):
    resident_hash: str
    subscriber_type: str        # employee(직장가입자) | regional(지역가입자)
    employer_name: str | None
    monthly_premium: float      # 월 보험료 (원)
    income_level: float         # 보험료 환산 소득 (원/년)
    subscription_months: int    # 가입 유지 기간 (월)
    income_verified: bool
    data_source: str = "NHIS_MOCK"


@router.post("/income", response_model=NhisIncomeResponse)
async def get_nhis_income(
    resident_hash: str,
    consent_token: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """건강보험공단 소득 검증"""
    seed = int(resident_hash[:8], 16) % 10000 + 9999
    rng = random.Random(seed)

    sub_type = "employee" if rng.random() < 0.70 else "regional"
    monthly_income = max(1_800_000, rng.gauss(4_000_000, 1_500_000))
    premium_rate = 0.0709 if sub_type == "employee" else 0.0709
    monthly_premium = round(monthly_income * premium_rate / 2, 0)

    employer = None
    if sub_type == "employee":
        employers = ["삼성전자", "현대차", "LG전자", "카카오", "공공기관", "중소기업"]
        raw = rng.choice(employers)
        employer = raw[:1] + "*" * (len(raw) - 1)

    return NhisIncomeResponse(
        resident_hash=resident_hash,
        subscriber_type=sub_type,
        employer_name=employer,
        monthly_premium=monthly_premium,
        income_level=round(monthly_income * 12, -4),
        subscription_months=rng.randint(12, 240),
        income_verified=True,
    )
