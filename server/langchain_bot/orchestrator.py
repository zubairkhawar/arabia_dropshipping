"""
LLM-first orchestrator (Phase 2 of the bot redesign).

Responsibilities:
  - Take a customer message + conversation state, drive the LLM via tool-use,
    return a final reply text + any side-effect signals.
  - Hard-cap iterations to keep p95 latency under the budget set in
    ``settings.llm_max_tool_calls_per_turn`` (default: 2).
  - Record token usage / latency / errors via ``llm_cost_tracker``.

Design rule: the LLM drafts; the **control plane** gates and executes;
templates are the protocol library for messages whose exact bytes are
contractually meaningful. This module knows nothing about verification
state, handoff state, or pagination cursors — that lives in
``control_plane.py`` which wraps this orchestrator.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import get_openai_api_key, settings
from langchain_bot.llm_cost_tracker import LLMCallTimer
from langchain_bot.prompts import (
    build_system_prompt_template,
    llm_unavailable_reply,
    normalize_context_text,
    now_utc_iso,
)
from langchain_bot.tools import ToolDefinition, ToolResult, get_tool
from langchain_bot.tools.handlers import HANDLERS, ToolContext

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result type returned by `run_turn`
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class OrchestratorResult:
    reply_text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    escalation_signal: bool = False
    verification_signal: Optional[Dict[str, Any]] = None  # {step, payload}
    csv_signal: Optional[Dict[str, Any]] = None
    trending_signal: Optional[Dict[str, Any]] = None
    used_fallback: bool = False
    error: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Tool schema serialization for OpenAI tool-use
# ─────────────────────────────────────────────────────────────────────────────
def _tool_to_openai_function(t: ToolDefinition) -> Dict[str, Any]:
    """Convert a ToolDefinition to OpenAI tool-calling JSON schema."""
    return {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.args_schema.model_json_schema(),
        },
    }


def _serialize_tools_for_llm(allowed: List[ToolDefinition]) -> List[Dict[str, Any]]:
    return [_tool_to_openai_function(t) for t in allowed]


# ─────────────────────────────────────────────────────────────────────────────
# Side-effect signal extraction
# Tool handlers return ToolResult with structured data; some carry "signals"
# (escalation, verification step, csv, trending) that the caller acts on.
# ─────────────────────────────────────────────────────────────────────────────
def _harvest_signals(result: OrchestratorResult, name: str, payload: Dict[str, Any]) -> None:
    if name == "escalate_to_agent" and payload.get("ok"):
        result.escalation_signal = True
    if name in (
        "start_verification",
        "submit_verification_email",
        "verify_otp",
        "submit_verification_mobile",
        "send_otp_resend",
    ):
        data = payload.get("data") or {}
        result.verification_signal = {
            "step": data.get("verification_signal"),
            "payload": data,
        }
    if name == "generate_csv":
        data = payload.get("data") or {}
        if data.get("csv_signal"):
            result.csv_signal = data
    if name == "get_trending_products":
        data = payload.get("data") or {}
        if data.get("trending_signal"):
            result.trending_signal = data


# ─────────────────────────────────────────────────────────────────────────────
# The main entry point
# ─────────────────────────────────────────────────────────────────────────────
async def run_turn(
    *,
    db: Session,
    tenant_id: int,
    customer_phone: str,
    conversation_id: Optional[int],
    user_message: str,
    language: str,
    bot_flow: Dict[str, Any],
    store_client: Any,
    allowed_tools: List[ToolDefinition],
    extra_context_blocks: Optional[Dict[str, str]] = None,
    model_override: Optional[str] = None,
) -> OrchestratorResult:
    """Drive one customer turn through the LLM with tool-use.

    The control plane is responsible for:
      - Filtering ``allowed_tools`` (e.g. dropping account_data when unverified)
      - Handing in any extra context the LLM should see (orders, invoices, etc.)
      - Handling signals on the returned ``OrchestratorResult``

    On hard LLM failure (timeouts, API down) the orchestrator returns a
    fallback reply rather than raising — same contract as the legacy bot.
    """
    key = get_openai_api_key()
    if not key:
        return OrchestratorResult(
            reply_text=llm_unavailable_reply(language),
            error="missing_openai_api_key",
            used_fallback=True,
        )

    # Lazy import to keep this module importable in test environments without
    # the full LangChain stack installed.
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    model_name = model_override or settings.openai_model
    llm = ChatOpenAI(
        model_name=model_name,
        temperature=settings.openai_temperature,
        openai_api_key=key,
        timeout=getattr(settings, "openai_request_timeout", 30.0),
        max_retries=0,
    )

    tools_payload = _serialize_tools_for_llm(allowed_tools)
    llm_with_tools = llm.bind_tools(tools_payload) if tools_payload else llm

    system_prompt = _build_system_prompt(
        language=language,
        extra_context_blocks=extra_context_blocks or {},
    )

    messages: List[Any] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    ctx = ToolContext(
        db=db,
        tenant_id=tenant_id,
        customer_phone=customer_phone,
        conversation_id=conversation_id,
        language=language,
        store_client=store_client,
        bot_flow=bot_flow,
    )

    result = OrchestratorResult(reply_text="")
    max_iters = max(1, int(getattr(settings, "llm_max_tool_calls_per_turn", 2)) + 1)

    for iteration in range(max_iters):
        try:
            with LLMCallTimer(
                model=model_name, customer_phone=customer_phone, tenant_id=tenant_id
            ) as timer:
                response = await llm_with_tools.ainvoke(messages)
                # Best-effort token bookkeeping
                usage = getattr(response, "response_metadata", {}).get("token_usage", {})
                timer.input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                timer.output_tokens = int(usage.get("completion_tokens", 0) or 0)
                timer.tool_calls = len(getattr(response, "tool_calls", []) or [])
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "orchestrator LLM call failed (iter=%d, model=%s)", iteration, model_name
            )
            return OrchestratorResult(
                reply_text=llm_unavailable_reply(language),
                error=f"{type(exc).__name__}:{exc!s}"[:200],
                used_fallback=True,
            )

        tool_calls = list(getattr(response, "tool_calls", []) or [])
        text = (getattr(response, "content", None) or "").strip()

        # No tool calls — LLM produced a final answer.
        if not tool_calls:
            result.reply_text = text or ""
            return result

        # Hard-cap exceeded — stop the chain and use whatever text the LLM gave.
        if iteration >= max_iters - 1:
            logger.warning(
                "orchestrator: tool-call cap hit (max=%d). Using last text response.", max_iters
            )
            result.reply_text = text or ""
            return result

        # Append the AI message that contained the tool calls so the conversation
        # is well-formed for the follow-up LLM call.
        messages.append(response)

        # Execute each tool call, append results.
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            args_raw = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "tool")

            tool_payload = await _execute_tool(name=name, args_raw=args_raw, ctx=ctx)
            result.tool_calls.append({"name": name, "args": args_raw, "id": tc_id})
            result.tool_results.append({"id": tc_id, "name": name, "payload": tool_payload})
            _harvest_signals(result, name or "", tool_payload)

            messages.append(
                ToolMessage(
                    content=json.dumps(tool_payload, default=str),
                    tool_call_id=tc_id,
                    name=name or "tool",
                )
            )

    # Should not be reachable, but guard for safety.
    if not result.reply_text:
        result.reply_text = llm_unavailable_reply(language)
        result.used_fallback = True
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Tool dispatch helper
# ─────────────────────────────────────────────────────────────────────────────
async def _execute_tool(
    *, name: Optional[str], args_raw: Any, ctx: ToolContext
) -> Dict[str, Any]:
    """Validate args, dispatch to handler, return ``ToolResult.to_llm_payload()``."""
    if not name or name not in HANDLERS:
        return ToolResult(ok=False, data={}, error=f"unknown_tool:{name}").to_llm_payload()

    try:
        tool_def = get_tool(name)
    except KeyError:
        return ToolResult(ok=False, data={}, error=f"unknown_tool:{name}").to_llm_payload()

    # Re-validate args server-side. The LLM is allowed to be wrong about types.
    try:
        if isinstance(args_raw, str):
            args_raw = json.loads(args_raw or "{}")
        validated = tool_def.args_schema.model_validate(args_raw or {})
    except Exception as exc:  # noqa: BLE001
        return ToolResult(
            ok=False, data={}, error=f"invalid_args:{type(exc).__name__}:{exc!s}"[:200]
        ).to_llm_payload()

    handler = HANDLERS[name]
    try:
        out: ToolResult = await handler(validated, ctx)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool handler %s failed", name)
        return ToolResult(
            ok=False, data={}, error=f"handler_error:{type(exc).__name__}"
        ).to_llm_payload()

    return out.to_llm_payload()


# ─────────────────────────────────────────────────────────────────────────────
# System prompt assembly
# Reuses prompts.py but stitches in any pre-fetched context blocks the
# control plane wants the LLM to see (recent orders, KB, etc.).
# ─────────────────────────────────────────────────────────────────────────────
def _build_system_prompt(*, language: str, extra_context_blocks: Dict[str, str]) -> str:
    base = build_system_prompt_template()
    # The base template uses {placeholders}; with tool-use we don't always
    # have a full fetch_context. Render any placeholder we don't care about as
    # "None" or whatever the caller passes in.
    defaults = {
        "current_time": now_utc_iso(),
        "channel": "whatsapp",
        "language": normalize_context_text(language, "english"),
        "recent_context_hint": "None",
        "memory_context": "None",
        "customer_context": "None",
        "order_discovery_context": "None",
        "orders_context": "None",
        "invoices_context": "None",
        "schedule_context": "None",
        "broadcast_context": "None",
        "agent_availability_context": "None",
        "post_close_handover_context": "None",
        "knowledge_context": "None — call the search_kb tool for service / policy questions.",
        "kb_followup_suggestions": "None",
        "conversation_history": "None",
        "user_message": "{user_message}",  # left for compatibility with legacy template
    }
    defaults.update({k: v for k, v in (extra_context_blocks or {}).items() if v is not None})

    try:
        return base.format(**defaults)
    except KeyError as exc:
        logger.warning("system prompt missing placeholder %s — using safe defaults", exc)
        # Fall back to substituting unknown placeholders with the literal "None".
        # Iterating with str.format_map and a defaultdict-like wrapper.
        class _SafeDict(dict):
            def __missing__(self, k: str) -> str:
                return "None"

        return base.format_map(_SafeDict(defaults))
