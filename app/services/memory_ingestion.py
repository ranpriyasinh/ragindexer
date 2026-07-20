"""
Memory Ingestion Service (Branch B).

Orchestrates conversation memory turns & user summaries ingestion:
  MemoryTurn list -> PHI validation -> vector embedding -> memory_id (uuid) -> NestClient
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.clients.nest_client import NestClient
from app.config import Settings, get_settings
from app.models.request import MemoryTurn
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from app.services.phi import PHISanitizer, PHISafetyViolationError
from app.utils import new_memory_id

logger = logging.getLogger("comori-rag-indexer.memory_ingestion")


class MemoryIngestionError(ValueError):
    """Raised when memory turn processing encounters unrecoverable errors."""
    pass


class MemoryIngestionService:
    """Dedicated enterprise service for Pipeline 2 (User Memory Ingestion)."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        nest_client: NestClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._embeddings = embedding_provider or get_embedding_provider()
        self._nest_client = nest_client or NestClient(self._settings)

    def ingest_memory_turns(
        self, turns: List[MemoryTurn], auto_sanitize_phi: bool = False
    ) -> Dict[str, Any]:
        """
        Processes a list of PHI-scrubbed conversation turns or user summaries.

        Args:
            turns: List of MemoryTurn objects containing user_id, snippet, kind, etc.
            auto_sanitize_phi: If True, automatically redacts PHI patterns instead of throwing.

        Returns:
            Dict containing operational metrics and dispatch status.
        """
        if not turns:
            logger.info("ingest_memory_turns called with empty turn list.")
            return {
                "memories_added": 0,
                "memories_skipped": 0,
                "dispatched": False,
                "mode": self._settings.COMORI_API_MODE,
            }

        valid_turns: List[MemoryTurn] = []
        processed_snippets: List[str] = []
        memories_skipped = 0

        for idx, turn in enumerate(turns):
            snippet = turn.snippet.strip() if turn.snippet else ""
            if not snippet:
                logger.warning("Turn index %d skipped: empty snippet.", idx)
                memories_skipped += 1
                continue

            if auto_sanitize_phi:
                sanitized, _ = PHISanitizer.sanitize(snippet)
                processed_snippets.append(sanitized)
                valid_turns.append(turn)
            else:
                try:
                    PHISanitizer.assert_phi_free(snippet)
                    processed_snippets.append(snippet)
                    valid_turns.append(turn)
                except PHISafetyViolationError as exc:
                    logger.error("Turn index %d PHI check failed: %s", idx, exc)
                    raise MemoryIngestionError(
                        f"Memory turn at index {idx} failed PHI safety check: {exc}"
                    ) from exc

        if not valid_turns:
            return {
                "memories_added": 0,
                "memories_skipped": memories_skipped,
                "dispatched": False,
                "mode": self._settings.COMORI_API_MODE,
            }

        # Batch vector generation
        vectors = self._embeddings.embed(processed_snippets)

        # Build memory_vectors payload rows
        rows: List[Dict[str, Any]] = []
        for turn, snippet, vector in zip(valid_turns, processed_snippets, vectors):
            rows.append(
                {
                    "memory_id": new_memory_id(),
                    "user_id": turn.user_id,
                    "kind": turn.kind.value if hasattr(turn.kind, "value") else str(turn.kind),
                    "snippet": snippet,
                    "ref": turn.ref,
                    "embedding": vector,
                    "occurred_at": turn.occurred_at.isoformat() if turn.occurred_at else None,
                }
            )

        # Dispatch rows to comori-api (print mode or http mode)
        dispatched = self._nest_client.push_memory_vectors(rows)
        logger.info(
            "Ingested %d memory vectors successfully (skipped %d).",
            len(rows),
            memories_skipped,
        )

        return {
            "memories_added": len(rows),
            "memories_skipped": memories_skipped,
            "dispatched": dispatched,
            "mode": self._settings.COMORI_API_MODE,
        }
