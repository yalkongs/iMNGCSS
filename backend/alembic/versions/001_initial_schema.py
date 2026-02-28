"""Initial schema v1.1

KCS 전체 DB 스키마 초기 생성:
  - applicants (신청인 정보, 개인/개인사업자, 특수 세그먼트)
  - loan_applications (대출 신청, 스트레스 DSR, Shadow 모델)
  - credit_scores (평가 결과, 바젤III IRB, RAROC)
  - regulation_params (BRMS 규제 파라미터 관리)
  - eq_grade_master (EQ Grade 마스터)
  - irg_master (산업 리스크 등급)
  - model_versions (ML 모델 버전 관리)
  - audit_logs (감사 로그, 신용정보법 5년 보존)

Revision ID: 001
Revises:
Create Date: 2026-02-28 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. applicants ──────────────────────────────────────────────────────
    op.create_table(
        "applicants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("applicant_type", sa.String(20), nullable=False, server_default="individual",
                  comment="individual(개인) | self_employed(개인사업자)"),
        # 개인정보 가명처리
        sa.Column("resident_registration_hash", sa.String(64), nullable=False, unique=True,
                  comment="주민번호 HMAC-SHA256 해시 (Vault KMS 키 관리)"),
        sa.Column("name_masked", sa.String(10), comment="가명처리된 성명 (예: 홍*동)"),
        # 인구통계
        sa.Column("age", sa.Integer),
        sa.Column("age_band", sa.String(10), comment="20s/30s/40s/50s/60+"),
        sa.Column("employment_type", sa.String(20),
                  comment="employed/self_employed/unemployed/retired/student"),
        sa.Column("employment_duration_months", sa.Integer),
        sa.Column("income_annual", sa.Numeric(15, 2), comment="연간 소득 (원)"),
        sa.Column("income_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("residence_type", sa.String(20), comment="own/rent/family/public"),
        sa.Column("education_level", sa.String(20),
                  comment="high_school/college/university/graduate"),
        # 직종/직장
        sa.Column("occupation_code", sa.String(10)),
        sa.Column("employer_name", sa.String(100), comment="직장명 (가명처리)"),
        sa.Column("employer_registration_no", sa.String(20), comment="사업자등록번호 해시"),
        # EQ Grade
        sa.Column("employer_eq_grade", sa.String(5), comment="EQ-S/A/B/C/D/E"),
        sa.Column("eq_grade_source", sa.String(20), comment="dart/nice_biz/manual/mou_list"),
        sa.Column("eq_grade_updated_at", sa.DateTime(timezone=True)),
        # IRG
        sa.Column("irg_code", sa.String(5), comment="L/M/H/VH"),
        sa.Column("ksic_code", sa.String(10), comment="한국표준산업분류 코드"),
        # OSI
        sa.Column("osi_score", sa.Numeric(6, 2), comment="현장심사 점수 0~100"),
        # 특수 세그먼트
        sa.Column("segment_code", sa.String(30),
                  comment="SEG-DR/SEG-JD/SEG-ART/SEG-YTH/SEG-MIL/SEG-MOU-{code}"),
        sa.Column("segment_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("segment_verified_at", sa.DateTime(timezone=True)),
        # 디지털 채널
        sa.Column("digital_channel", sa.String(30), comment="kakao/naver/bank_app/web/branch"),
        # CB 동의 (신용정보법 §32)
        sa.Column("cb_consent_granted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cb_consent_date", sa.DateTime(timezone=True)),
        sa.Column("alt_data_consent_granted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mydata_consent_granted", sa.Boolean, nullable=False, server_default="false"),
        # SOHO 전용
        sa.Column("business_registration_no", sa.String(20), comment="사업자등록번호 해시"),
        sa.Column("business_type", sa.String(50), comment="음식업/도소매업/서비스업"),
        sa.Column("business_duration_months", sa.Integer, comment="사업 영위 기간 (월)"),
        sa.Column("revenue_annual", sa.Numeric(15, 2), comment="연간 매출액 (원)"),
        sa.Column("operating_income", sa.Numeric(15, 2), comment="영업이익 (원)"),
        sa.Column("business_credit_score", sa.Integer, comment="사업자 CB 점수"),
        sa.Column("tax_filing_count", sa.Integer, comment="최근 3년 확정신고 횟수"),
        sa.Column("revenue_growth_rate", sa.Numeric(8, 4), comment="매출 성장률"),
        # 예술인 (SEG-ART)
        sa.Column("art_income_12m_avg", sa.Numeric(15, 2), comment="12개월 평균 소득"),
        sa.Column("art_fund_registered", sa.Boolean, nullable=False, server_default="false"),
        # 타임스탬프
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ── 2. loan_applications ───────────────────────────────────────────────
    op.create_table(
        "loan_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("applicant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("applicants.id"), nullable=False),
        # 상품
        sa.Column("product_type", sa.String(20), nullable=False,
                  comment="credit|mortgage|micro|credit_soho"),
        # 신청 금액
        sa.Column("requested_amount", sa.Numeric(15, 2), nullable=False, comment="신청 금액 (원)"),
        sa.Column("requested_term_months", sa.Integer, comment="대출 기간 (월)"),
        sa.Column("purpose", sa.String(100), comment="대출 목적"),
        # 주담대 전용
        sa.Column("collateral_type", sa.String(20), comment="apartment/house/commercial"),
        sa.Column("collateral_value", sa.Numeric(15, 2), comment="담보 시세 (원)"),
        sa.Column("collateral_address", sa.Text, comment="담보 주소 (가명처리)"),
        sa.Column("is_regulated_area", sa.Boolean, comment="규제지역 여부"),
        sa.Column("is_speculation_area", sa.Boolean, comment="투기과열지구 여부"),
        sa.Column("owned_property_count", sa.Integer, comment="보유 주택 수"),
        # 스트레스 DSR
        sa.Column("stress_dsr_region", sa.String(20),
                  comment="metropolitan | non_metropolitan"),
        sa.Column("stress_dsr_rate_applied", sa.Numeric(6, 4), comment="적용 스트레스 금리 (%p)"),
        sa.Column("stress_dsr_phase", sa.String(10), comment="phase1/phase2/phase3"),
        # 기존 부채
        sa.Column("existing_loan_monthly_payment", sa.Numeric(15, 2), comment="기존 대출 월 원리금"),
        sa.Column("existing_credit_line", sa.Numeric(15, 2), comment="마이너스통장 한도"),
        sa.Column("existing_credit_balance", sa.Numeric(15, 2), comment="마이너스통장 잔액"),
        # EQ / IRG 적용값
        sa.Column("eq_grade_applied", sa.String(5), comment="EQ-S/A/B/C/D/E"),
        sa.Column("eq_limit_multiplier", sa.Numeric(4, 2), comment="한도 배수"),
        sa.Column("irg_applied", sa.String(5), comment="L/M/H/VH"),
        sa.Column("irg_pd_adjustment", sa.Numeric(6, 4), comment="PD 조정값"),
        # 세그먼트
        sa.Column("segment_code_applied", sa.String(30)),
        sa.Column("segment_benefit_json", postgresql.JSONB(astext_type=sa.Text()),
                  comment="세그먼트 혜택 (한도배수, 금리우대 등)"),
        # Shadow 챌린저
        sa.Column("shadow_challenger_score", sa.Integer, comment="Shadow 모델 점수 (내부용)"),
        sa.Column("shadow_challenger_decision", sa.String(20)),
        sa.Column("shadow_model_version", sa.String(30)),
        # 비대면 채널
        sa.Column("channel_type", sa.String(20), nullable=False, server_default="digital"),
        sa.Column("digital_channel", sa.String(30), comment="kakao/naver/bank_app/web"),
        sa.Column("session_id", sa.String(64)),
        sa.Column("application_step", sa.String(30),
                  comment="identity_verify/consent/basic_info/financial_info/product_select/review/submit"),
        sa.Column("ocr_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("esign_completed", sa.Boolean, nullable=False, server_default="false"),
        # 심사 상태
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.String(100)),
        sa.Column("reviewer_note", sa.Text),
        sa.Column("auto_decision", sa.Boolean, nullable=False, server_default="true"),
        # BRMS 스냅샷
        sa.Column("regulation_snapshot", postgresql.JSONB(astext_type=sa.Text()),
                  comment="심사 시점 규제 파라미터 스냅샷"),
        # 타임스탬프
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_loan_applications_applicant", "loan_applications", ["applicant_id"])
    op.create_index("idx_loan_applications_status", "loan_applications", ["status"])

    # ── 3. credit_scores ──────────────────────────────────────────────────
    op.create_table(
        "credit_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("loan_applications.id"), nullable=False),
        # 평가 점수
        sa.Column("score", sa.Integer, nullable=False, comment="신용점수 300~900"),
        sa.Column("grade", sa.String(5), nullable=False, comment="AAA/AA/A/BBB/BB/B/CCC/CC/C/D"),
        sa.Column("scorecard_type", sa.String(30), comment="application/behavioral/collection"),
        sa.Column("model_version", sa.String(30)),
        # 바젤III IRB
        sa.Column("pd_estimate", sa.Numeric(8, 6), comment="부도확률 PD"),
        sa.Column("lgd_estimate", sa.Numeric(8, 6), comment="부도손실률 LGD"),
        sa.Column("ead_estimate", sa.Numeric(15, 2), comment="부도시 익스포져 EAD"),
        sa.Column("ccf_applied", sa.Numeric(6, 4), comment="CCF 적용값"),
        sa.Column("risk_weight", sa.Numeric(6, 4), comment="위험가중치 RW"),
        sa.Column("economic_capital", sa.Numeric(15, 2), comment="경제자본"),
        # RAROC 금리 분해
        sa.Column("rate_breakdown", postgresql.JSONB(astext_type=sa.Text()),
                  comment="금리 분해표: base_rate/credit_spread/final_rate/raroc"),
        sa.Column("hurdle_rate_satisfied", sa.Boolean, comment="RAROC≥15% 허들금리 충족"),
        # 승인 결과
        sa.Column("decision", sa.String(20), nullable=False,
                  comment="approved|rejected|manual_review"),
        sa.Column("approved_amount", sa.Numeric(15, 2), comment="승인 금액 (원)"),
        sa.Column("approved_rate", sa.Numeric(6, 4), comment="최종 적용 금리 (%)"),
        sa.Column("approved_term_months", sa.Integer, comment="승인 기간 (월)"),
        # 규제 비율
        sa.Column("dsr_ratio", sa.Numeric(6, 4), comment="DSR 비율"),
        sa.Column("stress_dsr_ratio", sa.Numeric(6, 4), comment="스트레스DSR 비율"),
        sa.Column("ltv_ratio", sa.Numeric(6, 4), comment="LTV 비율 (주담대)"),
        sa.Column("dti_ratio", sa.Numeric(6, 4), comment="DTI 비율 (주담대)"),
        sa.Column("dsr_limit_breached", sa.Boolean),
        sa.Column("ltv_limit_breached", sa.Boolean),
        # 설명가능성 (금소법 §19)
        sa.Column("rejection_reason", postgresql.JSONB(astext_type=sa.Text()),
                  comment="거절 사유 3가지 (한국어)"),
        sa.Column("shap_values", postgresql.JSONB(astext_type=sa.Text()), comment="SHAP 피처 기여도"),
        sa.Column("top_positive_factors", postgresql.JSONB(astext_type=sa.Text()),
                  comment="점수 상승 요인 3개"),
        sa.Column("top_negative_factors", postgresql.JSONB(astext_type=sa.Text()),
                  comment="점수 하락 요인 3개"),
        sa.Column("appeal_deadline", sa.DateTime(timezone=True),
                  comment="이의제기 기한 (scored_at + 30일)"),
        # 칼리브레이션
        sa.Column("calibration_bin", sa.Integer, comment="ECE 계산용 확률 구간 (1~10)"),
        sa.Column("raw_probability", sa.Numeric(8, 6), comment="모델 출력 원시 확률"),
        # 타임스탬프
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_check_constraint("chk_score_range", "credit_scores", "score BETWEEN 300 AND 900")
    op.create_check_constraint("chk_pd_range", "credit_scores", "pd_estimate BETWEEN 0 AND 1")
    op.create_index("idx_credit_scores_application", "credit_scores", ["application_id"])
    op.create_index("idx_credit_scores_scored_at", "credit_scores", ["scored_at"])
    op.create_index("idx_credit_scores_decision", "credit_scores", ["decision"])

    # ── 4. regulation_params (BRMS) ────────────────────────────────────────
    op.create_table(
        "regulation_params",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("param_key", sa.String(100), nullable=False,
                  comment="예: stress_dsr.metropolitan.variable.phase3"),
        sa.Column("param_category", sa.String(30), nullable=False,
                  comment="dsr|ltv|dti|rate|limit|eq_grade|irg|segment|ccf"),
        sa.Column("phase_label", sa.String(20), comment="phase1|phase2|phase3"),
        sa.Column("param_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("condition_json", postgresql.JSONB(astext_type=sa.Text())),
        # 유효 기간
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        # 법령 근거
        sa.Column("legal_basis", sa.String(200)),
        sa.Column("description", sa.Text),
        # 변경 관리 (4-eyes)
        sa.Column("created_by", sa.String(50)),
        sa.Column("approved_by", sa.String(50)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("change_reason", sa.Text),
        # 타임스탬프
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_param_key_effective_from",
        "regulation_params",
        ["param_key", "effective_from"],
    )
    op.create_index("idx_regulation_params_key_active", "regulation_params", ["param_key", "is_active"])
    op.create_index("idx_regulation_params_category", "regulation_params", ["param_category"])
    op.create_index("idx_regulation_params_effective", "regulation_params", ["effective_from", "effective_to"])

    # ── 5. eq_grade_master ────────────────────────────────────────────────
    op.create_table(
        "eq_grade_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employer_name", sa.String(100), nullable=False),
        sa.Column("employer_registration_no", sa.String(20), comment="사업자등록번호 해시"),
        sa.Column("eq_grade", sa.String(5), nullable=False,
                  comment="EQ-S|EQ-A|EQ-B|EQ-C|EQ-D|EQ-E"),
        sa.Column("limit_multiplier", sa.Numeric(4, 2), nullable=False, comment="한도 배수"),
        sa.Column("rate_adjustment", sa.Numeric(5, 3), nullable=False, comment="금리 조정 (%p)"),
        # MOU
        sa.Column("mou_code", sa.String(20), comment="SEG-MOU-{code}"),
        sa.Column("mou_start_date", sa.DateTime(timezone=True)),
        sa.Column("mou_end_date", sa.DateTime(timezone=True)),
        sa.Column("mou_special_rate", sa.Numeric(5, 3), comment="MOU 특별 금리"),
        # 관리
        sa.Column("grade_source", sa.String(30), comment="dart/nice_biz/manual"),
        sa.Column("grade_date", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_eq_grade_employer", "eq_grade_master", ["employer_registration_no"])
    op.create_index("idx_eq_grade_mou_code", "eq_grade_master", ["mou_code"])

    # ── 6. irg_master ─────────────────────────────────────────────────────
    op.create_table(
        "irg_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ksic_code", sa.String(10), nullable=False, comment="한국표준산업분류 코드"),
        sa.Column("industry_name", sa.String(100)),
        sa.Column("irg_grade", sa.String(5), nullable=False, comment="L|M|H|VH"),
        sa.Column("pd_adjustment", sa.Numeric(5, 3), nullable=False,
                  comment="PD 조정값 (L=-0.10, M=0.0, H=+0.15, VH=+0.30)"),
        sa.Column("limit_cap", sa.Numeric(4, 2), comment="한도 상한 배수 (VH=0.5x 등)"),
        sa.Column("review_year", sa.Integer),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_irg_ksic_code", "irg_master", ["ksic_code"])
    op.create_index("idx_irg_master_grade", "irg_master", ["irg_grade"])

    # ── 7. model_versions ─────────────────────────────────────────────────
    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, comment="모델명 (예: application_v2)"),
        sa.Column("scorecard_type", sa.String(30), comment="application|behavioral|collection"),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("artifact_path", sa.String(500)),
        # 성능 지표
        sa.Column("gini_train", sa.Numeric(6, 4)),
        sa.Column("gini_test", sa.Numeric(6, 4)),
        sa.Column("gini_oot", sa.Numeric(6, 4)),
        sa.Column("ks_statistic", sa.Numeric(6, 4)),
        sa.Column("auc_roc", sa.Numeric(6, 4)),
        # 공정성
        sa.Column("fairness_metrics", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("fairness_passed", sa.Boolean),
        # 승인 워크플로우
        sa.Column("status", sa.String(20), nullable=False, server_default="draft",
                  comment="draft|validated|champion|retired"),
        sa.Column("is_champion", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("approved_by", sa.String(100)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        # 문서화
        sa.Column("training_data_period", sa.String(50)),
        sa.Column("feature_count", sa.Integer),
        sa.Column("training_sample_count", sa.Integer),
        sa.Column("bad_rate_train", sa.Numeric(6, 4)),
        sa.Column("notes", sa.Text),
        # 타임스탬프
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_model_versions_type_champion", "model_versions",
                    ["scorecard_type", "is_champion"])

    # ── 8. audit_logs ─────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(50), nullable=False,
                  comment="credit_score|application|model_version|applicant"),
        sa.Column("entity_id", sa.String(36), comment="UUID 문자열"),
        sa.Column("action", sa.String(50), nullable=False,
                  comment="score_created|application_approved|application_rejected|model_deployed|data_accessed"),
        sa.Column("actor_id", sa.String(100)),
        sa.Column("actor_type", sa.String(20), nullable=False, comment="user|api|system|batch"),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), comment="변경 전후 데이터"),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("regulation_ref", sa.String(100), comment="관련 법령 조항"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("idx_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_id"])


def downgrade() -> None:
    # 역순으로 삭제 (FK 의존성 고려)
    op.drop_table("audit_logs")
    op.drop_table("model_versions")
    op.drop_table("irg_master")
    op.drop_table("eq_grade_master")
    op.drop_table("regulation_params")
    op.drop_table("credit_scores")
    op.drop_table("loan_applications")
    op.drop_table("applicants")
