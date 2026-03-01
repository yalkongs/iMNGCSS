"""
POC (Proof of Concept) 전용 API 라우터
======================================
i뱅크 차세대 신용평가 POC 데모용 엔드포인트.
DB 없을 때도 random.seed(42) 결정론적 Mock 데이터 반환.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import random
from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user

router = APIRouter()

_rng = random.Random(42)  # noqa: S311


def _r(lo: float, hi: float, n: int = 2) -> float:
    return round(_rng.uniform(lo, hi), n)


def _ri(lo: int, hi: int) -> int:
    return _rng.randint(lo, hi)


# ─── 현실적 한국인 이름 ─────────────────────────────────────────────────────
_LAST = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
         "한", "오", "서", "신", "권", "황", "안", "송", "류", "전"]
_FIRST = ["민준", "서연", "지호", "수아", "예린", "도현", "채원", "준혁", "하은", "태양",
          "지민", "유진", "현우", "미래", "강민", "나연", "성훈", "아름", "재원", "소희",
          "승현", "지수", "민서", "건우", "유나", "태민", "보경", "진우", "수빈", "민혁"]


def _name(rng: random.Random) -> str:
    return rng.choice(_LAST) + rng.choice(_FIRST)


# ─── 상품별 현실적 대출금액 ─────────────────────────────────────────────────
def _amount(rng: random.Random, product: str) -> int:
    """상품 유형에 맞는 현실적 대출 금액(원) 반환"""
    if product == "신용대출":
        return rng.randint(300, 5_000) * 10_000        # 300만 ~ 5,000만
    elif product == "주담대":
        return rng.randint(5_000, 80_000) * 10_000     # 5,000만 ~ 8억
    else:  # 소액론
        return rng.randint(50, 300) * 10_000            # 50만 ~ 300만


_PRODUCTS = ["신용대출", "주담대", "소액론"]
_OCCUPATIONS = ["직장인(대기업)", "직장인(중소기업)", "공무원", "교사", "의사", "약사",
                "변호사", "회계사", "군인", "예술인", "자영업(요식업)", "자영업(도소매)",
                "프리랜서(IT)", "프리랜서(디자인)"]
_AREAS = ["서울 강남", "서울 마포", "서울 노원", "경기 수원", "경기 성남", "인천 연수",
          "대구 수성", "대구 달서", "부산 해운대", "부산 동래", "광주 서구", "대전 유성"]

# ─── 개인 EWS 경보 신호 유형 (개인 고객 대상) ─────────────────────────────────
_EWS_SIGNAL_TYPES = [
    ("연체 D+1 발생", "WARNING", "1일 이상 원리금 미납"),
    ("신용점수 급락 (-45점)", "WARNING", "CB 점수 한 달 내 45점 하락"),
    ("타기관 대출 3건 신규", "CAUTION", "30일 내 타 금융사 대출 3건 이상 실행"),
    ("카드 한도 소진율 92%", "CAUTION", "주요 카드사 이용한도 90% 이상 소진"),
    ("주거래계좌 입금 62% 감소", "WARNING", "전월 대비 입금액 50% 이상 감소"),
    ("신용카드 현금서비스 이용", "CAUTION", "현금서비스 2회 이상 이용"),
    ("공공요금 자동이체 미납", "INFO", "공공요금 자동이체 실패 2회"),
    ("대출 원리금 상환 지연 예상", "INFO", "DSR 39.5% → 소득 감소 감지"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  대시보드
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard/branch")
async def branch_dashboard(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    today_apps = _ri(30, 80)
    approved = _ri(18, 55)
    pending = _ri(3, 12)
    rejected = max(0, today_apps - approved - pending)

    recent: list[dict[str, Any]] = []
    for i in range(10):
        prod = _rng.choice(_PRODUCTS)
        score = _ri(450, 850)
        status = "승인" if score >= 530 else ("심사중" if score >= 450 else "거절")
        recent.append({
            "id": f"APP-2025{2000 + i}",
            "name": _name(_rng),
            "product": prod,
            "amount": _amount(_rng, prod),
            "score": score,
            "grade": _grade(score),
            "status": status,
            "applied_at": (datetime.now() - timedelta(hours=_ri(0, 8))).strftime("%H:%M"),
        })

    # EWS 알림 (영업점용: 담당 고객 위험 신호)
    ews_alerts = [
        {"id": i + 1, "name": _name(_rng), "signal": sig, "severity": sev,
         "detail": detail, "time": f"{_ri(1, 8)}시간 전"}
        for i, (sig, sev, detail) in enumerate([
            ("연체 3일 발생", "WARNING", "신용대출 1,200만원"),
            ("DSR 한도 근접 (38.9%)", "CAUTION", "주담대 3.2억"),
            ("CB 점수 42점 하락", "INFO", "신용대출 800만원"),
        ])
    ]

    # 최근 7일 신청 추이 (sparkline용)
    weekly_trend = [_ri(20, 70) for _ in range(7)]

    return {
        "kpi": {
            "today_applications": today_apps,
            "approved": approved,
            "pending": pending,
            "rejected": rejected,
            "approval_rate": round(approved / today_apps * 100, 1),
            "avg_processing_hours": _r(1.8, 6.4),
        },
        "weekly_trend": weekly_trend,
        "recent_applications": recent,
        "ews_alerts": ews_alerts,
    }


@router.get("/dashboard/marketing")
async def marketing_dashboard(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    channels = ["모바일앱", "인터넷뱅킹", "카카오뱅크연계", "네이버파이낸셜", "제휴사"]
    channel_data: list[dict[str, Any]] = [
        {
            "channel": ch,
            "applications": _ri(200, 1_200),
            "conversion_rate": _r(12, 45),
            "avg_score": _ri(580, 720),
            "approval_rate": _r(55, 85),
        }
        for ch in channels
    ]

    # 월별 채널별 신청 추이 (StackedArea용)
    months = [(datetime.now() - timedelta(days=30 * i)).strftime("%m월")
              for i in range(5, -1, -1)]
    stacked = [
        {"month": m, **{ch: _ri(100, 600) for ch in channels}}
        for m in months
    ]

    segments = [
        {"segment": seg, "count": _ri(50, 800), "approval_rate": _r(55, 90),
         "avg_rate": _r(3.5, 8.9), "avg_score": _ri(560, 760)}
        for seg in ["SEG-DR", "SEG-JD", "SEG-ART", "SEG-YTH", "SEG-MIL", "일반"]
    ]

    kpi_trend = [_ri(15, 38) for _ in range(7)]

    return {
        "channel_stats": channel_data,
        "stacked_trend": stacked,
        "channel_keys": channels,
        "segment_distribution": segments,
        "kpi": {
            "total_applications": sum(c["applications"] for c in channel_data),
            "avg_conversion": round(sum(c["conversion_rate"] for c in channel_data) / len(channel_data), 1),
            "best_channel": max(channel_data, key=lambda x: x["conversion_rate"])["channel"],
            "prescore_today": _ri(120, 350),
        },
        "conversion_trend": kpi_trend,
    }


@router.get("/dashboard/risk")
async def risk_dashboard(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    psi_score = _r(0.02, 0.22)
    psi_status = "green" if psi_score < 0.1 else ("yellow" if psi_score < 0.2 else "red")

    # EWS 워치리스트 (개인 고객)
    watchlist = []
    for _ in range(5):
        score = _ri(20, 54)
        grade = "CRITICAL" if score < 35 else "WARNING"
        watchlist.append({"name": _name(_rng), "score": score, "grade": grade,
                          "trend": _rng.choice(["악화", "악화", "유지"]),
                          "signal": _rng.choice(["연체 D+1", "CB 급락", "부채 급증", "카드한도 소진"])})

    psi_trend = [_r(0.02, 0.25) for _ in range(6)]

    return {
        "psi_summary": {
            "score_psi": psi_score,
            "feature_psi_avg": _r(0.01, 0.15),
            "target_psi": _r(0.005, 0.08),
            "status": psi_status,
        },
        "psi_trend": psi_trend,
        "portfolio": {
            "total_exposure": _ri(500_000, 2_000_000) * 10_000,
            "avg_pd": _r(0.02, 0.08),
            "avg_lgd": _r(0.30, 0.55),
            "expected_loss": _r(0.01, 0.05),
            "rwa": _ri(100_000, 800_000) * 10_000,
        },
        "calibration": {
            "ece": _r(0.005, 0.03),
            "brier_score": _r(0.04, 0.12),
            "gini": _r(0.55, 0.78),
            "ks_stat": _r(0.38, 0.62),
        },
        "ews_watchlist": watchlist,
        "grade_distribution": [
            {"grade": g, "count": _ri(50, 600)}
            for g in ["1등급", "2등급", "3등급", "4등급", "5등급", "6등급", "7등급", "8등급"]
        ],
    }


@router.get("/dashboard/product")
async def product_dashboard(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    products = [
        ("신용대출", 3.5, 14.8, "일반 직장인/개인사업자"),
        ("주담대", 3.2, 6.9, "주택 보유자 대상"),
        ("소액론", 4.5, 18.9, "소액 급전 수요"),
    ]
    stats = [
        {
            "product": name,
            "raroc": _r(8.5, 18.2),
            "el_ratio": _r(0.8, 3.5),
            "rwa": _ri(50_000, 400_000) * 10_000,
            "nim": _r(1.8, 4.2),
            "avg_rate": _r(rate_lo, rate_hi),
            "description": desc,
            "count": _ri(3_000, 15_000),
        }
        for name, rate_lo, rate_hi, desc in products
    ]

    raroc_trend = [_r(10, 16) for _ in range(6)]

    return {
        "product_stats": stats,
        "rate_decomposition": {
            "base_rate": 3.50,
            "funding_cost": _r(0.3, 0.8),
            "credit_spread": _r(1.2, 4.8),
            "capital_charge": _r(0.5, 1.5),
            "operating_cost": _r(0.3, 0.7),
            "profit_margin": _r(0.3, 1.2),
        },
        "raroc_trend": raroc_trend,
    }


@router.get("/dashboard/policy")
async def policy_dashboard(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    # 프론트엔드 Policy/Dashboard.tsx 인터페이스에 맞는 구조
    dsr_rate = _r(97.5, 99.8)
    ltv_rate = _r(98.1, 99.9)
    rate_rate = _r(99.5, 100.0)
    overall = round((dsr_rate + ltv_rate + rate_rate) / 3, 1)
    return {
        "param_stats": {
            "total": 27,
            "active": 24,
            "modified_this_month": _ri(2, 6),
            "pending_review": _ri(0, 3),
        },
        "compliance": {
            "dsr_compliance_rate": round(dsr_rate, 1),
            "ltv_compliance_rate": round(ltv_rate, 1),
            "rate_compliance_rate": round(rate_rate, 1),
            "overall": round(overall, 1),
        },
        "recent_changes": [
            {"param_key": "dsr.max_ratio", "old_value": "0.38", "new_value": "0.40",
             "changed_by": "admin", "changed_at": "2025-01-15 14:23", "category": "DSR"},
            {"param_key": "rate.max_interest", "old_value": "0.18", "new_value": "0.20",
             "changed_by": "risk_manager", "changed_at": "2025-02-01 09:15", "category": "금리"},
            {"param_key": "ltv.adjusted", "old_value": "0.65", "new_value": "0.60",
             "changed_by": "compliance", "changed_at": "2025-02-14 16:30", "category": "LTV"},
            {"param_key": "stress_dsr.phase3.seoul", "old_value": "0.0", "new_value": "0.015",
             "changed_by": "admin", "changed_at": "2025-02-20 10:00", "category": "스트레스DSR"},
        ],
        "approval_pipeline": [
            {"stage": "초안 작성", "count": _ri(1, 3)},
            {"stage": "리스크 검토", "count": _ri(1, 4)},
            {"stage": "준법감시 승인", "count": _ri(0, 2)},
            {"stage": "위원회 상정", "count": _ri(0, 1)},
            {"stage": "최종 적용", "count": _ri(2, 5)},
        ],
        "policy_kpi": [
            {"name": "DSR 준수율", "value": round(dsr_rate, 1), "target": 99.0, "unit": "%", "ok": dsr_rate >= 99.0},
            {"name": "LTV 준수율", "value": round(ltv_rate, 1), "target": 99.0, "unit": "%", "ok": ltv_rate >= 99.0},
            {"name": "최고금리 준수율", "value": round(rate_rate, 1), "target": 100.0, "unit": "%", "ok": rate_rate >= 100.0},
            {"name": "파라미터 변경 주기", "value": _ri(12, 18), "target": 30, "unit": "일", "ok": True},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  신청 관련
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications")
async def list_applications(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    product: str | None = None,
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    rng = random.Random(42)  # noqa: S311
    all_apps = []
    for i in range(100):
        prod = rng.choice(_PRODUCTS)
        score = rng.randint(420, 880)
        st = "승인" if score >= 530 else ("심사중" if score >= 450 else "거절")
        amt = _amount(rng, prod)
        dsr = rng.uniform(15.0, 39.5)
        all_apps.append({
            "id": f"APP-2025{2000 + i:04d}",
            "customer_name": _name(rng),
            "occupation": rng.choice(_OCCUPATIONS),
            "product": prod,
            "amount": amt,
            "score": score,
            "grade": _grade(score),
            "rate": round(rng.uniform(3.5, 14.9), 2),
            "dsr": round(dsr, 1),
            "status": st,
            "applied_at": (date.today() - timedelta(days=rng.randint(0, 30))).isoformat(),
            "segment": rng.choice(["일반", "SEG-YTH", "SEG-DR", "SEG-JD", ""]),
            "area": rng.choice(_AREAS),
        })
    if status:
        all_apps = [a for a in all_apps if a["status"] == status]
    if product:
        all_apps = [a for a in all_apps if a["product"] == product]
    total = len(all_apps)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size,
            "items": all_apps[start:start + page_size]}


@router.get("/applications/{app_id}")
async def get_application(app_id: str, _: Any = Depends(get_current_user)) -> dict[str, Any]:
    seed = int(app_id.replace("APP-", "").replace("-", "")) % 10000
    rng = random.Random(seed)  # noqa: S311
    prod = rng.choice(_PRODUCTS)
    score = rng.randint(450, 880)
    amt = _amount(rng, prod)
    cust = _name(rng)
    occ = rng.choice(_OCCUPATIONS)
    income = rng.randint(2_500, 12_000) * 10_000  # 2500만 ~ 1.2억
    existing_debt = rng.randint(0, int(income * 2))
    dsr = round(min(39.9, (amt * 0.05 + existing_debt * 0.04) / income * 100), 1)

    return {
        "id": app_id,
        "customer_name": cust,
        "occupation": occ,
        "age": rng.randint(25, 58),
        "income": income,
        "area": rng.choice(_AREAS),
        "product": prod,
        "amount": amt,
        "score": score,
        "grade": _grade(score),
        "rate": round(rng.uniform(3.5, 12.0), 2),
        "dsr": dsr,
        "ltv": round(rng.uniform(45.0, 68.0), 1) if prod == "주담대" else None,
        "status": "승인" if score >= 530 else "심사중",
        "eq_grade": rng.choice(["EQ-A", "EQ-B", "EQ-C", "EQ-D"]),
        "segment": _detect_segment({"occupation": occ, "age": rng.randint(25, 58)}),
        "shap_top5": [
            {"feature": f, "contribution": round(rng.uniform(-80, 80), 1)}
            for f in ["연소득", "기존부채비율", "신용점수(CB)", "연체이력(24M)", "근속연수"]
        ],
        "applied_at": (date.today() - timedelta(days=rng.randint(0, 7))).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  사전심사 (Shadow Mode)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/prescore")
async def prescore(data: dict[str, Any], _: Any = Depends(get_current_user)) -> dict[str, Any]:
    seed = hash(str(sorted(data.items()))) % 10_000
    rng = random.Random(seed)  # noqa: S311
    prod = str(data.get("product", "신용대출"))
    score = rng.randint(450, 880)
    amt_req = int(data.get("loan_amount", 1_000)) * 10_000
    limit = min(amt_req, _amount(rng, prod))
    dsr = round(rng.uniform(18.0, 39.9), 1)
    rate = round(rng.uniform(3.5, 14.9), 2)
    seg = _detect_segment(data)
    if seg == "SEG-DR" or seg == "SEG-YTH" or seg == "SEG-MIL":
        rate -= 0.5

    return {
        "shadow_mode": True,
        "score": score,
        "grade": _grade(score),
        "rate": round(rate, 2),
        "credit_limit": limit,
        "dsr": dsr,
        "decision": "승인" if score >= 530 else ("조건부심사" if score >= 450 else "거절"),
        "segment": seg,
        "rejection_reasons": [] if score >= 530 else (
            ["신용점수 기준 미달 (530점)"] if score < 450 else ["수동심사 구간 해당"]
        ),
        "note": "사전심사 결과는 DB에 저장되지 않습니다.",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  이의제기 관리
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/appeals")
async def list_appeals(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    statuses = ["접수", "검토중", "완료-인용", "완료-기각"]
    appeals = []
    for i in range(20):
        st = _rng.choice(statuses)
        prod = _rng.choice(_PRODUCTS)
        amt = _amount(_rng, prod)
        orig_score = _ri(420, 528)
        appeals.append({
            "id": f"APL-2025{100 + i:04d}",
            "app_id": f"APP-2025{2000 + i:04d}",
            "customer_name": _name(_rng),
            "product": prod,
            "amount": amt,
            "original_score": orig_score,
            "original_grade": _grade(orig_score),
            "reason": _rng.choice([
                "소득 증빙 추가 제출", "직장 재직 증명 오류 수정",
                "타 금융사 부채 상환 완료", "배우자 소득 합산 요청", "담보 추가 제공",
            ]),
            "status": st,
            "revised_score": orig_score + _ri(10, 80) if "인용" in st else None,
            "filed_at": (date.today() - timedelta(days=_ri(0, 30))).isoformat(),
            "resolved_at": (date.today() - timedelta(days=_ri(0, 10))).isoformat() if "완료" in st else None,
            "handler": _name(_rng),
        })
    summary = {
        "total": len(appeals),
        "pending": sum(1 for a in appeals if a["status"] in ["접수", "검토중"]),
        "upheld": sum(1 for a in appeals if a["status"] == "완료-인용"),
        "rejected": sum(1 for a in appeals if a["status"] == "완료-기각"),
        "uphold_rate": round(
            sum(1 for a in appeals if a["status"] == "완료-인용") /
            max(1, sum(1 for a in appeals if "완료" in str(a["status"]))) * 100, 1
        ),
    }
    return {"summary": summary, "appeals": appeals}


# ─────────────────────────────────────────────────────────────────────────────
#  EWS 조기경보 시스템
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ews/summary")
async def ews_summary(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """개인 고객 EWS 조기경보 통합 대시보드"""
    _rng.seed(42)
    monitored: list[dict[str, Any]] = []
    for _ in range(20):
        score = _ri(20, 90)
        grade = ("CRITICAL" if score < 35 else
                 "WARNING" if score < 55 else
                 "WATCH" if score < 75 else "NORMAL")
        trend = _rng.choice(["악화", "악화", "유지", "유지", "개선"])
        prod = _rng.choice(_PRODUCTS)
        signals: list[str] = []
        if score < 35:
            signals.append("연체위험")
        if _ri(-60, 5) < -20:
            signals.append("CB점수급락")
        if _rng.random() < 0.3:
            signals.append("부채급증")
        monitored.append({
            "name": _name(_rng),
            "product": prod,
            "loan_amount": _amount(_rng, prod),
            "score": score,
            "grade": grade,
            "trend": trend,
            "txn_score": _ri(30, 95),
            "cb_score_change": _ri(-60, 5),
            "debt_score": _ri(35, 95),
            "inquiry_score": _ri(40, 95),
            "payment_score": _ri(30, 95),
            "income_score": _ri(35, 95),
            "composite": score,
            "signals": signals,
        })

    months = [(datetime.now() - timedelta(days=30 * i)).strftime("%Y-%m")
              for i in range(11, -1, -1)]
    monthly_alerts = [
        {"month": m, "critical": _ri(0, 3), "warning": _ri(1, 5), "watch": _ri(2, 6)}
        for m in months
    ]

    signal_summary = [
        {"signal_type": st, "count": _ri(3, 20), "this_month": _ri(0, 5)}
        for st in ["연체 D+1 발생", "CB점수 급락", "부채 급증", "신용조회 급증", "소득 감소 감지"]
    ]

    return {
        "overview": {
            "total_monitored": len(monitored),
            "critical": sum(1 for c in monitored if c["grade"] == "CRITICAL"),
            "warning": sum(1 for c in monitored if c["grade"] == "WARNING"),
            "watch": sum(1 for c in monitored if c["grade"] == "WATCH"),
            "normal": sum(1 for c in monitored if c["grade"] == "NORMAL"),
        },
        "monitored": monitored,
        "signal_summary": signal_summary,
        "monthly_alerts": monthly_alerts,
    }


@router.get("/ews/transaction")
async def ews_transaction(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """개인 고객 거래 행태 이상 탐지"""
    _rng.seed(42)
    months = [(datetime.now() - timedelta(days=30 * i)).strftime("%m월")
              for i in range(5, -1, -1)]
    anomalies = []
    txn_types = ["입금액 급감", "현금 인출 집중", "카드 한도 소진율 90% 초과",
                 "자동이체 미납", "타행 이체 패턴 이상", "새벽 거래 급증"]
    for _ in range(8):
        anomalies.append({
            "name": _name(_rng),
            "product": _rng.choice(_PRODUCTS),
            "type": _rng.choice(txn_types),
            "severity": _rng.choice(["HIGH", "MEDIUM", "LOW"]),
            "detected_at": (datetime.now() - timedelta(days=_ri(0, 14))).strftime("%Y-%m-%d"),
            "score_change": _ri(-35, -5),
            "detail": _rng.choice([
                "전월 대비 주거래계좌 입금 58% 감소",
                "신용카드 이용한도 92% 소진 (3개월 연속)",
                "현금서비스 월 3회 이용 탐지",
                "자동이체 3건 미납 → 불량 마크 우려",
                "야간 23시~새벽 5시 거래 집중",
            ]),
        })
    utilization = [
        {"month": m, "avg_card_util": _r(45, 78), "avg_loan_util": _r(65, 92),
         "high_util_count": _ri(2, 12)}
        for m in months
    ]
    return {"anomalies": anomalies, "utilization_trend": utilization}


@router.get("/ews/cb-signal")
async def ews_cb_signal(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """CB 신용점수 변동 시그널 (개인 고객 전용)"""
    _rng.seed(42)
    months = [(datetime.now() - timedelta(days=30 * i)).strftime("%m월")
              for i in range(5, -1, -1)]
    drops = []
    for _ in range(10):
        before = _ri(550, 800)
        change = _ri(-80, -15)
        drops.append({
            "name": _name(_rng),
            "cb_score_before": before,
            "cb_score_after": before + change,
            "change": change,
            "reason": _rng.choice([
                "타 금융사 연체 발생", "신규 대출 과다 실행",
                "카드 연체 등록", "신용조회 5회 이상", "보증 채무 발생",
            ]),
            "detected_at": (date.today() - timedelta(days=_ri(0, 30))).isoformat(),
            "severity": "HIGH" if change < -50 else "MEDIUM",
        })

    monthly_avg_cb = [
        {"month": m, "avg_kcb": _ri(650, 720), "avg_nice": _ri(640, 710),
         "below_530": _ri(5, 25)}
        for m in months
    ]
    return {"cb_drops": drops, "monthly_cb_trend": monthly_avg_cb}


@router.get("/ews/debt-signal")
async def ews_debt_signal(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """부채 급증 / 다중채무자 탐지 (개인 고객 전용)"""
    _rng.seed(42)
    multi_debtors: list[dict[str, Any]] = []
    for _ in range(10):
        income = _ri(2_500, 8_000) * 10_000
        total_debt = _ri(int(income * 1.5), int(income * 5))
        dsr = round(total_debt * 0.05 / income * 100, 1)
        multi_debtors.append({
            "name": _name(_rng),
            "income": income,
            "total_debt": total_debt,
            "loan_count": _ri(3, 8),
            "financial_count": _ri(2, 5),
            "dsr": dsr,
            "dsr_status": "위험" if dsr > 40 else ("경고" if dsr > 35 else "주의"),
            "new_debt_30d": _ri(1, 3),
        })
    return {
        "multi_debtors": multi_debtors,
        "high_dsr_count": sum(1 for d in multi_debtors if d["dsr"] > 40),
    }


@router.get("/ews/delinquency-signal")
async def ews_delinquency(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """연체 초기 경보 및 DPD 현황 (개인 고객 전용)"""
    _rng.seed(42)
    dpd_buckets = [
        {"bucket": "D+1~D+3 (경미)", "count": _ri(15, 45), "amount": _ri(500, 3_000) * 10_000, "color": "#faad14"},
        {"bucket": "D+4~D+10 (주의)", "count": _ri(8, 25), "amount": _ri(300, 2_000) * 10_000, "color": "#fa8c16"},
        {"bucket": "D+11~D+30 (위험)", "count": _ri(3, 12), "amount": _ri(200, 1_500) * 10_000, "color": "#f5222d"},
        {"bucket": "D+31 이상 (NPL)", "count": _ri(1, 5), "amount": _ri(100, 800) * 10_000, "color": "#a8071a"},
    ]
    early_list = []
    for _ in range(8):
        prod = _rng.choice(_PRODUCTS)
        dpd = _ri(1, 25)
        early_list.append({
            "name": _name(_rng),
            "product": prod,
            "amount": _amount(_rng, prod),
            "dpd": dpd,
            "overdue_amount": _ri(30, 500) * 10_000,
            "contact_status": _rng.choice(["미연락", "연락완료", "입금약속", "연락불가"]),
            "last_contact": (date.today() - timedelta(days=_ri(0, 5))).isoformat(),
        })
    monthly_dpd = [
        {"month": f"2025-{m:02d}", "new_delinquency": _ri(10, 50), "resolved": _ri(8, 45)}
        for m in range(1, 7)
    ]
    return {"dpd_buckets": dpd_buckets, "early_warning_list": early_list,
            "monthly_trend": monthly_dpd}


@router.get("/ews/public")
async def ews_public(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """공적정보 이상 탐지 (개인 고객 기준: 소송/체납/압류)"""
    _rng.seed(42)
    records = []
    rec_types = ["소득세 체납", "지방세 체납", "신용카드 대금 소송", "임금 압류",
                 "부동산 경매 신청", "사기 관련 소송"]
    for _ in range(8):
        records.append({
            "customer_name": _name(_rng),
            "type": _rng.choice(rec_types),
            "amount": _ri(100, 3_000) * 10_000,
            "filed_at": (date.today() - timedelta(days=_ri(0, 180))).isoformat(),
            "severity": _rng.choice(["HIGH", "MEDIUM", "LOW"]),
            "status": _rng.choice(["진행중", "완료(화해)", "완료(패소)"]),
        })
    return {"public_records": records, "total": len(records)}


# ─────────────────────────────────────────────────────────────────────────────
#  포트폴리오 집중도
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/portfolio-concentration")
async def portfolio_concentration(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    """개인 고객 포트폴리오 집중도 분석 (상품/세그먼트/지역/직업군별)"""
    _rng.seed(42)
    total_exposure = 1_200_000_000_000  # 1.2조 기준 (개인여신)

    # 상품별 구성
    products = [
        ("신용대출", 0.48), ("주담대", 0.42), ("소액론", 0.10),
    ]
    prod_hhi = round(sum(s ** 2 for _, s in products) * 10_000, 0)

    product_data = [
        {
            "name": p,
            "share": round(pct * 100, 1),
            "count": _ri(2_000, 20_000),
            "avg_score": _ri(560, 720),
            "avg_rate": _r(3.5, 15.0),
            "total_amount": int(pct * total_exposure),
        }
        for p, pct in products
    ]

    # 세그먼트별 구성
    segments = [
        ("일반", 0.58), ("SEG-YTH", 0.18), ("SEG-DR", 0.08),
        ("SEG-JD", 0.06), ("SEG-MIL", 0.05), ("SEG-ART", 0.05),
    ]
    seg_data = [
        {
            "name": s,
            "share": round(pct * 100, 1),
            "count": _ri(200, 15_000),
            "avg_score": _ri(560, 780),
            "approval_rate": _r(55, 90),
        }
        for s, pct in segments
    ]

    # 지역별 구성
    region_shares = [0.28, 0.22, 0.08, 0.10, 0.07, 0.06, 0.05, 0.14]
    region_data = [
        {
            "name": r,
            "share": round(region_shares[i] * 100, 1),
            "count": _ri(500, 8_000),
            "avg_amount": _ri(1_500, 5_000) * 10_000,
        }
        for i, r in enumerate(["서울", "경기", "인천", "부산", "대구", "대전", "광주", "기타"])
    ]

    # 소득 구간별 구성
    income_bands = [
        ("3,000만원 미만", 0.15), ("3,000~5,000만원", 0.32),
        ("5,000~8,000만원", 0.35), ("8,000만원 이상", 0.18),
    ]
    income_data = [
        {
            "name": b,
            "share": round(pct * 100, 1),
            "count": _ri(1_000, 10_000),
            "avg_dsr": _r(18, 38),
            "default_rate": _r(0.5, 4.5),
        }
        for b, pct in income_bands
    ]

    top3_share = round(sum(s for _, s in products[:3]) * 100, 1)
    alert_level = "HIGH" if prod_hhi > 3_000 else ("MEDIUM" if prod_hhi > 1_500 else "LOW")
    alert_msg = {
        "HIGH": "상품 집중도 위험 — 신용대출·주담대 쏠림 심화. 분산 전략 검토 필요.",
        "MEDIUM": "집중도 보통 — 모니터링 유지",
        "LOW": "집중도 양호 — 포트폴리오 균형적",
    }[alert_level]

    return {
        "summary": {
            "hhi": int(prod_hhi),
            "top3_share": top3_share,
            "alert_level": alert_level,
            "alert_message": alert_msg,
        },
        "by_product": product_data,
        "by_segment": seg_data,
        "by_region": region_data,
        "by_income": income_data,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  점수 분포
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/score-distribution")
async def score_distribution(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    # 50점 구간 히스토그램 (프론트엔드 ScoreDistribution.tsx 기대 구조)
    histogram: list[dict[str, Any]] = []
    cum = 0
    total_approx = 10_000
    for lo in range(300, 900, 50):
        hi = lo + 50
        if hi <= 450:
            count = _ri(50, 250)
            zone = "자동거절"
        elif hi <= 530:
            count = _ri(400, 800)
            zone = "수동심사"
        else:
            count = _ri(500, 1_800)
            zone = "자동승인"
        cum += count
        histogram.append({
            "bin": f"{lo}~{hi-1}",
            "count": count,
            "zone": zone,
            "cum_pct": round(cum / total_approx * 100, 1),
        })

    # 등급별 분포
    grade_ranges = [
        ("AAA", 800, 900, 0.05, 0.003),
        ("AA",  720, 799, 0.12, 0.008),
        ("A",   650, 719, 0.22, 0.020),
        ("B",   580, 649, 0.28, 0.055),
        ("C",   530, 579, 0.18, 0.120),
        ("D",   450, 529, 0.10, 0.250),
    ]
    by_grade = [
        {
            "grade": g, "min": lo, "max": hi,
            "count": int(pct * total_approx),
            "pct": round(pct * 100, 1),
            "avg_pd": pd,
        }
        for g, lo, hi, pct, pd in grade_ranges
    ]

    reject_pct = _r(5, 12)
    manual_pct = _r(10, 18)
    return {
        "histogram": histogram,
        "by_grade": by_grade,
        "stats": {
            "mean": _ri(620, 660),
            "median": _ri(615, 655),
            "p10": _ri(480, 520),
            "p90": _ri(760, 810),
            "std": _ri(80, 110),
            "auto_reject_pct": reject_pct,
            "manual_review_pct": manual_pct,
            "auto_approve_pct": round(100 - reject_pct - manual_pct, 1),
        },
        "gini": _r(0.32, 0.48),
        "ks": _r(0.22, 0.38),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  고객 수익성 (RAROC / CLV)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/profitability")
async def profitability(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    customers: list[dict[str, Any]] = []
    for i in range(30):
        loan_balance = _ri(500, 30_000) * 10_000   # 대출 잔액
        gross_rate = _r(0.06, 0.13)                  # 대출 금리 6~13%
        funding_rate = _r(0.03, 0.05)               # 조달 금리 3~5%
        nim = loan_balance * (gross_rate - funding_rate)
        op_cost = nim * _r(0.25, 0.40)              # 운영비용 25~40%
        el = loan_balance * _r(0.003, 0.015) * 0.45  # EL = PD * LGD
        capital = loan_balance * 0.12               # 경제적 자본 12% (위험가중자산 기준)
        profit = nim - op_cost - el
        raroc = round(profit / capital * 100, 1) if capital > 0 else 0
        customers.append({
            "rank": i + 1,
            "name": _name(_rng),
            "segment": _rng.choice(["SEG-DR", "SEG-JD", "일반(대기업)", "일반(중소)", "SEG-YTH"]),
            "revenue": int(nim),
            "cost": int(op_cost),
            "el": int(el),
            "profit": int(profit),
            "raroc": raroc,
            "clv": _ri(500, 5_000) * 10_000,
            "churn_risk": _r(5, 40),
            "product_count": _ri(1, 4),
        })
    customers.sort(key=lambda x: x["raroc"], reverse=True)

    cross_sell = [
        {"name": _name(_rng), "product": p, "prob": _r(40, 85),
         "expected_revenue": _ri(100, 800) * 10_000, "priority": pr}
        for p, pr in [("신용대출→주담대", "HIGH"), ("예금연계", "MEDIUM"),
                      ("펀드 추천", "LOW"), ("보험 연계", "MEDIUM")]
    ]

    # 등급별 수익성
    grade_data = [
        {
            "grade": g, "raroc": raroc, "avg_clv": _ri(500, 5_000) * 10_000,
            "nim": _r(1.2, 3.5), "count": _ri(100, 2_000), "avg_pd": pd,
        }
        for g, raroc, pd in [
            ("AAA", _r(18, 28), 0.003), ("AA", _r(14, 22), 0.008),
            ("A",   _r(11, 18), 0.020), ("B",  _r(8,  14), 0.055),
            ("C",   _r(4,  10), 0.120), ("D",  _r(1,   6), 0.250),
        ]
    ]
    # 상품별 수익성
    prod_data = [
        {
            "product": p, "raroc": raroc,
            "avg_clv": _ri(300, 8_000) * 10_000,
            "total_el": _ri(10, 500) * 1_000_000,
            "rwa": _ri(100, 5_000) * 1_000_000,
        }
        for p, raroc in [("신용대출", _r(12, 20)), ("주담대", _r(8, 14)), ("소액론", _r(15, 30))]
    ]
    # 산점도 데이터
    scatter = [
        {
            "name": c["name"],
            "pd": round(_r(0.3, 25), 2),
            "raroc": c["raroc"],
            "clv": c["clv"],
            "grade": _rng.choice(["AAA", "AA", "A", "B", "C", "D"]),
        }
        for c in customers
    ]

    avg_raroc = round(sum(c["raroc"] for c in customers) / len(customers), 1)
    avg_clv = int(sum(c["clv"] for c in customers) / len(customers))
    return {
        "summary": {
            "avg_raroc": avg_raroc,
            "avg_clv": avg_clv,
            "avg_nim": _r(1.8, 2.8),
            "portfolio_return": _r(3.5, 6.0),
            "cost_of_risk": _r(0.8, 1.8),
        },
        "by_grade": grade_data,
        "by_product": prod_data,
        "scatter": scatter,
        "customers": customers,
        "cross_sell_opportunities": cross_sell,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  금리 시뮬레이션 (What-if)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/rate-simulation")
async def rate_simulation(
    data: dict[str, Any],
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    target_raroc = float(data.get("target_raroc", 12.0))
    pd_pct = float(data.get("pd", 2.0))
    lgd_pct = float(data.get("lgd", 45.0))
    product = str(data.get("product", "신용대출"))
    term_months = int(data.get("term_months", 36))

    # 금리 분해 계산
    funding_cost = 3.50
    el = pd_pct / 100 * lgd_pct / 100
    credit_spread = round(el * 5 + 1.0, 2)
    capital_charge = round(pd_pct / 100 * lgd_pct / 100 * 12.5 * target_raroc / 100, 2)
    operating_cost = 0.45
    profit_margin = 0.30
    suggested_rate = round(funding_cost + credit_spread + capital_charge + operating_cost + profit_margin, 2)

    # 경쟁사 비교
    market_avg = {
        "신용대출": round(8.5 + (pd_pct - 2) * 0.5, 2),
        "주담대": round(4.8 + (pd_pct - 1) * 0.3, 2),
        "소액론": round(15.0 + (pd_pct - 3) * 0.8, 2),
    }

    return {
        "suggested_rate": suggested_rate,
        "decomposition": {
            "funding_cost": funding_cost,
            "credit_spread": credit_spread,
            "capital_charge": capital_charge,
            "operating_cost": operating_cost,
            "profit_margin": profit_margin,
        },
        "raroc_at_rate": round((suggested_rate - funding_cost - credit_spread - operating_cost) /
                               (pd_pct / 100 * lgd_pct / 100 * 12.5) * 100, 1),
        "market_avg_rate": market_avg.get(product, 7.5),
        "competitiveness": "경쟁력 있음" if suggested_rate <= market_avg.get(product, 7.5) else "재검토 필요",
        "term_months": term_months,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  캠페인 분석
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/campaign")
async def campaign(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    channels = ["모바일앱 푸시", "카카오 알림톡", "이메일", "SMS", "인스타그램 광고"]
    campaigns = [
        {
            "id": f"CMP-{2025000 + i}",
            "name": nm,
            "channel": _rng.choice(channels),
            "target_segment": seg,
            "start_date": (date.today() - timedelta(days=_ri(10, 60))).isoformat(),
            "target_count": _ri(5_000, 50_000),
            "sent_count": _ri(4_000, 45_000),
            "opened_count": _ri(1_000, 20_000),
            "applied_count": _ri(50, 2_000),
            "approved_count": _ri(30, 1_500),
            "open_rate": _r(18, 45),
            "conversion_rate": _r(2, 12),
            "avg_loan_amount": _ri(500, 5_000) * 10_000,
            "status": _rng.choice(["진행중", "완료", "진행중", "완료"]),
        }
        for i, (nm, seg) in enumerate([
            ("청년 첫 신용대출 프로모션", "SEG-YTH"),
            ("전문직 특별금리 캠페인", "SEG-DR+JD"),
            ("생활안정자금 소액론", "일반"),
            ("주담대 갈아타기 특판", "기존고객"),
            ("모바일 사전심사 유도", "전체"),
        ])
    ]

    # 채널별 집계 (by_channel)
    channel_list = ["모바일앱", "카카오", "이메일", "SMS", "SNS광고"]
    by_channel: list[dict[str, Any]] = [
        {
            "channel": ch,
            "sent": _ri(5_000, 50_000),
            "applied": _ri(200, 3_000),
            "approved": _ri(100, 2_000),
            "conversion_rate": _r(2, 15),
            "approval_rate": _r(50, 85),
            "avg_loan_amount": _ri(500, 5_000) * 10_000,
            "total_disbursed": _ri(5, 200) * 100_000_000,
        }
        for ch in channel_list
    ]

    # 월별 추이 (monthly)
    monthly = [
        {
            "month": f"2025-{m:02d}",
            "sent": _ri(10_000, 80_000),
            "applied": _ri(500, 5_000),
            "approved": _ri(300, 3_500),
        }
        for m in range(1, 7)
    ]

    # 세그먼트별 성과
    segment_perf = [
        {
            "segment": seg,
            "count": _ri(100, 5_000),
            "conversion_rate": _r(3, 18),
            "avg_score": _ri(560, 750),
            "avg_rate": _r(4.0, 12.0),
        }
        for seg in ["일반", "SEG-YTH", "SEG-DR", "SEG-JD", "SEG-MIL"]
    ]

    total_sent = sum(c["sent"] for c in by_channel)
    total_applied = sum(c["applied"] for c in by_channel)
    total_approved = sum(c["approved"] for c in by_channel)
    total_disbursed = sum(c["total_disbursed"] for c in by_channel)

    return {
        "overview": {
            "total_sent": total_sent,
            "total_applied": total_applied,
            "total_approved": total_approved,
            "overall_conversion": round(total_applied / total_sent * 100, 1) if total_sent else 0,
            "total_disbursed": total_disbursed,
            "avg_loan_amount": int(total_disbursed / total_approved) if total_approved else 0,
        },
        "by_channel": by_channel,
        "monthly": monthly,
        "segment_performance": segment_perf,
        "campaigns": campaigns,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  정책 시뮬레이션
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/policy-simulation")
async def policy_simulation(
    data: dict[str, Any],
    _: Any = Depends(get_current_user),
) -> dict[str, Any]:
    changes = data.get("changes", [])  # [{key, old_value, new_value}]

    # 변경 파라미터별 영향 계산 (단순화된 추정)
    impacts: list[dict[str, Any]] = []
    total_approval_change = 0.0
    total_rate_change = 0.0

    for ch in changes:
        key = ch.get("key", "")
        try:
            old_v = float(ch.get("old_value", 0))
            new_v = float(ch.get("new_value", 0))
        except ValueError:
            continue
        delta = new_v - old_v

        impact: dict[str, Any] = {"key": key, "delta": delta}
        if "dsr" in key:
            approval_change = delta * 150  # DSR 1%p → 승인건 약 150건 변화
            impact["approval_count_change"] = round(approval_change)
            impact["description"] = f"DSR 한도 {'완화' if delta > 0 else '강화'} → 승인율 {'+' if delta > 0 else ''}{round(approval_change / 50, 1)}%p"
            total_approval_change += approval_change
        elif "rate" in key:
            rate_change = delta * 10
            impact["avg_rate_change"] = round(rate_change, 3)
            impact["description"] = f"금리 한도 변경 → 평균 금리 {round(rate_change, 2)}%p 영향"
            total_rate_change += rate_change
        elif "ltv" in key:
            impact["description"] = f"LTV 한도 {'완화' if delta > 0 else '강화'} → 주담대 승인 영향"
        impacts.append(impact)

    return {
        "parameter_impacts": impacts,
        "portfolio_impact": {
            "approval_count_change": round(total_approval_change),
            "approval_rate_change": round(total_approval_change / 5_000 * 100, 2),
            "avg_rate_change": round(total_rate_change, 3),
            "el_change": round(total_approval_change * 0.0001, 4),
        },
        "simulation_note": "시뮬레이션 결과는 추정값입니다. 실제 적용 전 리스크팀 검토 필요.",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  알림 센터
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/notifications")
async def notifications(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    # 프론트엔드 NotificationCenter.tsx 인터페이스에 맞는 구조
    # { id, level, category, message, created_at, read }
    notifications = [
        {"id": "N-001", "level": "CRITICAL", "category": "EWS",
         "message": "고객 EWS CRITICAL 진입 — 종합점수 28점, 즉시 모니터링 강화 필요",
         "created_at": "10분 전", "read": False},
        {"id": "N-002", "level": "WARNING", "category": "PSI",
         "message": "Score PSI 0.21 초과 (임계값 0.20) — 신용대출 모델 재학습 검토 권고",
         "created_at": "1시간 전", "read": False},
        {"id": "N-003", "level": "WARNING", "category": "BRMS",
         "message": "stress_dsr.phase3 파라미터 25.07.01 발효 예정 — 수도권 +1.5%p 준비 필요",
         "created_at": "3시간 전", "read": False},
        {"id": "N-004", "level": "INFO", "category": "COMPLIANCE",
         "message": "DSR 준수율 99.2% — 이번 달 규제 준수 현황 이상 없음",
         "created_at": "5시간 전", "read": True},
        {"id": "N-005", "level": "INFO", "category": "APPEAL",
         "message": "이의제기 3건 처리 대기 — APL-20250101 외 2건 검토 필요",
         "created_at": "1일 전", "read": True},
    ]
    return {"notifications": notifications}


# ─────────────────────────────────────────────────────────────────────────────
#  기존 엔드포인트 (유지)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/audit-trail")
async def audit_trail(limit: int = 30, _: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    params = ["dsr.max_ratio", "ltv.general", "ltv.adjusted", "ltv.speculative",
              "rate.max_interest", "stress_dsr.phase2.seoul", "stress_dsr.phase3.non_seoul"]
    records = []
    for i in range(limit):
        param = _rng.choice(params)
        old_v = round(_rng.uniform(0.1, 0.9), 3)
        new_v = round(old_v + _rng.uniform(-0.05, 0.05), 3)
        records.append({
            "id": i + 1,
            "param_key": param,
            "old_value": str(old_v),
            "new_value": str(new_v),
            "changed_by": _rng.choice(["admin", "risk_manager", "compliance"]),
            "changed_at": (datetime.now() - timedelta(days=_ri(0, 90),
                                                       hours=_ri(0, 23))).isoformat(timespec="seconds"),
            "reason": _rng.choice(["금융위 가이드라인 반영", "내부 정책 개정", "규제 개정", "리스크위원회 결의"]),
        })
    return {"total": limit,
            "records": sorted(records, key=lambda r: r["changed_at"], reverse=True)}


@router.get("/compliance-status")
async def compliance_status(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    return {
        "as_of": date.today().isoformat(),
        "dsr": {"limit": 0.40, "actual_avg": _r(0.28, 0.37),
                "violation_count": _ri(0, 3), "compliance_rate": _r(97.5, 100.0), "status": "green"},
        "ltv": {"general_limit": 0.70, "adjusted_limit": 0.60, "speculative_limit": 0.40,
                "actual_avg": _r(0.42, 0.65), "violation_count": _ri(0, 2),
                "compliance_rate": _r(98.0, 100.0), "status": "green"},
        "rate": {"max_limit": 0.20, "actual_max": _r(0.135, 0.178),
                 "violation_count": 0, "compliance_rate": 100.0, "status": "green"},
    }


@router.post("/stress-test")
async def stress_test(data: dict[str, Any], _: Any = Depends(get_current_user)) -> dict[str, Any]:
    scenario = data.get("scenario", "base")
    seed = {"base": 42, "rate_shock": 100, "real_estate": 200, "recession": 300}.get(scenario, 42)
    rng = random.Random(seed)  # noqa: S311
    shocks = {"base": (1.0, 0.0, 0.0), "rate_shock": (1.5, 0.15, 0.05),
              "real_estate": (1.2, 0.08, 0.12), "recession": (2.2, 0.22, 0.18)}
    pd_mult, el_add, rwa_add = shocks.get(scenario, (1.0, 0.0, 0.0))
    base_pd = round(rng.uniform(0.03, 0.06), 4)
    base_el = round(rng.uniform(0.015, 0.035), 4)
    return {
        "scenario": scenario,
        "impact": {
            "pd_change": round(base_pd * pd_mult - base_pd, 4),
            "stressed_pd": round(base_pd * pd_mult, 4),
            "el_change": round(el_add, 4),
            "stressed_el": round(base_el + el_add, 4),
            "rwa_increase_pct": round(rwa_add * 100, 1),
            "capital_adequacy_ratio": round(rng.uniform(12.5, 16.8), 1),
            "tier1_ratio": round(rng.uniform(10.2, 14.5), 1),
        },
        "portfolio_impact": {
            "approval_rate_change": round(-el_add * 150, 1),
            "avg_rate_change": round(el_add * 50, 2),
            "affected_accounts": rng.randint(100, 5_000),
        },
    }


@router.get("/segment-stats")
async def segment_stats(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    segs = [
        ("SEG-DR", "의사/치과/한의사", -0.005, 3.0, "EQ-B"),
        ("SEG-JD", "변호사/법무사/회계사", -0.002, 2.5, "EQ-B"),
        ("SEG-ART", "예술인(복지재단 등록)", 0.0, 2.0, "EQ-C"),
        ("SEG-YTH", "청년(만 19~34세)", -0.005, 2.0, "EQ-C"),
        ("SEG-MIL", "군인/부사관/장교", -0.005, 2.0, "EQ-S"),
        ("일반", "일반 직장인/자영업", 0.0, 1.0, "—"),
    ]
    return {
        "segments": [
            {
                "segment_code": code, "segment_name": name,
                "count": _ri(50, 2_000),
                "approval_rate": _r(55, 92),
                "avg_score": _ri(560, 760),
                "avg_rate": _r(3.5, 9.5),
                "rate_discount": disc, "limit_multiplier": mult, "eq_floor": eq,
                "monthly_trend": [_ri(20, 200) for _ in range(6)],
            }
            for code, name, disc, mult, eq in segs
        ]
    }


@router.get("/psi-detail")
async def psi_detail(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    months = [(datetime.now() - timedelta(days=30 * i)).strftime("%Y-%m")
              for i in range(11, -1, -1)]
    score_psi = [_r(0.02, 0.25) for _ in months]
    feature_psi = {
        "연소득": [_r(0.01, 0.12) for _ in months],
        "부채비율": [_r(0.02, 0.18) for _ in months],
        "신용점수(CB)": [_r(0.01, 0.09) for _ in months],
    }
    return {"months": months, "score_psi": score_psi, "feature_psi": feature_psi,
            "threshold": {"green": 0.1, "yellow": 0.2}}


@router.get("/calibration-curve")
async def calibration_curve(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    deciles = list(range(1, 11))
    predicted = [_r(0.005, 0.15) * (d / 10) ** 0.8 for d in deciles]
    actual = [p + _r(-0.01, 0.01) for p in predicted]
    return {"deciles": deciles, "predicted_pd": predicted, "actual_dr": actual,
            "ece": _r(0.005, 0.025), "brier_score": _r(0.04, 0.10)}


@router.get("/vintage")
async def vintage(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    _rng.seed(42)
    cohorts = [f"2024-{m:02d}" for m in range(1, 13)]
    mobs = [3, 6, 12]
    data = []
    for cohort in cohorts:
        row: dict[str, Any] = {"cohort": cohort}
        for mob in mobs:
            row[f"mob_{mob}"] = _r(0.3, 4.8)
        data.append(row)
    return {"cohorts": data, "mobs": mobs}


@router.get("/eq-grade-master")
async def eq_grade_master(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    grades = [("EQ-S", 2.0, -0.005, "초우량"), ("EQ-A", 1.5, -0.003, "우량"),
              ("EQ-B", 1.2, -0.001, "양호"), ("EQ-C", 1.0, 0.000, "보통"),
              ("EQ-D", 0.9, 0.002, "주의"), ("EQ-E", 0.7, 0.005, "경계")]
    return {"grades": [{"grade": g, "limit_multiplier": lm, "rate_adj": ra,
                        "description": desc, "active": True}
                       for g, lm, ra, desc in grades]}


@router.get("/irg-master")
async def irg_master(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    industries = [
        ("IT/소프트웨어", "L", -0.001), ("의료/바이오", "L", -0.001),
        ("금융/보험", "M", 0.000), ("제조업(일반)", "M", 0.000),
        ("건설업", "H", 0.0015), ("부동산업", "H", 0.0015),
        ("요식/숙박업", "VH", 0.003), ("가상자산/코인", "VH", 0.003),
    ]
    return {
        "irg_grades": [{"industry": ind, "irg": irg, "rate_adj": adj, "active": True}
                       for ind, irg, adj in industries],
        "scale": {"L": -0.10, "M": 0.00, "H": 0.15, "VH": 0.30},
    }


@router.get("/brms-params")
async def brms_params(_: Any = Depends(get_current_user)) -> dict[str, Any]:
    params = [
        ("dsr.max_ratio", "0.40", "DSR 최대 비율 (총부채원리금상환비율)", "규제", True),
        ("ltv.general", "0.70", "LTV 일반 지역 한도", "규제", True),
        ("ltv.adjusted", "0.60", "LTV 조정지역 한도", "규제", True),
        ("ltv.speculative", "0.40", "LTV 투기지역 한도", "규제", True),
        ("rate.max_interest", "0.20", "법정 최고금리 (이자제한법)", "규제", True),
        ("stress_dsr.phase2.seoul", "0.0075", "스트레스DSR Phase2 수도권 가산율", "스트레스DSR", True),
        ("stress_dsr.phase2.non_seoul", "0.0150", "스트레스DSR Phase2 비수도권 가산율", "스트레스DSR", True),
        ("stress_dsr.phase3.seoul", "0.0150", "스트레스DSR Phase3 수도권 (25.07.01 발효)", "스트레스DSR", False),
        ("stress_dsr.phase3.non_seoul", "0.0300", "스트레스DSR Phase3 비수도권 (25.07.01 발효)", "스트레스DSR", False),
        ("score.auto_reject", "450", "자동거절 점수 하한선", "스코어", True),
        ("score.manual_review_min", "450", "수동심사 구간 하한", "스코어", True),
        ("score.manual_review_max", "530", "수동심사 구간 상한 / 자동승인 하한", "스코어", True),
        ("score.base_point", "600", "기준점 (PD 7.2%)", "스코어", True),
        ("score.pdo", "40", "PDO - 점수 40점 = PD 2배 변화", "스코어", True),
        ("micro.max_amount", "3000000", "소액마이크로론 최대 금액 (300만원)", "상품", True),
        ("micro.max_term", "36", "소액마이크로론 최장 기간(개월)", "상품", True),
    ]
    return {"params": [{"key": k, "value": v, "description": d, "category": cat,
                        "active": active, "updated_at": "2025-01-15"}
                       for k, v, d, cat, active in params]}


# ─────────────────────────────────────────────────────────────────────────────
#  헬퍼 함수
# ─────────────────────────────────────────────────────────────────────────────

def _grade(score: int) -> str:
    if score >= 820:
        return "1등급"
    if score >= 760:
        return "2등급"
    if score >= 700:
        return "3등급"
    if score >= 640:
        return "4등급"
    if score >= 580:
        return "5등급"
    if score >= 520:
        return "6등급"
    if score >= 460:
        return "7등급"
    return "8등급"


def _detect_segment(data: dict[str, Any]) -> str:
    occupation = str(data.get("occupation", ""))
    age = int(data.get("age", 35))
    if any(k in occupation for k in ["의사", "치과", "한의사"]):
        return "SEG-DR"
    if any(k in occupation for k in ["변호사", "법무사", "회계사"]):
        return "SEG-JD"
    if "군인" in occupation or "부사관" in occupation:
        return "SEG-MIL"
    if "예술" in occupation:
        return "SEG-ART"
    if 19 <= age <= 34:
        return "SEG-YTH"
    return "일반"
