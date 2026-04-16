import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import hydrate_openai_api_key_from_db, settings, set_openai_api_key_override
from database import SessionLocal, engine, get_db
from models import Agent, Tenant, TenantSchedule, User
from services.auth_service.api import get_current_user
from services.auth_service.services import get_password_hash

router = APIRouter()
logger = logging.getLogger(__name__)

# PostGIS / system-ish tables that may appear in public schema — never truncate these.
_PG_PUBLIC_SKIP_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "geography_columns",
        "geometry_columns",
        "raster_columns",
        "raster_overviews",
    }
)


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


class EraseAllApplicationDataIn(BaseModel):
    """Must match exactly (case-sensitive) to run the destructive erase."""

    confirmation: str = Field(..., min_length=1, max_length=64)


def _public_tables_to_truncate() -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        ).fetchall()
    names = [r[0] for r in rows if r[0] not in _PG_PUBLIC_SKIP_TABLES]
    return names


def _truncate_all_public_tables() -> int:
    names = _public_tables_to_truncate()
    if not names:
        return 0
    quoted = ", ".join(f'"{n}"' for n in names)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
    return len(names)


def _reseed_default_tenant_and_admin(db: Session) -> dict:
    """
    Recreate tenant id=1, default online schedule, and bootstrap admin from env
    (same spirit as main.ensure_admin_user).
    """
    admin_created = False
    tenant = db.query(Tenant).filter(Tenant.id == 1).first()
    if tenant is None:
        tenant = Tenant(
            id=1,
            name="Default Tenant",
            domain=None,
            display_timezone="Asia/Karachi",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(tenant)
    else:
        tenant.name = "Default Tenant"
        tenant.domain = None
        tenant.display_timezone = "Asia/Karachi"
        tenant.is_active = True
        tenant.updated_at = datetime.utcnow()

    sched = db.query(TenantSchedule).filter(TenantSchedule.tenant_id == 1).first()
    if sched is None:
        db.add(
            TenantSchedule(
                tenant_id=1,
                working_days=[1, 2, 3, 4, 5, 6],
                start_time="09:00",
                end_time="18:00",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    else:
        sched.working_days = [1, 2, 3, 4, 5, 6]
        sched.start_time = "09:00"
        sched.end_time = "18:00"
        sched.updated_at = datetime.utcnow()

    if settings.admin_email and settings.admin_password:
        existing = db.query(User).filter(User.email == settings.admin_email).first()
        if existing is None:
            db.add(
                User(
                    tenant_id=1,
                    email=settings.admin_email,
                    full_name="Arabia Admin",
                    role="admin",
                    hashed_password=get_password_hash(settings.admin_password),
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            admin_created = True

    db.commit()
    return {"admin_recreated": admin_created}


@router.post("/{tenant_id}/erase-all-application-data")
async def erase_all_application_data(
    tenant_id: int,
    payload: EraseAllApplicationDataIn,
    current_user: User = Depends(get_current_user),
):
    """
    Nuclear option for staging / QA: truncate every application table in `public`,
    then recreate default tenant (id=1), default schedule, and admin user from env.

    Requires tenant admin JWT and exact confirmation phrase.
    Only supported on PostgreSQL. R2 / Cloudflare must be cleared separately.
    """
    _require_tenant_admin(current_user, tenant_id)
    if (payload.confirmation or "").strip() != "ERASE_ALL_DATA":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation must be exactly "ERASE_ALL_DATA"',
        )
    raw_url = (settings.database_url or "").lower()
    if not (raw_url.startswith("postgresql") or raw_url.startswith("postgres://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erase is only supported for PostgreSQL (Render Postgres)",
        )
    if not settings.admin_email or not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set ADMIN_EMAIL and ADMIN_PASSWORD on the server before using erase "
            "(they are used to recreate the admin user).",
        )

    try:
        n_tables = _truncate_all_public_tables()
    except Exception as exc:
        logger.exception("erase-all-application-data: truncate failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database truncate failed: {exc!s}"[:500],
        ) from exc

    db2 = SessionLocal()
    try:
        meta = _reseed_default_tenant_and_admin(db2)
    except Exception as exc:
        logger.exception("erase-all-application-data: reseed failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reseed after erase failed: {exc!s}"[:500],
        ) from exc
    finally:
        db2.close()

    set_openai_api_key_override(None)
    hydrate_openai_api_key_from_db()

    logger.warning(
        "erase-all-application-data completed by admin user_id=%s email=%s tenant_id=%s tables=%s",
        getattr(current_user, "id", "?"),
        getattr(current_user, "email", "?"),
        tenant_id,
        n_tables,
    )
    return {
        "ok": True,
        "tables_truncated": n_tables,
        "admin_recreated": meta.get("admin_recreated", False),
    }
