"""Intent parser — pattern matching with optional LLM fallback."""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.engines.llm_engine import LLMEngine
from src.schemas.message import ParsedMessage, UserIntent
from src.schemas.trade import TradeDirection

logger = logging.getLogger(__name__)

# ── Symbol slang → canonical mapping ─────────────────────────────────────────
SLANG_MAP: dict[str, str] = {
    "gold": "XAUUSD",
    "xau": "XAUUSD",
    "silver": "XAGUSD",
    "cable": "GBPUSD",
    "fiber": "EURUSD",
    "euro": "EURUSD",
    "eur": "EURUSD",
    "nas": "NAS100",
    "nasdaq": "NAS100",
    "nas100": "NAS100",
    "dow": "US30",
    "dji": "US30",
    "sp500": "US500",
    "spx": "US500",
    "uj": "USDJPY",
    "aussie": "AUDUSD",
    "aud": "AUDUSD",
    "kiwi": "NZDUSD",
    "loonie": "USDCAD",
    "swissy": "USDCHF",
    "oil": "USOIL",
    "crude": "USOIL",
    "wti": "USOIL",
    "brent": "UKOIL",
    "btc": "BTCUSD",
    "bitcoin": "BTCUSD",
    "eth": "ETHUSD",
    "ethereum": "ETHUSD",
    "gbp": "GBPUSD",
    "jpy": "USDJPY",
    "chf": "USDCHF",
    "cad": "USDCAD",
}

# ── Keyword → direction mapping ───────────────────────────────────────────────
LONG_WORDS = {"long", "buy", "bull", "bullish", "long", "up", "long position"}
SHORT_WORDS = {"short", "sell", "bear", "bearish", "down", "short position"}

# ── Intent keyword patterns ───────────────────────────────────────────────────
_CONFIRM_PATTERN = re.compile(r"\b(confirm|yes|do it|execute|place it|go ahead)\b", re.I)
_REJECT_PATTERN = re.compile(r"\b(no|reject|don'?t|cancel it|abort)\b", re.I)
_CANCEL_PATTERN = re.compile(r"\b(cancel|reset|forget it|start over|stop everything|stop the bot)\b", re.I)
_REFINE_PATTERN = re.compile(
    r"\b(change|adjust|move|update|refine|modify|use|set|tighter|wider|different)\b", re.I
)
_QUESTION_PATTERN = re.compile(r"(\?|what|how|why|should|would|could|can i|is it|tell me)", re.I)
_ANALYSIS_PATTERN = re.compile(r"\b(analyse|analyze|analysis|check|look at|what does|technical|atr|rsi)\b", re.I)
_TRADE_PATTERN = re.compile(
    r"\b(long|short|buy|sell|trade|setup|position|entry|going|thinking of)\b", re.I
)

_PRICE_PATTERN = re.compile(r"\b(\d{1,6}(?:\.\d{1,5})?)\b")
_RISK_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:risk)?", re.I)


class IntentParser:
    """Parse raw user messages into structured ParsedMessage objects.

    Uses regex/keyword rules as the primary approach and falls back to
    the LLMEngine when confidence is low or fields are missing.
    """

    def __init__(self, llm_engine: Optional[LLMEngine] = None) -> None:
        self._llm = llm_engine

    async def parse(
        self,
        text: str,
        user_id: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> ParsedMessage:
        """Parse *text* and return a ParsedMessage."""
        intent = self._classify_intent(text)
        symbol = self._extract_symbol(text)
        direction = self._extract_direction(text)
        price_levels = self._extract_price_levels(text)
        risk_pct = self._extract_risk_pct(text)
        confidence = self._estimate_confidence(intent, symbol, direction)

        # If confidence is low and an LLM is available, attempt enrichment.
        if confidence < 0.6 and self._llm:
            try:
                llm_result = await self._llm.parse_trade_intent(
                    text, conversation_history=conversation_history
                )
                symbol = symbol or _canonicalise(llm_result.get("symbol"))
                direction = direction or _parse_direction(llm_result.get("direction"))
                risk_pct = risk_pct or llm_result.get("risk_pct")
                for key in ("entry_price", "stop_loss", "take_profit"):
                    val = llm_result.get(key)
                    if val and key not in price_levels:
                        price_levels[key] = float(val)
                llm_intent = _parse_intent(llm_result.get("intent"))
                if llm_intent:
                    intent = llm_intent
                llm_conf = llm_result.get("confidence", 0.5)
                confidence = max(confidence, float(llm_conf))
            except Exception as exc:
                logger.debug("LLM intent enrichment failed: %s", exc)

        return ParsedMessage(
            intent=intent,
            extracted_symbol=symbol,
            extracted_direction=direction,
            extracted_price_levels=price_levels,
            extracted_risk_pct=risk_pct,
            raw_text=text,
            confidence=confidence,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _classify_intent(self, text: str) -> UserIntent:
        t = text.lower()
        if _CONFIRM_PATTERN.search(t):
            return UserIntent.CONFIRM_TRADE
        if _REJECT_PATTERN.search(t):
            return UserIntent.REJECT_TRADE
        if _CANCEL_PATTERN.search(t):
            return UserIntent.CANCEL
        if _ANALYSIS_PATTERN.search(t):
            return UserIntent.REQUEST_ANALYSIS
        if _REFINE_PATTERN.search(t) and self._has_trade_context(t):
            return UserIntent.REFINE_TRADE
        if _TRADE_PATTERN.search(t):
            return UserIntent.NEW_TRADE
        if _QUESTION_PATTERN.search(t):
            return UserIntent.ASK_QUESTION
        return UserIntent.GENERAL_CHAT

    @staticmethod
    def _has_trade_context(text: str) -> bool:
        return bool(_TRADE_PATTERN.search(text))

    def _extract_symbol(self, text: str) -> Optional[str]:
        lower = text.lower()
        # Check slang map first (longest match wins)
        best: Optional[str] = None
        best_len = 0
        for slang, canonical in SLANG_MAP.items():
            pattern = rf"\b{re.escape(slang)}\b"
            if re.search(pattern, lower) and len(slang) > best_len:
                best = canonical
                best_len = len(slang)
        if best:
            return best
        # Fallback: look for known FX/CFD ticker patterns (must look like a pair or index)
        # Require pairs (6-letter like EURUSD) or indices with digits (NAS100, US30)
        match = re.search(
            r"\b([A-Z]{3,4}(?:USD|EUR|GBP|JPY|CHF|CAD|AUD|NZD)|"
            r"[A-Z]{2,4}(?:100|200|30|500|1000))\b",
            text.upper(),
        )
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_direction(text: str) -> Optional[TradeDirection]:
        lower = text.lower()
        words = set(re.findall(r"\b\w+\b", lower))
        if words & LONG_WORDS:
            return TradeDirection.LONG
        if words & SHORT_WORDS:
            return TradeDirection.SHORT
        return None

    @staticmethod
    def _extract_price_levels(text: str) -> dict[str, float]:
        levels: dict[str, float] = {}
        # Named levels with optional prepositions: "entry at 1.2345", "stop loss: 1.23", "tp = 1.25"
        for label, keys in [
            (r"(?:entry|at price|price)\s*(?:at|:|-|=)?\s*", "entry_price"),
            (r"(?:stop.?loss|stop|sl)\s*(?:at|:|-|=)?\s*(?:at\s+)?", "stop_loss"),
            (r"(?:take.?profit|target|tp|t\.?p\.?)\s*(?:at|:|-|=)?\s*(?:at\s+)?", "take_profit"),
        ]:
            m = re.search(label + r"(\d{1,6}(?:\.\d{1,5})?)", text, re.I)
            if m:
                levels[keys] = float(m.group(1))
        return levels

    @staticmethod
    def _extract_risk_pct(text: str) -> Optional[float]:
        m = _RISK_PATTERN.search(text)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def _estimate_confidence(
        intent: UserIntent, symbol: Optional[str], direction: Optional[TradeDirection]
    ) -> float:
        score = 0.4
        if intent in (UserIntent.NEW_TRADE, UserIntent.REFINE_TRADE):
            score += 0.2
        if symbol:
            score += 0.2
        if direction:
            score += 0.2
        return min(score, 1.0)


# ── Module-level helpers ───────────────────────────────────────────────────────


def _canonicalise(symbol: Optional[str]) -> Optional[str]:
    if not symbol:
        return None
    lower = symbol.lower().strip()
    return SLANG_MAP.get(lower, symbol.upper())


def _parse_direction(value: Optional[str]) -> Optional[TradeDirection]:
    if not value:
        return None
    upper = value.upper()
    try:
        return TradeDirection(upper)
    except ValueError:
        return None


def _parse_intent(value: Optional[str]) -> Optional[UserIntent]:
    if not value:
        return None
    try:
        return UserIntent(value.upper())
    except ValueError:
        return None
