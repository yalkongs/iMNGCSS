"""
설정 및 규제 파라미터
금융감독원·금융위원회 기준 하드코딩된 규제값 + 환경 변수 설정
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    PROJECT_NAME: str = "Korea Credit Scoring System"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "dev-secret-key-CHANGE-IN-PRODUCTION"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://kcs_user:kcs_pass@localhost:5432/kcs_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # ----------------------------------------------------------------
    # 규제 파라미터 - 은행업 감독규정 / 금융감독원 기준
    # ----------------------------------------------------------------

    # LTV 한도 (주택담보대출, %)
    LTV_MAX_GENERAL: float = 70.0        # 일반 지역
    LTV_MAX_REGULATED: float = 60.0      # 조정대상지역
    LTV_MAX_SPECULATION: float = 40.0    # 투기과열지구

    # DSR 한도 (전체 가계대출, %)
    DSR_MAX_RATIO: float = 40.0

    # DTI 한도 (주택담보대출, %)
    DTI_MAX_RATIO: float = 60.0

    # 신용대출 한도 배수 (연소득 대비)
    CREDIT_LOAN_INCOME_MULTIPLIER: float = 1.5

    # 소액마이크로론 최대 한도 (원)
    MICRO_LOAN_MAX_AMOUNT: float = 30_000_000  # 3,000만원

    # 최고금리 (대부업법, %)
    MAX_INTEREST_RATE: float = 20.0

    # 기준금리 (한국은행 기준금리, %)
    BASE_RATE: float = 3.5

    # ----------------------------------------------------------------
    # 신용등급 → PD 매핑 (바젤III IRB 내부 기준)
    # ----------------------------------------------------------------
    GRADE_PD_MAP: dict = {
        "AAA": 0.0005,
        "AA": 0.0010,
        "A":  0.0030,
        "BBB": 0.0100,
        "BB": 0.0300,
        "B":  0.0700,
        "CCC": 0.1500,
        "CC": 0.3000,
        "C":  0.5000,
        "D":  1.0000,
    }

    # LGD 기본값 (무담보: 45%, 주담대: 25%)
    LGD_UNSECURED: float = 0.45
    LGD_MORTGAGE: float = 0.25
    LGD_MICRO: float = 0.60

    # ----------------------------------------------------------------
    # 모델 설정
    # ----------------------------------------------------------------
    MODEL_ARTIFACTS_PATH: str = "./artifacts"

    # ----------------------------------------------------------------
    # 모니터링 임계값
    # ----------------------------------------------------------------
    PSI_WARNING_THRESHOLD: float = 0.1
    PSI_CRITICAL_THRESHOLD: float = 0.2
    GINI_MIN_THRESHOLD: float = 0.3

    # ----------------------------------------------------------------
    # 감사 로그 보존 기간 (신용정보법: 5년)
    # ----------------------------------------------------------------
    AUDIT_LOG_RETENTION_YEARS: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
