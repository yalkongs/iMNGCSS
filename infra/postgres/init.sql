-- KCS PostgreSQL 초기화 스크립트
-- docker-compose 최초 실행 시 자동 실행
-- 테이블 생성 + 핵심 규제 파라미터 시드 데이터 포함

-- ─────────────────────────────────────────────────────────────
-- 확장 기능
-- ─────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- HMAC-SHA256 해시
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID 생성

-- 타임존 설정
SET timezone = 'Asia/Seoul';

-- ─────────────────────────────────────────────────────────────
-- 테이블 생성 (SQLAlchemy create_all과 중복되지 않도록 IF NOT EXISTS 사용)
-- ─────────────────────────────────────────────────────────────

-- 규제 파라미터 테이블 (BRMS)
CREATE TABLE IF NOT EXISTS regulation_params (
    id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    param_key       VARCHAR(100) NOT NULL,
    param_category  VARCHAR(30)  NOT NULL,
    phase_label     VARCHAR(20),
    param_value     JSONB        NOT NULL,
    condition_json  JSONB,
    effective_from  TIMESTAMPTZ  NOT NULL,
    effective_to    TIMESTAMPTZ,
    is_active       BOOLEAN      DEFAULT TRUE,
    legal_basis     VARCHAR(200),
    description     TEXT,
    created_by      VARCHAR(50),
    approved_by     VARCHAR(50),
    approved_at     TIMESTAMPTZ,
    change_reason   TEXT,
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT uq_param_key_effective_from UNIQUE (param_key, effective_from)
);

-- EQ Grade 마스터 테이블
CREATE TABLE IF NOT EXISTS eq_grade_master (
    id                         UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    employer_name              VARCHAR(100) NOT NULL,
    employer_registration_no   VARCHAR(20),
    eq_grade                   VARCHAR(5)   NOT NULL,
    limit_multiplier           NUMERIC(4,2) NOT NULL,
    rate_adjustment            NUMERIC(5,3) NOT NULL,
    mou_code                   VARCHAR(20),
    mou_start_date             TIMESTAMPTZ,
    mou_end_date               TIMESTAMPTZ,
    mou_special_rate           NUMERIC(5,3),
    grade_source               VARCHAR(30),
    grade_date                 TIMESTAMPTZ,
    is_active                  BOOLEAN DEFAULT TRUE,
    created_at                 TIMESTAMPTZ DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ DEFAULT NOW()
);

-- IRG 마스터 테이블 (산업 리스크 등급)
CREATE TABLE IF NOT EXISTS irg_master (
    id              UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    ksic_code       VARCHAR(10)  NOT NULL,
    industry_name   VARCHAR(100),
    irg_grade       VARCHAR(5)   NOT NULL,
    pd_adjustment   NUMERIC(6,4) NOT NULL,
    limit_cap       NUMERIC(4,2),
    review_year     INTEGER,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_irg_ksic_code UNIQUE (ksic_code)
);

-- ─────────────────────────────────────────────────────────────
-- 성능 인덱스
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_regulation_params_key_active
    ON regulation_params (param_key, is_active);

CREATE INDEX IF NOT EXISTS idx_regulation_params_category
    ON regulation_params (param_category);

CREATE INDEX IF NOT EXISTS idx_regulation_params_effective
    ON regulation_params (effective_from, effective_to);

CREATE INDEX IF NOT EXISTS idx_eq_grade_employer
    ON eq_grade_master (employer_registration_no);

CREATE INDEX IF NOT EXISTS idx_eq_grade_mou_code
    ON eq_grade_master (mou_code);

CREATE INDEX IF NOT EXISTS idx_irg_master_grade
    ON irg_master (irg_grade);

-- ─────────────────────────────────────────────────────────────
-- 시드: regulation_params (핵심 규제 파라미터)
-- ON CONFLICT DO NOTHING → 재실행 시 중복 방지
-- ─────────────────────────────────────────────────────────────

-- 1. DSR 한도 (은행업감독규정 §35의5)
INSERT INTO regulation_params
    (param_key, param_category, param_value, effective_from, is_active, legal_basis, description, created_by)
VALUES
    ('dsr.max_ratio', 'dsr',
     '{"max_ratio": 40.0, "unit": "percent"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '은행업감독규정 §35의5',
     'DSR 40% 한도 (총부채원리금상환비율)',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 2. LTV 한도 (주택담보대출)
INSERT INTO regulation_params
    (param_key, param_category, param_value, condition_json, effective_from, is_active, legal_basis, description, created_by)
VALUES
    ('ltv.general', 'ltv',
     '{"ltv_ratio": 70.0, "unit": "percent"}'::jsonb,
     '{"area_type": "general"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '은행업감독규정 §35',
     'LTV 일반지역 70%',
     'system'),
    ('ltv.regulated_area', 'ltv',
     '{"ltv_ratio": 60.0, "unit": "percent"}'::jsonb,
     '{"area_type": "regulated_area"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '은행업감독규정 §35',
     'LTV 조정대상지역 60%',
     'system'),
    ('ltv.speculation_area', 'ltv',
     '{"ltv_ratio": 40.0, "unit": "percent"}'::jsonb,
     '{"area_type": "speculation_area"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '은행업감독규정 §35',
     'LTV 투기과열지구 40%',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 3. 최고금리 (대부업법 §11)
INSERT INTO regulation_params
    (param_key, param_category, param_value, effective_from, is_active, legal_basis, description, created_by)
VALUES
    ('rate.max_interest', 'rate',
     '{"rate": 20.0, "unit": "percent_per_year"}'::jsonb,
     '2021-07-07T00:00:00Z', TRUE,
     '대부업법 §11, 이자제한법',
     '법정 최고금리 연 20%',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 4. 스트레스 DSR - 수도권 (금감원 행정지도 2024-02)
INSERT INTO regulation_params
    (param_key, param_category, phase_label, param_value, condition_json,
     effective_from, effective_to, is_active, legal_basis, description, created_by)
VALUES
    ('stress_dsr.metropolitan.variable', 'dsr', 'phase2',
     '{"rate": 0.75, "unit": "percentage_point", "apply_ratio": 1.0}'::jsonb,
     '{"region": "metropolitan", "rate_type": "variable"}'::jsonb,
     '2024-02-26T00:00:00Z', '2025-07-01T00:00:00Z', TRUE,
     '금감원 행정지도 2024-02',
     '수도권 변동금리 스트레스DSR Phase2 (+0.75%p)',
     'system'),
    ('stress_dsr.metropolitan.variable', 'dsr', 'phase3',
     '{"rate": 1.50, "unit": "percentage_point", "apply_ratio": 1.0}'::jsonb,
     '{"region": "metropolitan", "rate_type": "variable"}'::jsonb,
     '2025-07-01T00:00:00Z', NULL, TRUE,
     '금감원 행정지도 2025-07',
     '수도권 변동금리 스트레스DSR Phase3 (+1.50%p)',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 5. 스트레스 DSR - 비수도권
INSERT INTO regulation_params
    (param_key, param_category, phase_label, param_value, condition_json,
     effective_from, effective_to, is_active, legal_basis, description, created_by)
VALUES
    ('stress_dsr.non_metropolitan.variable', 'dsr', 'phase2',
     '{"rate": 1.50, "unit": "percentage_point", "apply_ratio": 1.0}'::jsonb,
     '{"region": "non_metropolitan", "rate_type": "variable"}'::jsonb,
     '2024-02-26T00:00:00Z', '2025-07-01T00:00:00Z', TRUE,
     '금감원 행정지도 2024-02',
     '비수도권 변동금리 스트레스DSR Phase2 (+1.50%p)',
     'system'),
    ('stress_dsr.non_metropolitan.variable', 'dsr', 'phase3',
     '{"rate": 3.00, "unit": "percentage_point", "apply_ratio": 1.0}'::jsonb,
     '{"region": "non_metropolitan", "rate_type": "variable"}'::jsonb,
     '2025-07-01T00:00:00Z', NULL, TRUE,
     '금감원 행정지도 2025-07',
     '비수도권 변동금리 스트레스DSR Phase3 (+3.00%p)',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 6. EQ Grade 파라미터 (한도배수/금리조정)
INSERT INTO regulation_params
    (param_key, param_category, param_value, effective_from, is_active, description, created_by)
VALUES
    ('eq_grade.EQ-S', 'eq_grade',
     '{"multiplier": 2.0, "rate_adjustment": -0.5, "grade": "EQ-S"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-S 등급 (최상위 기업) 2.0x 한도, -0.5%p', 'system'),
    ('eq_grade.EQ-A', 'eq_grade',
     '{"multiplier": 1.8, "rate_adjustment": -0.3, "grade": "EQ-A"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-A 등급 1.8x 한도, -0.3%p', 'system'),
    ('eq_grade.EQ-B', 'eq_grade',
     '{"multiplier": 1.5, "rate_adjustment": -0.2, "grade": "EQ-B"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-B 등급 1.5x 한도, -0.2%p', 'system'),
    ('eq_grade.EQ-C', 'eq_grade',
     '{"multiplier": 1.2, "rate_adjustment": 0.0, "grade": "EQ-C"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-C 등급 1.2x 한도, 조정없음', 'system'),
    ('eq_grade.EQ-D', 'eq_grade',
     '{"multiplier": 1.0, "rate_adjustment": 0.2, "grade": "EQ-D"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-D 등급 1.0x 한도, +0.2%p', 'system'),
    ('eq_grade.EQ-E', 'eq_grade',
     '{"multiplier": 0.7, "rate_adjustment": 0.5, "grade": "EQ-E"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'EQ-E 등급 (하위 기업) 0.7x 한도, +0.5%p', 'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 7. IRG 파라미터 (산업 리스크 등급 PD 조정)
INSERT INTO regulation_params
    (param_key, param_category, param_value, effective_from, is_active, description, created_by)
VALUES
    ('irg.pd_adjustment.L', 'irg',
     '{"pd_adjustment": -0.10, "grade": "L", "label": "저위험"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'IRG L등급 (저위험) PD -10%p', 'system'),
    ('irg.pd_adjustment.M', 'irg',
     '{"pd_adjustment": 0.0, "grade": "M", "label": "중위험"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'IRG M등급 (중위험) PD 조정없음', 'system'),
    ('irg.pd_adjustment.H', 'irg',
     '{"pd_adjustment": 0.15, "grade": "H", "label": "고위험"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'IRG H등급 (고위험) PD +15%p', 'system'),
    ('irg.pd_adjustment.VH', 'irg',
     '{"pd_adjustment": 0.30, "grade": "VH", "label": "초고위험", "limit_cap": 0.5}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE, 'IRG VH등급 (초고위험) PD +30%p, 한도 0.5x', 'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- 8. CCF (신용환산율, 회전한도 전용)
INSERT INTO regulation_params
    (param_key, param_category, param_value, effective_from, is_active, legal_basis, description, created_by)
VALUES
    ('ccf.revolving.default', 'ccf',
     '{"ccf": 0.50, "unit": "ratio", "note": "마이너스통장 기본 CCF"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '바젤III IRB 기본법',
     '회전한도 기본 CCF 50%',
     'system'),
    ('ccf.revolving.ml_model', 'ccf',
     '{"ccf": null, "unit": "ratio", "note": "ML 모델 예측값 사용"}'::jsonb,
     '2023-01-01T00:00:00Z', TRUE,
     '바젤III IRB 내부모델법',
     '회전한도 ML 모델 CCF (AUROC≥0.70 충족 시)',
     'system')
ON CONFLICT (param_key, effective_from) DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- 시드: eq_grade_master (표준 등급 기준 항목)
-- ─────────────────────────────────────────────────────────────
INSERT INTO eq_grade_master
    (employer_name, eq_grade, limit_multiplier, rate_adjustment, grade_source, is_active)
VALUES
    ('표준 EQ-S 기준 (최상위)', 'EQ-S', 2.0, -0.500, 'manual', TRUE),
    ('표준 EQ-A 기준',          'EQ-A', 1.8, -0.300, 'manual', TRUE),
    ('표준 EQ-B 기준',          'EQ-B', 1.5, -0.200, 'manual', TRUE),
    ('표준 EQ-C 기준',          'EQ-C', 1.2,  0.000, 'manual', TRUE),
    ('표준 EQ-D 기준',          'EQ-D', 1.0,  0.200, 'manual', TRUE),
    ('표준 EQ-E 기준 (하위)',   'EQ-E', 0.7,  0.500, 'manual', TRUE);

-- ─────────────────────────────────────────────────────────────
-- 시드: irg_master (주요 KSIC 업종별 산업 리스크 등급)
-- ─────────────────────────────────────────────────────────────
INSERT INTO irg_master
    (ksic_code, industry_name, irg_grade, pd_adjustment, limit_cap, review_year, is_active)
VALUES
    -- 저위험 업종 (L)
    ('Q861', '의원 및 병원', 'L', -0.1000, NULL, 2023, TRUE),
    ('Q862', '치과의원',    'L', -0.1000, NULL, 2023, TRUE),
    ('K641', '은행 및 신탁',    'L', -0.1000, NULL, 2023, TRUE),
    ('J621', '소프트웨어 개발', 'L', -0.1000, NULL, 2023, TRUE),
    ('M711', '법무서비스',  'L', -0.1000, NULL, 2023, TRUE),
    ('M712', '회계서비스',  'L', -0.1000, NULL, 2023, TRUE),
    ('O841', '일반 공공행정', 'L', -0.1000, NULL, 2023, TRUE),
    -- 중위험 업종 (M)
    ('G471', '종합 소매업',   'M', 0.0000, NULL, 2023, TRUE),
    ('G461', '도매업',        'M', 0.0000, NULL, 2023, TRUE),
    ('C101', '식품 제조업',   'M', 0.0000, NULL, 2023, TRUE),
    ('C201', '화학제품 제조', 'M', 0.0000, NULL, 2023, TRUE),
    ('H491', '철도 운송업',   'M', 0.0000, NULL, 2023, TRUE),
    ('H501', '수상 운송업',   'M', 0.0000, NULL, 2023, TRUE),
    ('P851', '초중고 교육',   'M', 0.0000, NULL, 2023, TRUE),
    -- 고위험 업종 (H)
    ('F411', '건물 건설업',   'H', 0.1500, NULL, 2023, TRUE),
    ('F421', '토목 건설업',   'H', 0.1500, NULL, 2023, TRUE),
    ('I561', '음식점업',      'H', 0.1500, NULL, 2023, TRUE),
    ('I551', '숙박업',        'H', 0.1500, NULL, 2023, TRUE),
    ('R901', '예술 공연업',   'H', 0.1500, NULL, 2023, TRUE),
    ('N752', '여행 서비스',   'H', 0.1500, NULL, 2023, TRUE),
    -- 초고위험 업종 (VH)
    ('I582', '주점업',        'VH', 0.3000, 0.50, 2023, TRUE),
    ('R921', '도박 및 복권',  'VH', 0.3000, 0.50, 2023, TRUE),
    ('S961', '개인 서비스',   'VH', 0.3000, 0.50, 2023, TRUE)
ON CONFLICT (ksic_code) DO NOTHING;

-- ─────────────────────────────────────────────────────────────
-- DB 메타 정보
-- ─────────────────────────────────────────────────────────────
COMMENT ON DATABASE kcs_db IS 'Korea Credit Scoring System - Production Database';
COMMENT ON TABLE regulation_params IS 'BRMS 규제 파라미터 (DSR/LTV/금리/EQ/IRG)';
COMMENT ON TABLE eq_grade_master IS 'EQ Grade 마스터 (기업 신용도 등급)';
COMMENT ON TABLE irg_master IS 'IRG 마스터 (산업 리스크 등급)';
