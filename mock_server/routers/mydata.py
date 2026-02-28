"""
금융결제원 마이데이터 Mock API
================================
계좌잔액, 카드내역, 보험, 증권 정보 통합 조회
"""
import random
from fastapi import APIRouter, Header
from pydantic import BaseModel

from mock_server.routers._fixture_loader import get_fixture_by_resident

router = APIRouter()


class AssetSummary(BaseModel):
    total_deposit: float        # 예금 잔액 합계
    total_savings: float        # 적금 잔액 합계
    total_investment: float     # 투자자산 (주식/펀드)
    total_insurance_premium: float  # 월 보험료 합계
    monthly_card_spend_3m_avg: float  # 최근 3개월 평균 월 카드 사용액
    regular_transfer_monthly: float   # 월 정기이체 합계 (관리비, 통신비 등)
    data_source: str = "MYDATA_MOCK"


@router.post("/assets", response_model=AssetSummary)
async def get_assets(
    resident_hash: str,
    consent_token: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """마이데이터 자산 요약 조회"""
    fixture = get_fixture_by_resident(resident_hash)
    if fixture:
        return AssetSummary(**fixture["mydata"])

    seed = int(resident_hash[:8], 16) % 10000 + 7777
    rng = random.Random(seed)

    monthly_income_est = max(1_500_000, rng.gauss(4_000_000, 1_500_000))

    return AssetSummary(
        total_deposit=round(rng.uniform(500_000, 50_000_000), -3),
        total_savings=round(rng.uniform(0, 30_000_000), -3),
        total_investment=round(rng.uniform(0, 100_000_000), -3) if rng.random() < 0.4 else 0.0,
        total_insurance_premium=round(rng.uniform(0, 500_000), -3),
        monthly_card_spend_3m_avg=round(rng.uniform(200_000, monthly_income_est * 0.5), -3),
        regular_transfer_monthly=round(rng.uniform(100_000, 800_000), -3),
    )
