"""
Mock Server 픽스처 로더
========================
scenario_customers.json 에서 사전 정의된 고객 데이터를 로드하고
resident_hash / employer_hash 로 빠르게 조회.

사용법:
    from mock_server.routers._fixture_loader import get_fixture_by_resident, get_fixture_by_employer

    fixture = get_fixture_by_resident("kcs_demo_prime_001")
    if fixture:
        return fixture["nice_cb"]   # NICE CB 응답 직접 반환
"""
import json
import os
from functools import lru_cache
from typing import Optional

_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "scenario_customers.json"
)


@lru_cache(maxsize=1)
def _load_all() -> dict:
    """픽스처 파일을 한 번만 로드 후 캐싱."""
    path = os.path.abspath(_FIXTURE_PATH)
    if not os.path.exists(path):
        return {"by_resident": {}, "by_employer": {}}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    by_resident: dict = {}
    by_employer: dict = {}
    for customer in data.get("customers", []):
        rh = customer.get("resident_hash", "")
        eh = customer.get("employer_hash", "")
        bh = customer.get("business_hash", "")
        if rh:
            by_resident[rh] = customer
        if eh:
            by_employer[eh] = customer
        if bh:
            by_employer[bh] = customer   # business_hash도 employer lookup에 포함

    return {"by_resident": by_resident, "by_employer": by_employer}


def get_fixture_by_resident(resident_hash: str) -> Optional[dict]:
    """resident_hash로 픽스처 고객 전체 데이터 반환. 없으면 None."""
    return _load_all()["by_resident"].get(resident_hash)


def get_fixture_by_employer(employer_hash: str) -> Optional[dict]:
    """employer_hash / business_hash로 픽스처 고객 전체 데이터 반환. 없으면 None."""
    return _load_all()["by_employer"].get(employer_hash)


def list_scenarios() -> list[dict]:
    """모든 시나리오 요약 목록 반환 (디버그/문서용)."""
    db = _load_all()
    return [
        {
            "scenario_id": c["scenario_id"],
            "scenario_name": c["scenario_name"],
            "category": c["category"],
            "expected_decision": c["expected_decision"],
            "resident_hash": c["resident_hash"],
        }
        for c in db["by_resident"].values()
    ]
