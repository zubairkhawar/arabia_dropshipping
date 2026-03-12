from fastapi import APIRouter, WebSocket, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any

from services.ai_orchestrator_service.services import AIOrchestrator

router = APIRouter()


class MessageCreate(BaseModel):
    conversation_id: int
    content: str
    sender_type: str  # customer, agent, ai
    channel: str  # whatsapp, web, portal


class WhatsAppWebhookPayload(BaseModel):
    """
    Minimal normalized payload for a WhatsApp-style webhook.
    In production you would validate the raw provider payload and signature
    before mapping into this schema.
    """

    from_phone: str
    text: str
    store_code: Optional[str] = None
    conversation_id: Optional[str] = None


@router.get("/conversations")
async def list_conversations():
    """List all conversations"""
    return {"message": "List conversations endpoint"}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    """Get conversation details and messages"""
    return {"message": f"Get conversation {conversation_id} endpoint"}


@router.post("/conversations")
async def create_conversation():
    """Create a new conversation"""
    return {"message": "Create conversation endpoint"}


@router.post("/messages")
async def send_message(message: MessageCreate):
    """Send a message"""
    return {"message": "Send message endpoint"}


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(payload: WhatsAppWebhookPayload, request: Request) -> Dict[str, Any]:
    """
    Entry point for WhatsApp provider webhooks (normalized).
    - Inbound: customer message
    - Outbound: AI reply (provider-specific send to be implemented separately)

    For now this endpoint only returns the AI's reply in the HTTP response
    so you can test the full pipeline without a real provider.
    """
    orchestrator = AIOrchestrator()
    ai_result = await orchestrator.process_message(
        message=payload.text,
        channel="whatsapp",
        phone=payload.from_phone,
        store_code=payload.store_code,
    )

    # TODO: call your actual WhatsApp provider client here to send ai_result["reply_text"]

    return {
        "status": "ok",
        "reply_text": ai_result["reply_text"],
        "escalate": ai_result["escalate"],
        "language": ai_result["language"],
    }


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: int):
    """WebSocket endpoint for real-time messaging"""
    await websocket.accept()
    # Implementation for WebSocket handling
    await websocket.close()
