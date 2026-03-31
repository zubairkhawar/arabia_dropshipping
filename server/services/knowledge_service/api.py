from datetime import datetime
import base64
from io import BytesIO
import re
from typing import List, Optional, Dict, Any, Tuple

import httpx
from fastapi import APIRouter, Depends, status, HTTPException
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


def _clean_text(raw: str) -> str:
    # Best-effort HTML/text cleanup without external parser deps.
    txt = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    txt = re.sub(r"(?is)<style.*?>.*?</style>", " ", txt)
    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    if not text:
        return []
    size = max(300, chunk_size)
    ov = max(0, min(overlap, size // 2))
    chunks: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + size)
        chunks.append(text[i:end].strip())
        if end >= n:
            break
        i = max(i + 1, end - ov)
    return [c for c in chunks if c]


async def _fetch_url_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = (resp.headers.get("content-type") or "").lower()
        raw = resp.text if "text" in content_type or "html" in content_type else resp.text
    return _clean_text(raw)


def _build_api_source_text(src: KnowledgeSource) -> str:
    md = src.knowledge_metadata or {}
    schema_notes = str(md.get("schema_notes") or "").strip()
    auth_type = str(md.get("auth_type") or "none").strip()
    refresh = md.get("refresh_interval_hours")
    headers = md.get("headers") or {}
    if isinstance(headers, dict):
        header_keys = ", ".join(sorted(str(k) for k in headers.keys()))
    else:
        header_keys = ""
    lines = [
        f"API source: {src.name}",
        f"Base URL: {src.url or 'N/A'}",
        f"Auth type: {auth_type or 'none'}",
        f"Refresh interval hours: {refresh if refresh is not None else 'N/A'}",
    ]
    if header_keys:
        lines.append(f"Header keys: {header_keys}")
    if schema_notes:
        lines.append(f"Schema notes: {schema_notes}")
    return "\n".join(lines)


async def _ingest_source_content(src: KnowledgeSource) -> Tuple[str, int, Dict[str, Any]]:
    """
    Returns: status, chunk_count, metadata_patch
    """
    md = dict(src.knowledge_metadata or {})
    md.pop("last_error", None)

    if src.type == "url":
        if not src.url:
            md["last_error"] = "URL source missing url"
            return "error", 0, md
        text = await _fetch_url_text(src.url)
        if not text:
            md["last_error"] = "No readable content fetched from URL"
            return "error", 0, md
        chunks = _chunk_text(text)
        md["chunks"] = chunks
        md["content_preview"] = text[:500]
        return "ready", len(chunks), md

    if src.type == "api":
        text = _build_api_source_text(src)
        chunks = _chunk_text(text, chunk_size=700, overlap=80)
        md["chunks"] = chunks
        md["content_preview"] = text[:500]
        return "ready", len(chunks), md

    # file source ingestion
    existing_chunks = md.get("chunks")
    if isinstance(existing_chunks, list) and existing_chunks:
        return "ready", len(existing_chunks), md

    text = str(md.get("file_text") or "").strip()
    if not text:
        b64 = str(md.get("file_data_base64") or "").strip()
        mime = str(md.get("mime_type") or "").lower().strip()
        if b64:
            try:
                blob = base64.b64decode(b64)
                if mime.startswith("text/") or mime in {
                    "application/json",
                    "application/csv",
                    "text/csv",
                }:
                    text = blob.decode("utf-8", errors="ignore")
                elif mime == "application/pdf":
                    try:
                        from pypdf import PdfReader  # type: ignore

                        reader = PdfReader(BytesIO(blob))
                        pages: List[str] = []
                        for page in reader.pages:
                            pages.append((page.extract_text() or "").strip())
                        text = "\n".join(p for p in pages if p).strip()
                    except Exception:
                        # pypdf unavailable or parse failed
                        text = ""
            except Exception:
                text = ""

    if text:
        cleaned = _clean_text(text)
        chunks = _chunk_text(cleaned)
        md["chunks"] = chunks
        md["content_preview"] = cleaned[:500]
        return "ready", len(chunks), md

    filename = str(md.get("filename") or src.name or "file").strip()
    md["chunks"] = [f"File source connected: {filename}"]
    md["content_preview"] = f"File source connected: {filename}"
    return "ready", 1, md


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
        knowledge_metadata=payload.metadata or {},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    # Practical synchronous ingestion for URL/API so KB becomes usable immediately.
    status_value, chunk_count, md_patch = await _ingest_source_content(src)
    src.status = status_value
    src.chunk_count = chunk_count
    src.knowledge_metadata = md_patch
    src.updated_at = datetime.utcnow()
    db.add(src)
    db.commit()
    db.refresh(src)

    return _to_knowledge_source_out(src)


@router.post("/sources/{source_id}/reindex", response_model=KnowledgeSourceOut)
async def reindex_source(source_id: int, db: Session = Depends(get_db)):
    src = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Knowledge source not found")
    src.status = "indexing"
    src.updated_at = datetime.utcnow()
    db.add(src)
    db.commit()
    db.refresh(src)

    status_value, chunk_count, md_patch = await _ingest_source_content(src)
    src.status = status_value
    src.chunk_count = chunk_count
    src.knowledge_metadata = md_patch
    src.updated_at = datetime.utcnow()
    db.add(src)
    db.commit()
    db.refresh(src)
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

