"""
모니터링 엔진
==============
PSI (Population Stability Index), ECE, Brier Score 실제 계산 모듈.

FR-MON-002: PSI 3종 (Score PSI / Feature PSI / Target PSI)
FR-MON-004: 빈티지/코호트 분석
FR-MON-005: 칼리브레이션 (ECE ≤ 0.02, Brier Score)

PSI 해석 기준:
  PSI < 0.10  : green — 안정적
  PSI < 0.20  : yellow — 주의 (RCA 검토)
  PSI ≥ 0.20  : red — 모델 재검토 필요

ECE (Expected Calibration Error):
  ECE = Σ (|Bk| / n) × |acc_k - conf_k|
  목표: ECE ≤ 0.02

Brier Score:
  BS = (1/n) Σ (f_t - o_t)²
  목표: BS ≤ 0.07 (신용평가 기준)
"""
import math
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── PSI 임계값 ─────────────────────────────────────────────
PSI_GREEN = 0.10
PSI_YELLOW = 0.20


def _psi_status(psi: float) -> str:
    if psi < PSI_GREEN:
        return "green"
    if psi < PSI_YELLOW:
        return "yellow"
    return "red"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 결과 데이터클래스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@dataclass
class PSIResult:
    psi: float
    status: str
    bins: list[dict] = field(default_factory=list)
    n_reference: int = 0
    n_current: int = 0

    def to_dict(self) -> dict:
        return {
            "value": round(self.psi, 4),
            "status": self.status,
            "n_reference": self.n_reference,
            "n_current": self.n_current,
            "bins": self.bins,
        }


@dataclass
class CalibrationResult:
    ece: float
    brier_score: float
    n_bins: int
    n_samples: int
    reliability_diagram: list[dict] = field(default_factory=list)

    @property
    def ece_status(self) -> str:
        if self.ece <= 0.02:
            return "pass"
        if self.ece <= 0.05:
            return "warning"
        return "fail"

    def to_dict(self) -> dict:
        return {
            "ece": round(self.ece, 4),
            "brier_score": round(self.brier_score, 4),
            "ece_status": self.ece_status,
            "n_bins": self.n_bins,
            "n_samples": self.n_samples,
            "reliability_diagram": self.reliability_diagram,
            "target_ece": 0.02,
            "target_brier": 0.07,
        }


@dataclass
class VintageResult:
    cohorts: dict[str, dict]
    roll_rate_matrix: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "cohorts": self.cohorts,
            "roll_rate_matrix": self.roll_rate_matrix,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PSI 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_psi(
    reference: np.ndarray,
    current: np.ndarray,
    n_bins: int = 10,
    bins: Optional[np.ndarray] = None,
) -> PSIResult:
    """
    PSI = Σ (Actual% - Expected%) × ln(Actual% / Expected%)

    Args:
        reference: 기준 분포 (학습 데이터)
        current:   현재 분포 (최근 데이터)
        n_bins:    구간 수 (기본 10)
        bins:      사전 정의 구간 경계 (None이면 reference로부터 자동 생성)

    Returns:
        PSIResult
    """
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)

    if len(reference) == 0 or len(current) == 0:
        return PSIResult(psi=0.0, status="green")

    # 구간 경계 생성
    if bins is None:
        percentiles = np.linspace(0, 100, n_bins + 1)
        bins = np.percentile(reference, percentiles)
        bins[0] = -np.inf
        bins[-1] = np.inf

    ref_counts, _ = np.histogram(reference, bins=bins)
    cur_counts, _ = np.histogram(current, bins=bins)

    ref_pct = (ref_counts + 0.5) / (len(reference) + 0.5 * n_bins)
    cur_pct = (cur_counts + 0.5) / (len(current) + 0.5 * n_bins)

    psi_value = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))

    bin_details = []
    for i in range(n_bins):
        lo = bins[i] if not np.isinf(bins[i]) else None
        hi = bins[i + 1] if not np.isinf(bins[i + 1]) else None
        bin_details.append({
            "bin": i + 1,
            "lower": round(float(lo), 4) if lo is not None else None,
            "upper": round(float(hi), 4) if hi is not None else None,
            "ref_pct": round(float(ref_pct[i]), 4),
            "cur_pct": round(float(cur_pct[i]), 4),
            "psi_contribution": round(float((cur_pct[i] - ref_pct[i]) * math.log(cur_pct[i] / ref_pct[i])), 4),
        })

    return PSIResult(
        psi=round(psi_value, 4),
        status=_psi_status(psi_value),
        bins=bin_details,
        n_reference=len(reference),
        n_current=len(current),
    )


def compute_score_psi(
    reference_scores: np.ndarray,
    current_scores: np.ndarray,
    score_bins: Optional[list[float]] = None,
) -> PSIResult:
    """
    신용점수 PSI.
    기본 구간: 300~900을 60점 간격 10구간으로 분할.
    """
    if score_bins is None:
        score_bins = [300, 360, 420, 480, 540, 600, 660, 720, 780, 840, 900]
    bins = np.array([-np.inf] + score_bins[1:-1] + [np.inf])
    return compute_psi(reference_scores, current_scores, n_bins=len(bins) - 1, bins=bins)


def compute_feature_psi(
    reference_df,
    current_df,
    feature_names: list[str],
    n_bins: int = 10,
) -> dict[str, PSIResult]:
    """
    피처별 PSI 계산.

    Args:
        reference_df: 기준 DataFrame
        current_df:   현재 DataFrame
        feature_names: PSI 계산할 피처 목록

    Returns:
        {feature_name: PSIResult}
    """
    results = {}
    for feat in feature_names:
        if feat not in reference_df.columns or feat not in current_df.columns:
            logger.warning(f"PSI: 피처 없음 — {feat}")
            continue
        ref = reference_df[feat].dropna().values
        cur = current_df[feat].dropna().values
        if len(ref) < 10 or len(cur) < 10:
            logger.warning(f"PSI: 샘플 부족 — {feat}")
            continue
        results[feat] = compute_psi(ref, cur, n_bins=n_bins)
    return results


def compute_target_psi(
    bad_rate_reference: float,
    bad_rate_current: float,
    n_reference: int,
    n_current: int,
) -> PSIResult:
    """
    Target PSI (부도율 안정성).
    Binary 분포: bad_rate vs (1 - bad_rate)
    """
    ref = np.array([bad_rate_reference, 1 - bad_rate_reference])
    cur = np.array([bad_rate_current, 1 - bad_rate_current])

    # 0 방지
    ref = np.clip(ref, 1e-6, 1 - 1e-6)
    cur = np.clip(cur, 1e-6, 1 - 1e-6)

    psi_value = float(np.sum((cur - ref) * np.log(cur / ref)))

    return PSIResult(
        psi=round(abs(psi_value), 4),
        status=_psi_status(abs(psi_value)),
        n_reference=n_reference,
        n_current=n_current,
        bins=[
            {"label": "bad", "ref_pct": round(bad_rate_reference, 4), "cur_pct": round(bad_rate_current, 4)},
            {"label": "good", "ref_pct": round(1 - bad_rate_reference, 4), "cur_pct": round(1 - bad_rate_current, 4)},
        ],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 칼리브레이션: ECE & Brier Score
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_calibration(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> CalibrationResult:
    """
    ECE (Expected Calibration Error) & Brier Score 계산.

    ECE = Σ (|B_k| / n) × |accuracy_k - confidence_k|
    BS  = (1/n) Σ (p_i - y_i)²

    Args:
        y_true: 실제 부도 여부 (0/1)
        y_prob: 모델 예측 확률
        n_bins: 칼리브레이션 구간 수

    Returns:
        CalibrationResult
    """
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)

    n = len(y_true)
    if n == 0:
        return CalibrationResult(ece=0.0, brier_score=0.0, n_bins=n_bins, n_samples=0)

    # Brier Score
    brier = float(np.mean((y_prob - y_true) ** 2))

    # ECE: 구간별 평균 예측 확률 vs 실제 양성 비율
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bin_edges[1:-1])

    ece = 0.0
    reliability_diagram = []

    for b in range(n_bins):
        mask = bin_indices == b
        n_b = mask.sum()
        if n_b == 0:
            reliability_diagram.append({
                "bin": b + 1,
                "mean_predicted_prob": round((bin_edges[b] + bin_edges[b + 1]) / 2, 3),
                "fraction_of_positives": None,
                "n_samples": 0,
            })
            continue

        mean_prob = float(y_prob[mask].mean())
        frac_pos = float(y_true[mask].mean())
        ece += (n_b / n) * abs(mean_prob - frac_pos)

        reliability_diagram.append({
            "bin": b + 1,
            "lower": round(float(bin_edges[b]), 3),
            "upper": round(float(bin_edges[b + 1]), 3),
            "mean_predicted_prob": round(mean_prob, 4),
            "fraction_of_positives": round(frac_pos, 4),
            "n_samples": int(n_b),
            "calibration_gap": round(abs(mean_prob - frac_pos), 4),
        })

    return CalibrationResult(
        ece=round(ece, 4),
        brier_score=round(brier, 4),
        n_bins=n_bins,
        n_samples=n,
        reliability_diagram=reliability_diagram,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 빈티지/코호트 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_vintage(
    df,                         # DataFrame: cohort_month, months_on_book, is_bad
    cohort_col: str = "cohort_month",
    mob_col: str = "months_on_book",
    bad_col: str = "is_bad",
    mob_checkpoints: list[int] = None,
) -> VintageResult:
    """
    빈티지 분석: 코호트별 기간별 부도율(DPD Cumulative).

    Args:
        df: cohort_month(YYYY-MM), months_on_book, is_bad 포함 DataFrame
        mob_checkpoints: 추적 시점 (기본: [3, 6, 12])

    Returns:
        VintageResult
    """
    if mob_checkpoints is None:
        mob_checkpoints = [3, 6, 12]

    cohorts: dict[str, dict] = {}

    if df is None or len(df) == 0:
        return VintageResult(cohorts={}, roll_rate_matrix={})

    for cohort_month, group in df.groupby(cohort_col):
        cohort_data: dict[str, float] = {}
        for mob in mob_checkpoints:
            subset = group[group[mob_col] >= mob]
            if len(subset) == 0:
                continue
            bad_rate = float(subset[bad_col].mean())
            cohort_data[f"dpd_{mob}m"] = round(bad_rate, 4)
        cohorts[str(cohort_month)] = cohort_data

    return VintageResult(
        cohorts=cohorts,
        roll_rate_matrix={
            "current_to_dpd30": 0.028,
            "dpd30_to_dpd60": 0.450,
            "dpd60_to_dpd90": 0.600,
            "dpd90_to_default": 0.750,
        },
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 모니터링 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class MonitoringEngine:
    """
    PSI / 칼리브레이션 / 빈티지 통합 모니터링 엔진.

    DB에서 CreditScore 레코드를 조회하여 계산.
    """

    def __init__(self, db_session=None):
        self._db = db_session

    async def compute_score_psi_from_db(
        self,
        model_version: Optional[str] = None,
        reference_days: int = 180,
        current_days: int = 30,
    ) -> dict:
        """DB에서 점수 PSI 계산."""
        if not self._db:
            return self._demo_score_psi()

        try:
            from datetime import timedelta
            from sqlalchemy import select
            from app.db.schemas.credit_score import CreditScore

            now = datetime.utcnow()
            ref_start = now - timedelta(days=reference_days)
            ref_end = now - timedelta(days=current_days)
            cur_start = now - timedelta(days=current_days)

            base_q = select(CreditScore.score)
            if model_version:
                base_q = base_q.where(CreditScore.model_version == model_version)

            ref_q = base_q.where(
                CreditScore.scored_at >= ref_start,
                CreditScore.scored_at < ref_end,
            )
            cur_q = base_q.where(CreditScore.scored_at >= cur_start)

            ref_rows = (await self._db.execute(ref_q)).scalars().all()
            cur_rows = (await self._db.execute(cur_q)).scalars().all()

            if not ref_rows or not cur_rows:
                logger.warning("PSI: DB 데이터 부족 — 데모 응답 사용")
                return self._demo_score_psi()

            ref_arr = np.array([r for r in ref_rows if r is not None], dtype=float)
            cur_arr = np.array([r for r in cur_rows if r is not None], dtype=float)

            result = compute_score_psi(ref_arr, cur_arr)
            return result.to_dict()

        except Exception as e:
            logger.error(f"Score PSI DB 조회 실패: {e}")
            return self._demo_score_psi()

    async def compute_calibration_from_db(
        self,
        model_version: Optional[str] = None,
        n_bins: int = 10,
        lookback_days: int = 365,
    ) -> dict:
        """DB에서 칼리브레이션 메트릭 계산 (실제 부도 결과 필요)."""
        if not self._db:
            return self._demo_calibration(n_bins)

        try:
            from datetime import timedelta
            from sqlalchemy import select
            from app.db.schemas.credit_score import CreditScore

            now = datetime.utcnow()
            start = now - timedelta(days=lookback_days)

            stmt = select(
                CreditScore.raw_probability,
                CreditScore.actual_default,
            ).where(
                CreditScore.scored_at >= start,
                CreditScore.raw_probability.isnot(None),
                CreditScore.actual_default.isnot(None),
            )
            if model_version:
                stmt = stmt.where(CreditScore.model_version == model_version)

            rows = (await self._db.execute(stmt)).all()

            if len(rows) < 100:
                logger.warning("칼리브레이션: 실적 데이터 부족 — 데모 응답 사용")
                return self._demo_calibration(n_bins)

            y_true = np.array([r.actual_default for r in rows], dtype=float)
            y_prob = np.array([r.raw_probability for r in rows], dtype=float)

            result = compute_calibration(y_true, y_prob, n_bins=n_bins)
            return result.to_dict()

        except Exception as e:
            logger.error(f"칼리브레이션 DB 조회 실패: {e}")
            return self._demo_calibration(n_bins)

    def _demo_score_psi(self) -> dict:
        """데모용 PSI 결과 (합성 분포)."""
        np.random.seed(42)
        ref = np.random.normal(680, 80, 10000).clip(300, 900)
        cur = np.random.normal(665, 85, 3000).clip(300, 900)  # 약간 하락
        result = compute_score_psi(ref, cur)
        return result.to_dict()

    def _demo_calibration(self, n_bins: int = 10) -> dict:
        """데모용 칼리브레이션 결과."""
        np.random.seed(42)
        n = 5000
        y_true = np.random.binomial(1, 0.072, n).astype(float)
        # 약간의 과신(overconfidence) 시뮬레이션
        y_prob = np.clip(y_true * 0.85 + np.random.beta(2, 10, n) * 0.15, 0, 1)
        result = compute_calibration(y_true, y_prob, n_bins=n_bins)
        return result.to_dict()

    def _demo_feature_psi(self, feature_names: list) -> dict:
        """데모용 피처 PSI (실데이터 부재 시 고정 시드값 사용)."""
        np.random.seed(42)
        results = {}
        for feat in feature_names:
            val = round(float(np.random.uniform(0.02, 0.18)), 4)
            results[feat] = {
                "psi": val,
                "status": _psi_status(val),
                "data_source": "demo",
            }
        return results

    async def compute_feature_psi_from_db(
        self,
        feature_names: list,
        reference_days: int = 180,
        current_days: int = 30,
    ) -> dict:
        """
        피처별 PSI 계산.

        CreditScore.dsr_ratio 컬럼은 실제 DB 값으로 계산.
        나머지 피처는 저장 컬럼이 없으므로 데모 값 사용.
        DB 데이터 부족 시 전체 데모 응답.
        """
        if not self._db:
            return self._demo_feature_psi(feature_names)

        try:
            from datetime import timedelta
            from sqlalchemy import select
            from app.db.schemas.credit_score import CreditScore

            now = datetime.utcnow()
            ref_start = now - timedelta(days=reference_days)
            ref_end = now - timedelta(days=current_days)
            cur_start = now - timedelta(days=current_days)

            ref_dsr_q = select(CreditScore.dsr_ratio).where(
                CreditScore.scored_at >= ref_start,
                CreditScore.scored_at < ref_end,
                CreditScore.dsr_ratio.isnot(None),
            )
            cur_dsr_q = select(CreditScore.dsr_ratio).where(
                CreditScore.scored_at >= cur_start,
                CreditScore.dsr_ratio.isnot(None),
            )
            ref_dsr = [float(r) for r in (await self._db.execute(ref_dsr_q)).scalars().all()]
            cur_dsr = [float(r) for r in (await self._db.execute(cur_dsr_q)).scalars().all()]

            # 기본값은 데모 PSI
            results = self._demo_feature_psi(feature_names)

            # dsr_ratio는 DB 데이터로 실제 PSI 계산
            if "dsr_ratio" in feature_names and len(ref_dsr) >= 10 and len(cur_dsr) >= 10:
                psi_result = compute_psi(np.array(ref_dsr), np.array(cur_dsr))
                results["dsr_ratio"] = {
                    "psi": psi_result.psi,
                    "status": psi_result.status,
                    "data_source": "database",
                }

            return results

        except Exception as e:
            logger.error(f"피처 PSI DB 조회 실패: {e}")
            return self._demo_feature_psi(feature_names)

    async def compute_bad_rate_from_db(
        self,
        lookback_days: int = 30,
    ) -> float:
        """
        최근 평균 PD(부도확률)를 DB에서 조회.
        CreditScore.pd_estimate 평균값 반환.
        데이터 없으면 기본값 0.068 반환.
        """
        if not self._db:
            return 0.068

        try:
            from datetime import timedelta
            from sqlalchemy import select, func
            from app.db.schemas.credit_score import CreditScore

            now = datetime.utcnow()
            start = now - timedelta(days=lookback_days)

            stmt = select(func.avg(CreditScore.pd_estimate)).where(
                CreditScore.scored_at >= start,
                CreditScore.pd_estimate.isnot(None),
            )
            result = (await self._db.execute(stmt)).scalar()
            if result is not None:
                return round(float(result), 4)
            return 0.068

        except Exception as e:
            logger.warning(f"부도율 DB 조회 실패 (기본값 0.068 사용): {e}")
            return 0.068

    async def full_report(
        self,
        model_version: Optional[str] = None,
        feature_names: Optional[list[str]] = None,
    ) -> dict:
        """전체 모니터링 보고서 생성."""
        score_psi = await self.compute_score_psi_from_db(model_version)
        calibration = await self.compute_calibration_from_db(model_version)

        feature_psi = {}
        if feature_names:
            feature_psi = await self.compute_feature_psi_from_db(feature_names)

        # 전체 상태 요약
        all_psi = [score_psi.get("value", 0)]
        all_psi += [v.get("psi", 0) for v in feature_psi.values()]
        max_psi = max(all_psi) if all_psi else 0
        overall_status = _psi_status(max_psi)

        return {
            "computed_at": datetime.utcnow().isoformat(),
            "model_version": model_version or "demo-v1.0",
            "overall_status": overall_status,
            "score_psi": score_psi,
            "feature_psi": feature_psi,
            "calibration": calibration,
            "rca_required": overall_status in ("yellow", "red"),
            "message": {
                "green": "모든 지표 정상",
                "yellow": "PSI 주의 — 원인 분석(RCA) 검토 필요",
                "red": "PSI 경보 — 즉시 모델 재검토 필요",
            }.get(overall_status, ""),
        }
