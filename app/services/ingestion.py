"""
Ingestion orchestration for both branches described in the spec:

Branch A ("knowledge"): file upload -> extract -> chunk -> embed -> chunk_id (content hash) -> push
Branch B ("memory"):    JSON turns  -> embed -> memory_id (uuid)        -> push
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from app.clients.nest_client import NestClient
from app.services import parser
from app.services.chunker import chunk_text
from app.services.embeddings import EmbeddingProvider, get_embedding_provider
from schema.request import KnowledgeIngestMetadata, MemoryTurn
from utils import content_hash_chunk_id, new_memory_id


class IngestionService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider | None = None,
        nest_client: NestClient | None = None,
    ) -> None:
        self._chunk_size = int(os.getenv("CHUNK_TOKEN_SIZE", "400"))
        self._chunk_overlap = int(os.getenv("CHUNK_TOKEN_OVERLAP", "50"))
        self._corpus_version_default = os.getenv("CORPUS_VERSION", "v0.1.0")
        self._embeddings = embedding_provider or get_embedding_provider()
        self._nest_client = nest_client or NestClient()

    # ------------------------------------------------------------------
    # Branch A — knowledge documents
    # ------------------------------------------------------------------
    def ingest_knowledge_document(
        self, filename: str, raw_bytes: bytes, metadata: KnowledgeIngestMetadata
    ) -> Dict[str, Any]:
        raw_text = parser.extract_text(filename, raw_bytes)
        cleaned = parser.clean_text(raw_text)

        chunks = chunk_text(
            cleaned,
            chunk_size=self._chunk_size,
            overlap=self._chunk_overlap,
        )
        if not chunks:
            return {
                "docs_processed": 1,
                "chunks_added": 0,
                "chunks_updated": 0,
                "chunks_skipped": 0,
                "dispatched": False,
            }

        corpus_version = metadata.corpus_version or self._corpus_version_default
        contents = [c.content for c in chunks]
        vectors = self._embeddings.embed(contents)

        rows: List[Dict[str, Any]] = []
        seen_ids = set()
        chunks_skipped = 0
        for chunk, vector in zip(chunks, vectors):
            chunk_id = content_hash_chunk_id(chunk.content)
            if chunk_id in seen_ids:
                # Duplicate content within the same document — idempotency
                # means we don't emit the same chunk_id twice in one batch.
                chunks_skipped += 1
                continue
            seen_ids.add(chunk_id)
            rows.append(
                {
                    "chunkId": chunk_id,
                    "source": metadata.source,
                    "domain": metadata.domain_display or metadata.domain.value,
                    "evidenceTier": metadata.evidence_tier_display or metadata.evidence_tier.value,
                    "topicTags": metadata.topic_tags,
                    "content": chunk.content,
                    "embedding": vector,
                    "corpusVersion": corpus_version,
                }
            )

        dispatched = self._nest_client.push_knowledge_chunks(rows)

        return {
            "docs_processed": 1,
            "chunks_added": len(rows),
            "chunks_updated": 0,  # comori-api owns upsert semantics; indexer only proposes rows
            "chunks_skipped": chunks_skipped,
            "dispatched": dispatched,
        }

    def ingest_knowledge_text(
        self, text: str, metadata: KnowledgeIngestMetadata
    ) -> Dict[str, Any]:
        cleaned = parser.clean_text(text)

        chunks = chunk_text(
            cleaned,
            chunk_size=self._chunk_size,
            overlap=self._chunk_overlap,
        )
        if not chunks:
            return {
                "docs_processed": 1,
                "chunks_added": 0,
                "chunks_updated": 0,
                "chunks_skipped": 0,
                "dispatched": False,
            }

        corpus_version = metadata.corpus_version or self._corpus_version_default
        contents = [c.content for c in chunks]
        vectors = self._embeddings.embed(contents)

        rows: List[Dict[str, Any]] = []
        seen_ids = set()
        chunks_skipped = 0
        for chunk, vector in zip(chunks, vectors):
            chunk_id = content_hash_chunk_id(chunk.content)
            if chunk_id in seen_ids:
                chunks_skipped += 1
                continue
            seen_ids.add(chunk_id)
            rows.append(
                {
                    "chunkId": chunk_id,
                    "source": metadata.source,
                    "domain": metadata.domain_display or metadata.domain.value,
                    "evidenceTier": metadata.evidence_tier_display or metadata.evidence_tier.value,
                    "topicTags": metadata.topic_tags,
                    "content": chunk.content,
                    "embedding": vector,
                    "corpusVersion": corpus_version,
                }
            )

        dispatched = self._nest_client.push_knowledge_chunks(rows)

        return {
            "docs_processed": 1,
            "chunks_added": len(rows),
            "chunks_updated": 0,
            "chunks_skipped": chunks_skipped,
            "dispatched": dispatched,
        }

    # ------------------------------------------------------------------
    # Branch B — memory / conversation turns
    # ------------------------------------------------------------------
    def ingest_memory_turns(self, turns: List[MemoryTurn]) -> Dict[str, Any]:
        if not turns:
            return {"memories_added": 0, "dispatched": False}

        snippets = [turn.snippet for turn in turns]
        vectors = self._embeddings.embed(snippets)

        rows: List[Dict[str, Any]] = []
        for turn, vector in zip(turns, vectors):
            rows.append(
                {
                    "memory_id": new_memory_id(),
                    "user_id": turn.user_id,
                    "kind": turn.kind.value,
                    "snippet": turn.snippet,
                    "ref": turn.ref,
                    "embedding": vector,
                    "occurred_at": turn.occurred_at.isoformat() if turn.occurred_at else None,
                }
            )

        dispatched = self._nest_client.push_memory_vectors(rows)

        return {"memories_added": len(rows), "dispatched": dispatched}
