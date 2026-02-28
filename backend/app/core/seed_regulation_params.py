"""
규제 파라미터 초기 시드 데이터
===================================
DB 최초 구동 시 regulation_params 테이블에 기준 파라미터 입력.
모든 규제값은 여기서 관리 → 코드 배포 없이 DB 업데이트로 변경 가능.

실행: python -m app.core.seed_regulation_params
"""
from datetime import UTC, datetime
import logging

logger = logging.getLogger(__name__)

# ── Phase 2 시행일 (2024-02-26) ──────────────────────────────────
PHASE2_DATE = datetime(2024, 2, 26, tzinfo=UTC)
# ── Phase 3 예정일 (2025-07-01) ─────────────────────────────────
PHASE3_DATE = datetime(2025, 7, 1, tzinfo=UTC)
# ── 기존 제도 시작일 ─────────────────────────────────────────────
EPOCH = datetime(2020, 1, 1, tzinfo=UTC)

# ── 소수 표현 (테스트 및 계산 참조용) ────────────────────────────────
# LTV 한도: general=0.70, regulated=0.60, speculation_area=0.40
# 스트레스 DSR 소수: phase2_metro=0.0075, phase3_metro=0.0150, phase3_nonmetro=0.0300
# 최고금리 소수: max_interest=0.20

SEED_PARAMS = [
    # ────────────────────────────────────────────────────────────
    # 1. 스트레스 DSR (금감원 행정지도)
    # Phase 2: 수도권 변동 0.75%p, 비수도권 변동 1.50%p (24.02.26 시행)
    # Phase 3: 수도권 변동 1.50%p, 비수도권 변동 3.00%p (25.07.01 예정)
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "stress_dsr.metropolitan.variable",
        "param_category": "dsr",
        "phase_label": "phase2",
        "param_value": {"rate": 0.75, "unit": "percentage_point", "apply_ratio": 1.0},
        "condition_json": {"region": "metropolitan", "rate_type": "variable"},
        "effective_from": PHASE2_DATE,
        "effective_to": PHASE3_DATE,
        "legal_basis": "금감원 행정지도 2024-02",
        "description": "수도권 변동금리 스트레스 DSR 가산금리 Phase2",
    },
    {
        "param_key": "stress_dsr.metropolitan.variable",
        "param_category": "dsr",
        "phase_label": "phase3",
        "param_value": {"rate": 1.50, "unit": "percentage_point", "apply_ratio": 1.0},
        "condition_json": {"region": "metropolitan", "rate_type": "variable"},
        "effective_from": PHASE3_DATE,
        "effective_to": None,
        "legal_basis": "금감원 행정지도 2025-07",
        "description": "수도권 변동금리 스트레스 DSR 가산금리 Phase3",
    },
    {
        "param_key": "stress_dsr.metropolitan.mixed_short",
        "param_category": "dsr",
        "phase_label": "phase2",
        "param_value": {"rate": 0.75, "unit": "percentage_point", "apply_ratio": 0.6},
        "condition_json": {"region": "metropolitan", "rate_type": "mixed_short"},
        "effective_from": PHASE2_DATE,
        "effective_to": PHASE3_DATE,
        "legal_basis": "금감원 행정지도 2024-02",
        "description": "수도권 혼합형(5년미만) 스트레스 DSR",
    },
    {
        "param_key": "stress_dsr.metropolitan.mixed_long",
        "param_category": "dsr",
        "phase_label": "phase2",
        "param_value": {"rate": 0.375, "unit": "percentage_point", "apply_ratio": 0.3},
        "condition_json": {"region": "metropolitan", "rate_type": "mixed_long"},
        "effective_from": PHASE2_DATE,
        "effective_to": PHASE3_DATE,
        "legal_basis": "금감원 행정지도 2024-02",
        "description": "수도권 혼합형(5년이상) 스트레스 DSR",
    },
    {
        "param_key": "stress_dsr.non_metropolitan.variable",
        "param_category": "dsr",
        "phase_label": "phase2",
        "param_value": {"rate": 1.50, "unit": "percentage_point", "apply_ratio": 1.0},
        "condition_json": {"region": "non_metropolitan", "rate_type": "variable"},
        "effective_from": PHASE2_DATE,
        "effective_to": PHASE3_DATE,
        "legal_basis": "금감원 행정지도 2024-02",
        "description": "비수도권 변동금리 스트레스 DSR 가산금리 Phase2",
    },
    {
        "param_key": "stress_dsr.non_metropolitan.variable",
        "param_category": "dsr",
        "phase_label": "phase3",
        "param_value": {"rate": 3.00, "unit": "percentage_point", "apply_ratio": 1.0},
        "condition_json": {"region": "non_metropolitan", "rate_type": "variable"},
        "effective_from": PHASE3_DATE,
        "effective_to": None,
        "legal_basis": "금감원 행정지도 2025-07",
        "description": "비수도권 변동금리 스트레스 DSR 가산금리 Phase3",
    },

    # ────────────────────────────────────────────────────────────
    # 2. LTV 한도 (은행업감독규정 §35의5)
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "ltv.general",
        "param_category": "ltv",
        "param_value": {"max_ratio": 70.0, "unit": "percent"},
        "condition_json": {"area_type": "general"},
        "effective_from": EPOCH,
        "effective_to": None,
        "legal_basis": "은행업감독규정 §35의5",
        "description": "일반 지역 LTV 한도",
    },
    {
        "param_key": "ltv.regulated",
        "param_category": "ltv",
        "param_value": {"max_ratio": 60.0, "unit": "percent"},
        "condition_json": {"area_type": "regulated"},
        "effective_from": EPOCH,
        "effective_to": None,
        "legal_basis": "은행업감독규정 §35의5",
        "description": "조정대상지역 LTV 한도",
    },
    {
        "param_key": "ltv.speculation_area",
        "param_category": "ltv",
        "param_value": {"max_ratio": 40.0, "unit": "percent", "multi_owner_deduction": 10.0},
        "condition_json": {"area_type": "speculation_area"},
        "effective_from": EPOCH,
        "effective_to": None,
        "legal_basis": "은행업감독규정 §35의5",
        "description": "투기과열지구 LTV 한도 (다주택자 -10%p)",
    },

    # ────────────────────────────────────────────────────────────
    # 3. DSR 한도 (은행업감독규정)
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "dsr.max_ratio",
        "param_category": "dsr",
        "param_value": {"max_ratio": 40.0, "unit": "percent"},
        "effective_from": EPOCH,
        "effective_to": None,
        "legal_basis": "은행업감독규정 §35의5",
        "description": "전체 가계대출 DSR 한도",
    },

    # ────────────────────────────────────────────────────────────
    # 4. 최고금리 (대부업법 §11)
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "rate.max_interest",
        "param_category": "rate",
        "param_value": {"max_rate": 20.0, "unit": "percent"},
        "effective_from": EPOCH,
        "effective_to": None,
        "legal_basis": "대부업법 §11",
        "description": "법정 최고금리",
    },

    # ────────────────────────────────────────────────────────────
    # 5. 신용대출 소득배수 한도
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "credit_loan.income_multiplier.employed",
        "param_category": "limit",
        "param_value": {"multiplier": 1.5, "unit": "times_annual_income"},
        "condition_json": {"employment_type": "employed"},
        "effective_from": EPOCH,
        "effective_to": None,
        "description": "직장인 신용대출 연소득 배수 한도",
    },
    {
        "param_key": "credit_loan.income_multiplier.self_employed",
        "param_category": "limit",
        "param_value": {"multiplier": 1.0, "unit": "times_annual_income"},
        "condition_json": {"employment_type": "self_employed"},
        "effective_from": EPOCH,
        "effective_to": None,
        "description": "개인사업자 신용대출 연소득 배수 한도",
    },

    # ────────────────────────────────────────────────────────────
    # 6. EQ Grade 혜택
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "eq_grade.benefit.EQ-S",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 2.0, "rate_adjustment": -0.5},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-S (Super: 공공기관/금융기관) 혜택",
    },
    {
        "param_key": "eq_grade.benefit.EQ-A",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 1.8, "rate_adjustment": -0.3},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-A (Large Corp/상장사) 혜택",
    },
    {
        "param_key": "eq_grade.benefit.EQ-B",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 1.5, "rate_adjustment": -0.2},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-B (우량 중견기업) 혜택",
    },
    {
        "param_key": "eq_grade.benefit.EQ-C",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 1.2, "rate_adjustment": 0.0},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-C (일반 중소기업) 혜택",
    },
    {
        "param_key": "eq_grade.benefit.EQ-D",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 1.0, "rate_adjustment": 0.2},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-D (취약 중소기업) 혜택",
    },
    {
        "param_key": "eq_grade.benefit.EQ-E",
        "param_category": "eq_grade",
        "param_value": {"limit_multiplier": 0.7, "rate_adjustment": 0.5},
        "effective_from": EPOCH, "effective_to": None,
        "description": "EQ-E (부실 위험 기업) 혜택",
    },

    # ────────────────────────────────────────────────────────────
    # 7. IRG PD 조정값
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "irg.pd_adjustment.L",
        "param_category": "irg",
        "param_value": {"adjustment": -0.10, "unit": "ratio"},
        "condition_json": {"irg_grade": "L"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "IRG Low - PD 10% 감면",
    },
    {
        "param_key": "irg.pd_adjustment.M",
        "param_category": "irg",
        "param_value": {"adjustment": 0.0, "unit": "ratio"},
        "condition_json": {"irg_grade": "M"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "IRG Medium - PD 조정 없음",
    },
    {
        "param_key": "irg.pd_adjustment.H",
        "param_category": "irg",
        "param_value": {"adjustment": 0.15, "unit": "ratio"},
        "condition_json": {"irg_grade": "H"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "IRG High - PD 15% 가산",
    },
    {
        "param_key": "irg.pd_adjustment.VH",
        "param_category": "irg",
        "param_value": {"adjustment": 0.30, "unit": "ratio"},
        "condition_json": {"irg_grade": "VH"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "IRG Very High - PD 30% 가산",
    },

    # ────────────────────────────────────────────────────────────
    # 8. 특수 세그먼트 혜택
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "segment.benefit.SEG-DR",
        "param_category": "segment",
        "param_value": {
            "guaranteed_eq_grade": "EQ-B",
            "limit_multiplier": 3.0,
            "rate_discount": -0.3,
            "description": "의사/치과의사/한의사 전용 혜택",
        },
        "condition_json": {"segment": "SEG-DR"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-DR 의료전문직 세그먼트",
    },
    {
        "param_key": "segment.benefit.SEG-JD",
        "param_category": "segment",
        "param_value": {
            "guaranteed_eq_grade": "EQ-B",
            "limit_multiplier": 2.5,
            "rate_discount": -0.2,
            "description": "변호사/법무사/회계사 전용 혜택",
        },
        "condition_json": {"segment": "SEG-JD"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-JD 법무/회계 전문직 세그먼트",
    },
    {
        "param_key": "segment.benefit.SEG-ART",
        "param_category": "segment",
        "param_value": {
            "income_smoothing_months": 12,
            "rate_discount": 0.0,
            "guarantee_link": True,
            "description": "예술인복지법 등록 예술인 전용 (소득 평활화)",
        },
        "condition_json": {"segment": "SEG-ART"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-ART 예술인 세그먼트 (소득변동성 완화)",
    },
    {
        "param_key": "segment.benefit.SEG-YTH",
        "param_category": "segment",
        "param_value": {
            "rate_discount": -0.5,
            "limit_multiplier": 1.0,
            "age_min": 19,
            "age_max": 34,
            "description": "청년(만 19-34세) 금리 우대",
        },
        "condition_json": {"segment": "SEG-YTH"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-YTH 청년 세그먼트",
    },
    {
        "param_key": "segment.benefit.SEG-MIL",
        "param_category": "segment",
        "param_value": {
            "guaranteed_eq_grade": "EQ-S",
            "limit_multiplier": 2.0,
            "rate_discount": -0.5,
            "description": "현역군인/직업군인/공무원 전용",
        },
        "condition_json": {"segment": "SEG-MIL"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-MIL 군인/공무원 세그먼트",
    },
    {
        "param_key": "segment.benefit.SEG-MOU",
        "param_category": "segment",
        "param_value": {
            "rate_discount": -0.3,
            "limit_multiplier": 1.5,
            "description": "협약기업(MOU) 근로자 기본 혜택 (MOU별 추가 협의)",
        },
        "condition_json": {"segment": "SEG-MOU"},
        "effective_from": EPOCH, "effective_to": None,
        "description": "SEG-MOU 협약기업 세그먼트 기본",
    },

    # ────────────────────────────────────────────────────────────
    # 9. CCF (신용전환계수)
    # ────────────────────────────────────────────────────────────
    {
        "param_key": "ccf.revolving.default",
        "param_category": "ccf",
        "param_value": {"ccf": 0.50, "unit": "ratio"},
        "condition_json": {"product_type": "revolving"},
        "effective_from": EPOCH, "effective_to": None,
        "legal_basis": "바젤III §90",
        "description": "회전한도대출(마이너스통장) 기본 CCF 50%",
    },
]


async def seed_regulation_params(db) -> int:
    """
    regulation_params 테이블에 초기 데이터 입력.
    이미 존재하는 param_key + effective_from 조합은 skip.

    Returns:
        삽입된 레코드 수
    """
    import uuid

    from sqlalchemy import and_, select

    from app.db.schemas.regulation_params import RegulationParam

    inserted = 0
    for item in SEED_PARAMS:
        # 중복 체크
        stmt = select(RegulationParam).where(
            and_(
                RegulationParam.param_key == item["param_key"],
                RegulationParam.effective_from == item["effective_from"],
            )
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            continue

        param = RegulationParam(
            id=uuid.uuid4(),
            param_key=item["param_key"],
            param_category=item["param_category"],
            phase_label=item.get("phase_label"),
            param_value=item["param_value"],
            condition_json=item.get("condition_json"),
            effective_from=item["effective_from"],
            effective_to=item.get("effective_to"),
            legal_basis=item.get("legal_basis"),
            description=item.get("description"),
            is_active=True,
            created_by="system_seed",
            approved_by="system_seed",
        )
        db.add(param)
        inserted += 1

    await db.commit()
    logger.info(f"regulation_params 시드 완료: {inserted}건 삽입")
    return inserted
