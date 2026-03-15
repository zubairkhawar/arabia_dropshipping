from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import time

from config import get_openai_api_key, set_openai_api_key_override
from services.ai_orchestrator_service.services import _clear_llm_cache

router = APIRouter()


class ChatMessage(BaseModel):
    conversation_id: Optional[int] = None
    message: str
    channel: str  # whatsapp, web, portal
    customer_id: Optional[int] = None
    store_id: Optional[int] = None
    language: Optional[str] = None


@router.post("/chat")
async def process_chat_message(message: ChatMessage):
    """Process incoming chat message through AI orchestrator"""
    return {"message": "AI chat processing endpoint"}


@router.post("/verify-customer")
async def verify_customer():
    """Verify customer using store code, mobile, or email"""
    return {"message": "Customer verification endpoint"}


@router.post("/detect-language")
async def detect_language():
    """Detect language of incoming message"""
    return {"message": "Language detection endpoint"}


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
