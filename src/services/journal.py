"""Journal service — persist trade records and audit events to JSON files."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import aiofiles

from src.schemas.journal import AuditLogEntry, JournalEntry
from src.schemas.trade import (
    ExecutionResult,
    RawUserThesis,
    TradeDraft,
    TradeDecision,
)

logger = logging.getLogger(__name__)


class JournalService:
    """Persist and retrieve journal entries as JSON files."""

    def __init__(self, journal_dir: str = "data/journal") -> None:
        self._dir = Path(journal_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._audit_file = self._dir / "audit.jsonl"

    # ── Entry management ───────────────────────────────────────────────────────

    def create_entry(self, draft: TradeDraft) -> JournalEntry:
        """Create a JournalEntry from a TradeDraft (before execution)."""
        return JournalEntry(
            trade_id=draft.draft_id,
            user_id=draft.user_id,
            raw_thesis=draft.raw_thesis,
            interpreted_thesis=draft.interpreted_thesis,
            variants_considered=list(draft.variants),
            objections_raised=list(draft.objections),
            final_decision=None,
            execution_result=None,
            market_context_at_entry=draft.market_context,
        )

    async def save_entry(self, entry: JournalEntry) -> Path:
        """Write a JournalEntry to a JSON file. Returns the file path."""
        path = self._dir / f"{entry.entry_id}.json"
        content = entry.model_dump_json(indent=2)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)
        logger.info("Journal entry saved: %s", path)
        return path

    async def log_audit_event(
        self,
        event_type: str,
        actor: str,
        details: dict,
        trade_id: Optional[str] = None,
    ) -> None:
        """Append a single audit log event to the JSONL audit file."""
        entry = AuditLogEntry(
            event_type=event_type,
            actor=actor,
            details=details,
            trade_id=trade_id,
        )
        line = entry.model_dump_json() + "\n"
        async with aiofiles.open(self._audit_file, "a", encoding="utf-8") as f:
            await f.write(line)

    async def get_entry(self, entry_id: str) -> Optional[JournalEntry]:
        """Load a single JournalEntry by ID."""
        path = self._dir / f"{entry_id}.json"
        if not path.exists():
            return None
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
        return JournalEntry.model_validate_json(content)

    async def get_recent_entries(self, limit: int = 10) -> list[JournalEntry]:
        """Return the *limit* most recently modified journal entries."""
        files = sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        entries: list[JournalEntry] = []
        for path in files[:limit]:
            try:
                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                entries.append(JournalEntry.model_validate_json(content))
            except Exception as exc:
                logger.warning("Failed to load journal entry %s: %s", path, exc)
        return entries
