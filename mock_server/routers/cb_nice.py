"""
NICE 개인 신용정보 Mock API
============================
실제 NICE신용평가 API를 모사.
요청: 주민번호 해시 → 응답: CB 점수, 연체정보, 대출현황
"""
import hashlib
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

router = APIRouter()


class CbRequest(BaseModel):
    resident_hash: str          # HMAC-SHA256 해시
    consent_token: str          # CB 조회 동의 토큰
    inquiry_purpose: str = "loan_application"


class DelinquencyInfo(BaseModel):
    has_delinquency: bool
    max_days_overdue: int = 0
    delinquency_amount: float = 0.0
    last_delinquency_date: str | None = None


class LoanSummary(BaseModel):
    total_loan_count: int
    total_balance: float
    monthly_payment: float
    credit_card_limit: float
    credit_card_balance: float


class NiceCbResponse(BaseModel):
    inquiry_id: str
    resident_hash: str
    score: int                  # NICE 신용점수 300~1000
    grade: int                  # 1~10등급
    score_date: str
    delinquency: DelinquencyInfo
    loans: LoanSummary
    public_record_count: int    # 공공기록(파산/압류 등)
    inquiry_count_6m: int       # 최근 6개월 조회 수
    data_source: str = "NICE_MOCK"


def _deterministic_score(resident_hash: str) -> int:
    """해시값으로 결정론적 점수 생성 (동일 해시 → 동일 점수)"""
    seed = int(resident_hash[:8], 16) % 10000
    rng = random.Random(seed)
    # 정규분포 기반 점수 (평균 680, 표준편차 120, 범위 300~1000)
    score = int(rng.gauss(680, 120))
    return max(300, min(1000, score))


def _score_to_grade(score: int) -> int:
    """NICE 점수 → 등급 변환"""
    thresholds = [900, 870, 840, 805, 750, 665, 600, 515, 445, 0]
    for i, t in enumerate(thresholds, 1):
        if score >= t:
            return i
    return 10


@router.post("/credit-info", response_model=NiceCbResponse)
async def get_credit_info(
    request: CbRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """NICE 개인 신용정보 조회"""
    if not request.resident_hash or len(request.resident_hash) < 10:
        raise HTTPException(status_code=400, detail="유효하지 않은 주민번호 해시")

    score = _deterministic_score(request.resident_hash)
    grade = _score_to_grade(score)

    # 해시 기반 결정론적 연체 정보
    seed = int(request.resident_hash[8:16], 16) % 10000
    rng = random.Random(seed)

    has_delinquency = rng.random() < 0.07  # 7% 연체율
    delinquency = DelinquencyInfo(
        has_delinquency=has_delinquency,
        max_days_overdue=rng.randint(30, 365) if has_delinquency else 0,
        delinquency_amount=rng.uniform(500_000, 10_000_000) if has_delinquency else 0.0,
        last_delinquency_date=(
            (datetime.now() - timedelta(days=rng.randint(30, 730))).strftime("%Y-%m-%d")
            if has_delinquency else None
        ),
    )

    # 대출 현황
    loan_count = rng.randint(0, 5)
    total_balance = rng.uniform(0, 150_000_000) if loan_count > 0 else 0.0
    loans = LoanSummary(
        total_loan_count=loan_count,
        total_balance=round(total_balance, 0),
        monthly_payment=round(total_balance / 120, 0) if total_balance > 0 else 0.0,
        credit_card_limit=rng.choice([0, 500_000, 1_000_000, 3_000_000, 5_000_000, 10_000_000]),
        credit_card_balance=round(rng.uniform(0, 3_000_000), 0),
    )

    return NiceCbResponse(
        inquiry_id=f"NICE-{request.resident_hash[:8].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        resident_hash=request.resident_hash,
        score=score,
        grade=grade,
        score_date=datetime.now().strftime("%Y-%m-%d"),
        delinquency=delinquency,
        loans=loans,
        public_record_count=1 if has_delinquency and rng.random() < 0.3 else 0,
        inquiry_count_6m=rng.randint(0, 8),
    )


@router.get("/score-only/{resident_hash}")
async def get_score_only(
    resident_hash: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """간편 점수 조회 (Circuit Breaker KCB fallback용 경량 버전)"""
    score = _deterministic_score(resident_hash)
    return {
        "resident_hash": resident_hash,
        "score": score,
        "grade": _score_to_grade(score),
        "data_source": "NICE_MOCK_LITE",
    }
