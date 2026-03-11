"""Telegram message formatting helpers."""

from __future__ import annotations

from typing import Optional

from src.schemas.journal import JournalEntry
from src.schemas.market import MarketContext
from src.schemas.trade import (
    ExecutionResult,
    TradeDraft,
    TradeDecision,
    TradeObjection,
    TradeVariant,
)


def format_trade_draft(draft: TradeDraft) -> str:
    """Return a human-readable summary of a TradeDraft."""
    lines = [f"📋 *Trade Draft* `{draft.draft_id[:8]}`"]
    lines.append(f"Status: *{draft.status.value}*")

    if draft.interpreted_thesis:
        t = draft.interpreted_thesis
        lines.append("")
        lines.append("*Interpreted Thesis*")
        if t.symbol:
            lines.append(f"  Symbol: `{t.symbol}`")
        if t.direction:
            lines.append(f"  Direction: *{t.direction.value}*")
        if t.rationale:
            lines.append(f"  Rationale: _{t.rationale}_")
        if t.timeframe_hint:
            lines.append(f"  Timeframe: {t.timeframe_hint}")
        if t.entry_price_hint:
            lines.append(f"  Entry hint: `{t.entry_price_hint}`")
        if t.stop_loss_hint:
            lines.append(f"  SL hint: `{t.stop_loss_hint}`")
        if t.take_profit_hint:
            lines.append(f"  TP hint: `{t.take_profit_hint}`")
        if t.risk_pct_hint:
            lines.append(f"  Risk: `{t.risk_pct_hint}%`")

    if draft.current_best_variant:
        lines.append("")
        lines.append(format_variants([draft.current_best_variant], title="*Best Variant*"))

    if draft.objections:
        lines.append("")
        lines.append(format_objections(draft.objections))

    return "\n".join(lines)


def format_trade_decision(decision: TradeDecision) -> str:
    """Return a structured order confirmation message."""
    direction_emoji = "🟢" if decision.direction.value == "LONG" else "🔴"
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  {direction_emoji} *ORDER SUMMARY* — Awaiting Confirmation",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Symbol:    `{decision.symbol}`",
        f"  Direction: *{decision.direction.value}*",
        f"  Entry:     `{decision.entry_price}`",
        f"  Stop Loss: `{decision.stop_loss}`",
        f"  Take Profit: `{decision.take_profit}`",
        f"  Lot Size:  `{decision.lot_size}`",
        f"  Risk:      `{decision.risk_pct:.2f}%`",
        f"  R:R Ratio: `{decision.risk_reward_ratio:.2f}:1`",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "_Rationale:_ " + decision.rationale,
        "",
        "👆 Reply /confirm to execute or /reject to cancel.",
    ]
    return "\n".join(lines)


def format_execution_result(result: ExecutionResult) -> str:
    """Return an execution summary message."""
    if result.success:
        lines = [
            "✅ *Order Executed Successfully*",
            f"  Ticket:     `{result.order_ticket}`",
            f"  Deal:       `{result.deal_id}`",
            f"  Symbol:     `{result.symbol}`",
            f"  Direction:  *{result.direction.value}*",
            f"  Fill Price: `{result.fill_price}`",
        ]
        if result.slippage is not None:
            lines.append(f"  Slippage:   `{result.slippage:.5f}`")
        lines.append(f"  Volume:     `{result.volume}`")
    else:
        lines = [
            "❌ *Order Execution Failed*",
            f"  Symbol:    `{result.symbol}`",
            f"  Direction: *{result.direction.value}*",
            f"  RetCode:   `{result.retcode}`",
            f"  Reason:    _{result.retcode_description}_",
        ]
    return "\n".join(lines)


def format_market_summary(ctx: Optional[MarketContext]) -> str:
    """Return a short market context summary."""
    if ctx is None:
        return "No market data available."
    t = ctx.technical
    lines = [f"📊 *Market Context — {ctx.symbol}*"]
    tick = ctx.snapshot.tick
    lines.append(f"  Bid/Ask: `{tick.bid}` / `{tick.ask}` (spread: `{tick.spread:.5f}`)")
    if t.atr_14 is not None:
        lines.append(f"  ATR(14): `{t.atr_14:.5f}`")
    if t.rsi_14 is not None:
        lines.append(f"  RSI(14): `{t.rsi_14:.1f}`")
    if t.sma_20 is not None:
        lines.append(f"  SMA20:   `{t.sma_20:.5f}`")
    if t.sma_50 is not None:
        lines.append(f"  SMA50:   `{t.sma_50:.5f}`")
    if t.recent_swing_high is not None:
        lines.append(f"  Swing H: `{t.recent_swing_high:.5f}`")
    if t.recent_swing_low is not None:
        lines.append(f"  Swing L: `{t.recent_swing_low:.5f}`")
    if t.volatility_percentile is not None:
        lines.append(f"  Vol%ile: `{t.volatility_percentile:.0f}th`")
    if ctx.regime_label:
        lines.append(f"  Regime:  _{ctx.regime_label}_")
    return "\n".join(lines)


def format_objections(objections: list[TradeObjection]) -> str:
    if not objections:
        return "✅ No objections raised."
    lines = ["⚠️ *Objections*"]
    for o in objections:
        emoji = {"LOW": "🔵", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(
            o.severity.value, "⚪"
        )
        lines.append(f"{emoji} [{o.severity.value}] {o.description}")
        if o.suggestion:
            lines.append(f"   → _{o.suggestion}_")
    return "\n".join(lines)


def format_variants(variants: list[TradeVariant], title: str = "*Variants*") -> str:
    if not variants:
        return "No variants available."
    lines = [title]
    for i, v in enumerate(variants, 1):
        lines.append(
            f"  {i}. Entry `{v.entry_price}` | SL `{v.stop_loss}` | TP `{v.take_profit}` "
            f"| Lots `{v.lot_size}` | R:R `{v.risk_reward_ratio:.2f}:1`"
        )
        lines.append(f"     _{v.rationale}_")
    return "\n".join(lines)


def format_risk_calculation(
    balance: float,
    risk_pct: float,
    lot_size: float,
    entry: float,
    stop_loss: float,
    risk_reward: float,
) -> str:
    risk_amount = balance * risk_pct / 100
    return "\n".join([
        "📐 *Risk Calculation*",
        f"  Balance:    `${balance:,.2f}`",
        f"  Risk %:     `{risk_pct:.2f}%`",
        f"  Risk $:     `${risk_amount:,.2f}`",
        f"  Lot Size:   `{lot_size}`",
        f"  Entry:      `{entry}`",
        f"  Stop Loss:  `{stop_loss}`",
        f"  Stop Dist:  `{abs(entry - stop_loss):.5f}`",
        f"  R:R Ratio:  `{risk_reward:.2f}:1`",
    ])


def format_journal_entry(entry: JournalEntry) -> str:
    lines = [f"📓 *Journal Entry* `{entry.entry_id[:8]}`"]
    lines.append(f"  Time: `{entry.timestamp.strftime('%Y-%m-%d %H:%M UTC')}`")
    if entry.interpreted_thesis:
        t = entry.interpreted_thesis
        lines.append(f"  Symbol: `{t.symbol}` | Dir: *{t.direction.value if t.direction else 'N/A'}*")
    if entry.final_decision:
        d = entry.final_decision
        lines.append(
            f"  Entry `{d.entry_price}` SL `{d.stop_loss}` TP `{d.take_profit}` "
            f"Lots `{d.lot_size}` R:R `{d.risk_reward_ratio:.2f}`"
        )
    if entry.outcome_pips is not None:
        lines.append(f"  Outcome: `{entry.outcome_pips:+.1f} pips`")
    if entry.outcome_pnl is not None:
        lines.append(f"  P&L: `${entry.outcome_pnl:+,.2f}`")
    if entry.tags:
        lines.append(f"  Tags: {' '.join(f'#{t}' for t in entry.tags)}")
    return "\n".join(lines)
