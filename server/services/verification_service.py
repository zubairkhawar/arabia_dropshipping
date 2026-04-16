"""
Local verification code store + SMTP delivery.

Used as fallback when no external CLIENT_API_BASE_URL is configured.
Codes are kept in-memory with a configurable TTL (default 10 min).
"""
from __future__ import annotations

import logging
import random
import string
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from config import settings
from services.email_service import send_html_email

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_EXPIRY_MINUTES = 10
MAX_ATTEMPTS = 5  # per email per code window

_lock = threading.Lock()
# email → (code, expires_at, attempts_remaining)
_store: Dict[str, Tuple[str, datetime, int]] = {}


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=CODE_LENGTH))


def _cleanup_expired() -> None:
    now = datetime.utcnow()
    expired = [k for k, (_, exp, _) in _store.items() if now > exp]
    for k in expired:
        del _store[k]


def send_verification_code_local(email: str) -> bool:
    """Generate a code, store it, and email it via SMTP. Returns True on success."""
    e = (email or "").strip().lower()
    if not e:
        return False

    code = _generate_code()
    expires = datetime.utcnow() + timedelta(minutes=CODE_EXPIRY_MINUTES)

    html = (
        f"<div style='font-family:sans-serif;max-width:480px;margin:0 auto'>"
        f"<h2 style='color:#333'>Arabia Dropshipping</h2>"
        f"<p>Your verification code is:</p>"
        f"<p style='font-size:28px;font-weight:bold;letter-spacing:6px;"
        f"color:#0a7c42;margin:16px 0'>{code}</p>"
        f"<p style='color:#666'>This code expires in {CODE_EXPIRY_MINUTES} minutes.</p>"
        f"<hr style='border:none;border-top:1px solid #eee;margin:24px 0'>"
        f"<p style='font-size:12px;color:#999'>If you didn't request this, please ignore this email.</p>"
        f"</div>"
    )

    ok, err = send_html_email(e, "Your Verification Code – Arabia Dropshipping", html)
    if not ok:
        logger.error("Verification email failed for %s: %s", e, err)
        return False

    with _lock:
        _cleanup_expired()
        _store[e] = (code, expires, MAX_ATTEMPTS)

    logger.info("Verification code sent to %s (expires %s)", e, expires.isoformat())
    return True


def verify_code_local(email: str, code: str) -> bool:
    """Check the code. Returns True if valid; auto-deletes on success or exhaustion."""
    e = (email or "").strip().lower()
    c = (code or "").strip()
    if not e or not c:
        return False

    with _lock:
        _cleanup_expired()
        entry = _store.get(e)
        if entry is None:
            return False
        stored_code, expires, attempts = entry
        if datetime.utcnow() > expires:
            del _store[e]
            return False
        if stored_code == c:
            del _store[e]
            return True
        # Wrong code — decrement attempts
        attempts -= 1
        if attempts <= 0:
            del _store[e]
        else:
            _store[e] = (stored_code, expires, attempts)
        return False
