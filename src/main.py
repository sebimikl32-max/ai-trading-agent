"""Application entry-point — wire all services together and start the bot."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from config.settings import get_settings
from src.engines.llm_engine import LLMEngine
from src.services.conversation import ConversationManager
from src.services.debate_engine import DebateEngine
from src.services.intent_parser import IntentParser
from src.services.journal import JournalService
from src.services.market_data import MarketDataService
from src.services.mt5_executor import MT5Executor
from src.services.order_builder import OrderBuilder
from src.services.risk_manager import RiskManager
from src.services.technical_analysis import TechnicalAnalysisService
from src.services.telegram_bot import TradingBot
from src.services.trade_draft import TradeDraftManager
from src.utils.logging import setup_logging

logger = logging.getLogger(__name__)


def build_app() -> TradingBot:
    """Construct and wire all services. Returns a ready-to-run TradingBot."""
    settings = get_settings()
    setup_logging(level=settings.log_level)

    logger.info("Initialising AI Trading Agent — Phase 1")

    # ── Core services ──────────────────────────────────────────────────────────
    llm_engine = LLMEngine()
    intent_parser = IntentParser(llm_engine=llm_engine)
    draft_manager = TradeDraftManager()
    risk_manager = RiskManager(
        max_risk_pct=settings.max_risk_pct,
        max_positions=settings.max_positions,
    )
    debate_engine = DebateEngine(risk_manager=risk_manager, llm_engine=llm_engine)
    market_data = MarketDataService()
    ta_service = TechnicalAnalysisService()
    order_builder = OrderBuilder(
        magic_number=settings.magic_number,
        deviation=20,
    )
    mt5_executor = MT5Executor(
        path=settings.mt5_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )
    journal_service = JournalService(journal_dir=settings.journal_dir)

    # ── Conversation manager ───────────────────────────────────────────────────
    manager = ConversationManager(
        intent_parser=intent_parser,
        draft_manager=draft_manager,
        debate_engine=debate_engine,
        risk_manager=risk_manager,
        market_data=market_data,
        ta_service=ta_service,
        order_builder=order_builder,
        mt5_executor=mt5_executor,
        journal_service=journal_service,
        llm_engine=llm_engine,
        default_risk_pct=settings.default_risk_pct,
        allowed_user_ids=settings.allowed_user_id_set,
    )

    bot = TradingBot(token=settings.telegram_bot_token, conversation_manager=manager)
    return bot


def main() -> None:
    """Entry-point: initialise MT5 (optional), then start Telegram polling."""
    settings = get_settings()
    setup_logging(level=settings.log_level)

    bot = build_app()

    # Attempt MT5 initialisation — non-fatal if unavailable
    executor = MT5Executor(
        path=settings.mt5_path,
        login=settings.mt5_login,
        password=settings.mt5_password,
        server=settings.mt5_server,
    )

    async def _init_mt5() -> None:
        connected = await executor.initialize()
        if connected:
            logger.info("MT5 connected successfully")
        else:
            logger.warning(
                "MT5 not connected — market data and order execution will be unavailable"
            )

    asyncio.run(_init_mt5())

    logger.info("Starting Telegram polling…")
    try:
        bot.run_polling()
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        asyncio.run(executor.shutdown())
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
