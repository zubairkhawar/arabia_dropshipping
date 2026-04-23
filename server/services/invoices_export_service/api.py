"""
POST /api/invoices/export/csv — invoice-specific CSV export.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from models import User
from services.auth_service.api import get_current_user
from services.media_storage.r2 import is_r2_configured, presign_get, put_bytes
from services.orders_export_service.csv_builder import object_key_for_invoice_csv
from services.orders_export_service.exporter import build_invoice_csv_export_bytes
from services.store_integration_service.client import StoreIntegrationClient

router = APIRouter()


class InvoiceCsvExportIn(BaseModel):
    seller_id: int = Field(..., ge=1)
    invoice_id: Optional[str] = Field(default=None)
    invoice_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    include_tracking: Optional[bool] = Field(default=True)


class InvoiceCsvExportOut(BaseModel):
    success: bool
    download_url: str
    expires_at: str
    invoice_ref: Optional[str] = None
    invoice_date: Optional[str] = None
    order_count: int = 0


@router.post("/export/csv", response_model=InvoiceCsvExportOut)
async def post_invoice_export_csv(
    body: InvoiceCsvExportIn,
    current_user: User = Depends(get_current_user),
):
    role = (current_user.role or "").lower()
    if role not in ("admin", "agent"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or agent only")
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage is not configured",
        )
    if not (body.invoice_id or "").strip() and not (body.invoice_date or "").strip():
        raise HTTPException(status_code=400, detail="Provide invoice_id or invoice_date")

    sid = str(int(body.seller_id))
    iid = (body.invoice_id or "").strip() or None
    idate = (body.invoice_date or "").strip()[:10] or None

    store = StoreIntegrationClient()
    try:
        csv_bytes, row_count, inv_ref, inv_date = await build_invoice_csv_export_bytes(
            store,
            sid,
            invoice_id=iid,
            invoice_date=idate,
            include_tracking=bool(body.include_tracking),
        )
    except ValueError as exc:
        msg = str(exc)
        if "invoice_not_found" in msg:
            raise HTTPException(status_code=404, detail="Invoice not found")
        raise HTTPException(status_code=400, detail="Invalid invoice export request")

    if not csv_bytes:
        raise HTTPException(status_code=404, detail="No invoice data to export")

    ref_for_key = inv_ref or iid or idate or sid
    key = object_key_for_invoice_csv(sid, ref_for_key)
    put_bytes(key, csv_bytes, "text/csv")
    ttl = 86400
    url = presign_get(key, ttl)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z")
    return InvoiceCsvExportOut(
        success=True,
        download_url=url,
        expires_at=expires_at,
        invoice_ref=inv_ref or iid,
        invoice_date=inv_date or idate,
        order_count=row_count,
    )

