"""
Regression tests for WhatsApp transcript 2026-04-30 17:13:

  Customer (mid-trending KSA list): "arabia delivery and return charges"
  Bot:                              "Delivery aur return charges ki tafseel
                                     sales team se mil jayegi…"

Root cause: the trending LLM-runner has no access to CRITICAL FACTS or
the KB. Its system prompt tells it to answer topic-change questions
with a "short friendly one-liner" — so the LLM produced a vague
deflection. The controller then sent that deflection as the final reply
even though it didn't actually answer the question.

Fix: when the trending runner returns state="done" because of a topic
change, and the message is NOT a pure acknowledgement / thanks, the
controller now ignores the runner's reply and routes the question to
ai_forward (which has KB + CRITICAL FACTS context) for a real answer.

These tests verify the helper and the wiring.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.customer_bot_flow.service import _is_pure_ack_or_thanks


# Pure acks: the runner's one-liner is fine, no need to bail.
PURE_ACKS = [
    "ok", "okay", "okk", "kk",
    "thanks", "thank you", "thx", "ty",
    "shukriya", "shukria", "shukran", "bohat shukriya",
    "theek hai", "theek", "teek hai", "sahi",
    "got it", "cool", "nice", "great", "alright", "fine",
    "acha", "achha", "accha",
    "شكرا", "شكراً", "تمام", "حسناً", "طيب",
]


# Real informational questions that look "topic-change-y" but must NOT
# be treated as acks. Each of these must route to ai_forward.
INFORMATIONAL_QUESTIONS = [
    "arabia delivery and return charges",
    "Arabia ke shipping rates kya hain?",
    "How much is the return fee?",
    "payment kab hoti hai?",
    "When do I get paid?",
    "كم تكلفة الشحن؟",
    "what's the support number",
    "How does the COD work?",
    "Profit margin kaise calculate hoti hai",
    "Crypto payment kaise lete ho",
]


class TestPureAckDetector:
    @pytest.mark.parametrize("msg", PURE_ACKS)
    def test_pure_acks_detected(self, msg: str) -> None:
        assert _is_pure_ack_or_thanks(msg), (
            f"{msg!r} is a pure ack — runner's one-liner is fine"
        )

    @pytest.mark.parametrize("msg", INFORMATIONAL_QUESTIONS)
    def test_informational_questions_not_acks(self, msg: str) -> None:
        assert not _is_pure_ack_or_thanks(msg), (
            f"{msg!r} is an informational question — must route to "
            "ai_forward, not be treated as a topic-change ack"
        )

    def test_long_message_with_thanks_tail_not_ack(self) -> None:
        """A long message that just happens to end with 'thanks' is NOT a
        pure ack. The detector must require the WHOLE message to be an ack
        (length cap + anchored regex)."""
        assert not _is_pure_ack_or_thanks(
            "Tell me delivery and return charges, thanks"
        )
        assert not _is_pure_ack_or_thanks(
            "What's the COD fee for KSA? thank you"
        )

    def test_empty_input_is_not_ack(self) -> None:
        assert not _is_pure_ack_or_thanks("")
        assert not _is_pure_ack_or_thanks("   ")


class TestBuildBotflowResultBailsToAiForwardOnTopicChange:
    """Static check on the wiring inside service.py — when the trending
    runner returns state="done" and the message is not a pure ack, the
    controller must call ai_forward instead of using the runner's reply."""

    def _build_block(self) -> str:
        src = (
            Path(__file__).resolve().parent.parent
            / "server" / "services" / "customer_bot_flow" / "service.py"
        )
        text = src.read_text(encoding="utf-8")
        i = text.find("def _build_botflowresult_from_llm")
        # Read up to the next sibling fn definition.
        end = text.find("\n    def ", i + 50)
        return text[i:end] if end > i else text[i: i + 5000]

    def test_topic_change_branch_bails_to_ai_forward(self) -> None:
        block = self._build_block()
        # The state=="done" branch must check _is_pure_ack_or_thanks and
        # return ai_forward when the message is NOT an ack.
        assert "_is_pure_ack_or_thanks(text)" in block
        # ai_forward must be called inside the "done" branch.
        assert "ai_forward(" in block
        # And the [Customer question] prefix must be used so ai_forward
        # treats the message as a real ask (matches the order/invoice path).
        assert '"[Customer question] " + text' in block
