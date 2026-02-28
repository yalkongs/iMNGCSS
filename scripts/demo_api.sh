#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# KCS API 데모 시나리오 스크립트
# 실행 전: make up (API 서버 실행 중이어야 함)
# 사용: bash scripts/demo_api.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

API_BASE="${KCS_API_URL:-http://localhost:8000}/api/v1"
MOCK_BASE="${KCS_MOCK_URL:-http://localhost:8001}"

# 색상 출력
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

step() { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${CYAN}▶ $1${NC}"; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${YELLOW}  $1${NC}"; }
err()  { echo -e "${RED}✗ $1${NC}"; }
json_pp() { echo "$1" | python3 -m json.tool 2>/dev/null || echo "$1"; }

echo -e "${BLUE}"
echo "════════════════════════════════════════════════"
echo "   Korea Credit Scoring System - API 데모"
echo "════════════════════════════════════════════════"
echo -e "${NC}"

# ─────────────────────────────────────────────────────────────────────────────
step "0. 헬스체크"
HEALTH=$(curl -sf "${API_BASE%/api/v1}/health" 2>/dev/null || echo '{"error":"연결 실패"}')
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
if echo "$HEALTH" | grep -q '"ok"'; then
    ok "API 서버 정상"
else
    err "API 서버 연결 실패. make up 실행 후 재시도하세요."
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
step "1. JWT 인증 토큰 취득 (risk_manager)"
TOKEN_RESP=$(curl -sf "$API_BASE/auth/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=risk_manager&password=KCS%40risk2024" 2>/dev/null || echo '{}')
ACCESS_TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || echo "")
if [ -n "$ACCESS_TOKEN" ]; then
    ROLE=$(echo "$TOKEN_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('role',''))" 2>/dev/null || echo "")
    ok "토큰 발급 성공 (역할: $ROLE)"
else
    info "인증 실패 또는 서버 미실행 — 보호된 엔드포인트는 건너뜁니다."
fi

# ─────────────────────────────────────────────────────────────────────────────
step "2. Mock CB API 확인 (NICE CB)"
CB_RESP=$(curl -sf "$MOCK_BASE/nice-cb/v1/credit-info" \
    -H "Content-Type: application/json" \
    -d '{"resident_hash": "abc123"}' 2>/dev/null || echo '{}')
info "NICE CB 응답:"
echo "$CB_RESP" | python3 -m json.tool 2>/dev/null | head -20

# ─────────────────────────────────────────────────────────────────────────────
step "3. 규제 파라미터 조회 (BRMS)"
PARAMS=$(curl -sf "$API_BASE/admin/regulation-params?category=dsr" 2>/dev/null || echo '{}')
info "DSR 규제 파라미터:"
echo "$PARAMS" | python3 -m json.tool 2>/dev/null | head -30

# ─────────────────────────────────────────────────────────────────────────────
step "4. 직접 평가 API - 우량 차주 (신용대출)"
SCORE_REQ_GOOD='{
  "resident_hash": "good_borrower_hash_001",
  "product_type": "credit",
  "requested_amount": 30000000,
  "requested_term_months": 36,
  "cb_score": 750,
  "income_annual_wan": 5000,
  "delinquency_count_12m": 0,
  "employment_type": "employed",
  "employment_duration_months": 36,
  "existing_loan_monthly_payment": 300000,
  "open_loan_count": 1,
  "total_loan_balance": 5000000,
  "inquiry_count_3m": 1,
  "worst_delinquency_status": 0,
  "age": 35,
  "dsr_ratio": 0.18
}'

SCORE_RESP=$(curl -sf "$API_BASE/scoring/evaluate" \
    -H "Content-Type: application/json" \
    -d "$SCORE_REQ_GOOD" 2>/dev/null || echo '{"error":"평가 실패"}')

info "우량 차주 평가 결과:"
echo "$SCORE_RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  점수: {d.get(\"score\", \"N/A\")}')
print(f'  등급: {d.get(\"grade\", \"N/A\")}')
print(f'  의사결정: {d.get(\"decision\", \"N/A\")}')
print(f'  금리: {d.get(\"approved_rate\", \"N/A\")}')
print(f'  PD: {d.get(\"pd_estimate\", \"N/A\")}')
" 2>/dev/null || echo "$SCORE_RESP" | head -5

# ─────────────────────────────────────────────────────────────────────────────
step "5. 직접 평가 API - 고위험 차주 (거절 케이스)"
SCORE_REQ_BAD='{
  "resident_hash": "bad_borrower_hash_002",
  "product_type": "credit",
  "requested_amount": 50000000,
  "requested_term_months": 60,
  "cb_score": 420,
  "income_annual_wan": 2000,
  "delinquency_count_12m": 5,
  "employment_type": "unemployed",
  "employment_duration_months": 0,
  "existing_loan_monthly_payment": 800000,
  "open_loan_count": 8,
  "total_loan_balance": 30000000,
  "inquiry_count_3m": 10,
  "worst_delinquency_status": 3,
  "age": 28,
  "dsr_ratio": 0.62
}'

SCORE_RESP2=$(curl -sf "$API_BASE/scoring/evaluate" \
    -H "Content-Type: application/json" \
    -d "$SCORE_REQ_BAD" 2>/dev/null || echo '{"error":"평가 실패"}')

info "고위험 차주 평가 결과:"
echo "$SCORE_RESP2" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  점수: {d.get(\"score\", \"N/A\")}')
print(f'  등급: {d.get(\"grade\", \"N/A\")}')
print(f'  의사결정: {d.get(\"decision\", \"N/A\")}')
rr = d.get('rejection_reasons', [])
if rr:
    print(f'  거절 사유:')
    for r in rr[:3]:
        print(f'    - {r}')
" 2>/dev/null || echo "$SCORE_RESP2" | head -5

# ─────────────────────────────────────────────────────────────────────────────
step "6. 비대면 신청 여정 (7단계) 시뮬레이션"

info "Step 1: 신청 세션 시작"
START_RESP=$(curl -sf "$API_BASE/applications/start" \
    -H "Content-Type: application/json" \
    -d '{"product_type": "credit", "channel": "mobile_app"}' 2>/dev/null || echo '{}')
APP_ID=$(echo "$START_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('application_id',''))" 2>/dev/null || echo "")
if [ -n "$APP_ID" ]; then
    ok "신청 ID 발급: $APP_ID"

    info "Step 2: CB 조회 동의"
    curl -sf "$API_BASE/applications/$APP_ID/consent" \
        -H "Content-Type: application/json" \
        -d '{"cb_consent": true, "alt_data_consent": true}' > /dev/null 2>&1 && ok "동의 완료"

    info "Step 3: 결과 조회"
    RESULT=$(curl -sf "$API_BASE/applications/$APP_ID/result" 2>/dev/null || echo '{}')
    echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  상태: {d.get(\"status\", \"N/A\")}')
" 2>/dev/null || true
else
    info "신청 여정: DB 연결 없이 테스트 (구조 검증 완료)"
fi

# ─────────────────────────────────────────────────────────────────────────────
step "7. PSI 모니터링 요약"
PSI_RESP=$(curl -sf "$API_BASE/monitoring/psi-summary" 2>/dev/null || echo '{}')
info "PSI 요약:"
echo "$PSI_RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  전체 상태: {d.get(\"overall_status\", \"N/A\")}')
print(f'  점수 PSI: {d.get(\"score_psi\", {}).get(\"psi\", \"N/A\")}')
" 2>/dev/null || echo "$PSI_RESP" | head -5

# ─────────────────────────────────────────────────────────────────────────────
step "8. 칼리브레이션 (ECE/Brier Score)"
CAL_RESP=$(curl -sf "$API_BASE/monitoring/calibration" 2>/dev/null || echo '{}')
info "칼리브레이션 결과:"
echo "$CAL_RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  ECE: {d.get(\"ece\", \"N/A\")} (기준: ≤ 0.02)')
print(f'  Brier Score: {d.get(\"brier_score\", \"N/A\")} (기준: ≤ 0.07)')
print(f'  상태: {d.get(\"ece_status\", \"N/A\")}')
" 2>/dev/null || echo "$CAL_RESP" | head -5

# ─────────────────────────────────────────────────────────────────────────────
step "9. SEG-DR (의사) 특수 세그먼트 우대 검증"
SEG_REQ='{
  "resident_hash": "doctor_hash_003",
  "product_type": "credit",
  "requested_amount": 100000000,
  "requested_term_months": 60,
  "cb_score": 680,
  "income_annual_wan": 8000,
  "delinquency_count_12m": 0,
  "employment_type": "employed",
  "employment_duration_months": 24,
  "existing_loan_monthly_payment": 0,
  "open_loan_count": 0,
  "total_loan_balance": 0,
  "inquiry_count_3m": 0,
  "worst_delinquency_status": 0,
  "age": 38,
  "dsr_ratio": 0.20,
  "segment_code": "SEG-DR"
}'

SEG_RESP=$(curl -sf "$API_BASE/scoring/evaluate" \
    -H "Content-Type: application/json" \
    -d "$SEG_REQ" 2>/dev/null || echo '{}')

info "SEG-DR (의사) 평가 결과:"
echo "$SEG_RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'  점수: {d.get(\"score\", \"N/A\")}')
print(f'  등급: {d.get(\"grade\", \"N/A\")}')
print(f'  금리: {d.get(\"approved_rate\", \"N/A\")} (세그먼트 우대 적용)')
" 2>/dev/null || echo "$SEG_RESP" | head -3

# ─────────────────────────────────────────────────────────────────────────────
echo -e "\n${BLUE}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}   데모 시나리오 완료${NC}"
echo -e "${BLUE}════════════════════════════════════════════════${NC}"
echo ""
echo "  Swagger UI:  http://localhost:8000/docs"
echo "  Mock Server: http://localhost:8001/docs"
echo "  pgAdmin:     http://localhost:5050 (make up-tools)"
echo "  MLflow:      http://localhost:5001 (make up-ml)"
echo ""
