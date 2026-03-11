# AI Trading Agent — Phase Roadmap

## Phase 1 — Foundation (current) ✅

**Goal**: Debate-first, human-confirmed trading via Telegram and MetaTrader 5.

| Feature | Status |
|---------|--------|
| Telegram bot (commands + free-form text) | ✅ |
| Conversation state machine (IDLE → INTAKE → DEBATING → AWAITING_CONFIRMATION → EXECUTED) | ✅ |
| Intent parsing with slang mapping (gold, cable, fiber, nas, etc.) | ✅ |
| Trade draft lifecycle (RawThesis → InterpretedThesis → Variants → Decision) | ✅ |
| Rule-based debate engine (R:R, risk %, ATR stop checks) | ✅ |
| LLM debate narrative (OpenAI) with rule-based fallback | ✅ |
| Market data retrieval from MT5 | ✅ |
| Technical analysis (ATR, RSI, SMA, swing levels) | ✅ |
| Risk-based position sizing | ✅ |
| Order builder + directional validation | ✅ |
| Human confirmation gate (/confirm) | ✅ |
| MT5 order submission | ✅ |
| Trade journal (JSON persistence) | ✅ |
| Audit log (JSONL) | ✅ |
| Protocol interfaces for future extensibility | ✅ |

---

## Phase 2 — Macro & Sentiment Integration

**Goal**: Enrich trade debate with macroeconomic context.

- [ ] Implement `MacroDataProtocol`
- [ ] Integrate economic calendar (e.g., Forex Factory, Trading Economics API)
- [ ] CPI, interest rate, NFP event awareness
- [ ] Pre-trade macro risk warnings ("CPI release in 2 hours — consider waiting")
- [ ] Sentiment data integration (COT reports, positioning data)
- [ ] Populate `macro_context` and `sentiment_context` on `MarketContext`
- [ ] Store macro snapshot in `JournalEntry.market_context_at_entry`

---

## Phase 3 — Pattern Recognition & ML Intent

**Goal**: Move beyond rules toward learned pattern detection.

- [ ] Implement `PatternRecognitionProtocol`
- [ ] Chart pattern detection from OHLCV (head & shoulders, double tops, triangles)
- [ ] Support/resistance level detection
- [ ] Replace regex-based `IntentParser` with fine-tuned NLU model
- [ ] Implement `RegimeClassifierProtocol` (trending / ranging / volatile)
- [ ] Populate `regime_label` on `MarketContext`
- [ ] Start tagging `JournalEntry` with `strategy_label` and `tags` for ML training

---

## Phase 4 — Behavioural Safeguards & Autonomy

**Goal**: Protect the user from emotional trading; begin reducing manual control.

- [ ] Implement `BehaviourAnalysisProtocol`
- [ ] Detect overtrading, revenge trading, FOMO patterns
- [ ] Block trades during high emotional risk windows
- [ ] Optional "cooling off" period after a losing trade
- [ ] Populate `user_mood_hint` in `JournalEntry`
- [ ] Add ML-driven objection scoring (not just rule-based)
- [ ] Trade management: AI suggests "reduce position", "move stop to breakeven"
- [ ] Outcome tracking: populate `outcome_pips` and `outcome_pnl` on closed trades

---

## Phase 5 — Full Autonomy (Optional)

**Goal**: Allow the system to operate with minimal user intervention.

- [ ] Configurable autonomy levels (per user, per strategy)
- [ ] Scan-and-propose mode: AI monitors markets and proposes setups
- [ ] Auto-confirm threshold: trades above quality score N execute automatically
- [ ] Multi-broker support via `ExecutorProtocol`
- [ ] Cloud deployment (cloud VM or containerised service)
- [ ] Dashboards: trade performance, journal analytics, regime statistics
- [ ] Notification system for trade events (entry, SL hit, TP hit)

---

## Journal-Driven Learning Loop

The `JournalEntry` schema is designed to support continuous improvement:

```
Phase 1: Record all trade decisions and outcomes
Phase 2: Add macro context at entry
Phase 3: Tag setups, strategies, and regime labels
Phase 4: Add mood/behaviour annotations
Phase 5: Train models on historical journal data to improve all phases
```

Every field in `JournalEntry` that is marked `Optional` and defaults to `None` in Phase 1
is a placeholder for a future phase's data.
