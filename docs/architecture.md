# AI Trading Agent — Architecture

## Overview

The system is a modular, debate-first Telegram-to-MetaTrader 5 trading agent built with clean
separation of concerns. Every trade is treated as a managed case: the user discusses ideas with
the AI, the system debates and refines the proposal, and a human confirmation gate ensures no
order is ever placed without explicit approval.

---

## Layer Diagram

```
Telegram User
     │
     ▼
TradingBot (src/services/telegram_bot.py)
     │   command + message handlers
     ▼
ConversationManager (src/services/conversation.py)
     │   per-user state machine: IDLE → INTAKE → DEBATING → AWAITING_CONFIRMATION → EXECUTED
     ▼
┌────────────┬──────────────┬──────────────┬───────────────┬───────────────┐
│IntentParser│TradeDraftMgr │ DebateEngine │  RiskManager  │  OrderBuilder │
│            │              │              │               │               │
│ pattern +  │create/update │ rule checks  │ lot sizing    │ build MT5     │
│ LLM        │ draft state  │ + LLM narr.  │ risk validate │ request dict  │
└────────────┴──────────────┴──────────────┴───────────────┴───────────────┘
     │                              │                              │
     ▼                              ▼                              ▼
LLMEngine                   MarketDataService               MT5Executor
(OpenAI)                    + TechnicalAnalysis             (asyncio.to_thread)
                            (ATR/RSI/SMA)

JournalService ← every significant event recorded to JSON
```

---

## Data Flow — New Trade

1. User sends text: _"Thinking of longing gold here at 2320, SL 2305, TP 2360, 1% risk"_
2. **TradingBot** receives the Telegram `Message`, extracts `user_id` and `text`.
3. **ConversationManager.handle_message** is called.
4. **IntentParser.parse** runs regex + optional LLM to produce a `ParsedMessage`.
5. State is `IDLE` → intent is `NEW_TRADE` → `_start_intake` is called.
6. A `TradeDraft` is created with `RawUserThesis` + `InterpretedTradeThesis`.
7. **MarketDataService** fetches a `MarketSnapshot` for XAUUSD.
8. **TechnicalAnalysisService** computes `TechnicalFeatures` (ATR, RSI, SMA, swings).
9. A `MarketContext` is attached to the draft.
10. **DebateEngine.evaluate_trade** runs:
    - Checks R:R ratio (raises MEDIUM objection if < 1.5, HIGH if < 1.0)
    - Checks risk % against max
    - Checks SL distance vs ATR (tight/wide stop warnings)
    - Checks rationale presence
    - Generates ATR-based and swing-based `TradeVariant` alternatives
    - Calls LLM to produce a conversational narrative
11. Objections and alternatives are added to the draft.
12. If no blocking objections: draft transitions to `READY`, context to `AWAITING_CONFIRMATION`.
13. `format_trade_decision` renders a structured order summary to the user.
14. User sends `/confirm`.
15. **OrderBuilder** builds `MT5OrderRequest` from `TradeDecision`.
16. `validate_order` checks directional consistency.
17. **MT5Executor** submits the order via `asyncio.to_thread`.
18. `ExecutionResult` is built and returned.
19. **JournalService** persists a complete `JournalEntry` to `data/journal/<uuid>.json`.
20. Success/failure message is sent to the user.

---

## Extension Points

| Interface | Protocol | Future Implementation |
|-----------|----------|----------------------|
| `MacroDataProtocol` | `engines/base.py` | Phase 2: CPI, rates, event calendar |
| `PatternRecognitionProtocol` | `engines/base.py` | Phase 3: chart pattern detection |
| `BehaviourAnalysisProtocol` | `engines/base.py` | Phase 4: emotional trading detection |
| `RegimeClassifierProtocol` | `engines/base.py` | Phase 4: trending/ranging/volatile classifier |
| `DebateEngineProtocol` | `engines/base.py` | Phase 3+: ML-based debate engine |
| `IntentParserProtocol` | `engines/base.py` | Phase 3+: fine-tuned NLU model |
| `ExecutorProtocol` | `engines/base.py` | Phase 5: multi-broker execution |

---

## Schema Design

All schemas are Pydantic v2. The `TradeDraft` is the central mutable state object:

```
TradeDraft
├── raw_thesis: RawUserThesis          ← original, immutable user text
├── interpreted_thesis: InterpretedTradeThesis  ← parsed structure
├── variants: list[TradeVariant]       ← all proposals (user + system + debate)
├── objections: list[TradeObjection]   ← all concerns raised
├── current_best_variant: TradeVariant ← selected for confirmation
├── market_context: MarketContext      ← snapshot at debate time
└── conversation_history: list[str]    ← full dialogue for ML analysis
```

The `JournalEntry` mirrors this structure for persistence. It is designed so that Phase 4+
can train models on historical patterns.

---

## Configuration

All configuration is loaded from `.env` via `pydantic-settings`. See `.env.example` for all
available options. The `Settings` object is a singleton cached via `@lru_cache`.

---

## Security

- **Access control**: `ALLOWED_USER_IDS` in `.env` restricts bot access to specific Telegram user IDs.
- **No secrets in code**: all credentials are loaded from environment variables.
- **No auto-execution**: the confirmation gate is implemented in `ConversationManager._handle_confirm` and cannot be bypassed.
