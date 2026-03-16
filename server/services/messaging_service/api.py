from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, Request, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import Conversation, Message, Customer
from services.ai_orchestrator_service.services import AIOrchestrator

router = APIRouter()


class ConversationSummary(BaseModel):
    id: int
    tenant_id: int
    store_id: int
    customer_id: int
    agent_id: Optional[int]
    channel: str
    status: str
    customer_name: Optional[str] = None
    last_message: Optional[str] = None
    last_activity_at: Optional[datetime] = None


class ConversationCreate(BaseModel):
    tenant_id: int
    store_id: int
    customer_id: int
    channel: str  # whatsapp, web, portal
    initial_message: Optional[str] = None
    sender_type: Optional[str] = "customer"


class MessageCreate(BaseModel):
    conversation_id: int
    content: str
    sender_type: str  # customer, agent, ai
    channel: str  # whatsapp, web, portal


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    content: str
    sender_type: str
    sender_id: Optional[int]
    language: Optional[str]
    created_at: datetime


class WhatsAppWebhookPayload(BaseModel):
    """
    Minimal normalized payload for a WhatsApp-style webhook.
    In production you would validate the raw provider payload and signature
    before mapping into this schema.
    """

    from_phone: str
    text: str
    store_code: Optional[str] = None
    conversation_id: Optional[int] = None


def _build_conversation_summary(c: Conversation) -> ConversationSummary:
    last_msg = c.messages[-1] if c.messages else None
    customer_name = None
    if c.customer and getattr(c.customer, "name", None):
        customer_name = c.customer.name

    return ConversationSummary(
        id=c.id,
        tenant_id=c.tenant_id,
        store_id=c.store_id,
        customer_id=c.customer_id,
        agent_id=c.agent_id,
        channel=c.channel,
        status=c.status,
        customer_name=customer_name,
        last_message=last_msg.content if last_msg else None,
        last_activity_at=last_msg.created_at if last_msg else c.updated_at,
    )


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(
    tenant_id: int,
    status_param: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List conversations for admin/agent inboxes with basic filters.
    """
    query = (
        db.query(Conversation)
        .filter(Conversation.tenant_id == tenant_id)
        .order_by(desc(Conversation.updated_at))
    )
    if status_param:
        query = query.filter(Conversation.status == status_param)
    if agent_id is not None:
        query = query.filter(Conversation.agent_id == agent_id)

    conversations = query.offset(offset).limit(limit).all()

    # Eager-load relationships used in the summary (customer, messages)
    for conv in conversations:
        _ = conv.customer
        _ = conv.messages

    return [_build_conversation_summary(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=Dict[str, Any])
async def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """
    Get conversation details and messages.
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    messages: List[Message] = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return {
        "conversation": {
            "id": conversation.id,
            "tenant_id": conversation.tenant_id,
            "store_id": conversation.store_id,
            "customer_id": conversation.customer_id,
            "agent_id": conversation.agent_id,
            "channel": conversation.channel,
            "status": conversation.status,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        },
        "messages": [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "content": m.content,
                "sender_type": m.sender_type,
                "sender_id": m.sender_id,
                "language": m.language,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new conversation, optionally with an initial message.
    """
    # Ensure customer exists in DB
    customer: Customer | None = (
        db.query(Customer)
        .filter(
            Customer.id == payload.customer_id,
            Customer.tenant_id == payload.tenant_id,
        )
        .first()
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer not found for tenant",
        )

    conversation = Conversation(
        tenant_id=payload.tenant_id,
        store_id=payload.store_id,
        customer_id=payload.customer_id,
        channel=payload.channel,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.flush()  # get conversation.id before creating message

    if payload.initial_message:
        initial_msg = Message(
            conversation_id=conversation.id,
            content=payload.initial_message,
            sender_type=payload.sender_type or "customer",
            sender_id=None,
            created_at=datetime.utcnow(),
        )
        db.add(initial_msg)

    db.commit()
    db.refresh(conversation)

    # Load relationships for summary
    _ = conversation.customer
    _ = conversation.messages

    return _build_conversation_summary(conversation)


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
):
    """
    Persist a message in a conversation.
    Frontend uses this for agent messages; AI and customer messages are persisted via ingestion pipelines.
    """
    conversation: Conversation | None = (
        db.query(Conversation)
        .filter(Conversation.id == message.conversation_id)
        .first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    sender_id: Optional[int] = None
    if message.sender_type == "agent":
        # Best-effort: use currently assigned agent
        sender_id = conversation.agent_id

    msg = Message(
        conversation_id=message.conversation_id,
        content=message.content,
        sender_type=message.sender_type,
        sender_id=sender_id,
        created_at=datetime.utcnow(),
    )
    conversation.updated_at = datetime.utcnow()

    db.add(msg)
    db.add(conversation)
    db.commit()
    db.refresh(msg)

    # TODO: push to WebSocket / notifications layer

    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        content=msg.content,
        sender_type=msg.sender_type,
        sender_id=msg.sender_id,
        language=msg.language,
        created_at=msg.created_at,
    )


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
    # TODO: persist conversation + message + AI reply into the database.

    return {
        "status": "ok",
        "reply_text": ai_result["reply_text"],
        "escalate": ai_result["escalate"],
        "language": ai_result["language"],
    }


@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: int):
    """
    WebSocket endpoint for real-time messaging.
    For now this is a simple echo-style placeholder.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)
    except Exception:
        await websocket.close()
