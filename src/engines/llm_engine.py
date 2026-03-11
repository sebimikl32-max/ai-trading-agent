"""LLM engine — OpenAI async client with rule-based fallbacks.

Responsibilities:
- parse_trade_intent: convert raw text → structured intent
- generate_debate_narrative: produce a conversational trade assessment
- answer_question: general Q&A about the trade or market
- assess_trade_quality: return a structured quality score + commentary
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import AsyncOpenAI, APIError

from config.settings import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a professional quantitative trading assistant.
You help traders think clearly about trade ideas.
You are disciplined, analytical, and always consider risk first.
When asked to return JSON, respond with raw JSON only — no markdown, no explanation.
"""

_DEBATE_SYSTEM_PROMPT = """You are a rigorous trading debate partner.
You challenge trade ideas constructively, raise genuine concerns about risk,
timing, and structure, and always suggest concrete improvements.
Your tone is calm, professional, and focused on protecting capital.
"""


class LLMEngine:
    """Thin async wrapper around OpenAI chat completions."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._temperature = settings.openai_temperature

    # ── Public API ─────────────────────────────────────────────────────────────

    async def parse_trade_intent(self, text: str) -> dict[str, Any]:
        """Parse raw user text into a structured trade intent dict.

        Returns a dict with keys: intent, symbol, direction, entry_price,
        stop_loss, take_profit, risk_pct, rationale, confidence.
        Falls back to an empty dict on any error.
        """
        schema = {
            "intent": "NEW_TRADE|REFINE_TRADE|ASK_QUESTION|CONFIRM_TRADE|REJECT_TRADE|CANCEL|GENERAL_CHAT|REQUEST_ANALYSIS",
            "symbol": "string or null",
            "direction": "LONG|SHORT or null",
            "entry_price": "number or null",
            "stop_loss": "number or null",
            "take_profit": "number or null",
            "risk_pct": "number or null",
            "rationale": "string or null",
            "confidence": "0.0–1.0",
        }
        prompt = (
            f"Parse the following trading message and return JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n\nMessage: {text}"
        )
        return await self._json_completion(_SYSTEM_PROMPT, prompt, fallback={})

    async def generate_debate_narrative(
        self,
        draft_summary: str,
        objections: list[str],
        variants: list[str],
        market_summary: str,
    ) -> str:
        """Return a conversational debate narrative for the user."""
        prompt = (
            f"Trade draft:\n{draft_summary}\n\n"
            f"Market context:\n{market_summary}\n\n"
            f"Objections raised:\n" + "\n".join(f"- {o}" for o in objections) + "\n\n"
            f"Alternative variants:\n" + "\n".join(f"- {v}" for v in variants) + "\n\n"
            "Write a clear, concise debate narrative (3–6 paragraphs) addressing these points. "
            "End with a question or recommendation for the user."
        )
        return await self._text_completion(_DEBATE_SYSTEM_PROMPT, prompt, fallback="")

    async def answer_question(self, question: str, context: str) -> str:
        """Answer a trading question given context."""
        prompt = f"Context:\n{context}\n\nQuestion: {question}"
        return await self._text_completion(_SYSTEM_PROMPT, prompt, fallback="I couldn't process that question right now.")

    async def assess_trade_quality(self, draft_summary: str) -> dict[str, Any]:
        """Return a structured trade quality assessment."""
        schema = {
            "overall_score": "1–10",
            "risk_score": "1–10",
            "timing_score": "1–10",
            "rationale_score": "1–10",
            "summary": "string",
            "key_risks": ["string"],
            "recommendation": "PROCEED|REFINE|WAIT|REJECT",
        }
        prompt = (
            f"Assess the following trade draft and return JSON matching this schema:\n"
            f"{json.dumps(schema, indent=2)}\n\nTrade draft:\n{draft_summary}"
        )
        return await self._json_completion(
            _DEBATE_SYSTEM_PROMPT,
            prompt,
            fallback={"overall_score": 5, "summary": "Assessment unavailable.", "recommendation": "REFINE"},
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _json_completion(
        self, system: str, prompt: str, fallback: Any
    ) -> Any:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except (APIError, json.JSONDecodeError, Exception) as exc:
            logger.warning("LLMEngine._json_completion failed: %s", exc)
            return fallback

    async def _text_completion(
        self, system: str, prompt: str, fallback: str
    ) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or fallback
        except (APIError, Exception) as exc:
            logger.warning("LLMEngine._text_completion failed: %s", exc)
            return fallback
