from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import httpx
import time
from sqlalchemy.orm import Session

from config import get_openai_api_key, set_openai_api_key_override
from services.ai_orchestrator_service.services import _clear_llm_cache
from services.ai_orchestrator_service.services import AIOrchestrator
from database import get_db
from langchain_bot import ArabiaLangChainBot
from models import Conversation, Message

router = APIRouter()


class ChatMessage(BaseModel):
    tenant_id: int = 1
    conversation_id: Optional[int] = None
    message: str
    channel: str  # whatsapp, web, portal
    phone: Optional[str] = None
    store_code: Optional[str] = None
    customer_id: Optional[int] = None
    store_id: Optional[int] = None
    language: Optional[str] = None


class LanguageDetectRequest(BaseModel):
    message: str


@router.post("/chat")
async def process_chat_message(message: ChatMessage, db: Session = Depends(get_db)):
    """
    Process incoming chat with LangChain bot and return AI reply.
    """
    orchestrator = AIOrchestrator()
    detected_language = message.language or await orchestrator.detect_language(message.message)
    customer_context = await orchestrator.fetch_customer_context(
        phone=message.phone,
        message_text=message.message,
    )
    recent_orders = customer_context.get("recent_orders") or []
    customer = customer_context.get("customer") or {}

    bot = ArabiaLangChainBot(db=db)
    reply_text = await bot.generate_reply(
        tenant_id=message.tenant_id,
        user_message=message.message,
        channel=message.channel,
        language=detected_language,
        customer_context=customer,
        recent_orders=recent_orders,
    )

    # If conversation exists, persist user message + AI reply.
    if message.conversation_id is not None:
      conversation = (
          db.query(Conversation)
          .filter(Conversation.id == message.conversation_id)
          .first()
      )
      if conversation:
          db.add(
              Message(
                  conversation_id=conversation.id,
                  content=message.message,
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

    escalate = await orchestrator.should_escalate(message.message)
    return {
        "reply_text": reply_text,
        "language": detected_language,
        "escalate": escalate,
        "context": {
            "customer": customer,
            "recent_orders": recent_orders,
        },
    }


@router.post("/verify-customer")
async def verify_customer():
    """Verify customer using store code, mobile, or email"""
    return {"message": "Customer verification endpoint"}


@router.post("/detect-language")
async def detect_language(payload: LanguageDetectRequest):
    """Detect message language: arabic | english | roman_urdu."""
    orchestrator = AIOrchestrator()
    language = await orchestrator.detect_language(payload.message)
    return {"language": language}


@router.post("/escalate")
async def escalate_to_agent():
    """Escalate conversation to human agent"""
    return {"message": "Agent escalation endpoint"}


# --- OpenAI API key config (admin Settings) ---

class OpenAIConfigUpdate(BaseModel):
    api_key: str


@router.get("/openai-config")
async def get_openai_config():
    """Return whether an OpenAI API key is configured (never the key itself)."""
    key = get_openai_api_key()
    return {"key_configured": bool(key and key.strip())}


@router.post("/openai-config")
async def update_openai_config(body: OpenAIConfigUpdate):
    """Set or update the OpenAI API key used by the bot."""
    key = (body.api_key or "").strip()
    set_openai_api_key_override(key if key else None)
    _clear_llm_cache()
    return {"key_configured": bool(key)}


@router.get("/openai-usage")
async def get_openai_usage(start_time: Optional[int] = None, end_time: Optional[int] = None):
    """Fetch OpenAI usage (tokens/costs) for the configured API key. Uses OpenAI Usage API."""
    key = get_openai_api_key()
    if not key:
        raise HTTPException(status_code=400, detail="No OpenAI API key configured. Add one in Settings.")
    now = int(time.time())
    start_time = start_time or (now - 30 * 24 * 3600)  # default last 30 days
    end_time = end_time or now
    url = "https://api.openai.com/v1/organization/usage/completions"
    params = {"start_time": start_time, "end_time": end_time, "bucket_width": "1d", "limit": 31}
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {key}"},
                timeout=15.0,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach OpenAI: {str(e)}")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid API key or key cannot access usage.")
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI returned {r.status_code}. Usage API may require an admin key or different plan.",
        )
    try:
        data = r.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Invalid response from OpenAI.")
    return data
