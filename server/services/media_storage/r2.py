"""
Cloudflare R2 (S3-compatible) helpers: presigned PUT/GET and server-side uploads.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from config import settings

logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def is_r2_configured() -> bool:
    return bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket_name
    )


def _endpoint() -> str:
    return f"https://{settings.r2_account_id}.r2.cloudflarestorage.com"


def _s3() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=_endpoint(),
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def validate_upload_request(
    kind: str,
    content_type: str,
    size_bytes: int,
) -> Tuple[str, str]:
    """
    Returns (normalized_kind, extension_hint) or raises ValueError.
    """
    k = (kind or "").strip().lower()
    ct = (content_type or "").strip().lower()
    if size_bytes < 1 or size_bytes > _MAX_UPLOAD_BYTES:
        raise ValueError("size_bytes must be between 1 and 10MB")
    if k == "voice":
        if ct not in ("audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav"):
            raise ValueError("Unsupported audio content type")
        ext = ".webm" if "webm" in ct else ".ogg" if "ogg" in ct else ".mp3" if "mpeg" in ct else ".m4a" if "mp4" in ct else ".wav"
        return k, ext
    if k == "image":
        if ct not in (
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
            "image/heic",
            "image/heif",
            "image/avif",
            "image/tiff",
            "image/bmp",
        ):
            raise ValueError("Unsupported image content type")
        ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/heic": ".heic",
            "image/heif": ".heif",
            "image/avif": ".avif",
            "image/tiff": ".tiff",
            "image/bmp": ".bmp",
        }.get(ct, ".bin")
        return k, ext
    if k in ("file", "document"):
        return "file", ""
    raise ValueError("type must be voice, image, or file")


def trending_product_object_key(country_folder: str, ext: str) -> str:
    """
    R2 key under arabia-media-style prefix: trending-products/{uae|ksa|pk}/<uuid><ext>
    """
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = uuid.uuid4().hex
    folder = (country_folder or "uae").strip().lower()
    if folder not in ("uae", "ksa", "pk"):
        folder = "uae"
    e = ext if ext.startswith(".") else f".{ext}" if ext else ".jpg"
    return f"trending-products/{folder}/{day}_{uid}{e}"


def new_object_key(kind: str, ext: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = uuid.uuid4().hex
    if kind == "voice":
        return f"voice/{day}_{uid}{ext}"
    if kind == "image":
        return f"images/{day}/{uid}{ext}"
    return f"docs/{day}/{uid}{ext or '.bin'}"


def presign_put(object_key: str, content_type: str, expires_in: int) -> str:
    if not is_r2_configured():
        raise RuntimeError("R2 is not configured")
    return _s3().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.r2_bucket_name,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def presign_get(object_key: str, expires_in: int) -> str:
    if not is_r2_configured():
        raise RuntimeError("R2 is not configured")
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket_name, "Key": object_key},
        ExpiresIn=expires_in,
    )


def put_bytes(object_key: str, body: bytes, content_type: str) -> None:
    if not is_r2_configured():
        raise RuntimeError("R2 is not configured")
    _s3().put_object(
        Bucket=settings.r2_bucket_name,
        Key=object_key,
        Body=body,
        ContentType=content_type or "application/octet-stream",
    )


def guess_ext_from_mime(mime: Optional[str]) -> str:
    if not mime:
        return ".bin"
    m = mime.split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
        "video/mp4": ".mp4",
    }.get(m, ".bin")


def store_inbound_whatsapp_media(body: bytes, wa_kind: str, mime: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Upload bytes from WhatsApp to R2. wa_kind is 'image' or 'audio'.
    Returns metadata dict with object_key, type, mime_type, size_bytes or None.
    """
    if not body or len(body) > _MAX_UPLOAD_BYTES:
        return None
    if not is_r2_configured():
        return None
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    uid = uuid.uuid4().hex
    ext = guess_ext_from_mime(mime)
    if wa_kind == "image":
        key = f"images/wa/{day}/{uid}{ext}"
        typ = "image"
        ct = mime or "image/jpeg"
    else:
        key = f"voice/wa/{day}/{uid}{ext}"
        typ = "voice"
        ct = mime or "audio/ogg"
    try:
        put_bytes(key, body, ct)
    except Exception:
        logger.exception("R2 put_bytes failed for inbound WA media")
        return None
    return {
        "type": typ,
        "object_key": key,
        "mime_type": ct,
        "size_bytes": len(body),
    }


def delete_object(object_key: str) -> bool:
    if not is_r2_configured() or not object_key:
        return False
    try:
        _s3().delete_object(Bucket=settings.r2_bucket_name, Key=object_key)
        return True
    except ClientError as e:
        logger.warning("R2 delete_object failed key=%s err=%s", object_key, e)
        return False


def enrich_metadata_for_api(meta: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Copy metadata for JSON responses: add media_url (presigned GET), drop object_key.
    """
    if not meta:
        return None
    out = dict(meta)
    key = out.get("object_key")
    typ = out.get("type")
    if key and typ in ("image", "voice", "file") and is_r2_configured():
        try:
            out["media_url"] = presign_get(str(key), settings.r2_presign_get_seconds)
        except Exception as e:
            logger.warning("presign_get failed: %s", e)
            out["media_error"] = "sign_failed"
    if "object_key" in out:
        del out["object_key"]
    return out
