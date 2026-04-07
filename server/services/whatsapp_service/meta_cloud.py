import logging
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class MetaWhatsAppClient:
    """
    Thin client for Meta WhatsApp Cloud API.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        graph_version: Optional[str] = None,
    ):
        self.access_token = access_token or settings.meta_whatsapp_access_token
        self.phone_number_id = phone_number_id or settings.meta_whatsapp_phone_number_id
        self.graph_version = graph_version or settings.meta_graph_api_version

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id and self.graph_version)

    async def send_text_message(self, to_phone: str, text: str) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")

        url = (
            f"https://graph.facebook.com/{self.graph_version}/"
            f"{self.phone_number_id}/messages"
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        logger.info(
            "Sending WhatsApp message using:\nPHONE_NUMBER_ID = %s\nTO = %s\n(body length: %s chars)",
            self.phone_number_id,
            to_phone,
            len(text or ""),
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp messages API HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def download_media(self, media_id: str) -> tuple[bytes, Optional[str]]:
        """
        Fetch WhatsApp media bytes via Graph API (media URL is short-lived).
        Returns (body, mime_type).
        """
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        graph = f"https://graph.facebook.com/{self.graph_version}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            info = await client.get(graph, headers=headers)
            if info.status_code >= 400:
                logger.error(
                    "Meta media info HTTP %s: %s",
                    info.status_code,
                    (info.text or "")[:500],
                )
            info.raise_for_status()
            data = info.json()
            url = data.get("url")
            mime = data.get("mime_type")
            if not url or not isinstance(url, str):
                raise RuntimeError("Meta media response missing url")
            binary = await client.get(url, headers=headers)
            binary.raise_for_status()
            return binary.content, mime if isinstance(mime, str) else None
