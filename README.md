# Korea Credit Scoring System (KCS)

> **한국형 AI 신용평가 시스템** — 금융감독원 가이드라인·바젤III IRB 기준의 엔터프라이즈 신용평가 백엔드

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-389%20passed-brightgreen)](#테스트)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

---

## 개요

KCS는 은행·저축은행·여신전문회사를 위한 **비대면 채널 신용평가 플랫폼**입니다.

| 항목 | 상세 |
|------|------|
| **평가 대상** | 개인, 개인사업자 |
| **지원 상품** | 신용대출, 주택담보대출, 소액마이크로론 |
| **점수 범위** | 300 ~ 900점 (Base 600점 = PD 7.2%, PDO 40점) |
| **SLA 목표** | p95 ≤ 500ms, 에러율 ≤ 1%, TPS ≥ 100 |
| **규제 준거** | 금감원 AI 모범규준, 바젤III IRB, 신용정보법, 대부업법 §11 |

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│                      클라이언트 (앱/웹)                        │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS
┌────────────────────────▼─────────────────────────────────────┐
│                  KCS API (FastAPI :8000)                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐   │
│  │  Auth   │  │Scoring   │  │ Admin    │  │ Monitoring  │   │
│  │  (JWT)  │  │(평가/Shadow)│  │(BRMS)  │  │(PSI/Cal)   │   │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘   │
│       └────────────┴─────────────┴────────────────┘          │
│                  ┌──────────────────┐                        │
│                  │  ScoringEngine   │  LightGBM + 통계 폴백   │
│                  │  PolicyEngine    │  BRMS Redis+PostgreSQL  │
│                  │  MonitoringEngine│  PSI/ECE/Brier Score   │
│                  └──────────────────┘                        │
└───────┬──────────────────────┬───────────────────────────────┘
        │                      │
┌───────▼──────┐     ┌─────────▼────────┐
│  PostgreSQL  │     │      Redis        │
│  (영구 저장)  │     │  (BRMS 캐시,      │
│              │     │   Rate Limiting)  │
└──────────────┘     └──────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│                  Mock Server (FastAPI :8001)                  │
│  NICE CB | KCB CB | 국세청 | 건강보험 | 기업신용 | 전문직면허  │
└──────────────────────────────────────────────────────────────┘
```

---

## 빠른 시작

### 사전 요구사항

- Docker ≥ 24.0 + Docker Compose v2
- Python 3.12 (로컬 테스트 시)

### 1. 서비스 기동

```bash
# 전체 스택 실행 (API + Mock Server + PostgreSQL + Redis)
make up

# 로그 확인
make logs

# 상태 확인
make status
```

- API Swagger: http://localhost:8000/docs
- Mock Server: http://localhost:8001/docs

### 2. ML 모델 학습

```bash
# 합성 학습 데이터 생성 (10만 건)
make gen-synthetic

# 3개 스코어카드 학습
make train
```

### 3. 데모 시나리오 실행

```bash
# JWT 인증 → CB 조회 → 신용평가 → 대출 신청 여정 → PSI 모니터링
make demo
```

### 4. 전체 테스트

```bash
make test                       # 전체 테스트
make test-unit                  # 단위 테스트
make test-auth                  # JWT/RBAC 인증 테스트
make test-regulatory            # 규제 준수 테스트 (DSR/LTV/금리)
make test-audit                 # 내부감사 검증
make test-performance           # 성능 기준 검증
make load-test                  # Locust 부하 테스트 (API 서버 실행 후)
```

---

## API 엔드포인트 요약

### 인증 (`/api/v1/auth`)

| Method | 경로 | 설명 |
|--------|------|------|
| `POST` | `/token` | JWT 액세스 토큰 발급 (OAuth2 Password Flow) |
| `GET`  | `/me`    | 현재 사용자 정보 조회 |

**데모 계정**

| 사용자 | 비밀번호 | 역할 | 접근 권한 |
|--------|---------|------|---------|
| `admin` | `KCS@admin2024` | admin | 전체 |
| `risk_manager` | `KCS@risk2024` | risk_manager | BRMS 파라미터 관리 |
| `compliance` | `KCS@comp2024` | compliance | 규제 조회 |
| `developer` | `KCS@dev2024` | developer | 읽기 |

### 신용평가 (`/api/v1/scoring`)

| Method | 경로 | 설명 |
|--------|------|------|
| `POST` | `/evaluate` | 즉시 신용평가 (LightGBM + 통계 폴백) |
| `GET`  | `/result/{id}` | 평가 결과 조회 |

### 대출 신청 (`/api/v1/applications`)

7단계 비대면 신청 여정:

```
1. POST /start          → 신청 세션 생성
2. POST /{id}/identity  → 본인인증 (CB 조회)
3. POST /{id}/income    → 소득 증빙 (국세청 연동)
4. POST /{id}/loan-info → 대출 조건 입력
5. POST /{id}/evaluate  → 신용평가 실행
6. POST /{id}/submit    → 최종 제출
7. GET  /{id}/status    → 심사 결과 조회
```

### 관리자 (`/api/v1/admin`) — `risk_manager` 역할 필요

| Method | 경로 | 설명 |
|--------|------|------|
| `GET`    | `/regulation-params`     | 규제 파라미터 목록 |
| `POST`   | `/regulation-params`     | 파라미터 추가/수정 |
| `DELETE` | `/regulation-params/{id}`| 파라미터 삭제 |
| `GET`    | `/eq-grade-master`       | EQ Grade 마스터 조회 |
| `GET`    | `/irg-master`            | IRG 마스터 조회 |

### 모니터링 (`/api/v1/monitoring`)

| Method | 경로 | 설명 |
|--------|------|------|
| `GET` | `/psi-summary`  | PSI 모니터링 요약 |
| `GET` | `/psi-report`   | PSI 전체 보고서 |
| `GET` | `/calibration`  | ECE/Brier Score 캘리브레이션 |
| `GET` | `/vintage`      | 빈티지 분석 |

---

## 프로젝트 구조

```
korea-credit-scoring/
├── backend/                   # FastAPI 백엔드
│   ├── app/
│   │   ├── api/v1/            # REST API 라우터 (5개)
│   │   ├── core/              # 핵심 엔진 (ScoringEngine, PolicyEngine...)
│   │   ├── db/schemas/        # SQLAlchemy ORM 모델
│   │   ├── middleware/        # 미들웨어 (로깅, Rate Limiting)
│   │   └── services/          # 비즈니스 서비스 (CB API, Scoring)
│   ├── alembic/               # DB 마이그레이션
│   ├── Dockerfile
│   ├── requirements.txt       # 프로덕션 의존성
│   └── requirements-dev.txt   # 개발/테스트 의존성 (Locust, Ruff, Bandit...)
├── ml_pipeline/               # ML 파이프라인
│   ├── data/                  # 합성 데이터 생성 (10만 건)
│   ├── training/              # 스코어카드 학습 (Application/Behavioral/Collection)
│   ├── registry/              # MLflow 모델 등록
│   └── run_pipeline.py        # 파이프라인 오케스트레이터
├── mock_server/               # 외부 CB/국세청/건보 API 모의 서버
├── tests/                     # 단위/통합/성능/부하 테스트
│   ├── unit/                  # test_scoring_engine, test_auth, test_monitoring_engine
│   ├── integration/           # test_api_e2e (FastAPI E2E)
│   ├── regulatory/            # test_brms_params
│   └── performance/           # test_api_performance, locustfile.py
├── validation/                # 규제·컴플라이언스 검증 (역할별)
│   └── roles/
│       ├── developer/         # 모델 성능, 규제 준수
│       ├── risk_management/   # 스트레스 시나리오, 바젤III
│       ├── compliance/        # 공정성, AI 7대 원칙
│       ├── internal_audit/    # 감사 추적, 개인정보 보호
│       └── regulatory/        # 규제 공시, 이의제기
├── k8s/                       # Kubernetes 배포 매니페스트
├── docs/                      # 설계 문서 (설계서·요건정의서·구현계획서)
├── scripts/                   # 유틸리티 스크립트 (demo_api.sh)
├── docker-compose.yml         # 로컬 개발 스택
├── pyproject.toml             # pytest/ruff/mypy/coverage 통합 설정
├── .pre-commit-config.yaml    # pre-commit 훅 (ruff, bandit, secrets 감지)
└── Makefile                   # 개발 자동화 명령어
```

---

## 핵심 규제 파라미터

> 모든 파라미터는 코드가 아닌 **BRMS DB(PostgreSQL)** 에 저장되며, Redis로 캐싱됩니다.

| 파라미터 | 값 | 법적 근거 |
|---------|-----|---------|
| DSR 한도 | 40% | 가계부채 관리방안 |
| LTV (일반) | 70% | 은행업 감독업무 시행세칙 |
| LTV (조정대상) | 60% | 부동산 대책 |
| LTV (투기과열) | 40% | 부동산 대책 |
| 최고금리 | 20% | 대부업법 §11 |
| 스트레스 DSR Phase2 | 수도권 +0.75%p | 금융위원회 고시 |
| 스트레스 DSR Phase3 (2025.07~) | 수도권 +1.50%p | 금융위원회 고시 |

---

## 특수 세그먼트

| 코드 | 대상 | 혜택 |
|------|------|------|
| `SEG-DR` | 의사·치과의사·한의사 | EQ-B 등급 보장, 한도 3.0x, 금리 -0.3%p |
| `SEG-JD` | 변호사·회계사·법무사 | EQ-B 등급 보장, 한도 2.5x, 금리 -0.2%p |
| `SEG-ART` | 예술인복지재단 등록 예술인 | 12개월 소득 평활화 |
| `SEG-YTH` | 청년 (만 19–34세) | 금리 -0.5%p |
| `SEG-MIL` | 군인 | EQ-S 등급 보장, 한도 2.0x, 금리 -0.5%p |
| `SEG-MOU-*` | 협약기업 근로자 | 금리 -0.3%p, 한도 1.5x |

---

## EQ Grade / IRG 체계

**EQ Grade** (소득 승수 · 금리 조정)

| 등급 | 한도 승수 | 금리 조정 |
|------|---------|---------|
| EQ-S | 2.0x | -0.50%p |
| EQ-A | 1.7x | -0.30%p |
| EQ-B | 1.4x | -0.10%p |
| EQ-C | 1.0x | 0.00%p |
| EQ-D | 0.9x | +0.20%p |
| EQ-E | 0.7x | +0.50%p |

**IRG** (금리 등급 가산금리)

| 등급 | 가산금리 |
|------|---------|
| L (저위험) | -0.10%p |
| M (중위험) | 0.00%p |
| H (고위험) | +0.15%p |
| VH (초고위험) | +0.30%p |

---

## 환경 변수

`backend/.env.example` 참고.

```bash
# 필수
SECRET_KEY=your-256-bit-secret-key
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/kcs_db
REDIS_URL=redis://host:6379/0

# 선택
ENVIRONMENT=production        # development | staging | production
RATE_LIMIT_PER_MINUTE=60      # 분당 요청 한도 (IP 기반)
RESIDENT_HASH_KEY=hmac-key    # 주민번호 HMAC-SHA256 키
CB_API_BASE_URL=http://mock-server:8001
KAFKA_ENABLED=false
```

---

## 개발 환경 설정

```bash
# 1. 의존성 설치 (개발 포함)
pip install -r backend/requirements-dev.txt

# 2. pre-commit 훅 설치
pre-commit install

# 3. 코드 품질 검사
make lint

# 4. 단위 테스트
make test-unit
```

---

## CI/CD 파이프라인

GitHub Actions (`.github/workflows/ci.yml`) 8개 잡:

| 잡 | 내용 |
|----|------|
| `lint` | Ruff 린트 + Mypy 타입 체크 |
| `unit-tests` | 단위/인증/감사/성능 테스트 |
| `regulatory-constants` | DSR/LTV/금리 규제 상수 검증 |
| `ml-validation` | 합성 데이터 생성 + ML 파이프라인 검증 |
| `docker-build` | API + Mock Server 이미지 빌드 |
| `integration-tests` | PostgreSQL·Redis 포함 E2E 테스트 |
| `security-scan` | pip-audit + Bandit 보안 스캔 |
| `locust-validate` | Locust 파일 문법 검증 |

---

## 보안 설계

- **인증**: JWT (HS256, 30분 만료) + OAuth2 Password Flow
- **인가**: RBAC 역할 계층 (`admin ⊇ risk_manager, compliance, developer ⊇ viewer`)
- **암호화**: 주민번호 HMAC-SHA256 해시 (신용정보법 §17), 타이밍 공격 방지 (`hmac.compare_digest`)
- **Rate Limiting**: Redis 슬라이딩 윈도우 (IP·토큰 기반, 기본 60 req/min)
- **Secrets 방지**: pre-commit `detect-secrets` 훅, `.env` 커밋 금지 훅
- **4-eyes principle**: BRMS 파라미터 변경 시 `approved_by` 필드 필수

---

## 라이선스

MIT License — 자세한 내용은 [LICENSE](LICENSE) 참고.

---

> **주의**: 이 시스템의 신용평가 로직 및 규제 파라미터는 실제 금융 서비스 적용 전 반드시 금융감독원 심사 및 법률 검토가 필요합니다.
