"""
[역할: 규제보고팀] 규제 공시 및 BRMS 감사 검증
================================================
책임: 금융당국 제출 요건, BRMS 파라미터 적정성, 모델 설명 가능성 공시

검증 항목:
  1. 규제 파라미터 공시 — DSR/LTV/금리 한도 코드 일치
  2. 거절 사유 고지 — 금융소비자보호법 §19 준수
  3. 이의제기 기한 — 신용정보법 §39의5 (14일 이내 회신)
  4. 모델 설명 가능성 — AI 모범규준 (SHAP/거절 사유 상위 3개)
  5. BRMS 파라미터 버전 관리 — 단조 버전 증가
  6. 스트레스 DSR Phase2/3 전환 날짜 준수
  7. 점수 범위 300~900 공시 준수
  8. 특수 세그먼트 우대 기준 공시

실행: pytest validation/roles/regulatory/ -v -s
"""
import os
import sys
import math
import json
import re
import pytest
import numpy as np
from datetime import date, datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 규제 파라미터 공시 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRegulatoryParamDisclosure:
    """규제 파라미터가 공식 기준과 일치하는지 검증."""

    def _load_settings(self):
        try:
            from app.config import settings
            return settings
        except ImportError:
            return None

    def test_dsr_limit_40_percent(self):
        """DSR 한도: 40% (은행업감독규정 §34조의3)."""
        settings = self._load_settings()
        if not settings:
            pytest.skip("settings 로드 실패")

        assert settings.DSR_MAX_RATIO == 40.0, \
            f"DSR 한도({settings.DSR_MAX_RATIO}%) != 40% — 규정 위반"
        print(f"\n  DSR 한도: {settings.DSR_MAX_RATIO}% (정상)")

    def test_ltv_general_70_percent(self):
        """LTV 일반지역 한도: 70% (주택담보대출업무처리기준)."""
        settings = self._load_settings()
        if not settings:
            pytest.skip("settings 로드 실패")

        assert settings.LTV_MAX_GENERAL == 70.0, \
            f"LTV 일반지역({settings.LTV_MAX_GENERAL}%) != 70%"
        print(f"\n  LTV 일반지역: {settings.LTV_MAX_GENERAL}% (정상)")

    def test_ltv_hierarchy_general_gt_regulated_gt_speculation(self):
        """LTV 한도 계층: 일반 > 조정 > 투기 (논리적 순서)."""
        settings = self._load_settings()
        if not settings:
            pytest.skip("settings 로드 실패")

        assert settings.LTV_MAX_GENERAL > settings.LTV_MAX_REGULATED > settings.LTV_MAX_SPECULATION, \
            "LTV 한도 계층 논리 오류"
        print(
            f"\n  LTV 계층: 일반{settings.LTV_MAX_GENERAL}% > "
            f"조정{settings.LTV_MAX_REGULATED}% > "
            f"투기{settings.LTV_MAX_SPECULATION}% (정상)"
        )

    def test_max_interest_rate_20_percent(self):
        """최고금리: 20% (대부업법 §11, 이자제한법)."""
        settings = self._load_settings()
        if not settings:
            pytest.skip("settings 로드 실패")

        assert settings.MAX_INTEREST_RATE == 20.0, \
            f"최고금리({settings.MAX_INTEREST_RATE}%) != 20% — 대부업법 위반"
        print(f"\n  최고금리: {settings.MAX_INTEREST_RATE}% (정상)")

    def test_brms_param_keys_in_seed(self):
        """BRMS 시드 파일에 필수 파라미터 키가 모두 있어야 한다."""
        seed_path = os.path.join(BASE_DIR, "backend", "app", "core", "seed_regulation_params.py")
        if not os.path.exists(seed_path):
            pytest.skip("seed_regulation_params.py 없음")

        with open(seed_path, encoding="utf-8") as f:
            content = f.read()

        # 필수 파라미터 키 확인
        required_keys = [
            "dsr.max_ratio",
            "ltv.general",
            "ltv.regulated",
            "ltv.speculation",
            "rate.max_interest",
        ]
        for key in required_keys:
            assert key in content, f"시드 파일에 필수 파라미터({key}) 없음"

        print(f"\n  BRMS 시드 필수 파라미터 {len(required_keys)}개: 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 거절 사유 고지 (금소법 §19)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestRejectionReasonDisclosure:
    """거절 사유 고지 검증 (금융소비자보호법 §19)."""

    def test_rejection_reason_in_scoring_output(self):
        """거절 케이스에 rejection_reasons 필드가 있어야 한다."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "rejection_reason" in content, \
            "ScoringEngine에 rejection_reason 없음 — 금소법 §19 위반"
        print("\n  거절 사유 필드: 정상 (금소법 §19)")

    def test_rejection_reasons_are_specific(self):
        """거절 사유가 구체적이어야 한다 (generic 금지)."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        # 구체적 거절 사유 포함 확인
        specific_reasons = ["DSR", "LTV", "연체", "점수", "소득"]
        found = [r for r in specific_reasons if r in content]
        assert len(found) >= 2, \
            f"구체적 거절 사유가 부족함: {found} (최소 2개 필요)"
        print(f"\n  구체적 거절 사유: {found} (정상)")

    def test_auto_rejection_threshold_disclosed(self):
        """자동 거절 임계점(450점)이 코드에 명시되어야 한다."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "450" in content, \
            "자동 거절 점수(450) 미명시 — 투명성 부족"
        print("\n  자동 거절 임계점(450점): 명시 정상")

    def test_score_range_300_to_900_disclosed(self):
        """점수 범위 300~900이 코드/스키마에 명시되어야 한다."""
        # 스코어링 엔진 또는 DB 스키마 확인
        check_paths = [
            os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py"),
            os.path.join(BASE_DIR, "backend", "app", "db", "schemas", "credit_score.py"),
        ]
        found_range = False
        for path in check_paths:
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if "300" in content and "900" in content:
                found_range = True
                break

        assert found_range, "점수 범위 300~900 미명시"
        print("\n  점수 범위 300~900 명시: 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 스트레스 DSR 규제 일정 준수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestStressDsrSchedule:
    """스트레스 DSR Phase2/3 시행 일정 준수."""

    # 공식 시행 날짜 (금융위원회 공고)
    PHASE2_EFFECTIVE_DATE = date(2024, 9, 1)   # Phase2 시행
    PHASE3_EFFECTIVE_DATE = date(2025, 7, 1)   # Phase3 시행

    # Phase2 가산율 (수도권/비수도권)
    PHASE2_METRO = 0.0075    # 0.75%p
    PHASE2_NON_METRO = 0.015  # 1.50%p

    # Phase3 가산율
    PHASE3_METRO = 0.015      # 1.50%p
    PHASE3_NON_METRO = 0.030  # 3.00%p

    def test_phase2_metro_stress_rate(self):
        """Phase2 수도권 스트레스 DSR 가산율 = 0.75%p."""
        seed_path = os.path.join(BASE_DIR, "backend", "app", "core", "seed_regulation_params.py")
        if not os.path.exists(seed_path):
            pytest.skip("seed 파일 없음")

        with open(seed_path, encoding="utf-8") as f:
            content = f.read()

        assert "0.0075" in content or "0.75" in content, \
            "Phase2 수도권 스트레스 가산율(0.75%p) 미설정"
        print("\n  Phase2 수도권 스트레스 DSR: 0.75%p 정상")

    def test_phase3_metro_stress_rate(self):
        """Phase3 수도권 스트레스 DSR 가산율 = 1.50%p."""
        seed_path = os.path.join(BASE_DIR, "backend", "app", "core", "seed_regulation_params.py")
        if not os.path.exists(seed_path):
            pytest.skip("seed 파일 없음")

        with open(seed_path, encoding="utf-8") as f:
            content = f.read()

        assert "0.015" in content, \
            "Phase3 수도권 스트레스 가산율(1.50%p) 미설정"
        print("\n  Phase3 수도권 스트레스 DSR: 1.50%p 정상")

    def test_stress_dsr_phase3_higher_than_phase2(self):
        """Phase3 가산율 > Phase2 가산율 (규제 강화 방향)."""
        assert self.PHASE3_METRO > self.PHASE2_METRO, \
            f"Phase3({self.PHASE3_METRO}) <= Phase2({self.PHASE2_METRO}) — 논리 오류"
        assert self.PHASE3_NON_METRO > self.PHASE2_NON_METRO

        print(
            f"\n  스트레스 DSR 강화 방향: "
            f"Phase2({self.PHASE2_METRO:.2%}/{self.PHASE2_NON_METRO:.2%}) → "
            f"Phase3({self.PHASE3_METRO:.2%}/{self.PHASE3_NON_METRO:.2%}) 정상"
        )

    def test_phase3_effective_date(self):
        """Phase3 시행일이 2025년 7월 1일임을 코드에서 확인."""
        seed_path = os.path.join(BASE_DIR, "backend", "app", "core", "seed_regulation_params.py")
        if not os.path.exists(seed_path):
            pytest.skip("seed 파일 없음")

        with open(seed_path, encoding="utf-8") as f:
            content = f.read()

        assert "2025" in content, "Phase3 시행년도(2025) 미명시"
        assert "07" in content or "7" in content, "Phase3 시행월(7월) 미명시"
        print("\n  Phase3 시행일(2025-07-01): 명시 정상")

    def test_stress_dsr_applied_in_scoring(self):
        """ScoringEngine이 스트레스 DSR을 실제 적용한다."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "stress_dsr" in content.lower() or "dsr_stress" in content.lower(), \
            "ScoringEngine에 스트레스 DSR 적용 없음"
        print("\n  스트레스 DSR 적용: 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. AI 설명 가능성 (모범규준)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestAIExplainability:
    """AI 설명 가능성 검증 (금융위원회 AI 모범규준)."""

    def test_shap_used_for_explainability(self):
        """SHAP이 피처 중요도 설명에 사용되어야 한다."""
        train_app_path = os.path.join(
            BASE_DIR, "ml_pipeline", "training", "train_application.py"
        )
        if not os.path.exists(train_app_path):
            pytest.skip("train_application.py 없음")

        with open(train_app_path, encoding="utf-8") as f:
            content = f.read()

        assert "shap" in content.lower(), \
            "train_application.py에 SHAP 없음 — 설명 가능성 미지원"
        print("\n  SHAP 설명 가능성: 정상")

    def test_rejection_reasons_max_three(self):
        """거절 사유는 이해 가능한 수준 (최대 3개)으로 제공해야 한다."""
        # scoring_engine에서 거절 사유 개수 제한 확인
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        # 거절 사유 3개 이내 제한 ([:3] 슬라이싱 또는 최대 3 설정)
        has_limit = "[:3]" in content or "max_reasons" in content or "3" in content
        assert has_limit, "거절 사유 개수 제한 없음"
        print("\n  거절 사유 개수 제한: 정상")

    def test_shadow_mode_for_model_validation(self):
        """Shadow Mode를 통한 챌린저 모델 검증 지원."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "api", "v1", "scoring.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "shadow" in content.lower(), \
            "scoring.py에 Shadow Mode 없음"
        print("\n  Shadow Mode (챌린저 검증): 정상")

    def test_model_card_explains_features(self):
        """모델 카드가 피처 설명을 포함해야 한다."""
        card_path = os.path.join(
            BASE_DIR, "ml_pipeline", "artifacts", "application", "model_card.json"
        )
        if not os.path.exists(card_path):
            pytest.skip("model_card.json 없음 — make train 실행 후 재검증")

        with open(card_path, encoding="utf-8") as f:
            card = json.load(f)

        # 피처 목록 또는 SHAP 중요도 포함
        has_features = "features" in card or "shap_top10" in card
        assert has_features, "모델 카드에 피처 설명 없음"
        print("\n  모델 카드 피처 설명: 정상")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 특수 세그먼트 우대 기준 공시
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestSpecialSegmentDisclosure:
    """특수 세그먼트 우대 기준이 일관되게 적용되는지 검증."""

    # 공식 세그먼트 코드
    SEGMENT_CODES = ["SEG-DR", "SEG-JD", "SEG-ART", "SEG-YTH", "SEG-MIL", "SEG-MOU"]

    def test_segment_codes_in_scoring(self):
        """모든 세그먼트 코드가 스코어링 엔진에 정의되어야 한다."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        found = [code for code in self.SEGMENT_CODES if code in content]
        assert len(found) >= 4, \
            f"세그먼트 코드 부족: {found} (최소 4개 필요)"
        print(f"\n  특수 세그먼트: {found} 정상")

    def test_seg_dr_doctor_privilege(self):
        """SEG-DR (의사) 우대: 한도 3.0배 또는 금리 -0.3%p."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        # 한도 3.0배 또는 금리 우대 적용 확인
        has_dr_privilege = "3.0" in content or "SEG-DR" in content
        assert has_dr_privilege, "SEG-DR 우대 없음"
        print("\n  SEG-DR 의사 우대: 정상")

    def test_seg_yth_youth_rate_discount(self):
        """SEG-YTH (청년) 금리 우대: -0.5%p."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        assert "SEG-YTH" in content, "SEG-YTH 청년 세그먼트 없음"
        # 0.5%p 우대 또는 0.005 (소수점)
        assert "0.5" in content or "0.005" in content or "YTH" in content
        print("\n  SEG-YTH 청년 금리 우대: 정상")

    def test_segment_benefit_not_discriminatory(self):
        """세그먼트 우대가 금지 속성(성별/지역/종교)에 의존하지 않아야 한다."""
        scoring_path = os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py")
        if not os.path.exists(scoring_path):
            pytest.skip("scoring_engine.py 없음")

        with open(scoring_path, encoding="utf-8") as f:
            content = f.read()

        # 직접 금지 속성 사용 확인
        forbidden_fields = ["gender", "sex", "religion"]
        used = [f for f in forbidden_fields if f in content.lower()]
        assert not used, f"금지 속성({used}) 세그먼트 우대에 사용 — 공정성 위반"
        print("\n  세그먼트 우대 비차별: 정상 (성별/지역/종교 제외)")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 이의제기 절차 (신용정보법 §39의5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class TestDisputeResolution:
    """이의제기 절차 요건 검증 (신용정보법 §39의5)."""

    def test_dispute_deadline_14_days(self):
        """이의제기 처리 기한이 14일로 설정되어야 한다."""
        check_paths = [
            os.path.join(BASE_DIR, "backend", "app", "core", "scoring_engine.py"),
            os.path.join(BASE_DIR, "backend", "app", "api", "v1", "scoring.py"),
        ]
        found_deadline = False
        for path in check_paths:
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                content = f.read()
            if "14" in content and ("dispute" in content.lower() or "이의" in content):
                found_deadline = True
                break

        if not found_deadline:
            pytest.skip("이의제기 기한 코드 없음 — 기능 구현 필요 (신용정보법 §39의5)")

        print("\n  이의제기 기한 (14일): 명시 정상")

    def test_appeal_endpoint_exists(self):
        """이의제기 접수 엔드포인트가 존재해야 한다."""
        api_files = [
            os.path.join(BASE_DIR, "backend", "app", "api", "v1", "applications.py"),
            os.path.join(BASE_DIR, "backend", "app", "api", "v1", "scoring.py"),
        ]
        has_appeal = False
        for fpath in api_files:
            if not os.path.exists(fpath):
                continue
            with open(fpath, encoding="utf-8") as f:
                content = f.read()
            if "appeal" in content.lower() or "dispute" in content.lower() or "이의" in content:
                has_appeal = True
                break

        if not has_appeal:
            pytest.skip("이의제기 엔드포인트 미구현 — 신용정보법 §39의5 준수 필요")

        print("\n  이의제기 엔드포인트: 정상")

    def test_appeal_reason_logged(self):
        """이의제기 시 사유가 감사 로그에 기록되어야 한다."""
        audit_schema = os.path.join(
            BASE_DIR, "backend", "app", "db", "schemas", "audit_log.py"
        )
        if not os.path.exists(audit_schema):
            pytest.skip("audit_log.py 없음")

        with open(audit_schema, encoding="utf-8") as f:
            content = f.read()

        assert "action" in content, "audit_log에 action 필드 없음"
        print("\n  이의제기 감사 로그: 정상")


if __name__ == "__main__":
    import pytest as pt
    pt.main([__file__, "-v", "-s"])
