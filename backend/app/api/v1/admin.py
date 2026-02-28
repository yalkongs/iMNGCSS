"""
관리자 API (규제 파라미터 관리 - BRMS)
=======================================
규제 파라미터 조회/등록/비활성화.
변경 이력 감사 추적.

접근 제어:
  GET  (조회)  → 인증 불필요 (데모 편의)
  POST (등록)  → risk_manager 역할 필요
  DELETE       → risk_manager 역할 필요
"""
import uuid
import logging
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.policy_engine import PolicyEngine
from app.core.auth import require_role

router = APIRouter()
logger = logging.getLogger(__name__)


class ParamCreateRequest(BaseModel):
    param_key: str = Field(..., description="파라미터 키 (예: stress_dsr.metropolitan.variable)")
    param_category: str = Field(..., description="카테고리: dsr | ltv | rate | limit | eq_grade | irg | segment")
    phase_label: str | None = None
    param_value: dict = Field(..., description="파라미터 값 JSONB")
    condition_json: dict | None = None
    effective_from: datetime = Field(..., description="시행일")
    effective_to: datetime | None = None
    legal_basis: str | None = None
    description: str | None = None
    change_reason: str = Field(..., description="변경 사유 (감사 추적)")
    approved_by: str = Field(..., description="승인자 ID (4-eyes 원칙)")


@router.get("/regulation-params")
async def list_regulation_params(
    param_category: str | None = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """현재 활성화된 규제 파라미터 목록 조회"""
    from app.db.schemas.regulation_params import RegulationParam
    from sqlalchemy import and_

    conditions = [RegulationParam.is_active == is_active]
    if param_category:
        conditions.append(RegulationParam.param_category == param_category)

    stmt = (
        select(RegulationParam)
        .where(and_(*conditions))
        .order_by(RegulationParam.param_category, RegulationParam.param_key)
    )
    result = await db.execute(stmt)
    params = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "param_key": p.param_key,
            "param_category": p.param_category,
            "phase_label": p.phase_label,
            "param_value": p.param_value,
            "condition_json": p.condition_json,
            "effective_from": p.effective_from.isoformat() if p.effective_from else None,
            "effective_to": p.effective_to.isoformat() if p.effective_to else None,
            "legal_basis": p.legal_basis,
            "description": p.description,
            "is_active": p.is_active,
            "approved_by": p.approved_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in params
    ]


@router.post("/regulation-params", status_code=201)
async def create_regulation_param(
    request: ParamCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_role("risk_manager")),
):
    """
    규제 파라미터 신규 등록.
    4-eyes 원칙: approved_by 필수.
    """
    from app.db.schemas.regulation_params import RegulationParam

    new_param = RegulationParam(
        id=uuid.uuid4(),
        param_key=request.param_key,
        param_category=request.param_category,
        phase_label=request.phase_label,
        param_value=request.param_value,
        condition_json=request.condition_json,
        effective_from=request.effective_from,
        effective_to=request.effective_to,
        legal_basis=request.legal_basis,
        description=request.description,
        is_active=True,
        created_by=_["username"],
        approved_by=request.approved_by,
        approved_at=datetime.utcnow(),
        change_reason=request.change_reason,
    )
    db.add(new_param)
    await db.commit()

    # Redis 캐시 무효화
    pe = PolicyEngine(db)
    await pe.invalidate_cache(request.param_key)

    logger.info(
        f"규제 파라미터 등록: key={request.param_key}, "
        f"effective_from={request.effective_from}, "
        f"approved_by={request.approved_by}"
    )

    return {
        "id": str(new_param.id),
        "param_key": new_param.param_key,
        "status": "created",
        "message": "규제 파라미터가 등록되었습니다. 캐시가 무효화되었습니다.",
    }


@router.delete("/regulation-params/{param_id}")
async def deactivate_regulation_param(
    param_id: str,
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_role("risk_manager")),
):
    """규제 파라미터 비활성화 (삭제가 아닌 이력 보존)"""
    from app.db.schemas.regulation_params import RegulationParam

    stmt = select(RegulationParam).where(RegulationParam.id == uuid.UUID(param_id))
    result = await db.execute(stmt)
    param = result.scalar_one_or_none()

    if not param:
        raise HTTPException(status_code=404, detail="파라미터를 찾을 수 없습니다.")

    param.is_active = False
    param.effective_to = datetime.utcnow()
    param.change_reason = f"[비활성화] {reason} (요청자: {current_user['username']})"
    await db.commit()

    # 캐시 무효화
    pe = PolicyEngine(db)
    await pe.invalidate_cache(param.param_key)

    return {"status": "deactivated", "param_key": param.param_key}


@router.get("/eq-grade-master")
async def list_eq_grade_master(
    db: AsyncSession = Depends(get_db),
):
    """EQ Grade 마스터 조회"""
    from app.db.schemas.regulation_params import EqGradeMaster

    stmt = select(EqGradeMaster).where(EqGradeMaster.is_active == True)  # noqa
    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "id": str(item.id),
            "employer_name": item.employer_name,
            "eq_grade": item.eq_grade,
            "limit_multiplier": item.limit_multiplier,
            "rate_adjustment": item.rate_adjustment,
            "mou_code": item.mou_code,
            "mou_special_rate": item.mou_special_rate,
        }
        for item in items
    ]


@router.get("/irg-master")
async def list_irg_master(
    db: AsyncSession = Depends(get_db),
):
    """IRG 마스터 조회"""
    from app.db.schemas.regulation_params import IrgMaster

    stmt = select(IrgMaster).where(IrgMaster.is_active == True)  # noqa
    result = await db.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "ksic_code": item.ksic_code,
            "industry_name": item.industry_name,
            "irg_grade": item.irg_grade,
            "pd_adjustment": item.pd_adjustment,
        }
        for item in items
    ]
