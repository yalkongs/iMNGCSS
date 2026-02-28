"""
KCS 외부 API Mock Server
===================================
실제 외부 시스템 대신 사용하는 가상 API 서버.
모든 응답은 사전 생성된 mock 데이터 기반.

포함 API:
  /api/cb/nice    - NICE 개인 신용정보 (CB)
  /api/cb/kcb     - KCB 개인 신용정보 (CB)
  /api/nts        - 국세청 소득/사업자 정보
  /api/nhis       - 건강보험공단 소득/가입자 정보
  /api/biz_credit - 기업 신용정보 (NICE/KCB 사업자)
  /api/mydata     - 금융결제원 마이데이터
  /api/art_fund   - 예술인복지재단 등록 확인
  /api/profession - 전문직 면허 검증 (의사/변호사)

실행: uvicorn mock_server.main:app --port 8001
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mock_server.routers import cb_nice, cb_kcb, nts, nhis, biz_credit, mydata, profession

app = FastAPI(
    title="KCS External API Mock Server",
    description="한국 신용평가 시스템 외부 API 가상 인터페이스",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(cb_nice.router, prefix="/api/cb/nice", tags=["NICE CB"])
app.include_router(cb_kcb.router, prefix="/api/cb/kcb", tags=["KCB CB"])
app.include_router(nts.router, prefix="/api/nts", tags=["국세청"])
app.include_router(nhis.router, prefix="/api/nhis", tags=["건강보험공단"])
app.include_router(biz_credit.router, prefix="/api/biz_credit", tags=["기업신용정보"])
app.include_router(mydata.router, prefix="/api/mydata", tags=["마이데이터"])
app.include_router(profession.router, prefix="/api/profession", tags=["전문직 면허"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kcs-mock-server"}


@app.get("/")
async def root():
    return {
        "service": "KCS External API Mock Server",
        "endpoints": [
            "/api/cb/nice/credit-info",
            "/api/cb/kcb/credit-info",
            "/api/nts/income",
            "/api/nts/business",
            "/api/nhis/income",
            "/api/biz_credit/company",
            "/api/mydata/assets",
            "/api/profession/license",
        ],
    }
