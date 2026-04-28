"""
Tool registry for the LLM-first bot orchestrator.

Tools are how the LLM is *allowed* to take actions. Every side effect on
behalf of a customer goes through this registry — never via free-form text.

Design rules (see ``schemas.py`` docstring for the full design rule):
  - LLM proposes a tool call; the **control plane** validates and dispatches.
  - Tools are categorised so the verification gate can filter at runtime
    (account_data tools require ``verified=True``).
  - Each tool returns a structured ``ToolResult`` — the orchestrator feeds
    that back to the LLM as a tool message.
"""
from langchain_bot.tools.registry import (
    TOOL_REGISTRY,
    ToolCategory,
    ToolDefinition,
    ToolResult,
    available_tool_names,
    get_tool,
    tools_for_verification_state,
)

__all__ = [
    "TOOL_REGISTRY",
    "ToolCategory",
    "ToolDefinition",
    "ToolResult",
    "available_tool_names",
    "get_tool",
    "tools_for_verification_state",
]
