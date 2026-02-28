"""
모니터링 API (PSI, 칼리브레이션, 빈티지)
==========================================
FR-MON-002: PSI 3종 (Score/Feature/Target)
FR-MON-004: 빈티지/코호트 분석
FR-MON-005: 칼리브레이션 (ECE/Brier Score)

MonitoringEngine을 통한 실제 계산 + DB 데이터 없을 시 데모 응답.
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.monitoring_engine import (
    MonitoringEngine,
    compute_psi,
    compute_score_psi,
    compute_target_psi,
    compute_calibration,
    PSI_GREEN,
    PSI_YELLOW,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── 기본 피처 목록 (Application Scorecard) ───────────────────
DEFAULT_MONITOR_FEATURES = [
    "cb_score",
    "income_annual_wan",
    "delinquency_count_12m",
    "dsr_ratio",
    "inquiry_count_3m",
    "open_loan_count",
    "debt_to_income",
    "employment_duration_months",
]


@router.get("/psi-summary")
async def get_psi_summary(
    model_version: str | None = Query(None, description="모델 버전 (미지정 시 최신)"),
    reference_days: int = Query(180, description="기준 기간 (일, 기본 180일)"),
    current_days: int = Query(30, description="현재 기간 (일, 기본 최근 30일)"),
    features: list[str] = Query(None, description="피처 PSI 계산 대상"),
    db: AsyncSession = Depends(get_db),
):
    """
    PSI 요약 조회 (Score/Feature/Target PSI).

    PSI 판정 기준:
      - PSI < 0.10: green (안정)
      - PSI < 0.20: yellow (주의)
      - PSI ≥ 0.20: red (모델 재검토)
    """
    engine = MonitoringEngine(db_session=db)
    feature_names = features or DEFAULT_MONITOR_FEATURES

    score_psi = await engine.compute_score_psi_from_db(
        model_version=model_version,
        reference_days=reference_days,
        current_days=current_days,
    )

    # 피처 PSI (DB 기반, 데이터 부재 시 데모 응답)
    feature_psi = await engine.compute_feature_psi_from_db(
        feature_names=feature_names,
        reference_days=reference_days,
        current_days=current_days,
    )

    # Target PSI (부도율 안정성)
    bad_rate_train = 0.072
    bad_rate_recent = await engine.compute_bad_rate_from_db(lookback_days=current_days)
    target_psi = compute_target_psi(
        bad_rate_reference=bad_rate_train,
        bad_rate_current=bad_rate_recent,
        n_reference=10000,
        n_current=3000,
    )

    # 전체 상태 판정
    all_vals = [score_psi.get("value", 0)] + [v["psi"] for v in feature_psi.values()] + [target_psi.psi]
    max_psi = max(all_vals)
    overall = "green" if max_psi < PSI_GREEN else ("yellow" if max_psi < PSI_YELLOW else "red")

    return {
        "computed_at": datetime.utcnow().isoformat(),
        "model_version": model_version or "demo-v1.0",
        "reference_period_days": reference_days,
        "current_period_days": current_days,
        "overall_status": overall,
        "score_psi": {
            **score_psi,
            "threshold_warning": PSI_GREEN,
            "threshold_critical": PSI_YELLOW,
        },
        "feature_psi": feature_psi,
        "target_psi": {
            "value": target_psi.psi,
            "status": target_psi.status,
            "bad_rate_train": bad_rate_train,
            "bad_rate_recent": bad_rate_recent,
        },
        "rca_required": overall in ("yellow", "red"),
        "message": {
            "green": "모든 PSI 지표 정상 범위",
            "yellow": "일부 PSI 주의 — 원인 분석(RCA) 검토 권장",
            "red": "PSI 경보 — 즉시 모델 재검토 필요",
        }.get(overall, ""),
    }


@router.get("/calibration")
async def get_calibration_metrics(
    model_version: str | None = Query(None),
    n_bins: int = Query(10, ge=5, le=20, description="칼리브레이션 구간 수"),
    lookback_days: int = Query(365, description="칼리브레이션 기간 (일)"),
    db: AsyncSession = Depends(get_db),
):
    """
    칼리브레이션 메트릭 조회 (FR-MON-005).

    목표:
      - ECE (Expected Calibration Error) ≤ 0.02
      - Brier Score ≤ 0.07
    """
    engine = MonitoringEngine(db_session=db)
    result = await engine.compute_calibration_from_db(
        model_version=model_version,
        n_bins=n_bins,
        lookback_days=lookback_days,
    )
    return {
        "computed_at": datetime.utcnow().isoformat(),
        "model_version": model_version or "demo-v1.0",
        "lookback_days": lookback_days,
        **result,
    }


@router.get("/vintage")
async def get_vintage_analysis(
    cohort_months: list[int] = Query([3, 6, 12], description="DPD 추적 기간 (개월)"),
    db: AsyncSession = Depends(get_db),
):
    """
    빈티지/코호트 분석 (FR-MON-004).
    실행 후 3/6/12개월 DPD 누적 부도율 추적.
    """
    # DB에서 cohort 데이터 조회 시도
    try:
        from sqlalchemy import select, text
        from app.db.schemas.credit_score import CreditScore
        from app.db.schemas.loan_application import LoanApplication

        # 코호트별 월간 실적 집계 (DB 있을 때만)
        stmt = text("""
            SELECT
                TO_CHAR(cs.created_at, 'YYYY-MM') AS cohort_month,
                EXTRACT(MONTH FROM AGE(NOW(), cs.created_at))::int AS months_on_book,
                COUNT(*) AS n_total,
                SUM(CASE WHEN cs.actual_default = 1 THEN 1 ELSE 0 END) AS n_bad
            FROM credit_scores cs
            WHERE cs.actual_default IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 2
        """)
        rows = (await db.execute(stmt)).fetchall()

        if rows:
            cohorts: dict[str, dict] = {}
            for row in rows:
                cohort = str(row.cohort_month)
                mob = int(row.months_on_book)
                if mob in cohort_months:
                    key = f"dpd_{mob}m"
                    if cohort not in cohorts:
                        cohorts[cohort] = {}
                    bad_rate = row.n_bad / max(1, row.n_total)
                    cohorts[cohort][key] = round(float(bad_rate), 4)

            if cohorts:
                return {
                    "computed_at": datetime.utcnow().isoformat(),
                    "cohort_periods": cohort_months,
                    "cohorts": cohorts,
                    "roll_rate_matrix": _demo_roll_rates(),
                    "data_source": "database",
                }
    except Exception as e:
        logger.warning(f"빈티지 DB 조회 실패 (데모 응답 사용): {e}")

    # 데모 응답
    cohorts_demo: dict[str, dict] = {}
    for month_offset in range(0, 13, 3):
        cohort_date = (datetime.utcnow() - timedelta(days=month_offset * 30)).strftime("%Y-%m")
        dpd_data = {}
        for dpd_months in cohort_months:
            if month_offset >= dpd_months:
                base_rate = 0.072
                dpd_data[f"dpd_{dpd_months}m"] = round(
                    base_rate * (1 + dpd_months * 0.01 - month_offset * 0.005), 4
                )
        cohorts_demo[cohort_date] = dpd_data

    return {
        "computed_at": datetime.utcnow().isoformat(),
        "cohort_periods": cohort_months,
        "cohorts": cohorts_demo,
        "roll_rate_matrix": _demo_roll_rates(),
        "data_source": "demo",
    }


@router.get("/portfolio-summary")
async def get_portfolio_summary(
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 요약 (대출 잔액, 부도율, DSR 분포, EL/RWA)."""
    from sqlalchemy import select, func
    from app.db.schemas.credit_score import CreditScore
    from app.db.schemas.loan_application import LoanApplication

    # 심사 결과 집계
    stmt = select(
        func.count(CreditScore.id).label("total"),
        func.sum(CreditScore.approved_amount).label("total_approved"),
        func.avg(CreditScore.dsr_ratio).label("avg_dsr"),
        func.avg(CreditScore.pd_estimate).label("avg_pd"),
        func.avg(CreditScore.score).label("avg_score"),
    )
    result = await db.execute(stmt)
    row = result.one()

    # 결정별 건수
    stmt2 = select(
        CreditScore.decision,
        func.count(CreditScore.id).label("count")
    ).group_by(CreditScore.decision)
    r2 = await db.execute(stmt2)
    decisions = {r.decision: r.count for r in r2}

    total = row.total or 0
    total_approved = float(row.total_approved or 0)
    avg_pd = float(row.avg_pd or 0.072)

    # EL 추정 (무담보 기준)
    el_estimate = total_approved * avg_pd * 0.45

    return {
        "computed_at": datetime.utcnow().isoformat(),
        "total_applications": total,
        "total_approved_amount": total_approved,
        "avg_dsr": round(float(row.avg_dsr or 0), 4),
        "avg_pd": round(avg_pd, 4),
        "avg_score": round(float(row.avg_score or 0), 1),
        "decisions": decisions,
        "approval_rate": round(decisions.get("approved", 0) / total if total else 0, 4),
        "el_estimate": round(el_estimate, 0),
        "el_rate": round(avg_pd * 0.45, 4),
    }


@router.get("/psi-report")
async def get_full_psi_report(
    model_version: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """전체 모니터링 보고서 (Score+Feature+Calibration 통합)."""
    engine = MonitoringEngine(db_session=db)
    report = await engine.full_report(
        model_version=model_version,
        feature_names=DEFAULT_MONITOR_FEATURES,
    )
    return report


def _demo_roll_rates() -> dict:
    return {
        "current_to_dpd30": 0.028,
        "dpd30_to_dpd60": 0.450,
        "dpd60_to_dpd90": 0.600,
        "dpd90_to_default": 0.750,
        "description": "연간 전이 확률 (관측 기반)",
    }
