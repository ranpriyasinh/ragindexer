"""
Token-based chunking with overlap.

Default: ~400 tokens per chunk, 50-token overlap (configurable via
CHUNK_TOKEN_SIZE / CHUNK_TOKEN_OVERLAP), per spec section 2 (Ingestion Flow).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import tiktoken

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    index: int
    content: str
    token_count: int


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[Chunk]:
    """Split `text` into overlapping token-windowed chunks.

    Overlap ensures no sentence/idea is cleanly severed at a chunk boundary.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    tokens = _ENCODING.encode(text)
    if not tokens:
        return []

    chunks: List[Chunk] = []
    start = 0
    index = 0
    step = chunk_size - overlap

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        window = tokens[start:end]
        content = _ENCODING.decode(window).strip()
        if content:
            chunks.append(Chunk(index=index, content=content, token_count=len(window)))
            index += 1
        if end == len(tokens):
            break
        start += step

    return chunks


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))
