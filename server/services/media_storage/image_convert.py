"""Normalize uploaded product images to WhatsApp-safe formats.

Meta's WhatsApp Cloud API only accepts ``image/jpeg`` and ``image/png`` when
sending an image by public link. Admins, however, often upload webp/heic/heif/
avif/gif/tiff, which fail silently on customer devices. We convert those
uploads to JPEG *once* at upload time so the stored R2 object is always
WhatsApp-friendly — no on-the-fly transcoding per message needed.

The helper is intentionally defensive: if Pillow or pillow-heif is missing,
it returns the original bytes unchanged so uploads never break.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image  # type: ignore

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - best-effort import
    Image = None  # type: ignore
    _PIL_AVAILABLE = False

try:
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
    _HEIF_AVAILABLE = True
except Exception:  # pragma: no cover - best-effort import
    _HEIF_AVAILABLE = False


# Formats we keep as-is (WhatsApp accepts them directly).
_PASSTHROUGH_MIMES = {"image/jpeg", "image/jpg", "image/png"}

# Upper bound on stored image dimensions to keep delivery fast.
_MAX_SIDE = 1600
_JPEG_QUALITY = 85


def _normalize_mime(content_type: Optional[str]) -> str:
    if not content_type:
        return ""
    return content_type.split(";")[0].strip().lower()


def convert_to_whatsapp_safe_image(
    body: bytes,
    *,
    content_type: Optional[str],
) -> Tuple[bytes, str, str]:
    """Return ``(bytes, extension, content_type)`` safe for WhatsApp.

    - ``image/jpeg`` and ``image/png`` are returned unchanged (no re-encode
      → avoids quality loss for product photos that are already compressed).
    - Anything else (webp/heic/heif/avif/gif/tiff/bmp/…) is decoded with
      Pillow, flattened onto a white background, optionally downscaled to
      ``_MAX_SIDE`` px, and saved as a progressive JPEG.
    - If Pillow is unavailable, we return the original bytes unchanged so
      uploads never fail — the messaging layer still has the runtime proxy
      as a last line of defence.
    """
    mime = _normalize_mime(content_type)
    if mime in _PASSTHROUGH_MIMES:
        ext = ".jpg" if mime in ("image/jpeg", "image/jpg") else ".png"
        return body, ext, mime

    if not _PIL_AVAILABLE:
        logger.warning(
            "image_convert: Pillow missing, storing original bytes unchanged "
            "(mime=%s bytes=%d)",
            mime or "?",
            len(body),
        )
        return body, _fallback_ext(mime), mime or "application/octet-stream"

    try:
        with Image.open(BytesIO(body)) as im:  # type: ignore[union-attr]
            im.load()

            # Animated sources (gif/webp/apng): grab the first frame so
            # WhatsApp shows *something* instead of nothing.
            if getattr(im, "is_animated", False):
                try:
                    im.seek(0)
                except Exception:  # pragma: no cover - defensive
                    pass

            if im.mode in ("RGBA", "LA") or (
                im.mode == "P" and "transparency" in im.info
            ):
                bg = Image.new("RGB", im.size, (255, 255, 255))  # type: ignore[union-attr]
                rgba = im.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")

            w, h = im.size
            if w > 0 and h > 0:
                scale = min(_MAX_SIDE / w, _MAX_SIDE / h, 1.0)
                if scale < 1.0:
                    new_size = (
                        max(1, int(w * scale)),
                        max(1, int(h * scale)),
                    )
                    resample = getattr(Image, "LANCZOS", None) or getattr(
                        Image, "ANTIALIAS", 1
                    )  # type: ignore[union-attr]
                    im = im.resize(new_size, resample)  # type: ignore[arg-type]

            out = BytesIO()
            im.save(
                out,
                format="JPEG",
                quality=_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
            jpeg_bytes = out.getvalue()
    except Exception as exc:
        logger.warning(
            "image_convert: transcode failed mime=%s bytes=%d err=%s",
            mime or "?",
            len(body),
            exc,
        )
        return body, _fallback_ext(mime), mime or "application/octet-stream"

    logger.info(
        "image_convert: %s → image/jpeg (in=%d out=%d heif=%s)",
        mime or "?",
        len(body),
        len(jpeg_bytes),
        _HEIF_AVAILABLE,
    )
    return jpeg_bytes, ".jpg", "image/jpeg"


def _fallback_ext(mime: str) -> str:
    """Best-guess extension when conversion is unavailable."""
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/heic": ".heic",
        "image/heif": ".heif",
        "image/avif": ".avif",
        "image/tiff": ".tiff",
        "image/bmp": ".bmp",
    }.get(mime, ".bin")
