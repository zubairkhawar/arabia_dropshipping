"""
SMTP email helper (e.g. Gmail with app password).
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Tuple

from config import settings


def send_html_email(to_email: str, subject: str, html_content: str) -> Tuple[bool, str]:
    """
    Send an HTML email using configured SMTP (STARTTLS).

    Returns (success, error_message). error_message is empty on success.
    """
    host = (settings.smtp_host or "").strip()
    user = (settings.smtp_user or "").strip()
    password = (settings.smtp_password or "").strip()
    from_addr = (settings.smtp_from_email or user or "").strip()
    port = int(settings.smtp_port or 587)

    if not host or not user or not password or not from_addr:
        return False, "SMTP is not fully configured (host, user, password, from)."

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"Dropship Arabia <{from_addr}>"
        msg["To"] = to_email
        msg.set_content("This message requires an HTML-capable mail client.")
        msg.add_alternative(html_content, subtype="html")

        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)

        return True, ""
    except Exception as exc:  # noqa: BLE001 — surface provider errors as string
        return False, str(exc)
