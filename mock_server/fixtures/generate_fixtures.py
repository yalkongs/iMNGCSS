"""
시나리오별 고객 픽스처 데이터 생성기
=====================================
30개 사전 정의 고객 시나리오를 JSON으로 생성.
Mock Server가 resident_hash로 이 데이터를 우선 반환.

시나리오 구성:
  PRIME-001~010 : 자동 승인 (우량)
  MANUAL-001~007: 수동 심사
  REJECT-001~010: 자동 거절
  SPECIAL-001~003: 특수 케이스

실행: python mock_server/fixtures/generate_fixtures.py
"""
import json
import os
from datetime import datetime

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "scenario_customers.json")


# ── 헬퍼 함수 ────────────────────────────────────────────────────────────────

def eq_info(grade: str) -> dict:
    TABLE = {
        "EQ-S": {"limit_multiplier": 2.0, "rate_adjustment": -0.5},
        "EQ-A": {"limit_multiplier": 1.8, "rate_adjustment": -0.3},
        "EQ-B": {"limit_multiplier": 1.5, "rate_adjustment": -0.2},
        "EQ-C": {"limit_multiplier": 1.2, "rate_adjustment":  0.0},
        "EQ-D": {"limit_multiplier": 1.0, "rate_adjustment":  0.2},
        "EQ-E": {"limit_multiplier": 0.7, "rate_adjustment":  0.5},
    }
    return TABLE[grade]


def nice_score_to_grade(score: int) -> int:
    if score >= 900: return 1
    elif score >= 870: return 2
    elif score >= 840: return 3
    elif score >= 805: return 4
    elif score >= 750: return 5
    elif score >= 665: return 6
    elif score >= 600: return 7
    elif score >= 515: return 8
    elif score >= 445: return 9
    else: return 10


def kcb_grade(score: int) -> str:
    if score >= 942: return "1"
    elif score >= 891: return "2"
    elif score >= 832: return "3"
    elif score >= 768: return "4"
    elif score >= 698: return "5"
    elif score >= 630: return "6"
    else: return "7"


def make_customer(
    scenario_id: str,
    scenario_name: str,
    category: str,          # auto_approved / manual_review / rejected / special
    expected_decision: str, # approved / manual_review / rejected
    resident_hash: str,
    employer_hash: str,
    # 고객 기본 정보
    age: int,
    employment_type: str,   # employed / self_employed / profession / military / unemployed
    # CB 정보
    nice_score: int,
    worst_delinquency_status: int = 0,  # 0=정상, 1=1개월, 2=2개월+, 3=3개월+
    delinquency_days: int = 0,
    delinquency_amount: float = 0.0,
    loan_count: int = 0,
    total_balance: float = 0.0,
    public_record_count: int = 0,
    inquiry_count_6m: int = 1,
    # 소득 정보
    employment_income: float = 0.0,
    business_income: float = 0.0,
    other_income: float = 0.0,
    employer_name: str = None,
    subscription_months: int = 60,
    # 기업 신용
    eq_grade: str = "EQ-C",
    mou_code: str = None,
    mou_rate_discount: float = 0.0,
    company_size: str = "mid",
    years_in_business: int = 5,
    # 자산
    total_deposit: float = 5_000_000,
    total_savings: float = 10_000_000,
    total_investment: float = 0.0,
    monthly_card_spend: float = 1_500_000,
    regular_transfer: float = 500_000,
    # 전문직
    license_type: str = None,
    segment_code: str = None,
    specialty: str = None,
    license_date: str = "2015-03-15",
    # 메타
    description: str = "",
    business_hash: str = None,
    # 대안 데이터
    telecom_no_delinquency: int = 1,
    health_insurance_paid_months: int = 12,
    national_pension_paid_months: int = 24,
    # 예술인복지재단
    art_fund_registered: bool = False,
    art_fund_registration_date: str = None,
    art_fund_field: str = None,
) -> dict:
    total_income = employment_income + business_income + other_income
    monthly_income = total_income / 12
    monthly_payment = round(total_balance / 120) if total_balance > 0 else 0.0
    kcb_score = max(300, min(1000, nice_score - 10))

    subscriber_type = (
        "employee"
        if employment_type in ("employed", "military", "profession")
        else "regional"
    )
    monthly_premium = round(monthly_income * 0.0709 / 2)
    eq = eq_info(eq_grade)

    # 카드한도 및 잔액
    cc_limit = 3_000_000 if nice_score >= 700 else 500_000
    cc_balance = 800_000 if nice_score >= 700 else 150_000

    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "category": category,
        "expected_decision": expected_decision,
        "description": description,
        "resident_hash": resident_hash,
        "employer_hash": employer_hash,
        "business_hash": business_hash or f"biz_{resident_hash}",
        "profile": {
            "age": age,
            "employment_type": employment_type,
            "segment_code": segment_code or "",
            "nice_score": nice_score,
            "total_income_annual": total_income,
            "worst_delinquency_status": worst_delinquency_status,
        },
        # ── NICE CB 응답 ────────────────────────────────────────────────────
        "nice_cb": {
            "inquiry_id": f"NICE-{resident_hash[:16]}-FIX",
            "resident_hash": resident_hash,
            "score": nice_score,
            "grade": nice_score_to_grade(nice_score),
            "score_date": "2025-01-15",
            "delinquency": {
                "has_delinquency": delinquency_days > 0,
                "max_days_overdue": delinquency_days,
                "delinquency_amount": delinquency_amount,
                "last_delinquency_date": "2024-08-01" if delinquency_days > 0 else None,
            },
            "loans": {
                "total_loan_count": loan_count,
                "total_balance": total_balance,
                "monthly_payment": monthly_payment,
                "credit_card_limit": cc_limit,
                "credit_card_balance": cc_balance,
            },
            "public_record_count": public_record_count,
            "inquiry_count_6m": inquiry_count_6m,
            "worst_delinquency_status": worst_delinquency_status,
            "data_source": "NICE_FIXTURE",
        },
        # ── KCB CB 응답 ─────────────────────────────────────────────────────
        "kcb_cb": {
            "inquiry_id": f"KCB-{resident_hash[:16]}-FIX",
            "resident_hash": resident_hash,
            "kcb_score": kcb_score,
            "kcb_grade": kcb_grade(kcb_score),
            "overdue_flag": delinquency_days > 0,
            "total_debt": total_balance,
            "monthly_obligation": monthly_payment,
            "data_source": "KCB_FIXTURE",
        },
        # ── 국세청 소득 응답 ────────────────────────────────────────────────
        "nts_income": {
            "resident_hash": resident_hash,
            "tax_year": 2024,
            "employment_income": employment_income,
            "business_income": business_income,
            "other_income": other_income,
            "total_income": total_income,
            "income_verified": total_income > 0,
            "employer_name": employer_name,
            "data_source": "NTS_FIXTURE",
        },
        # ── 건강보험공단 응답 ───────────────────────────────────────────────
        "nhis": {
            "resident_hash": resident_hash,
            "subscriber_type": subscriber_type,
            "employer_name": (employer_name[:1] + "*" * (len(employer_name) - 1)) if employer_name else None,
            "monthly_premium": monthly_premium,
            "income_level": total_income,
            "subscription_months": subscription_months,
            "income_verified": True,
            "data_source": "NHIS_FIXTURE",
        },
        # ── 기업신용정보 응답 ───────────────────────────────────────────────
        "biz_credit": {
            "employer_registration_hash": employer_hash,
            "eq_grade": eq_grade,
            "limit_multiplier": eq["limit_multiplier"],
            "rate_adjustment": eq["rate_adjustment"],
            "mou_code": mou_code,
            "mou_rate_discount": mou_rate_discount,
            "company_size": company_size,
            "years_in_business": years_in_business,
            "data_source": "BIZ_FIXTURE",
        },
        # ── 마이데이터 응답 ─────────────────────────────────────────────────
        "mydata": {
            "total_deposit": total_deposit,
            "total_savings": total_savings,
            "total_investment": total_investment,
            "total_insurance_premium": 150_000,
            "monthly_card_spend_3m_avg": monthly_card_spend,
            "regular_transfer_monthly": regular_transfer,
            "data_source": "MYDATA_FIXTURE",
        },
        # ── 전문직 면허 응답 ────────────────────────────────────────────────
        "profession": {
            "resident_hash": resident_hash,
            "license_type": license_type or "none",
            "is_valid": license_type is not None,
            "segment_code": segment_code if license_type else None,
            "license_date": license_date if license_type else None,
            "specialty": specialty,
            "registration_status": "active" if license_type else "not_found",
            "data_source": "PROFESSION_FIXTURE",
        },
        # ── 대안 데이터 (scoring_engine 직접 사용) ─────────────────────────
        "alternative_data": {
            "telecom_no_delinquency": telecom_no_delinquency,
            "health_insurance_paid_months_12m": health_insurance_paid_months,
            "national_pension_paid_months_24m": national_pension_paid_months,
            "art_fund_registered": art_fund_registered,
            "art_fund_registration_date": art_fund_registration_date,
            "art_fund_field": art_fund_field,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# 30개 시나리오 정의
# ══════════════════════════════════════════════════════════════════════════════

def build_all_customers() -> list[dict]:
    customers = []

    # ── PRIME: 자동 승인 (10개) ──────────────────────────────────────────────

    customers.append(make_customer(
        scenario_id="PRIME-001",
        scenario_name="우량 대기업 직장인",
        category="auto_approved",
        expected_decision="approved",
        description="CB 850, 소득 8000만, 대출 1건, DSR 22% — 전형적 우량 직장인",
        resident_hash="kcs_demo_prime_001",
        employer_hash="kcs_emp_prime_001",
        age=38, employment_type="employed",
        nice_score=850,
        loan_count=1, total_balance=20_000_000,
        employment_income=80_000_000,
        employer_name="삼성전자주식회사",
        subscription_months=96,
        eq_grade="EQ-B", company_size="large", years_in_business=30,
        total_deposit=15_000_000, total_savings=30_000_000, total_investment=20_000_000,
        monthly_card_spend=2_500_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-002",
        scenario_name="내과 의사 (SEG-DR)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 820, 소득 1.8억, SEG-DR 혜택 — EQ-B 보장, 한도 3.0x, -0.3%p",
        resident_hash="kcs_demo_prime_002",
        employer_hash="kcs_emp_prime_002",
        age=42, employment_type="profession",
        nice_score=820,
        loan_count=1, total_balance=30_000_000,
        employment_income=180_000_000,
        employer_name="서울대학교병원",
        subscription_months=120,
        eq_grade="EQ-A", company_size="large", years_in_business=20,
        license_type="doctor", segment_code="SEG-DR", specialty="내과",
        total_deposit=50_000_000, total_savings=80_000_000, total_investment=50_000_000,
        monthly_card_spend=5_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-003",
        scenario_name="직업군인 중령 (SEG-MIL)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 750, 소득 6500만, SEG-MIL — EQ-S 보장, 한도 2.0x, -0.5%p",
        resident_hash="kcs_demo_prime_003",
        employer_hash="kcs_emp_prime_003",
        age=44, employment_type="military",
        nice_score=750,
        loan_count=0, total_balance=0,
        employment_income=65_000_000,
        employer_name="대한민국육군",
        subscription_months=180,
        eq_grade="EQ-S", segment_code="SEG-MIL",
        company_size="large", years_in_business=50,
        total_deposit=20_000_000, total_savings=40_000_000,
        monthly_card_spend=2_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-004",
        scenario_name="청년 공기업 직원 (SEG-YTH)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 760, 소득 5000만, 만 29세 — SEG-YTH 금리 -0.5%p",
        resident_hash="kcs_demo_prime_004",
        employer_hash="kcs_emp_prime_004",
        age=29, employment_type="employed",
        nice_score=760,
        loan_count=1, total_balance=15_000_000,
        employment_income=50_000_000,
        employer_name="한국전력공사",
        subscription_months=36,
        eq_grade="EQ-C", segment_code="SEG-YTH",
        company_size="large", years_in_business=80,
        total_deposit=8_000_000, total_savings=12_000_000,
        monthly_card_spend=1_200_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-005",
        scenario_name="기업법 변호사 (SEG-JD)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 800, 소득 1.2억, SEG-JD — EQ-B 보장, 한도 2.5x, -0.2%p",
        resident_hash="kcs_demo_prime_005",
        employer_hash="kcs_emp_prime_005",
        age=45, employment_type="profession",
        nice_score=800,
        loan_count=0, total_balance=0,
        employment_income=120_000_000,
        employer_name="김앤장법률사무소",
        subscription_months=120,
        eq_grade="EQ-B", company_size="large", years_in_business=40,
        license_type="lawyer", segment_code="SEG-JD", specialty="기업법",
        total_deposit=40_000_000, total_savings=60_000_000, total_investment=30_000_000,
        monthly_card_spend=4_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-006",
        scenario_name="삼성전자 협약기업 직원 (SEG-MOU)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 720, 소득 6000만, SEG-MOU-SEC001 — EQ-B, -0.3%p 우대",
        resident_hash="kcs_demo_prime_006",
        employer_hash="kcs_emp_mou_sec001",
        age=36, employment_type="employed",
        nice_score=720,
        loan_count=1, total_balance=25_000_000,
        employment_income=60_000_000,
        employer_name="삼성전자주식회사",
        subscription_months=60,
        eq_grade="EQ-B", mou_code="MOU-SEC001", mou_rate_discount=-0.3,
        company_size="large", years_in_business=30,
        total_deposit=10_000_000, total_savings=20_000_000,
        monthly_card_spend=1_800_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-007",
        scenario_name="한식당 10년 자영업자",
        category="auto_approved",
        expected_decision="approved",
        description="CB 740, 사업소득 1억, 사업기간 10년 — 안정적 자영업 우량",
        resident_hash="kcs_demo_prime_007",
        employer_hash="kcs_emp_prime_007",
        business_hash="kcs_biz_prime_007",
        age=48, employment_type="self_employed",
        nice_score=740,
        loan_count=2, total_balance=50_000_000,
        business_income=100_000_000,
        subscription_months=120,
        eq_grade="EQ-C", company_size="micro", years_in_business=10,
        total_deposit=20_000_000, total_savings=30_000_000,
        monthly_card_spend=2_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-008",
        scenario_name="주담대 일반지역 우량 (LTV 62%)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 790, 소득 9000만, 일반지역 LTV 62% (한도 70%) — 주담대 승인",
        resident_hash="kcs_demo_prime_008",
        employer_hash="kcs_emp_prime_008",
        age=42, employment_type="employed",
        nice_score=790,
        loan_count=0, total_balance=0,
        employment_income=90_000_000,
        employer_name="현대자동차주식회사",
        subscription_months=120,
        eq_grade="EQ-B", company_size="large", years_in_business=60,
        total_deposit=30_000_000, total_savings=50_000_000, total_investment=20_000_000,
        monthly_card_spend=3_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-009",
        scenario_name="치과의사 (SEG-DR)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 830, 소득 2억, SEG-DR — 치과 전문의, EQ-A",
        resident_hash="kcs_demo_prime_009",
        employer_hash="kcs_emp_prime_009",
        age=38, employment_type="profession",
        nice_score=830,
        loan_count=0, total_balance=0,
        employment_income=200_000_000,
        employer_name="서울치과의원",
        subscription_months=96,
        eq_grade="EQ-A", company_size="small", years_in_business=8,
        license_type="dentist", segment_code="SEG-DR", specialty="보존과",
        total_deposit=80_000_000, total_savings=100_000_000, total_investment=50_000_000,
        monthly_card_spend=6_000_000,
    ))

    customers.append(make_customer(
        scenario_id="PRIME-010",
        scenario_name="공인회계사 (SEG-JD)",
        category="auto_approved",
        expected_decision="approved",
        description="CB 790, 소득 1.1억, SEG-JD — 회계법인 소속, EQ-B",
        resident_hash="kcs_demo_prime_010",
        employer_hash="kcs_emp_prime_010",
        age=40, employment_type="profession",
        nice_score=790,
        loan_count=1, total_balance=20_000_000,
        employment_income=110_000_000,
        employer_name="삼일회계법인",
        subscription_months=144,
        eq_grade="EQ-B", company_size="large", years_in_business=30,
        license_type="cpa", segment_code="SEG-JD", specialty="세무회계",
        total_deposit=30_000_000, total_savings=50_000_000, total_investment=20_000_000,
        monthly_card_spend=3_500_000,
    ))

    # ── MANUAL: 수동 심사 (7개) ──────────────────────────────────────────────

    customers.append(make_customer(
        scenario_id="MANUAL-001",
        scenario_name="경계 점수 직장인 (DSR 38%)",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 640, 소득 4500만, DSR 38% — 승인 기준은 넘지만 낮은 점수",
        resident_hash="kcs_demo_manual_001",
        employer_hash="kcs_emp_manual_001",
        age=33, employment_type="employed",
        nice_score=640,
        loan_count=2, total_balance=60_000_000,
        employment_income=45_000_000,
        employer_name="중소기업중앙회",
        subscription_months=48,
        eq_grade="EQ-C", company_size="small", years_in_business=12,
        total_deposit=3_000_000, total_savings=5_000_000,
        monthly_card_spend=1_200_000,
        inquiry_count_6m=3,
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-002",
        scenario_name="단기 재직 5개월",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 700, 소득 4000만, 재직 5개월 — 재직기간 부족으로 수동심사",
        resident_hash="kcs_demo_manual_002",
        employer_hash="kcs_emp_manual_002",
        age=28, employment_type="employed",
        nice_score=700,
        loan_count=1, total_balance=10_000_000,
        employment_income=40_000_000,
        employer_name="네이버주식회사",
        subscription_months=5,           # ← 단기 재직
        eq_grade="EQ-B", company_size="large", years_in_business=25,
        total_deposit=5_000_000, total_savings=8_000_000,
        monthly_card_spend=1_500_000,
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-003",
        scenario_name="프리랜서 소득 불규칙",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 680, 사업소득 4200만 (프리랜서) — 소득 안정성 검증 필요",
        resident_hash="kcs_demo_manual_003",
        employer_hash="kcs_emp_manual_003",
        age=35, employment_type="self_employed",
        nice_score=680,
        loan_count=1, total_balance=15_000_000,
        business_income=42_000_000,
        subscription_months=36,
        eq_grade="EQ-D", company_size="micro", years_in_business=3,
        total_deposit=4_000_000, total_savings=6_000_000,
        monthly_card_spend=1_000_000,
        national_pension_paid_months=18,   # 납부 불규칙
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-004",
        scenario_name="다중 대출 경계 (DSR 35%)",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 660, 소득 5500만, 대출 3건 DSR 35% — 다중채무 리스크",
        resident_hash="kcs_demo_manual_004",
        employer_hash="kcs_emp_manual_004",
        age=40, employment_type="employed",
        nice_score=660,
        loan_count=3, total_balance=80_000_000,
        employment_income=55_000_000,
        employer_name="롯데백화점",
        subscription_months=84,
        eq_grade="EQ-C", company_size="large", years_in_business=80,
        total_deposit=2_000_000, total_savings=4_000_000,
        monthly_card_spend=1_500_000,
        inquiry_count_6m=4,
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-005",
        scenario_name="연체 해결 후 회복기 (1년 경과)",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 580, 1년 전 연체 해결 완료 — 점수 낮지만 연체 현재 없음",
        resident_hash="kcs_demo_manual_005",
        employer_hash="kcs_emp_manual_005",
        age=37, employment_type="employed",
        nice_score=580,
        worst_delinquency_status=0,       # 현재 연체 없음
        delinquency_days=0,               # 해결 완료
        loan_count=1, total_balance=20_000_000,
        employment_income=48_000_000,
        employer_name="GS리테일",
        subscription_months=72,
        eq_grade="EQ-D", company_size="large", years_in_business=30,
        total_deposit=2_000_000, total_savings=3_000_000,
        monthly_card_spend=800_000,
        health_insurance_paid_months=11,
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-006",
        scenario_name="개인사업자 창업 초기 (8개월)",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 690, 사업 8개월 — 신규 창업자, 소득 검증 부족",
        resident_hash="kcs_demo_manual_006",
        employer_hash="kcs_emp_manual_006",
        business_hash="kcs_biz_manual_006",
        age=31, employment_type="self_employed",
        nice_score=690,
        loan_count=0, total_balance=0,
        business_income=36_000_000,       # 8개월 기준 환산
        subscription_months=8,            # 사업 8개월
        eq_grade="EQ-D", company_size="micro", years_in_business=1,
        total_deposit=5_000_000, total_savings=2_000_000,
        monthly_card_spend=1_200_000,
        national_pension_paid_months=8,
    ))

    customers.append(make_customer(
        scenario_id="MANUAL-007",
        scenario_name="고령 자영업자 (58세, 사업 15년)",
        category="manual_review",
        expected_decision="manual_review",
        description="CB 650, 58세, 사업 15년 — 고령 자영업자, 안정적이나 수동심사",
        resident_hash="kcs_demo_manual_007",
        employer_hash="kcs_emp_manual_007",
        business_hash="kcs_biz_manual_007",
        age=58, employment_type="self_employed",
        nice_score=650,
        loan_count=2, total_balance=40_000_000,
        business_income=60_000_000,
        subscription_months=180,
        eq_grade="EQ-C", company_size="small", years_in_business=15,
        total_deposit=8_000_000, total_savings=15_000_000,
        monthly_card_spend=1_800_000,
    ))

    # ── REJECT: 자동 거절 (10개) ─────────────────────────────────────────────

    customers.append(make_customer(
        scenario_id="REJECT-001",
        scenario_name="DSR 55% 초과 (기존부채 과다)",
        category="rejected",
        expected_decision="rejected",
        description="CB 720, 소득 3000만, 기존부채 1.2억 — DSR 55%로 자동거절",
        resident_hash="kcs_demo_reject_001",
        employer_hash="kcs_emp_reject_001",
        age=36, employment_type="employed",
        nice_score=720,
        loan_count=3, total_balance=120_000_000,
        employment_income=30_000_000,
        employer_name="중소제조업체",
        subscription_months=48,
        eq_grade="EQ-D", company_size="small", years_in_business=8,
        total_deposit=1_000_000, total_savings=0,
        monthly_card_spend=1_000_000,
        inquiry_count_6m=5,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-002",
        scenario_name="현재 연체 90일 진행중",
        category="rejected",
        expected_decision="rejected",
        description="CB 480, 연체 90일 5백만원 — 연체 중 하드 거절",
        resident_hash="kcs_demo_reject_002",
        employer_hash="kcs_emp_reject_002",
        age=33, employment_type="employed",
        nice_score=480,
        worst_delinquency_status=3,
        delinquency_days=90,
        delinquency_amount=5_000_000,
        loan_count=2, total_balance=40_000_000,
        employment_income=42_000_000,
        employer_name="서비스업체",
        subscription_months=36,
        eq_grade="EQ-E", company_size="micro", years_in_business=3,
        total_deposit=500_000, total_savings=0,
        monthly_card_spend=800_000,
        inquiry_count_6m=6,
        telecom_no_delinquency=0,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-003",
        scenario_name="저신용 다중채무 (CB 350)",
        category="rejected",
        expected_decision="rejected",
        description="CB 350, 대출 5건, 공공기록 1건 — 최저 신용, 하드 거절",
        resident_hash="kcs_demo_reject_003",
        employer_hash="kcs_emp_reject_003",
        age=44, employment_type="employed",
        nice_score=350,
        worst_delinquency_status=3,
        delinquency_days=180,
        delinquency_amount=15_000_000,
        loan_count=5, total_balance=180_000_000,
        public_record_count=1,
        employment_income=35_000_000,
        employer_name="일용직",
        subscription_months=24,
        eq_grade="EQ-E", company_size="micro", years_in_business=1,
        total_deposit=0, total_savings=0,
        monthly_card_spend=300_000,
        inquiry_count_6m=8,
        telecom_no_delinquency=0,
        health_insurance_paid_months=6,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-004",
        scenario_name="주담대 조정대상구역 LTV 63% 초과",
        category="rejected",
        expected_decision="rejected",
        description="CB 750, 소득 7000만, LTV 63% (한도 60%) — 조정대상구역 초과 거절",
        resident_hash="kcs_demo_reject_004",
        employer_hash="kcs_emp_reject_004",
        age=40, employment_type="employed",
        nice_score=750,
        loan_count=0, total_balance=0,
        employment_income=70_000_000,
        employer_name="중견기업",
        subscription_months=96,
        eq_grade="EQ-C", company_size="mid", years_in_business=20,
        total_deposit=10_000_000, total_savings=20_000_000,
        monthly_card_spend=2_000_000,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-005",
        scenario_name="주담대 투기과열구역 LTV 42% 초과",
        category="rejected",
        expected_decision="rejected",
        description="CB 800, 소득 8000만, LTV 42% (한도 40%) — 투기과열구역 초과 거절",
        resident_hash="kcs_demo_reject_005",
        employer_hash="kcs_emp_reject_005",
        age=45, employment_type="employed",
        nice_score=800,
        loan_count=0, total_balance=0,
        employment_income=80_000_000,
        employer_name="대기업",
        subscription_months=120,
        eq_grade="EQ-B", company_size="large", years_in_business=50,
        total_deposit=30_000_000, total_savings=50_000_000,
        monthly_card_spend=3_000_000,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-006",
        scenario_name="무직 소득 없음",
        category="rejected",
        expected_decision="rejected",
        description="CB 600, 소득 0 — 무직, 소득 미검증으로 자동 거절",
        resident_hash="kcs_demo_reject_006",
        employer_hash="kcs_emp_reject_006",
        age=29, employment_type="unemployed",
        nice_score=600,
        loan_count=0, total_balance=0,
        employment_income=0,
        subscription_months=0,
        eq_grade="EQ-D", company_size="micro", years_in_business=0,
        total_deposit=2_000_000, total_savings=0,
        monthly_card_spend=300_000,
        health_insurance_paid_months=0,
        national_pension_paid_months=0,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-007",
        scenario_name="연체 2개월 진행중 (worst_status=2)",
        category="rejected",
        expected_decision="rejected",
        description="CB 520, 연체 65일 — worst_delinquency_status=2 하드 거절",
        resident_hash="kcs_demo_reject_007",
        employer_hash="kcs_emp_reject_007",
        age=39, employment_type="employed",
        nice_score=520,
        worst_delinquency_status=2,
        delinquency_days=65,
        delinquency_amount=3_000_000,
        loan_count=3, total_balance=70_000_000,
        employment_income=40_000_000,
        employer_name="소규모 사업장",
        subscription_months=36,
        eq_grade="EQ-E", company_size="micro", years_in_business=2,
        total_deposit=300_000, total_savings=0,
        monthly_card_spend=600_000,
        telecom_no_delinquency=0,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-008",
        scenario_name="고위험 다중연체 (CB 430)",
        category="rejected",
        expected_decision="rejected",
        description="CB 430, 연체 150일, 대출 4건 — 심각한 연체, 자동 거절",
        resident_hash="kcs_demo_reject_008",
        employer_hash="kcs_emp_reject_008",
        age=42, employment_type="employed",
        nice_score=430,
        worst_delinquency_status=3,
        delinquency_days=150,
        delinquency_amount=8_000_000,
        loan_count=4, total_balance=100_000_000,
        public_record_count=1,
        employment_income=35_000_000,
        employer_name="임시직",
        subscription_months=12,
        eq_grade="EQ-E", company_size="micro", years_in_business=1,
        total_deposit=0, total_savings=0,
        monthly_card_spend=200_000,
        inquiry_count_6m=7,
        telecom_no_delinquency=0,
        health_insurance_paid_months=4,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-009",
        scenario_name="파산 이력 (공공기록 2건, CB 310)",
        category="rejected",
        expected_decision="rejected",
        description="CB 310, 공공기록(파산/압류) 2건 — 최저신용, 즉시 거절",
        resident_hash="kcs_demo_reject_009",
        employer_hash="kcs_emp_reject_009",
        age=50, employment_type="employed",
        nice_score=310,
        worst_delinquency_status=3,
        delinquency_days=365,
        delinquency_amount=20_000_000,
        loan_count=1, total_balance=10_000_000,
        public_record_count=2,
        employment_income=32_000_000,
        employer_name="일용직",
        subscription_months=24,
        eq_grade="EQ-E", company_size="micro", years_in_business=0,
        total_deposit=0, total_savings=0,
        monthly_card_spend=100_000,
        inquiry_count_6m=8,
        telecom_no_delinquency=0,
        health_insurance_paid_months=3,
        national_pension_paid_months=6,
    ))

    customers.append(make_customer(
        scenario_id="REJECT-010",
        scenario_name="극저소득 알바 (연 700만)",
        category="rejected",
        expected_decision="rejected",
        description="CB 680, 소득 700만 — 최소 소득 1200만 미충족, 자동 거절",
        resident_hash="kcs_demo_reject_010",
        employer_hash="kcs_emp_reject_010",
        age=22, employment_type="employed",
        nice_score=680,
        loan_count=0, total_balance=0,
        employment_income=7_000_000,      # < 12_000_000 최소 소득
        other_income=0,
        employer_name="편의점알바",
        subscription_months=6,
        eq_grade="EQ-D", company_size="micro", years_in_business=1,
        total_deposit=500_000, total_savings=0,
        monthly_card_spend=200_000,
        national_pension_paid_months=6,
    ))

    # ── SPECIAL: 특수 케이스 (3개) ───────────────────────────────────────────

    customers.append(make_customer(
        scenario_id="SPECIAL-001",
        scenario_name="예술인복지재단 등록 예술가 (SEG-ART)",
        category="special",
        expected_decision="manual_review",
        description="CB 620, 사업소득 2400만 (불규칙) — SEG-ART 12개월 소득 평활화",
        resident_hash="kcs_demo_special_001",
        employer_hash="kcs_emp_special_001",
        age=32, employment_type="self_employed",
        nice_score=620,
        loan_count=0, total_balance=0,
        business_income=24_000_000,       # 연환산, 실제 불규칙
        other_income=3_000_000,
        subscription_months=36,
        eq_grade="EQ-D", company_size="micro", years_in_business=4,
        license_type="artist", segment_code="SEG-ART", specialty="시각예술",
        license_date="2019-06-01",
        total_deposit=1_500_000, total_savings=2_000_000,
        monthly_card_spend=600_000,
        national_pension_paid_months=18,
        art_fund_registered=True,
        art_fund_registration_date="2020-03-01",
        art_fund_field="시각예술",
    ))

    customers.append(make_customer(
        scenario_id="SPECIAL-002",
        scenario_name="사회초년생 소액론 (만 24세)",
        category="special",
        expected_decision="manual_review",
        description="CB 580, 소득 2600만, 만 24세 — 소액론 신청, 신용 이력 짧음",
        resident_hash="kcs_demo_special_002",
        employer_hash="kcs_emp_special_002",
        age=24, employment_type="employed",
        nice_score=580,
        loan_count=0, total_balance=0,
        employment_income=26_000_000,
        employer_name="스타트업",
        subscription_months=8,
        eq_grade="EQ-C", company_size="small", years_in_business=3,
        total_deposit=800_000, total_savings=500_000,
        monthly_card_spend=500_000,
        national_pension_paid_months=8,
    ))

    customers.append(make_customer(
        scenario_id="SPECIAL-003",
        scenario_name="주담대 투기과열구역 우량 (LTV 38%)",
        category="special",
        expected_decision="approved",
        description="CB 830, 소득 1.2억, 투기과열 LTV 38% (한도 40% 이내) — 승인",
        resident_hash="kcs_demo_special_003",
        employer_hash="kcs_emp_special_003",
        age=45, employment_type="employed",
        nice_score=830,
        loan_count=0, total_balance=0,
        employment_income=120_000_000,
        employer_name="외국계금융사",
        subscription_months=144,
        eq_grade="EQ-A", company_size="large", years_in_business=50,
        total_deposit=50_000_000, total_savings=80_000_000, total_investment=30_000_000,
        monthly_card_spend=5_000_000,
    ))

    return customers


# ══════════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    customers = build_all_customers()

    output = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "total_scenarios": len(customers),
        "categories": {
            "auto_approved": sum(1 for c in customers if c["category"] == "auto_approved"),
            "manual_review": sum(1 for c in customers if c["category"] == "manual_review"),
            "rejected":      sum(1 for c in customers if c["category"] == "rejected"),
            "special":       sum(1 for c in customers if c["category"] == "special"),
        },
        "lookup": {
            "by_resident_hash": {c["resident_hash"]: c["scenario_id"] for c in customers},
            "by_employer_hash":  {c["employer_hash"]:  c["scenario_id"] for c in customers},
        },
        "customers": customers,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✓ 픽스처 생성 완료: {OUTPUT_PATH}")
    print(f"  총 {len(customers)}개 시나리오")
    for cat, cnt in output["categories"].items():
        print(f"  {cat}: {cnt}개")
    print("\n시나리오 목록:")
    for c in customers:
        print(f"  [{c['scenario_id']}] {c['scenario_name']}")
        print(f"         hash={c['resident_hash']}, 예상={c['expected_decision']}")
