from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Tenant, TenantSchedule


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
