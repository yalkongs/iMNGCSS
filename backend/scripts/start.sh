#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# KCS API 서버 시작 스크립트
# 순서: DB 마이그레이션 → 서버 실행
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "=================================================="
echo "Korea Credit Scoring System - API 서버 시작"
echo "환경: ${ENVIRONMENT:-development}"
echo "=================================================="

# ── 운영 환경: Alembic 마이그레이션 ──────────────────────────────────────
# 개발 환경에서는 main.py lifespan에서 create_all()을 직접 실행하므로 건너뜀
if [ "${ENVIRONMENT}" = "production" ] || [ "${ENVIRONMENT}" = "staging" ]; then
    echo "[DB] Alembic 마이그레이션 실행 중..."
    alembic upgrade head
    echo "[DB] 마이그레이션 완료"
else
    echo "[DB] 개발 환경 - create_all() 방식 사용 (lifespan에서 자동 실행)"
fi

# ── 서버 시작 ─────────────────────────────────────────────────────────────
if [ "${ENVIRONMENT}" = "production" ]; then
    echo "[서버] Production 모드 (workers=4, no-reload)"
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "${API_PORT:-8000}" \
        --workers 4 \
        --log-level info
else
    echo "[서버] Development 모드 (reload 활성화)"
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "${API_PORT:-8000}" \
        --reload \
        --log-level debug
fi
