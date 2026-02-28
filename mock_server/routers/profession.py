"""
전문직 면허 검증 Mock API
============================
의사 면허 (보건복지부), 변호사 (대한변호사협회), 예술인 (예술인복지재단)
특수 세그먼트 자격 검증용
"""
import random
from fastapi import APIRouter, Header
from pydantic import BaseModel

from mock_server.routers._fixture_loader import get_fixture_by_resident

router = APIRouter()


class LicenseRequest(BaseModel):
    resident_hash: str
    license_type: str       # doctor | dentist | oriental_medicine | lawyer | legal_scrivener | cpa | artist
    license_number: str | None = None


class LicenseResponse(BaseModel):
    resident_hash: str
    license_type: str
    is_valid: bool
    segment_code: str | None    # SEG-DR / SEG-JD / SEG-ART 등
    license_date: str | None    # 면허 취득일
    specialty: str | None       # 전문 분야 (의사: 내과/외과 등)
    registration_status: str    # active | suspended | revoked
    data_source: str = "PROFESSION_MOCK"


# 전문직 → 세그먼트 코드 매핑
LICENSE_SEGMENT_MAP = {
    "doctor":            "SEG-DR",
    "dentist":           "SEG-DR",
    "oriental_medicine": "SEG-DR",
    "lawyer":            "SEG-JD",
    "legal_scrivener":   "SEG-JD",
    "cpa":               "SEG-JD",
    "artist":            "SEG-ART",
}

DOCTOR_SPECIALTIES = ["내과", "외과", "정형외과", "신경외과", "산부인과", "소아과", "안과", "이비인후과", "피부과", "정신건강의학과"]
LAWYER_SPECIALTIES = ["민사", "형사", "기업법", "부동산", "이혼/가족", "행정", "지적재산권"]


@router.post("/license", response_model=LicenseResponse)
async def verify_license(
    request: LicenseRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """전문직 면허 검증"""
    fixture = get_fixture_by_resident(request.resident_hash)
    if fixture:
        return LicenseResponse(**fixture["profession"])

    seed = int(request.resident_hash[:8], 16) % 10000
    rng = random.Random(seed)

    segment = LICENSE_SEGMENT_MAP.get(request.license_type)
    # 면허 번호가 있으면 90% 유효, 없으면 70% 유효
    valid_prob = 0.90 if request.license_number else 0.70
    is_valid = rng.random() < valid_prob

    specialty = None
    if is_valid:
        if request.license_type in ("doctor", "dentist", "oriental_medicine"):
            specialty = rng.choice(DOCTOR_SPECIALTIES)
        elif request.license_type in ("lawyer", "legal_scrivener"):
            specialty = rng.choice(LAWYER_SPECIALTIES)
        elif request.license_type == "artist":
            specialty = rng.choice(["시각예술", "공연예술", "문학", "음악", "영화"])

    # 취득년도 (의사: 28세 이상, 변호사: 27세 이상)
    license_year = rng.randint(2000, 2022)
    license_date = f"{license_year}-{rng.randint(1,12):02d}-01"

    return LicenseResponse(
        resident_hash=request.resident_hash,
        license_type=request.license_type,
        is_valid=is_valid,
        segment_code=segment if is_valid else None,
        license_date=license_date if is_valid else None,
        specialty=specialty,
        registration_status="active" if is_valid else "not_found",
    )


@router.get("/artist-fund/{resident_hash}")
async def check_artist_fund(
    resident_hash: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """예술인복지재단 등록 여부 확인"""
    fixture = get_fixture_by_resident(resident_hash)
    if fixture and "art_fund_registered" in fixture.get("alternative_data", {}):
        alt = fixture["alternative_data"]
        return {
            "resident_hash": resident_hash,
            "art_fund_registered": alt.get("art_fund_registered", False),
            "registration_date": alt.get("art_fund_registration_date"),
            "art_field": alt.get("art_fund_field"),
            "data_source": "ART_FUND_FIXTURE",
        }

    seed = int(resident_hash[:8], 16) % 10000 + 3333
    rng = random.Random(seed)
    registered = rng.random() < 0.80  # 80% 등록

    return {
        "resident_hash": resident_hash,
        "art_fund_registered": registered,
        "registration_date": f"{rng.randint(2015, 2023)}-{rng.randint(1,12):02d}-01" if registered else None,
        "art_field": rng.choice(["시각예술", "공연예술", "문학", "음악"]) if registered else None,
        "data_source": "ART_FUND_MOCK",
    }
