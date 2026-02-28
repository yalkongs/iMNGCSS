"""
KCB 개인 신용정보 Mock API (NICE Circuit Breaker Fallback)
"""
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Header
from pydantic import BaseModel

router = APIRouter()


class KcbCbResponse(BaseModel):
    inquiry_id: str
    resident_hash: str
    kcb_score: int
    kcb_grade: str          # 1~7등급 (KCB 체계)
    overdue_flag: bool
    total_debt: float
    monthly_obligation: float
    data_source: str = "KCB_MOCK"


def _kcb_score(resident_hash: str) -> int:
    """KCB 점수 (NICE와 약간 다른 분포)"""
    seed = int(resident_hash[:8], 16) % 10000 + 1234
    rng = random.Random(seed)
    score = int(rng.gauss(670, 130))
    return max(300, min(1000, score))


def _kcb_grade(score: int) -> str:
    if score >= 942: return "1"
    if score >= 891: return "2"
    if score >= 832: return "3"
    if score >= 768: return "4"
    if score >= 698: return "5"
    if score >= 630: return "6"
    return "7"


@router.post("/credit-info", response_model=KcbCbResponse)
async def get_kcb_credit_info(
    resident_hash: str,
    consent_token: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """KCB 개인 신용정보 조회 (NICE 장애 시 fallback)"""
    score = _kcb_score(resident_hash)
    seed = int(resident_hash[8:16], 16) % 10000 + 5678
    rng = random.Random(seed)

    total_debt = rng.uniform(0, 120_000_000)
    overdue = rng.random() < 0.065

    return KcbCbResponse(
        inquiry_id=f"KCB-{resident_hash[:8].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        resident_hash=resident_hash,
        kcb_score=score,
        kcb_grade=_kcb_grade(score),
        overdue_flag=overdue,
        total_debt=round(total_debt, 0),
        monthly_obligation=round(total_debt / 120, 0),
    )
