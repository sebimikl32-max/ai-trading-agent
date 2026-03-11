"""Conversation manager — per-user state machine orchestrating the trade workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.engines.llm_engine import LLMEngine
from src.schemas.market import MarketContext
from src.schemas.message import ConversationContext, ConversationState, ParsedMessage, UserIntent
from src.schemas.trade import (
    InterpretedTradeThesis,
    TradeDraft,
    TradeDirection,
    TradeStatus,
    TradeVariant,
)
from src.services.debate_engine import DebateEngine
from src.services.intent_parser import IntentParser
from src.services.journal import JournalService
from src.services.market_data import MarketDataService
from src.services.order_builder import OrderBuilder
from src.services.mt5_executor import MT5Executor
from src.services.risk_manager import RiskManager
from src.services.technical_analysis import TechnicalAnalysisService
from src.services.trade_draft import TradeDraftManager
from src.utils.formatting import (
    format_execution_result,
    format_market_summary,
    format_trade_decision,
    format_trade_draft,
)

logger = logging.getLogger(__name__)


class ConversationManager:
    """Orchestrates the full trade lifecycle for each user session."""

    def __init__(
        self,
        intent_parser: IntentParser,
        draft_manager: TradeDraftManager,
        debate_engine: DebateEngine,
        risk_manager: RiskManager,
        market_data: MarketDataService,
        ta_service: TechnicalAnalysisService,
        order_builder: OrderBuilder,
        mt5_executor: MT5Executor,
        journal_service: JournalService,
        llm_engine: Optional[LLMEngine] = None,
        default_risk_pct: float = 1.0,
        allowed_user_ids: Optional[set[int]] = None,
    ) -> None:
        self._parser = intent_parser
        self._drafts = draft_manager
        self._debate = debate_engine
        self._risk = risk_manager
        self._market = market_data
        self._ta = ta_service
        self._builder = order_builder
        self._executor = mt5_executor
        self._journal = journal_service
        self._llm = llm_engine
        self._default_risk_pct = default_risk_pct
        self._allowed_ids = allowed_user_ids or set()

        # Per-user conversation contexts
        self._contexts: dict[str, ConversationContext] = {}

    # ── Public entry-point ─────────────────────────────────────────────────────

    async def handle_message(self, user_id: str, text: str) -> str:
        """Route an incoming user message and return a reply string."""
        if not self._is_allowed(user_id):
            return "⛔ You are not authorised to use this bot."

        ctx = self._get_or_create_context(user_id)
        ctx.last_activity = datetime.now(timezone.utc)
        ctx.message_history.append({"role": "user", "content": text})

        parsed = await self._parser.parse(text, user_id)
        logger.info(
            "User %s | state=%s | intent=%s | symbol=%s",
            user_id,
            ctx.state.value,
            parsed.intent.value,
            parsed.extracted_symbol,
        )

        # Global overrides regardless of state
        if parsed.intent == UserIntent.CANCEL:
            return self._handle_cancel(ctx)
        if parsed.intent == UserIntent.CONFIRM_TRADE:
            return await self._handle_confirm(ctx)
        if parsed.intent == UserIntent.REJECT_TRADE:
            return self._handle_reject(ctx)

        # Route by conversation state
        if ctx.state == ConversationState.IDLE:
            return await self._handle_idle(ctx, parsed, text)
        elif ctx.state == ConversationState.INTAKE:
            return await self._handle_intake(ctx, parsed, text)
        elif ctx.state == ConversationState.DEBATING:
            return await self._handle_debating(ctx, parsed, text)
        elif ctx.state == ConversationState.AWAITING_CONFIRMATION:
            return await self._handle_awaiting(ctx, parsed, text)
        elif ctx.state == ConversationState.EXECUTED:
            return self._handle_post_execution(ctx, parsed, text)
        return "I'm not sure how to respond to that. Try /help."

    async def handle_command(self, user_id: str, command: str) -> str:
        """Handle slash commands."""
        if not self._is_allowed(user_id):
            return "⛔ You are not authorised to use this bot."

        cmd = command.lower().strip("/").split()[0]
        if cmd == "start":
            return self._cmd_start()
        if cmd == "help":
            return self._cmd_help()
        if cmd == "status":
            return self._cmd_status(user_id)
        if cmd == "confirm":
            ctx = self._get_or_create_context(user_id)
            return await self._handle_confirm(ctx)
        if cmd == "reject":
            ctx = self._get_or_create_context(user_id)
            return self._handle_reject(ctx)
        if cmd == "cancel":
            ctx = self._get_or_create_context(user_id)
            return self._handle_cancel(ctx)
        if cmd == "journal":
            return await self._cmd_journal(user_id)
        if cmd == "trade":
            return "Tell me about the trade you're considering and I'll help you structure it."
        return f"Unknown command: /{cmd}. Use /help for a list of commands."

    # ── State handlers ─────────────────────────────────────────────────────────

    async def _handle_idle(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        if parsed.intent in (UserIntent.NEW_TRADE, UserIntent.REQUEST_ANALYSIS):
            return await self._start_intake(ctx, parsed, text)
        if parsed.intent == UserIntent.ASK_QUESTION:
            return await self._answer_question(text, ctx)
        return (
            "👋 Hello! Tell me about a trade you're considering, or use /trade to get started."
        )

    async def _handle_intake(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        if parsed.intent == UserIntent.NEW_TRADE:
            return await self._start_intake(ctx, parsed, text)
        if parsed.intent in (UserIntent.REFINE_TRADE, UserIntent.ASK_QUESTION):
            return await self._enrich_draft(ctx, parsed, text)
        return await self._enrich_draft(ctx, parsed, text)

    async def _handle_debating(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        if parsed.intent == UserIntent.REFINE_TRADE:
            return await self._refine_draft(ctx, parsed, text)
        if parsed.intent == UserIntent.ASK_QUESTION:
            return await self._answer_question(text, ctx)
        if parsed.intent == UserIntent.NEW_TRADE:
            # User wants a fresh trade
            return await self._start_intake(ctx, parsed, text)
        return await self._refine_draft(ctx, parsed, text)

    async def _handle_awaiting(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        if parsed.intent == UserIntent.ASK_QUESTION:
            return await self._answer_question(text, ctx)
        # Re-present the confirmation summary
        if ctx.active_draft and ctx.active_draft.current_best_variant:
            try:
                decision = self._drafts.to_decision(ctx.active_draft)
                return (
                    "⏳ Still waiting for your confirmation.\n\n"
                    + format_trade_decision(decision)
                )
            except Exception:
                pass
        return "Use /confirm to execute or /reject to cancel."

    def _handle_post_execution(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        if parsed.intent == UserIntent.NEW_TRADE:
            # Reset state for a new trade
            ctx.state = ConversationState.IDLE
            ctx.active_draft = None
            return "Starting fresh. Tell me about your next trade idea."
        return "The last trade has been executed. Start a new trade idea or use /journal to review."

    # ── Core workflow methods ──────────────────────────────────────────────────

    async def _start_intake(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        draft = self._drafts.create_draft(ctx.user_id, text)
        ctx.active_draft = draft
        ctx.state = ConversationState.INTAKE
        draft.conversation_history.append(f"User: {text}")

        # Build interpreted thesis from parsed message
        thesis = InterpretedTradeThesis(
            symbol=parsed.extracted_symbol,
            direction=parsed.extracted_direction,
            entry_price_hint=parsed.extracted_price_levels.get("entry_price"),
            stop_loss_hint=parsed.extracted_price_levels.get("stop_loss"),
            take_profit_hint=parsed.extracted_price_levels.get("take_profit"),
            risk_pct_hint=parsed.extracted_risk_pct,
        )
        self._drafts.update_draft(draft, thesis)

        # Fetch market context if symbol is known
        market_ctx = None
        if thesis.symbol:
            market_ctx = await self._get_market_context(thesis.symbol)
            draft.market_context = market_ctx

        # Build a first variant if we have enough data
        reply_lines = [f"📥 I've noted your trade idea for *{thesis.symbol or 'unknown symbol'}*."]
        missing_msg = self._list_missing(thesis, draft)
        if missing_msg:
            reply_lines.append(missing_msg)
        else:
            await self._run_debate(ctx, draft, market_ctx)
            return "\n".join(reply_lines)

        if market_ctx:
            reply_lines.append("\n" + format_market_summary(market_ctx))

        ctx.state = ConversationState.INTAKE
        return "\n".join(reply_lines)

    async def _enrich_draft(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        draft = ctx.active_draft
        if draft is None:
            return await self._start_intake(ctx, parsed, text)

        thesis = draft.interpreted_thesis or InterpretedTradeThesis()
        draft.conversation_history.append(f"User: {text}")

        # Merge new information
        if parsed.extracted_symbol and not thesis.symbol:
            thesis.symbol = parsed.extracted_symbol
        if parsed.extracted_direction and thesis.direction is None:
            thesis.direction = parsed.extracted_direction
        for key, value in parsed.extracted_price_levels.items():
            if key == "entry_price" and not thesis.entry_price_hint:
                thesis.entry_price_hint = value
            elif key == "stop_loss" and not thesis.stop_loss_hint:
                thesis.stop_loss_hint = value
            elif key == "take_profit" and not thesis.take_profit_hint:
                thesis.take_profit_hint = value
        if parsed.extracted_risk_pct and not thesis.risk_pct_hint:
            thesis.risk_pct_hint = parsed.extracted_risk_pct

        self._drafts.update_draft(draft, thesis)

        # Refresh market context if symbol is now known
        market_ctx = draft.market_context
        if thesis.symbol and market_ctx is None:
            market_ctx = await self._get_market_context(thesis.symbol)
            draft.market_context = market_ctx

        missing_msg = self._list_missing(thesis, draft)
        if missing_msg:
            return f"Thanks! {missing_msg}"

        return await self._run_debate(ctx, draft, market_ctx)

    async def _refine_draft(
        self, ctx: ConversationContext, parsed: ParsedMessage, text: str
    ) -> str:
        return await self._enrich_draft(ctx, parsed, text)

    async def _run_debate(
        self,
        ctx: ConversationContext,
        draft: TradeDraft,
        market_ctx: Optional[MarketContext],
    ) -> str:
        thesis = draft.interpreted_thesis
        if thesis is None:
            return "I need more information about the trade before we can debate it."

        ctx.state = ConversationState.DEBATING
        self._drafts.transition_status(draft, TradeStatus.DEBATING)

        # Build initial variant from thesis hints + risk sizing
        entry = thesis.entry_price_hint or 0.0
        sl = thesis.stop_loss_hint or 0.0
        tp = thesis.take_profit_hint or 0.0
        risk_pct = thesis.risk_pct_hint or self._default_risk_pct

        if entry and sl and tp:
            rr = self._risk.calculate_risk_reward(entry, sl, tp)
            # Use a sensible lot size — 0.01 as fallback when no account data
            lot_size = 0.01
            try:
                account = await self._market.get_account_info()
                sym_info = await self._market.get_symbol_info(thesis.symbol or "")
                if account and sym_info:
                    lot_size = self._risk.calculate_lot_size(
                        account.balance, risk_pct, entry, sl, sym_info
                    )
            except Exception as exc:
                logger.warning("Lot size calculation failed: %s", exc)

            variant = TradeVariant(
                entry_price=entry,
                stop_loss=sl,
                take_profit=tp,
                lot_size=lot_size,
                risk_pct=risk_pct,
                risk_reward_ratio=rr,
                rationale=thesis.rationale or "User-supplied levels",
                source="user",
            )
            self._drafts.add_variant(draft, variant)
            self._drafts.set_best_variant(draft, variant)

        objections, alternatives, narrative = await self._debate.evaluate_trade(draft, market_ctx)

        for obj in objections:
            self._drafts.add_objection(draft, obj)
        for alt in alternatives:
            self._drafts.add_variant(draft, alt)

        draft.conversation_history.append(f"System: {narrative}")

        # If no blocking objections, move to AWAITING_CONFIRMATION
        critical = [o for o in objections if o.severity.value in ("HIGH", "CRITICAL")]
        if not critical and draft.current_best_variant:
            self._drafts.transition_status(draft, TradeStatus.READY)
            ctx.state = ConversationState.AWAITING_CONFIRMATION
            try:
                decision = self._drafts.to_decision(draft)
                # Log audit event
                await self._journal.log_audit_event(
                    "trade_ready",
                    "system",
                    {"draft_id": draft.draft_id, "symbol": decision.symbol},
                    trade_id=draft.draft_id,
                )
                return narrative + "\n\n" + format_trade_decision(decision)
            except Exception as exc:
                logger.error("Could not build decision: %s", exc)

        return narrative

    # ── Confirmation / rejection ───────────────────────────────────────────────

    async def _handle_confirm(self, ctx: ConversationContext) -> str:
        if ctx.state != ConversationState.AWAITING_CONFIRMATION:
            if ctx.active_draft is None:
                return "No active trade to confirm. Start a new trade idea first."
            if ctx.state == ConversationState.DEBATING:
                return "The trade is still being debated. Resolve any concerns first."
            return "Nothing to confirm right now."

        draft = ctx.active_draft
        if draft is None or draft.current_best_variant is None:
            return "No confirmed trade setup available."

        try:
            decision = self._drafts.to_decision(draft)
        except ValueError as exc:
            return f"❌ Cannot confirm — {exc}"

        # ── CONFIRMATION GATE ────────────────────────────────────────────────
        # Show structured order summary (already shown, but log confirmation)
        self._drafts.transition_status(draft, TradeStatus.CONFIRMED)
        await self._journal.log_audit_event(
            "trade_confirmed",
            "user",
            {
                "draft_id": draft.draft_id,
                "symbol": decision.symbol,
                "direction": decision.direction.value,
                "entry": decision.entry_price,
                "sl": decision.stop_loss,
                "tp": decision.take_profit,
                "lots": decision.lot_size,
            },
            trade_id=draft.draft_id,
        )

        # Build and validate the MT5 request
        order_request = self._builder.build_market_order(decision)
        is_valid, errors = self._builder.validate_order(order_request)
        if not is_valid:
            return "❌ Order validation failed:\n" + "\n".join(f"• {e}" for e in errors)

        # Execute
        try:
            response = await self._executor.execute_order(order_request)
            result = MT5Executor.build_execution_result(decision, response)
        except RuntimeError as exc:
            # MT5 not connected — note the failure but do not lose the decision
            result_text = (
                "⚠️ MT5 executor is not connected. Order was NOT sent to the market.\n"
                f"Details: {exc}\n\n"
                "Please connect MT5 and retry or place the order manually using these levels:\n"
                + format_trade_decision(decision)
            )
            self._drafts.transition_status(draft, TradeStatus.REJECTED)
            ctx.state = ConversationState.IDLE
            return result_text

        # Journal the outcome
        journal_entry = self._journal.create_entry(draft)
        journal_entry.final_decision = decision
        journal_entry.execution_result = result
        await self._journal.save_entry(journal_entry)
        await self._journal.log_audit_event(
            "trade_executed" if result.success else "trade_execution_failed",
            "system",
            {"retcode": result.retcode, "description": result.retcode_description},
            trade_id=draft.draft_id,
        )

        if result.success:
            self._drafts.transition_status(draft, TradeStatus.EXECUTED)
            ctx.state = ConversationState.EXECUTED
        else:
            self._drafts.transition_status(draft, TradeStatus.REJECTED)
            ctx.state = ConversationState.IDLE

        return format_execution_result(result)

    def _handle_reject(self, ctx: ConversationContext) -> str:
        if ctx.active_draft:
            self._drafts.transition_status(ctx.active_draft, TradeStatus.REJECTED)
            ctx.active_draft = None
        ctx.state = ConversationState.IDLE
        return "❌ Trade rejected. The draft has been discarded. Start a new idea when ready."

    def _handle_cancel(self, ctx: ConversationContext) -> str:
        if ctx.active_draft:
            self._drafts.transition_status(ctx.active_draft, TradeStatus.CANCELLED)
            ctx.active_draft = None
        ctx.state = ConversationState.IDLE
        return "🚫 Trade cancelled. All state cleared. Tell me a new trade idea to start fresh."

    # ── Question answering ─────────────────────────────────────────────────────

    async def _answer_question(self, question: str, ctx: ConversationContext) -> str:
        if self._llm is None:
            return "LLM is not configured. I can only help with structured trade analysis."
        context_text = ""
        if ctx.active_draft:
            context_text = format_trade_draft(ctx.active_draft)
        return await self._llm.answer_question(question, context_text)

    # ── Commands ───────────────────────────────────────────────────────────────

    @staticmethod
    def _cmd_start() -> str:
        return (
            "👋 *Welcome to the AI Trading Agent*\n\n"
            "I'm your debate-first trade assistant. Tell me about a trade idea and I'll help you "
            "structure, analyse, and debate it before you commit.\n\n"
            "I will *never* place a trade without your explicit /confirm.\n\n"
            "Just describe your trade idea in plain English to get started, or use /help."
        )

    @staticmethod
    def _cmd_help() -> str:
        return (
            "📖 *Commands*\n\n"
            "/start — Welcome message\n"
            "/trade — Start a new trade discussion\n"
            "/status — Show current trade draft status\n"
            "/confirm — Confirm and execute the current trade\n"
            "/reject — Reject the current trade\n"
            "/cancel — Cancel and reset all state\n"
            "/journal — Show recent journal entries\n\n"
            "*Trade discussion:*\n"
            "Just type your idea — e.g. 'Thinking of longing gold here at 2320, "
            "stop below 2305, target 2360, 1% risk'"
        )

    def _cmd_status(self, user_id: str) -> str:
        ctx = self._contexts.get(user_id)
        if ctx is None or ctx.active_draft is None:
            return "No active trade. Tell me a trade idea to get started."
        return format_trade_draft(ctx.active_draft)

    async def _cmd_journal(self, user_id: str) -> str:
        from src.utils.formatting import format_journal_entry

        entries = await self._journal.get_recent_entries(limit=5)
        if not entries:
            return "📓 No journal entries yet."
        lines = ["📓 *Recent Journal Entries*\n"]
        for e in entries:
            lines.append(format_journal_entry(e))
            lines.append("─" * 30)
        return "\n".join(lines)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_or_create_context(self, user_id: str) -> ConversationContext:
        if user_id not in self._contexts:
            self._contexts[user_id] = ConversationContext(user_id=user_id)
        return self._contexts[user_id]

    def _is_allowed(self, user_id: str) -> bool:
        if not self._allowed_ids:
            return True  # Open access when no allow-list configured
        try:
            return int(user_id) in self._allowed_ids
        except (ValueError, TypeError):
            return False

    async def _get_market_context(self, symbol: str) -> Optional[MarketContext]:
        try:
            snapshot = await self._market.get_snapshot(symbol)
            if snapshot is None:
                return None
            features = self._ta.compute_features(snapshot)
            from src.schemas.market import MarketContext

            return MarketContext(symbol=symbol, snapshot=snapshot, technical=features)
        except Exception as exc:
            logger.warning("Could not fetch market context for %s: %s", symbol, exc)
            return None

    @staticmethod
    def _list_missing(thesis: InterpretedTradeThesis, draft: TradeDraft) -> str:
        gaps: list[str] = []
        if not thesis.symbol:
            gaps.append("Which *symbol* are you trading?")
        if thesis.direction is None:
            gaps.append("Are you going *long* or *short*?")
        if not thesis.entry_price_hint:
            gaps.append("What is your *entry price* (or should I use the current market price)?")
        if not thesis.stop_loss_hint:
            gaps.append("Where is your *stop loss*?")
        if not thesis.take_profit_hint:
            gaps.append("What is your *take profit* target?")
        if gaps:
            return "I need a few more details:\n" + "\n".join(f"• {g}" for g in gaps)
        return ""
