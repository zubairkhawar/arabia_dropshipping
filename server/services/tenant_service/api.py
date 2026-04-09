from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import Agent, Tenant, TenantSchedule
from services.auth_service.api import get_current_user
from services.auth_service.models import User

router = APIRouter()


@router.get("/")
async def list_tenants(db: Session = Depends(get_db)):
    """List all tenants (admin only)"""
    tenants = db.query(Tenant).all()
    return tenants


@router.post("/")
async def create_tenant():
    """Create a new tenant (placeholder)"""
    return {"message": "Create tenant endpoint"}


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: int, db: Session = Depends(get_db)):
    """Get tenant details"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.put("/{tenant_id}")
async def update_tenant(tenant_id: int):
    """Update tenant (placeholder)"""
    return {"message": f"Update tenant {tenant_id} endpoint"}


@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: int):
    """Delete tenant (placeholder)"""
    return {"message": f"Delete tenant {tenant_id} endpoint"}


class SchedulePayload(BaseModel):
    working_days: list[int]
    start_time: str
    end_time: str


class TenantDisplayTimezonePayload(BaseModel):
    display_timezone: str


class AgentManagementOut(BaseModel):
    max_concurrent_chats_per_agent: int


class AgentManagementPatch(BaseModel):
    max_concurrent_chats_per_agent: int = Field(ge=1, le=100)


def _require_tenant_admin(current_user: User, tenant_id: int) -> None:
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admin can manage this setting",
        )
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )


@router.get("/{tenant_id}/agent-management", response_model=AgentManagementOut)
async def get_agent_management(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Max concurrent customer chats per agent (tenant default, synced to all agents).
    """
    _require_tenant_admin(current_user, tenant_id)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    cap = getattr(tenant, "max_concurrent_chats_per_agent", None)
    if cap is None:
        cap = 5
    return AgentManagementOut(max_concurrent_chats_per_agent=int(cap))


@router.patch("/{tenant_id}/agent-management", response_model=AgentManagementOut)
async def patch_agent_management(
    tenant_id: int,
    payload: AgentManagementPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set tenant-wide max concurrent chats and apply to every agent in the tenant.
    """
    _require_tenant_admin(current_user, tenant_id)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.max_concurrent_chats_per_agent = payload.max_concurrent_chats_per_agent
    db.add(tenant)
    db.query(Agent).filter(Agent.tenant_id == tenant_id).update(
        {Agent.max_concurrent_chats: payload.max_concurrent_chats_per_agent},
        synchronize_session=False,
    )
    db.commit()
    db.refresh(tenant)
    return AgentManagementOut(
        max_concurrent_chats_per_agent=int(tenant.max_concurrent_chats_per_agent),
    )


class TenantDisplayTimezoneOut(BaseModel):
    display_timezone: str


@router.get("/{tenant_id}/display-timezone", response_model=TenantDisplayTimezoneOut)
async def get_tenant_display_timezone(
    tenant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Current saved display timezone for the tenant (any member of that tenant may read).
    """
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    raw = getattr(tenant, "display_timezone", None) or "Asia/Karachi"
    cleaned = raw.strip() if isinstance(raw, str) else "Asia/Karachi"
    return TenantDisplayTimezoneOut(display_timezone=cleaned or "Asia/Karachi")


def _validate_iana_timezone(tz: str) -> str:
    cleaned = (tz or "").strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="display_timezone is required",
        )
    try:
        ZoneInfo(cleaned)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IANA timezone: {cleaned}",
        ) from exc
    return cleaned


@router.patch("/{tenant_id}/display-timezone")
async def patch_tenant_display_timezone(
    tenant_id: int,
    payload: TenantDisplayTimezonePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Admin only: set tenant-wide display timezone (messages, attendance labels, etc.).
    """
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admin can change display timezone",
        )
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.display_timezone = _validate_iana_timezone(payload.display_timezone)
    db.commit()
    db.refresh(tenant)
    return {"display_timezone": tenant.display_timezone}


@router.get("/{tenant_id}/schedule", response_model=SchedulePayload)
async def get_schedule(tenant_id: int, db: Session = Depends(get_db)):
    """
    Get working days and hours for a tenant.
    """
    sched = (
        db.query(TenantSchedule)
        .filter(TenantSchedule.tenant_id == tenant_id)
        .first()
    )
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not configured")
    return SchedulePayload(
        working_days=sched.working_days,
        start_time=sched.start_time,
        end_time=sched.end_time,
    )


@router.put("/{tenant_id}/schedule", response_model=SchedulePayload)
async def put_schedule(
    tenant_id: int,
    payload: SchedulePayload,
    db: Session = Depends(get_db),
):
    """
    Upsert working days and hours for a tenant.
    """
    sched = (
        db.query(TenantSchedule)
        .filter(TenantSchedule.tenant_id == tenant_id)
        .first()
    )
    if not sched:
        sched = TenantSchedule(
            tenant_id=tenant_id,
            working_days=payload.working_days,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        db.add(sched)
    else:
        sched.working_days = payload.working_days
        sched.start_time = payload.start_time
        sched.end_time = payload.end_time
    db.commit()
    return payload
