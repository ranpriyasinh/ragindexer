"""
Client for `comori-api` (NestJS).

Per spec section 5.3 ("No Direct Database Connections"): this module is the
ONLY place that knows about comori-api. Every other module sends payloads
here and does not care whether they end up printed to the console or POSTed
over HTTP.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("comori-rag-indexer.nest_client")


class NestClientError(RuntimeError):
    pass


class NestClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def mode(self) -> str:
        return self._settings.COMORI_API_MODE

    def push_knowledge_chunks(self, chunks: List[Dict[str, Any]]) -> bool:
        """Send knowledge_chunks rows (Branch A) to comori-api."""
        return self._dispatch(endpoint="/v1/knowledge/chunks", payload={"chunks": chunks})

    def push_memory_vectors(self, memories: List[Dict[str, Any]]) -> bool:
        """Send memory_vectors rows (Branch B) to comori-api."""
        return self._dispatch(endpoint="/v1/memory/vectors", payload={"memories": memories})

    # -- internal --------------------------------------------------------

    def _dispatch(self, endpoint: str, payload: Dict[str, Any]) -> bool:
        if self._settings.COMORI_API_MODE == "print":
            self._print_payload(endpoint, payload)
            return True
        if self._settings.COMORI_API_MODE == "http":
            return self._send_http(endpoint, payload)
        raise NestClientError(f"Unknown COMORI_API_MODE: {self._settings.COMORI_API_MODE}")

    def _print_payload(self, endpoint: str, payload: Dict[str, Any]) -> None:
        logger.info(
            "[PRINT MODE] Would POST to comori-api%s\n%s",
            endpoint,
            json.dumps(payload, indent=2, default=str),
        )
        print(f"\n=== comori-api PRINT MODE: POST {endpoint} ===")
        print(json.dumps(payload, indent=2, default=str))
        print("=== end payload ===\n")

    def _send_http(self, endpoint: str, payload: Dict[str, Any]) -> bool:
        if not self._settings.COMORI_API_URL:
            raise NestClientError("COMORI_API_MODE=http requires COMORI_API_URL to be set.")

        url = self._settings.COMORI_API_URL.rstrip("/") + endpoint
        headers = {"Content-Type": "application/json"}
        if self._settings.COMORI_API_KEY:
            headers["Authorization"] = f"Bearer {self._settings.COMORI_API_KEY}"

        try:
            with httpx.Client(timeout=self._settings.HTTP_TIMEOUT_SECONDS) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("comori-api dispatch failed: %s", exc)
            raise NestClientError(f"Failed to reach comori-api at {url}: {exc}") from exc
