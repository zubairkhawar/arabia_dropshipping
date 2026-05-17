import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# WhatsApp Cloud API outbound document cap (product limit ~100 MB).
_MAX_WA_OUTBOUND_DOCUMENT_BYTES = 100 * 1024 * 1024


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

    def waba_templates_configured(self) -> bool:
        """List templates requires WABA id + token (not phone number id)."""
        return bool(
            self.access_token
            and (settings.meta_whatsapp_waba_id or "").strip()
            and self.graph_version
        )

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

    async def send_text_message(
        self,
        to_phone: str,
        text: str,
        context_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")

        url = self._messages_url()
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text},
        }
        if context_message_id and context_message_id.strip():
            payload["context"] = {"message_id": context_message_id.strip()}
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

    async def upload_whatsapp_media_file(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> str:
        """
        POST multipart to ``/{phone-number-id}/media``. Returns Graph ``id`` for use in messages.
        """
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not file_bytes:
            raise ValueError("file_bytes is empty")
        if len(file_bytes) > _MAX_WA_OUTBOUND_DOCUMENT_BYTES:
            raise ValueError("file_bytes exceeds WhatsApp document size limit")
        fn = (filename or "file").strip() or "file"
        ct = (mime_type or "application/octet-stream").split(";")[0].strip()
        files = {
            "file": (fn, file_bytes, ct),
            "messaging_product": (None, "whatsapp"),
            "type": (None, ct),
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
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
            return media_id

    async def send_document_by_media_id(
        self,
        to_phone: str,
        media_id: str,
        filename: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not to_phone or not media_id or not filename:
            raise ValueError("to_phone, media_id, and filename are required")
        doc: Dict[str, Any] = {
            "id": media_id.strip(),
            "filename": filename.strip()[:240],
        }
        if caption and caption.strip():
            doc["caption"] = caption.strip()[:1024]
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": doc,
        }
        url = self._messages_url()
        headers = self._headers()
        logger.info(
            "Sending WhatsApp document by media id PHONE_NUMBER_ID=%s TO=%s filename=%s",
            self.phone_number_id,
            to_phone,
            doc.get("filename"),
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp document (id) API HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def send_document_from_bytes(
        self,
        to_phone: str,
        file_bytes: bytes,
        filename: str,
        caption: Optional[str] = None,
        mime_type: str = "text/csv",
    ) -> Dict[str, Any]:
        """
        Upload CSV (or other document) to Meta then send by ``id`` — avoids public HTTPS on ``link``.
        """
        media_id = await self.upload_whatsapp_media_file(file_bytes, filename, mime_type)
        return await self.send_document_by_media_id(to_phone, media_id, filename, caption)

    async def send_document_message(
        self,
        to_phone: str,
        document_url: str,
        filename: str,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Outbound document via public ``link`` (HTTPS URL must be reachable by Meta servers).
        Prefer :meth:`send_document_from_bytes` for CSV when you already have the file bytes.
        """
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        if not to_phone or not document_url or not filename:
            raise ValueError("to_phone, document_url, and filename are required")
        url = self._messages_url()
        doc: Dict[str, Any] = {
            "link": document_url.strip(),
            "filename": filename.strip()[:240],
        }
        if caption and caption.strip():
            doc["caption"] = caption.strip()[:1024]
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": doc,
        }
        headers = self._headers()
        logger.info(
            "Sending WhatsApp document PHONE_NUMBER_ID=%s TO=%s filename=%s",
            self.phone_number_id,
            to_phone,
            doc.get("filename"),
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp document API HTTP %s: %s",
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

    async def list_message_templates(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        """
        GET ``/{waba-id}/message_templates`` — approved and pending templates for admin UI.
        """
        if not self.waba_templates_configured():
            return []
        waba = (settings.meta_whatsapp_waba_id or "").strip()
        url = f"https://graph.facebook.com/{self.graph_version}/{waba}/message_templates"
        params = {
            "fields": "name,language,status,category,components",
            "limit": str(min(max(1, limit), 200)),
        }
        headers = self._auth_headers()
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta list message_templates HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
                return []
            data = resp.json()
            rows = data.get("data")
            if not isinstance(rows, list):
                return []
            return [x for x in rows if isinstance(x, dict)]

    async def create_message_template(
        self,
        *,
        name: str,
        language: str,
        category: str,
        components: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        POST ``/{waba-id}/message_templates`` to submit a template for Meta approval.
        Returns the Graph response (typically ``{"id": "...", "status": "PENDING", "category": ...}``).
        """
        if not self.waba_templates_configured():
            raise RuntimeError("Meta WABA not configured (need access token + WABA id).")
        waba = (settings.meta_whatsapp_waba_id or "").strip()
        url = f"https://graph.facebook.com/{self.graph_version}/{waba}/message_templates"
        payload: Dict[str, Any] = {
            "name": name.strip().lower(),
            "language": language.strip(),
            "category": category.strip().upper(),
            "components": components,
        }
        headers = self._headers()
        logger.info(
            "Submitting WhatsApp template name=%s lang=%s category=%s",
            payload["name"],
            payload["language"],
            payload["category"],
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta create message_template HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def get_message_template(self, meta_template_id: str) -> Dict[str, Any]:
        """Fetch a single template by Meta id — used to reconcile status if webhook missed."""
        if not self.access_token or not meta_template_id:
            raise RuntimeError("access_token and meta_template_id are required")
        url = f"https://graph.facebook.com/{self.graph_version}/{meta_template_id}"
        params = {"fields": "name,language,status,category,components,rejected_reason"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=self._auth_headers())
            if resp.status_code >= 400:
                logger.error(
                    "Meta get message_template HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def delete_message_template(self, name: str) -> Dict[str, Any]:
        """DELETE ``/{waba-id}/message_templates?name=...`` — removes all language variants."""
        if not self.waba_templates_configured():
            raise RuntimeError("Meta WABA not configured.")
        waba = (settings.meta_whatsapp_waba_id or "").strip()
        url = f"https://graph.facebook.com/{self.graph_version}/{waba}/message_templates"
        params = {"name": name.strip().lower()}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(url, params=params, headers=self._auth_headers())
            if resp.status_code >= 400:
                logger.error(
                    "Meta delete message_template HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()

    async def send_template_message(
        self,
        to_phone: str,
        template_name: str,
        language_code: str,
        body_parameters: List[str],
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp ``template`` message with BODY parameters (text slots in order).
        """
        if not self.is_configured():
            raise RuntimeError("Meta WhatsApp Cloud API is not configured.")
        url = self._messages_url()
        params_out: List[Dict[str, str]] = []
        for p in body_parameters:
            txt = (p or "")[:900]
            params_out.append({"type": "text", "text": txt})
        components: List[Dict[str, Any]] = []
        if params_out:
            components.append({"type": "body", "parameters": params_out})
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name.strip(),
                "language": {"code": (language_code or "en_US").strip()},
            },
        }
        if components:
            payload["template"]["components"] = components
        headers = self._headers()
        logger.info(
            "Sending WhatsApp template name=%s lang=%s to=%s slots=%s",
            template_name,
            language_code,
            to_phone,
            len(params_out),
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.error(
                    "Meta WhatsApp template API HTTP %s: %s",
                    resp.status_code,
                    (resp.text or "")[:800],
                )
            resp.raise_for_status()
            return resp.json()
