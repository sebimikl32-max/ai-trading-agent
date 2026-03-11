# AI Trading Agent — Phase 1

> **Debate-first, human-confirmed** Telegram-to-MetaTrader 5 AI trading agent.

The system acts as a structured safeguard between you and your trading account. You discuss trade
ideas with an AI through Telegram; it debates, refines, and prepares the trade — but **never
executes without your explicit confirmation**.

---

## Vision

This is not a signal copier. Every trade is a managed case:

1. You share a trade idea in plain English
2. The bot extracts structure (symbol, direction, levels, risk)
3. Market data and technical analysis are retrieved from MT5
4. The debate engine raises objections, suggests alternatives, explains trade-offs
5. You refine and discuss until satisfied
6. The bot presents the final structured order for your review
7. Only after `/confirm` is the order sent to MT5

---

## Quick Start

### Prerequisites

- Python 3.11+
- MetaTrader 5 terminal (Windows) — optional in Phase 1, required for live execution
- Telegram bot token (from [@BotFather](https://t.me/BotFather))
- OpenAI API key

### Setup

```bash
git clone https://github.com/sebimikl32-max/ai-trading-agent.git
cd ai-trading-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python -m src.main
```

### Run Tests

```bash
pytest
```

---

## Example Interaction

```
You:  Thinking of longing gold here at 2320, stop 2305, target 2360, 1% risk

Bot:  📥 I've noted your trade idea for XAUUSD.

      📊 Market Context — XAUUSD
        Bid/Ask: 2319.50 / 2320.00 (spread: 0.50)
        ATR(14): 15.32
        RSI(14): 58.4
        Swing H: 2341.00
        Swing L: 2301.00

      **Trade Debate Summary**
      ✅ R:R of 2.67:1 is healthy.
      ⚠️ [MEDIUM] Stop distance (15.00) is close to 1× ATR (15.32). Normal volatility
         may trigger your stop.
         → Consider SL at 2303 (1× ATR below entry).

      📐 Alternative setups:
        1. Entry 2320 | SL 2304.68 | TP 2350.64 | R:R 2.00 — ATR-based: SL = 1× ATR
        2. Entry 2320 | SL 2301.00 | TP 2348.50 | R:R 1.50 — Swing-based: SL below swing low

      Review and reply to refine, or /confirm to proceed.

      ━━━━━━━━━━━━━━━━━━━━━━━━━
        🟢 ORDER SUMMARY — Awaiting Confirmation
      ━━━━━━━━━━━━━━━━━━━━━━━━━
        Symbol:    XAUUSD
        Direction: LONG
        Entry:     2320.0
        Stop Loss: 2305.0
        Take Profit: 2360.0
        Lot Size:  0.05
        Risk:      1.00%
        R:R Ratio: 2.67:1
      ━━━━━━━━━━━━━━━━━━━━━━━━━

      👆 Reply /confirm to execute or /reject to cancel.

You:  /confirm

Bot:  ✅ Order Executed Successfully
        Ticket:     12345678
        Fill Price: 2320.10
        Volume:     0.05
```

---

## Project Structure

```
ai-trading-agent/
├── config/settings.py          ← env-based configuration
├── src/
│   ├── main.py                 ← entry-point
│   ├── schemas/                ← Pydantic v2 models
│   │   ├── trade.py            ← TradeDraft, TradeVariant, TradeDecision…
│   │   ├── market.py           ← MarketContext, TechnicalFeatures…
│   │   ├── message.py          ← ParsedMessage, ConversationContext…
│   │   ├── journal.py          ← JournalEntry, AuditLogEntry
│   │   └── mt5.py              ← MT5OrderRequest, MT5AccountInfo…
│   ├── engines/
│   │   ├── base.py             ← Protocol interfaces for all services
│   │   └── llm_engine.py       ← OpenAI async client
│   ├── services/
│   │   ├── telegram_bot.py     ← Telegram handler + inline keyboards
│   │   ├── conversation.py     ← Per-user state machine
│   │   ├── intent_parser.py    ← Regex + LLM intent extraction
│   │   ├── trade_draft.py      ← Draft lifecycle management
│   │   ├── debate_engine.py    ← Rule-based objections + LLM narrative
│   │   ├── market_data.py      ← MT5 market data wrapper
│   │   ├── technical_analysis.py ← ATR, RSI, SMA, swing levels
│   │   ├── risk_manager.py     ← Lot sizing, risk validation
│   │   ├── order_builder.py    ← MT5OrderRequest construction
│   │   ├── mt5_executor.py     ← Async MT5 order submission
│   │   └── journal.py          ← JSON trade journal
│   └── utils/
│       ├── formatting.py       ← Telegram message formatters
│       └── logging.py          ← Structured JSON logging
├── tests/                      ← pytest test suite
├── docs/
│   ├── architecture.md         ← Detailed architecture + data flow
│   └── phases.md               ← Phase 1–5 roadmap
└── data/journal/               ← Trade journal files (JSON)
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for a full description of the data flow,
extension points, and schema design.

## Roadmap

See [docs/phases.md](docs/phases.md) for the Phase 1–5 feature roadmap.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | required | Telegram bot token |
| `OPENAI_API_KEY` | required | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `MT5_LOGIN` | optional | MT5 account number |
| `MT5_PASSWORD` | optional | MT5 password |
| `MT5_SERVER` | optional | MT5 broker server |
| `DEFAULT_RISK_PCT` | `1.0` | Default risk per trade (%) |
| `MAX_RISK_PCT` | `3.0` | Maximum allowed risk (%) |
| `MAX_POSITIONS` | `5` | Maximum open positions |
| `ALLOWED_USER_IDS` | blank (all) | Comma-separated Telegram user IDs |

---

## Critical Design Decisions

1. **Confirmation gate** — `/confirm` is the only path to MT5 execution. No auto-execute.
2. **Debate-first** — every trade goes through `INTAKE → DEBATING → READY → CONFIRMED → EXECUTED`.
3. **Protocol interfaces** — all major services implement a `Protocol` so future ML models,
   macro data sources, and behavioural engines can be swapped in without rewrites.
4. **Rich journal** — every `JournalEntry` captures the full debate context for future pattern analysis.
5. **Symbol slang** — `gold → XAUUSD`, `cable → GBPUSD`, `nas → NAS100`, and many more.

---

## License

MIT