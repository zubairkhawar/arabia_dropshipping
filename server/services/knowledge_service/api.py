from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeSource


router = APIRouter()


class KnowledgeSourceIn(BaseModel):
    tenant_id: int
    name: str
    type: str  # file | url | api
    url: str | None = None
    metadata: dict | None = None


class KnowledgeSourceOut(BaseModel):
    id: int
    tenant_id: int
    name: str
    type: str
    url: Optional[str]
    status: str
    chunk_count: int
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _to_knowledge_source_out(row: KnowledgeSource) -> KnowledgeSourceOut:
    return KnowledgeSourceOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        type=row.type,
        url=row.url,
        status=row.status,
        chunk_count=row.chunk_count,
        metadata=row.knowledge_metadata or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/sources", response_model=List[KnowledgeSourceOut])
async def list_sources(tenant_id: int, db: Session = Depends(get_db)):
    """
    List knowledge sources for a tenant.
    """
    rows = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.tenant_id == tenant_id)
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )
    return [_to_knowledge_source_out(row) for row in rows]


@router.post(
    "/sources",
    response_model=KnowledgeSourceOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_source(payload: KnowledgeSourceIn, db: Session = Depends(get_db)):
    """
    Create a knowledge source.
    Indexing is stubbed; status starts as 'indexing'.
    """
    src = KnowledgeSource(
        tenant_id=payload.tenant_id,
        name=payload.name,
        type=payload.type,
        url=payload.url,
        status="indexing",
        chunk_count=0,
        metadata=payload.metadata or {},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    # TODO: enqueue background job to fetch/chunk/embed and update status/chunk_count.
    return _to_knowledge_source_out(src)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: int, db: Session = Depends(get_db)):
    """
    Delete a knowledge source.
    """
    src = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not src:
        return
    db.delete(src)
    db.commit()
    # TODO: remove from vector store when plugged in.
    return

