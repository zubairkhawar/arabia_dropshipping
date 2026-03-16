from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Broadcast


router = APIRouter()


class BroadcastPayload(BaseModel):
    id: int | None = None
    tenant_id: int
    title: str
    message: str
    occasion: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class BroadcastCreate(BaseModel):
    tenant_id: int
    title: str
    message: str
    occasion: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@router.get("/broadcasts", response_model[List[BroadcastPayload]])
async def list_broadcasts(tenant_id: int, db: Session = Depends(get_db)):
    """
    List all broadcasts for a tenant.
    """
    rows = (
        db.query(Broadcast)
        .filter(Broadcast.tenant_id == tenant_id)
        .order_by(Broadcast.starts_at.desc().nullslast())
        .all()
    )
    return [
        BroadcastPayload(
            id=b.id,
            tenant_id=b.tenant_id,
            title=b.title,
            message=b.message,
            occasion=b.occasion,
            starts_at=b.starts_at,
            ends_at=b.ends_at,
        )
        for b in rows
    ]


@router.post(
    "/broadcasts",
    response_model=BroadcastPayload,
    status_code=status.HTTP_201_CREATED,
)
async def create_broadcast(
    payload: BroadcastCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new broadcast message.
    """
    b = Broadcast(
        tenant_id=payload.tenant_id,
        title=payload.title,
        message=payload.message,
        occasion=payload.occasion,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        created_at=datetime.utcnow(),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return BroadcastPayload(
        id=b.id,
        tenant_id=b.tenant_id,
        title=b.title,
        message=b.message,
        occasion=b.occasion,
        starts_at=b.starts_at,
        ends_at=b.ends_at,
    )


@router.delete("/broadcasts/{broadcast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_broadcast(broadcast_id: int, db: Session = Depends(get_db)):
    """
    Delete a broadcast.
    """
    b = db.query(Broadcast).filter(Broadcast.id == broadcast_id).first()
    if not b:
        return
    db.delete(b)
    db.commit()
    return

