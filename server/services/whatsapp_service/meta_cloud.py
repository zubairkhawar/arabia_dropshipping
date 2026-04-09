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

    def _messages_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.graph_version}/"
            f"{self.phone_number_id}/messages"
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _media_upload_url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.graph_version}/"
            f"{self.phone_number_id}/media"
        )

    async def send_text_message(self, to_phone: str, text: str) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")

        url = self._messages_url()
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        headers = self._headers()
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

    async def send_image_message(
        self,
        to_phone: str,
        image_url: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not image_url:
            raise ValueError("image_url is required")

        url = self._messages_url()
        image: Dict[str, Any] = {"link": image_url}
        if caption and caption.strip():
            image["caption"] = caption.strip()[:1024]
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "image",
            "image": image,
        }
        headers = self._headers()
        logger.info(
            "Sending WhatsApp image using PHONE_NUMBER_ID=%s TO=%s",
            self.phone_number_id,
            to_phone,
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp image API HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def send_audio_message(
        self,
        to_phone: str,
        audio_url: str,
        mime_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not to_phone or not audio_url:
            raise ValueError("to_phone and audio_url are required")
        async with httpx.AsyncClient(timeout=60.0) as client:
            media_resp = await client.get(audio_url)
            if media_resp.status_code >= 400:
                logger.error(
                    "Audio download for Meta upload HTTP %s: %s",
                    media_resp.status_code,
                    (media_resp.text or "")[:500],
                )
            media_resp.raise_for_status()
            body = media_resp.content
            if not body:
                raise RuntimeError("Audio file download is empty")

            ct = (mime_type or media_resp.headers.get("content-type") or "audio/ogg").split(";")[0].strip()
            files = {
                "file": ("voice_note.ogg", body, ct),
                "messaging_product": (None, "whatsapp"),
                "type": (None, ct),
            }
            upload = await client.post(
                self._media_upload_url(),
                files=files,
                headers=self._auth_headers(),
            )
            if upload.status_code >= 400:
                logger.error(
                    "Meta media upload API HTTP %s: %s",
                    upload.status_code,
                    (upload.text or "")[:800],
                )
            upload.raise_for_status()
            upload_json = upload.json()
            media_id = str(upload_json.get("id") or "").strip()
            if not media_id:
                raise RuntimeError("Meta media upload response missing id")

            payload = {
                "messaging_product": "whatsapp",
                "to": to_phone,
                "type": "audio",
                "audio": {"id": media_id},
            }
            resp = await client.post(self._messages_url(), json=payload, headers=self._headers())
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp audio API HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def send_reaction_message(
        self,
        to_phone: str,
        target_message_id: str,
        emoji: str,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not to_phone or not target_message_id:
            raise ValueError("to_phone and target_message_id are required")
        url = self._messages_url()
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "reaction",
            "reaction": {
                "message_id": target_message_id,
                "emoji": emoji or "",
            },
        }
        headers = self._headers()
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp reaction API HTTP %s: %s",
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
