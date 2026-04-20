"""On-the-fly image transcoder so WhatsApp Cloud API always receives a
supported format.

The Meta WhatsApp Cloud API only accepts ``image/jpeg`` and ``image/png`` when
sending an image by public link. Merchants in this platform, however, routinely
upload webp/heic/heif/avif/gif/tiff/bmp — those fail silently on WhatsApp.

This endpoint proxies the remote source image, normalises the pixel data with
Pillow (and ``pillow-heif`` when available for HEIC/HEIF), and re-encodes it as
a progressive JPEG that Meta happily accepts. The URL is publicly reachable so
Meta's servers can fetch it when we send an image message.

Pillow and pillow-heif are declared in ``requirements.txt``; if they are not
installed at runtime we gracefully stream the original bytes — the caller will
still attempt the send and WhatsApp will reject if the format is unsupported.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["media-proxy"])

try:
    from PIL import Image  # type: ignore

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - best-effort import
    Image = None  # type: ignore
    _PIL_AVAILABLE = False
    logger.warning(
        "Pillow is not installed; /v1/media/wa-image will only pass-through bytes."
    )

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except Exception:  # pragma: no cover - best-effort import
    _HEIF_AVAILABLE = False

# Hard cap on source image size to avoid blowing up server memory.
_MAX_SOURCE_BYTES = 25 * 1024 * 1024  # 25 MB

# Meta's WhatsApp Cloud API recommends images <= 5 MB and <= 1600px on the
# longest side; we target those limits so delivery is reliable.
_DEFAULT_MAX_SIDE = 1600
_DEFAULT_QUALITY = 85

# Formats WhatsApp accepts directly via a public link.
_WA_NATIVE_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png"}


def _should_pass_through(content_type: str, body_len: int) -> bool:
    """Return True when we can serve the source bytes unchanged."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in _WA_NATIVE_CONTENT_TYPES:
        return False
    # Keep a generous buffer below WhatsApp's 5 MB image cap.
    return body_len <= 5 * 1024 * 1024


@router.get("/v1/media/wa-image")
async def whatsapp_image_proxy(
    src: str = Query(..., description="Source image URL to transcode to JPEG."),
    quality: int = Query(_DEFAULT_QUALITY, ge=40, le=95),
    max_side: int = Query(_DEFAULT_MAX_SIDE, ge=256, le=4096),
) -> Response:
    """Fetch ``src`` and return a WhatsApp-friendly JPEG.

    If Pillow is unavailable, we fall back to streaming the original bytes so
    the caller is never blocked on this endpoint.
    """
    if not isinstance(src, str) or not src.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="src must be an http(s) URL")

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(src)
            resp.raise_for_status()
            body: bytes = resp.content
            content_type: str = (
                resp.headers.get("content-type") or ""
            ).split(";")[0].strip().lower()
    except httpx.HTTPError as exc:
        logger.warning(
            "wa-image proxy: fetch failed src=%s err=%s", src[:160], exc
        )
        raise HTTPException(status_code=502, detail="failed to fetch source image")
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "wa-image proxy: unexpected fetch error src=%s err=%s", src[:160], exc
        )
        raise HTTPException(status_code=502, detail="failed to fetch source image")

    if not body:
        raise HTTPException(status_code=502, detail="empty body from source")
    if len(body) > _MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="source image too large")

    # Serve jpeg/png passthrough directly when we don't need to resize or flatten.
    if _should_pass_through(content_type, len(body)):
        return Response(
            content=body,
            media_type=content_type or "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    if not _PIL_AVAILABLE:
        logger.warning(
            "wa-image proxy: Pillow missing, streaming original bytes src=%s ct=%s",
            src[:160],
            content_type,
        )
        return Response(
            content=body,
            media_type=content_type or "application/octet-stream",
        )

    try:
        with Image.open(BytesIO(body)) as im:  # type: ignore[union-attr]
            im.load()

            # Animated sources (gif/webp/apng): grab the first frame.
            if getattr(im, "is_animated", False):
                try:
                    im.seek(0)
                except Exception:  # pragma: no cover - defensive
                    pass

            # Flatten alpha onto a white background so JPEG encoding is clean.
            if im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info
            ):
                bg = Image.new("RGB", im.size, (255, 255, 255))  # type: ignore[union-attr]
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")

            # Downscale to WhatsApp-friendly dimensions while preserving aspect.
            w, h = im.size
            if w > 0 and h > 0:
                scale = min(max_side / w, max_side / h, 1.0)
                if scale < 1.0:
                    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                    resample = getattr(Image, "LANCZOS", None) or getattr(
                        Image, "ANTIALIAS", 1
                    )  # type: ignore[union-attr]
                    im = im.resize(new_size, resample)  # type: ignore[arg-type]

            out = BytesIO()
            im.save(
                out,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )
            jpeg_bytes = out.getvalue()
    except Exception as exc:
        logger.warning(
            "wa-image proxy: transcode failed src=%s ct=%s err=%s",
            src[:160],
            content_type,
            exc,
        )
        return Response(
            content=body,
            media_type=content_type or "application/octet-stream",
        )

    logger.info(
        "wa-image proxy: transcoded src=%s in_bytes=%d out_bytes=%d ct=%s heif=%s",
        src[:160],
        len(body),
        len(jpeg_bytes),
        content_type or "?",
        _HEIF_AVAILABLE,
    )
    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": 'inline; filename="image.jpg"',
        },
    )


# Formats WhatsApp's Cloud API does NOT accept via a public image link. When
# we see these extensions we force the URL through the transcoder.
_UNSUPPORTED_WA_EXTENSIONS = {
    ".webp",
    ".heic",
    ".heif",
    ".heics",
    ".heifs",
    ".avif",
    ".gif",
    ".tif",
    ".tiff",
    ".bmp",
    ".svg",
    ".ico",
}


def _url_extension(url: str) -> str:
    """Return the lowercase file extension (including dot) from a URL's path."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        path = urlparse(url).path or ""
    except Exception:
        path = url
    idx = path.rfind(".")
    if idx == -1:
        return ""
    ext = path[idx:].lower()
    # Guard against `.` appearing in a segment rather than as an extension.
    if "/" in ext or len(ext) > 8:
        return ""
    return ext


def is_wa_supported_image_url(url: str) -> bool:
    """Best-effort check: does this URL *look* like a WhatsApp-safe image?"""
    ext = _url_extension(url)
    if not ext:
        # Unknown extension — let Meta try; the messaging layer has a safety net.
        return True
    if ext in _UNSUPPORTED_WA_EXTENSIONS:
        return False
    return ext in {".jpg", ".jpeg", ".png"}


def proxy_url_for(src: str, *, base_url: Optional[str]) -> Optional[str]:
    """Build a public proxy URL that transcodes ``src`` to JPEG.

    Returns ``None`` if ``base_url`` is empty so the caller can decide whether
    to pass the original URL through unchanged.
    """
    if not src or not base_url:
        return None
    try:
        from urllib.parse import quote

        base = base_url.rstrip("/")
        return f"{base}/v1/media/wa-image?src={quote(src, safe='')}"
    except Exception:
        return None


def ensure_wa_safe_image_url(src: str, *, base_url: Optional[str]) -> str:
    """Return a WhatsApp-safe image URL.

    When ``src`` looks like an unsupported format (webp/heic/...) and a public
    base URL is configured, return the proxy URL. Otherwise return ``src``
    unchanged (possibly still unsupported — the messaging layer will log a
    warning if Meta rejects it).
    """
    if not src:
        return src
    if is_wa_supported_image_url(src):
        return src
    proxied = proxy_url_for(src, base_url=base_url)
    return proxied or src
