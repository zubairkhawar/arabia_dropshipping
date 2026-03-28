import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, WebSocket, Request, Depends, HTTPException, status, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from models import Conversation, Message, Customer, Store
from config import settings
from services.ai_orchestrator_service.services import AIOrchestrator
from langchain_bot import ArabiaLangChainBot
from services.whatsapp_service.meta_cloud import MetaWhatsAppClient
from services.customer_bot_flow import format_kb_reply, process_customer_bot_message
from services.agent_routing_service.api import assign_from_bot_flow

logger = logging.getLogger(__name__)

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


class ConversationStatusUpdate(BaseModel):
    status: str  # active | closed | escalated


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


def _extract_meta_text_message(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse Meta webhook payload and return first inbound text message.
    """
    if payload.get("object") != "whatsapp_business_account":
        return None
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages") or []
            if not messages:
                continue
            contacts = value.get("contacts") or []
            contact_name = None
            if contacts and isinstance(contacts[0], dict):
                profile = contacts[0].get("profile") or {}
                contact_name = profile.get("name")
            for msg in messages:
                if msg.get("type") != "text":
                    continue
                return {
                    "from_phone": msg.get("from"),
                    "text": (msg.get("text") or {}).get("body", ""),
                    "wa_message_id": msg.get("id"),
                    "contact_name": contact_name,
                }
    return None


def _get_or_create_default_store(db: Session, tenant_id: int) -> Store:
    store = (
        db.query(Store)
        .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
        .order_by(Store.id.asc())
        .first()
    )
    if store:
        return store
    store = Store(
        tenant_id=tenant_id,
        name="WhatsApp Default Store",
        store_code=f"tenant-{tenant_id}-whatsapp-default",
        store_type="custom_api",
        is_active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def _get_or_create_customer_by_phone(
    db: Session, tenant_id: int, store_id: int, phone: str, name: Optional[str]
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.tenant_id == tenant_id, Customer.phone == phone)
        .first()
    )
    if customer:
        if name and not customer.name:
            customer.name = name
            db.add(customer)
            db.commit()
            db.refresh(customer)
        return customer

    customer = Customer(
        tenant_id=tenant_id,
        store_id=store_id,
        phone=phone,
        name=name or f"WhatsApp {phone}",
        customer_data={"source": "meta_whatsapp_cloud"},
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _get_or_create_active_whatsapp_conversation(
    db: Session, tenant_id: int, store_id: int, customer_id: int
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.store_id == store_id,
            Conversation.customer_id == customer_id,
            Conversation.channel == "whatsapp",
            Conversation.status == "active",
        )
        .order_by(desc(Conversation.updated_at))
        .first()
    )
    if conversation:
        return conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        store_id=store_id,
        customer_id=customer_id,
        channel="whatsapp",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


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


@router.patch("/conversations/{conversation_id}/status", response_model=ConversationSummary)
async def update_conversation_status(
    conversation_id: int,
    payload: ConversationStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Update conversation status (active/closed/escalated).
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    conversation.status = payload.status
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    _ = conversation.customer
    _ = conversation.messages
    return _build_conversation_summary(conversation)


@router.post("/conversations/{conversation_id}/send-to-ai", response_model=ConversationSummary)
async def send_conversation_to_ai(
    conversation_id: int,
    db: Session = Depends(get_db),
):
    """
    Return ownership of a conversation to AI by clearing assigned agent.
    """
    conversation: Conversation | None = (
        db.query(Conversation).filter(Conversation.id == conversation_id).first()
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    conversation.agent_id = None
    conversation.status = "active"
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    _ = conversation.customer
    _ = conversation.messages
    return _build_conversation_summary(conversation)


@router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Meta Cloud API webhook verification.
    """
    expected = settings.meta_whatsapp_verify_token
    if hub_mode == "subscribe" and expected and hub_verify_token == expected:
        return PlainTextResponse(hub_challenge or "")
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Meta Cloud API webhook receiver:
    - parse inbound text message
    - persist inbound message to conversation
    - generate AI reply with LangChain bot
    - send outbound reply via Meta Cloud API
    - persist outbound AI reply
    """
    body = await request.json()
    inbound = _extract_meta_text_message(body)
    if not inbound:
        # Non-message webhooks (delivery/read/status) are valid and should ACK.
        return {"status": "ignored"}

    from_phone = inbound["from_phone"]
    text = inbound["text"]
    if not from_phone or not text:
        return {"status": "ignored"}

    tenant_id = 1
    store = _get_or_create_default_store(db, tenant_id=tenant_id)
    customer = _get_or_create_customer_by_phone(
        db,
        tenant_id=tenant_id,
        store_id=store.id,
        phone=from_phone,
        name=inbound.get("contact_name"),
    )
    conversation = _get_or_create_active_whatsapp_conversation(
        db,
        tenant_id=tenant_id,
        store_id=store.id,
        customer_id=customer.id,
    )

    orchestrator = AIOrchestrator()
    bot = ArabiaLangChainBot(db=db)

    if conversation.agent_id:
        detected_language = await orchestrator.detect_language(text)
        db.add(
            Message(
                conversation_id=conversation.id,
                content=text,
                sender_type="customer",
                sender_id=None,
                language=detected_language,
                created_at=datetime.utcnow(),
            )
        )
        conversation.updated_at = datetime.utcnow()
        db.add(conversation)
        db.commit()
        return {
            "status": "ok",
            "conversation_id": conversation.id,
            "skipped": "human_agent",
            "reply_text": "",
            "language": detected_language,
            "escalate": False,
            "meta_response": None,
        }

    flow = await process_customer_bot_message(
        db=db,
        conversation=conversation,
        user_message=text,
        tenant_id=tenant_id,
        orchestrator=orchestrator,
        phone=from_phone,
    )

    if flow.merge_metadata:
        conversation.conversation_metadata = flow.merge_metadata

    detected_language = await orchestrator.detect_language(text)
    bf_lang = (flow.merge_metadata.get("bot_flow") or {}).get("lang")
    if isinstance(bf_lang, str) and bf_lang.strip():
        detected_language = bf_lang

    if not flow.handled:
        customer_context = await orchestrator.fetch_customer_context(
            phone=from_phone,
            message_text=text,
        )
        recent_orders = customer_context.get("recent_orders") or []
        customer_ctx = customer_context.get("customer") or {}
        reply_text = await bot.generate_reply(
            tenant_id=tenant_id,
            user_message=text,
            channel="whatsapp",
            language=detected_language,
            customer_context=customer_ctx,
            recent_orders=recent_orders,
        )
    elif flow.use_ai:
        if flow.skip_store_api:
            customer_ctx = {}
            recent_orders = []
        else:
            customer_context = await orchestrator.fetch_customer_context(
                phone=from_phone,
                message_text=text,
            )
            recent_orders = customer_context.get("recent_orders") or []
            customer_ctx = customer_context.get("customer") or {}
        reply_text = await bot.generate_reply(
            tenant_id=tenant_id,
            user_message=flow.ai_user_message,
            channel="whatsapp",
            language=detected_language,
            customer_context=customer_ctx,
            recent_orders=recent_orders,
        )
        if flow.skip_store_api:
            reply_text = format_kb_reply(bf_lang or detected_language, reply_text)
    else:
        reply_text = flow.reply_text

    if flow.assign_team:
        kind = (flow.merge_metadata.get("bot_flow") or {}).get("customer_kind")
        assign_from_bot_flow(
            db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            store_id=store.id,
            customer_id=customer.id,
            routed_team=flow.assign_team,
            is_existing_customer=(kind == "existing"),
        )
        db.refresh(conversation)

    db.add(
        Message(
            conversation_id=conversation.id,
            content=text,
            sender_type="customer",
            sender_id=None,
            language=detected_language,
            created_at=datetime.utcnow(),
        )
    )
    db.add(
        Message(
            conversation_id=conversation.id,
            content=reply_text,
            sender_type="ai",
            sender_id=None,
            language=detected_language,
            created_at=datetime.utcnow(),
        )
    )
    conversation.updated_at = datetime.utcnow()
    db.add(conversation)
    db.commit()

    wa_response: Dict[str, Any] | None = None
    client = MetaWhatsAppClient()
    if reply_text:
        if not client.is_configured():
            logger.warning(
                "WhatsApp reply not sent: Meta Cloud API env missing. "
                "Set META_WHATSAPP_ACCESS_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID on the host."
            )
            wa_response = {"error": "meta_not_configured"}
        else:
            try:
                wa_response = await client.send_text_message(to_phone=from_phone, text=reply_text)
                logger.info(
                    "WhatsApp outbound sent to=%s conversation_id=%s",
                    from_phone[-6:] if from_phone else "?",
                    conversation.id,
                )
            except Exception:
                logger.exception(
                    "WhatsApp send_text_message failed (conversation_id=%s)",
                    conversation.id,
                )
                wa_response = {"error": "meta_send_failed"}

    escalate = flow.escalate or await orchestrator.should_escalate(text)
    return {
        "status": "ok",
        "conversation_id": conversation.id,
        "reply_text": reply_text,
        "language": detected_language,
        "escalate": escalate,
        "meta_response": wa_response,
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
