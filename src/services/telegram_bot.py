"""Telegram bot — command and message handlers delegating to ConversationManager."""

from __future__ import annotations

import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.services.conversation import ConversationManager

logger = logging.getLogger(__name__)

# Inline keyboard buttons shown after a trade summary
_CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    [[
        InlineKeyboardButton("✅ Confirm", callback_data="confirm"),
        InlineKeyboardButton("❌ Reject", callback_data="reject"),
        InlineKeyboardButton("🚫 Cancel", callback_data="cancel"),
    ]]
)


class TradingBot:
    """Telegram bot wrapping all trade-lifecycle interactions."""

    def __init__(self, token: str, conversation_manager: ConversationManager) -> None:
        self._token = token
        self._manager = conversation_manager
        self._app = Application.builder().token(token).build()
        self._register_handlers()

    # ── Handler registration ───────────────────────────────────────────────────

    def _register_handlers(self) -> None:
        app = self._app
        # Commands
        for cmd in ("start", "help", "trade", "status", "confirm", "reject", "cancel", "journal"):
            app.add_handler(CommandHandler(cmd, self._command_handler))
        # Free-form text
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._message_handler)
        )
        # Inline keyboard callbacks
        app.add_handler(CallbackQueryHandler(self._callback_handler))
        # Error handler
        app.add_error_handler(self._error_handler)

    # ── Telegram handlers ──────────────────────────────────────────────────────

    async def _command_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.message is None or update.effective_user is None:
            return
        user_id = str(update.effective_user.id)
        command = update.message.text or ""
        reply = await self._manager.handle_command(user_id, command)
        await self._send(update, reply)

    async def _message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if update.message is None or update.effective_user is None:
            return
        user_id = str(update.effective_user.id)
        text = update.message.text or ""
        reply = await self._manager.handle_message(user_id, text)
        await self._send(update, reply)

    async def _callback_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.from_user is None:
            return
        await query.answer()
        user_id = str(query.from_user.id)
        data = query.data or ""
        reply = await self._manager.handle_command(user_id, f"/{data}")
        if query.message:
            await query.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)

    @staticmethod
    async def _error_handler(
        update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.error("Telegram error: %s", context.error, exc_info=context.error)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    async def _send(update: Update, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
        if update.message is None:
            return
        # Split long messages to stay within Telegram's 4096-char limit
        chunks = _split_message(text)
        for i, chunk in enumerate(chunks):
            reply_markup = keyboard if (i == len(chunks) - 1 and keyboard) else None
            try:
                await update.message.reply_text(
                    chunk,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            except Exception as exc:
                logger.warning("Failed to send message with Markdown: %s — retrying plain", exc)
                await update.message.reply_text(chunk, reply_markup=reply_markup)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def run_polling(self) -> None:
        """Start the bot with long-polling (blocking)."""
        logger.info("Starting Telegram bot polling…")
        self._app.run_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        """Gracefully stop the bot."""
        await self._app.stop()
        await self._app.shutdown()


def _split_message(text: str, limit: int = 4000) -> list[str]:
    """Split *text* into chunks of at most *limit* characters."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
