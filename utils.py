"""Shared helpers: idempotency hashing, id generation."""
from __future__ import annotations

import hashlib
import uuid


def content_hash_chunk_id(content: str) -> str:
    """Deterministic chunk_id derived from raw chunk content.

    Re-ingesting identical content always yields the same chunk_id, which is
    what makes ingestion idempotent (upsert-on-conflict at the comori-api layer).
    """
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def new_memory_id() -> str:
    """UUID-based id for memory_vectors rows (spec section 2, Branch B)."""
    return f"mem_{uuid.uuid4().hex}"
