"""
기업 신용정보 Mock API (EQ Grade 산정용)
==========================================
NICE/KCB 기업 신용정보 → EQ Grade 조회
MOU 협약 기업 목록 포함
"""
import random
from fastapi import APIRouter, Header
from pydantic import BaseModel

from mock_server.routers._fixture_loader import get_fixture_by_employer

router = APIRouter()

# 사전 정의된 MOU 기업 목록 (협약 코드 포함)
MOU_COMPANIES = {
    "samsung_electronics": {"name": "삼성전자", "eq_grade": "EQ-S", "mou_code": "MOU-SEC001", "mou_rate_discount": -0.5},
    "hyundai_motor":       {"name": "현대자동차", "eq_grade": "EQ-S", "mou_code": "MOU-HMC001", "mou_rate_discount": -0.5},
    "kakao":               {"name": "카카오", "eq_grade": "EQ-A", "mou_code": "MOU-KKO001", "mou_rate_discount": -0.3},
    "naver":               {"name": "네이버", "eq_grade": "EQ-A", "mou_code": "MOU-NVR001", "mou_rate_discount": -0.3},
    "public_bank":         {"name": "국책은행", "eq_grade": "EQ-S", "mou_code": "MOU-GOV001", "mou_rate_discount": -0.5},
}

EQ_GRADE_DIST = {
    "EQ-S": 0.03,   # 3% - 공공기관/초대기업
    "EQ-A": 0.10,   # 10% - 대기업/상장사
    "EQ-B": 0.20,   # 20% - 우량 중견기업
    "EQ-C": 0.40,   # 40% - 일반 중소기업
    "EQ-D": 0.20,   # 20% - 취약 중소기업
    "EQ-E": 0.07,   # 7%  - 부실위험
}


class CompanyInfoResponse(BaseModel):
    employer_registration_hash: str
    eq_grade: str
    limit_multiplier: float
    rate_adjustment: float
    mou_code: str | None
    mou_rate_discount: float
    company_size: str           # large/mid/small/micro
    years_in_business: int
    data_source: str = "BIZ_CREDIT_MOCK"


@router.post("/company", response_model=CompanyInfoResponse)
async def get_company_info(
    employer_registration_hash: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """기업 신용정보 조회 → EQ Grade 반환"""
    # 픽스처 우선 조회
    fixture = get_fixture_by_employer(employer_registration_hash)
    if fixture:
        return CompanyInfoResponse(**fixture["biz_credit"])

    # MOU 기업 목록 체크 (해시 앞 8자리 기반)
    hash_prefix = employer_registration_hash[:8].lower()
    for key, company in MOU_COMPANIES.items():
        if hash_prefix[:4] in key[:4]:
            eq = company["eq_grade"]
            mou = company["mou_code"]
            mou_discount = company["mou_rate_discount"]
            break
    else:
        # 일반 기업: 확률적 EQ Grade 배정
        seed = int(employer_registration_hash[:8], 16) % 10000
        rng = random.Random(seed)
        grades = list(EQ_GRADE_DIST.keys())
        probs = list(EQ_GRADE_DIST.values())
        eq = rng.choices(grades, weights=probs, k=1)[0]
        mou = None
        mou_discount = 0.0

    # EQ Grade → 혜택 매핑
    benefit_map = {
        "EQ-S": (2.0, -0.5, "large"),
        "EQ-A": (1.8, -0.3, "large"),
        "EQ-B": (1.5, -0.2, "mid"),
        "EQ-C": (1.2,  0.0, "small"),
        "EQ-D": (1.0,  0.2, "small"),
        "EQ-E": (0.7,  0.5, "micro"),
    }
    mult, rate_adj, size = benefit_map[eq]

    seed2 = int(employer_registration_hash[4:12], 16) % 10000
    rng2 = random.Random(seed2)

    return CompanyInfoResponse(
        employer_registration_hash=employer_registration_hash,
        eq_grade=eq,
        limit_multiplier=mult,
        rate_adjustment=rate_adj,
        mou_code=mou,
        mou_rate_discount=mou_discount,
        company_size=size,
        years_in_business=rng2.randint(1, 50),
    )
