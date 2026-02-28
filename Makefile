.PHONY: help up up-tools up-kafka up-ml down build logs logs-all status migrate migrate-create install \
        mock-server seed-data gen-fixtures gen-synthetic train \
        test test-unit test-auth test-integration test-regulatory test-stress test-fairness test-model test-all-validation \
        test-audit test-regulatory-disclosure test-performance load-test \
        k8s-deploy k8s-delete k8s-status \
        up-prod down-prod secrets-baseline \
        lint clean demo

BASE_DIR := $(shell pwd)
BACKEND_DIR := $(BASE_DIR)/backend
ML_DIR := $(BASE_DIR)/ml_pipeline

# 가상환경 python/pytest 우선 사용 (없으면 시스템 폴백)
PYTHON := $(shell test -f "$(BASE_DIR)/.venv/bin/python" && echo '"$(BASE_DIR)/.venv/bin/python"' || (which python3 || which python))
PYTEST := $(shell test -f "$(BASE_DIR)/.venv/bin/pytest" && echo '"$(BASE_DIR)/.venv/bin/pytest"' || echo pytest)

help:
	@echo "Korea Credit Scoring System - 사용 가능한 명령어:"
	@echo ""
	@echo "  make up              - 전체 스택 실행 (API + Mock Server + DB + Redis)"
	@echo "  make up-tools        - 도구 포함 실행 (pgAdmin 포함)"
	@echo "  make up-kafka        - Kafka EWS 포함 실행"
	@echo "  make down            - 스택 종료"
	@echo "  make build           - Docker 이미지 빌드"
	@echo "  make migrate         - DB 마이그레이션 실행"
	@echo "  make train           - ML 모델 학습 (합성 데이터)"
	@echo "  make gen-fixtures    - Mock Server 시나리오 픽스처 생성 (30개)"
	@echo "  make gen-synthetic   - 합성 학습 데이터 생성 (10만건)"
	@echo "  make seed-data       - regulation_params 초기 시드"
	@echo "  make test                - 전체 테스트 실행 (단위 + 통합 + 검증)"
	@echo "  make test-unit           - 단위 테스트 (scoring_engine, monitoring_engine)"
	@echo "  make test-auth           - 인증/RBAC 단위 테스트 (JWT, 역할 계층)"
	@echo "  make test-audit          - 내부감사 테스트 (감사추적, 접근통제, 개인정보)"
	@echo "  make test-regulatory-disclosure - 규제공시 테스트 (DSR/LTV/거절사유/이의제기)"
	@echo "  make test-performance    - 성능 테스트 (ScoringEngine/JWT 응답시간)"
	@echo "  make load-test           - Locust 부하 테스트 (API 서버 필요, headless 60초)"
	@echo "  make test-integration    - 통합 테스트 (FastAPI E2E)"
	@echo "  make test-regulatory     - 규제 준수 테스트 (DSR/LTV/금리)"
	@echo "  make test-stress         - 스트레스 테스트 (금리/부동산/경기침체)"
	@echo "  make test-fairness       - 공정성 테스트 (AI 7대 원칙)"
	@echo "  make test-model          - 모델 성능 테스트 (Gini/KS/RAROC)"
	@echo "  make test-all-validation - 전체 검증 테스트 (validation/ 전체)"
	@echo "  make test-all-validation - 전체 검증 테스트 (validation/ 전체)"
	@echo "  make lint                - 코드 품질 검사 (ruff + mypy)"
	@echo "  make demo                - API 데모 시나리오 실행"
	@echo "  make install             - 의존성 설치"
	@echo ""
	@echo "  Kubernetes 배포:"
	@echo "  make k8s-deploy          - K8s 전체 리소스 배포 (namespace → configmap → db → api)"
	@echo "  make k8s-delete          - K8s 리소스 전체 삭제"
	@echo "  make k8s-status          - K8s 배포 상태 확인"
	@echo ""
	@echo "  운영 환경:"
	@echo "  make up-prod             - 운영 환경 Docker Compose 실행 (.env.prod 필요)"
	@echo "  make down-prod           - 운영 환경 종료"
	@echo "  make secrets-baseline    - .secrets.baseline 재생성 (detect-secrets)"
	@echo ""
	@echo "  포트 정보:"
	@echo "    API:         http://localhost:8000  (Swagger: /docs)"
	@echo "    Mock Server: http://localhost:8001  (/docs)"
	@echo "    pgAdmin:     http://localhost:5050"
	@echo "    MLflow:      http://localhost:5001"

up:
	docker compose up -d
	@echo "API:         http://localhost:8000  (Swagger: /docs)"
	@echo "Mock Server: http://localhost:8001  (/docs)"

up-tools:
	docker compose --profile tools up -d

up-kafka:
	docker compose --profile kafka up -d

up-ml:
	docker compose --profile ml up -d

up-prod:
	@echo "운영 환경 실행 중 (.env.prod 파일 필요)..."
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "운영 API: http://localhost:8000"

down-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

secrets-baseline:
	@echo ".secrets.baseline 재생성 중..."
	detect-secrets scan \
	    --exclude-files ".*\\.md$$" \
	    --exclude-files ".*test.*\\.py$$" \
	    --exclude-files ".*\\.example$$" \
	    > .secrets.baseline
	@echo ".secrets.baseline 생성 완료"

mock-server:
	cd "$(BASE_DIR)/mock_server" && uvicorn main:app --host 0.0.0.0 --port 8001 --reload

seed-data:
	@echo "규제 파라미터 시드 실행 중..."
	docker compose exec api python -c "\
import asyncio; \
from app.core.seed_regulation_params import seed_regulation_params; \
from app.db.session import AsyncSessionLocal; \
async def run(): \
    async with AsyncSessionLocal() as db: \
        n = await seed_regulation_params(db); \
        print(f'시드 완료: {n}건'); \
asyncio.run(run())"
	@echo "규제 파라미터 시드 완료"

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f api

logs-all:
	docker compose logs -f

status:
	@echo "서비스 상태:"
	@docker compose ps

migrate:
	docker compose exec api alembic upgrade head
	@echo "DB 마이그레이션 완료"

migrate-create:
	@read -p "마이그레이션 메시지: " msg; \
	docker compose exec api alembic revision --autogenerate -m "$$msg"

install:
	pip install -r $(BACKEND_DIR)/requirements.txt

gen-fixtures:
	$(PYTHON) mock_server/fixtures/generate_fixtures.py
	@echo "픽스처 생성 완료: mock_server/fixtures/scenario_customers.json (30개 시나리오)"

gen-synthetic:
	cd "$(ML_DIR)" && $(PYTHON) data/synthetic_data.py
	@echo "합성 데이터 생성 완료: ml_pipeline/data/synthetic_*.parquet"

train:
	@echo "Application Scorecard 학습 중..."
	cd "$(ML_DIR)" && $(PYTHON) training/train_application.py
	@echo "Behavioral Scorecard 학습 중..."
	cd "$(ML_DIR)" && $(PYTHON) training/train_behavioral.py
	@echo "Collection Scorecard 학습 중..."
	cd "$(ML_DIR)" && $(PYTHON) training/train_collection.py
	@echo "모든 모델 학습 완료. artifacts/ 폴더 확인"

test:
	@echo "전체 테스트 실행 (단위 + 통합 + 검증)..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/ validation/ -v --tb=short

test-unit:
	@echo "단위 테스트 실행..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/unit/ -v

test-auth:
	@echo "인증/RBAC 단위 테스트 실행..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/unit/test_auth.py -v

test-audit:
	@echo "내부감사 테스트 실행 (감사추적/접근통제/개인정보보호)..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/roles/internal_audit/ -v -s

test-regulatory-disclosure:
	@echo "규제공시 테스트 실행 (DSR/LTV/거절사유/스트레스DSR)..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/roles/regulatory/ -v -s

test-performance:
	@echo "성능 테스트 실행 (ScoringEngine/JWT/해시 응답시간)..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/performance/ -v -s

load-test:
	@echo "Locust 부하 테스트 실행 (API 서버가 http://localhost:8000 에서 실행 중이어야 함)..."
	locust -f tests/performance/locustfile.py \
	    --host=$${KCS_API_URL:-http://localhost:8000} \
	    --users=50 --spawn-rate=5 --run-time=60s \
	    --headless --only-summary

test-integration:
	@echo "통합 테스트 실행..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/integration/ -v -s

test-regulatory:
	@echo "규제 준수 테스트 실행 중 (DSR/LTV/금리 한도 검증)..."
	cd "$(BASE_DIR)" && $(PYTEST) tests/regulatory/ \
	    validation/roles/developer/test_regulatory_compliance.py \
	    validation/roles/risk_management/test_regulatory_validation.py -v -s

test-stress:
	@echo "스트레스 테스트 실행 중 (금리/부동산/경기침체 시나리오)..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/roles/risk_management/test_stress_scenarios.py -v -s

test-fairness:
	@echo "공정성 테스트 실행 중 (AI 가이드라인 7대 원칙)..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/roles/compliance/test_fairness.py -v -s

test-model:
	@echo "모델 성능 테스트 실행 중..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/roles/developer/test_model_performance.py \
	    validation/roles/risk_management/test_risk_profitability.py -v -s

test-all-validation:
	@echo "전체 검증 테스트 실행..."
	cd "$(BASE_DIR)" && $(PYTEST) validation/ -v -s --tb=short

k8s-deploy:
	@echo "Kubernetes 배포 시작 (kubectl 컨텍스트: $$(kubectl config current-context))..."
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/postgres-statefulset.yaml
	kubectl apply -f k8s/redis-deployment.yaml
	kubectl apply -f k8s/api-deployment.yaml
	kubectl apply -f k8s/hpa.yaml
	kubectl apply -f k8s/ingress.yaml
	@echo "배포 완료. 상태 확인: make k8s-status"

k8s-delete:
	@echo "Kubernetes 리소스 삭제 중..."
	kubectl delete namespace kcs --ignore-not-found
	@echo "삭제 완료"

k8s-status:
	@echo "=== Pod 상태 ==="
	kubectl get pods -n kcs
	@echo ""
	@echo "=== Service 상태 ==="
	kubectl get svc -n kcs
	@echo ""
	@echo "=== HPA 상태 ==="
	kubectl get hpa -n kcs

lint:
	cd "$(BACKEND_DIR)" && $(PYTHON) -m ruff check app/ && $(PYTHON) -m mypy app/ --ignore-missing-imports --explicit-package-bases

demo:
	@echo "API 데모 시나리오 실행 (API 서버가 실행 중이어야 함)..."
	bash scripts/demo_api.sh

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
