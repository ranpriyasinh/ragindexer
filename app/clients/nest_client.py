from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx

from app.constants import KNOWLEDGE_CHUNKS_ENDPOINT,MEMORY_VECTORS_ENDPOINT,KNOWLEDGE_SEARCH_ENDPOINT,MEMORY_SEARCH_ENDPOINT


logger = logging.getLogger("comori-rag-indexer.nest_client")


class NestClientError(RuntimeError):
    pass


class NestClient:
    def __init__(self) -> None:
        self._base_url = os.getenv("COMORI_API_BASE_URL", "https://api-dev.comori.io/")
        self._api_key = os.getenv("COMORI_API_KEY")
        self._timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15.0"))

    def push_knowledge_chunks(self, chunks: List[Dict[str, Any]]) -> bool:
        """Send knowledge_chunks rows (Branch A) to comori-api."""
        return self._post(endpoint=KNOWLEDGE_CHUNKS_ENDPOINT, payload={"chunks": chunks})

    def push_memory_vectors(self, memories: List[Dict[str, Any]]) -> bool:
        """Send memory_vectors rows (Branch B) to comori-api."""
        return self._post(endpoint=MEMORY_VECTORS_ENDPOINT, payload={"memories": memories})

    def search_knowledge_chunks(self, embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Ask comori-api to run a pgvector similarity search against knowledge_chunks."""
        return self._fetch(
            endpoint=KNOWLEDGE_SEARCH_ENDPOINT,
            payload={"embedding": embedding, "k": k},
        )

    def search_memory_vectors(self, user_id: str, embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Ask comori-api to run a pgvector similarity search against memory_vectors."""
        return self._fetch(
            endpoint=MEMORY_SEARCH_ENDPOINT,
            payload={"user_id": user_id, "embedding": embedding, "k": k},
        )

    # -- internal --------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> bool:
        url = self._base_url.rstrip("/") + endpoint
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("comori-api dispatch failed: %s", exc)
            raise NestClientError(f"Failed to reach comori-api at {url}: {exc}") from exc

    def _fetch(self, endpoint: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        url = self._base_url.rstrip("/") + endpoint
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
                return response.json().get("hits", [])
        except httpx.HTTPError as exc:
            logger.error("comori-api search failed: %s", exc)
            raise NestClientError(f"Failed to reach comori-api at {url}: {exc}") from exc
