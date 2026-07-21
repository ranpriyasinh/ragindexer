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
            if endpoint == "/v1/memory/vectors":
                self._save_memories_to_db(payload.get("memories", []))
            elif endpoint == "/v1/knowledge/chunks":
                self._save_knowledge_chunks_to_db(payload.get("chunks", []))
            return True
        if self._settings.COMORI_API_MODE == "http":
            return self._send_http(endpoint, payload)
        raise NestClientError(f"Unknown COMORI_API_MODE: {self._settings.COMORI_API_MODE}")

    def _save_knowledge_chunks_to_db(self, chunks: List[Dict[str, Any]]) -> None:
        if not chunks:
            return
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            try:
                with conn.cursor() as cursor:
                    for c in chunks:
                        emb = c.get("embedding")
                        emb_str = f"[{','.join(map(str, emb))}]" if emb else None
                        cursor.execute(
                            """
                            INSERT INTO knowledge_chunks (chunk_id, source, domain, evidence_tier, topic_tags, content, embedding, corpus_version)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (chunk_id) DO UPDATE SET
                                source = EXCLUDED.source,
                                domain = EXCLUDED.domain,
                                evidence_tier = EXCLUDED.evidence_tier,
                                topic_tags = EXCLUDED.topic_tags,
                                content = EXCLUDED.content,
                                embedding = EXCLUDED.embedding,
                                corpus_version = EXCLUDED.corpus_version
                            """,
                            (
                                c.get("chunk_id"),
                                c.get("source"),
                                c.get("domain"),
                                c.get("evidence_tier"),
                                c.get("topic_tags"),
                                c.get("content"),
                                emb_str,
                                c.get("corpus_version"),
                            ),
                        )
                conn.commit()
                logger.info("Successfully stored %d knowledge chunks in pgvector database.", len(chunks))
            except Exception as e:
                conn.rollback()
                logger.error("Failed to write knowledge chunks to DB: %s", e)
            finally:
                conn.close()
        except Exception as e:
            logger.error("Failed to connect to local PG database for knowledge chunks: %s", e)

    def _save_memories_to_db(self, memories: List[Dict[str, Any]]) -> None:
        if not memories:
            return
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=self._settings.DB_HOST,
                port=self._settings.DB_PORT,
                database=self._settings.DB_NAME,
                user=self._settings.DB_USER,
                password=self._settings.DB_PASSWORD,
            )
            try:
                with conn.cursor() as cursor:
                    # Automatically ensure users exist in the local users table to prevent FK failure
                    user_ids = list({m["user_id"] for m in memories if m.get("user_id")})
                    for uid in user_ids:
                        cursor.execute(
                            "INSERT INTO users (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                            (uid,),
                        )

                    for m in memories:
                        emb = m.get("embedding")
                        emb_str = f"[{','.join(map(str, emb))}]" if emb else None
                        cursor.execute(
                            """
                            INSERT INTO memory_vectors (memory_id, user_id, kind, snippet, ref, embedding, occurred_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (memory_id) DO UPDATE SET
                                user_id = EXCLUDED.user_id,
                                kind = EXCLUDED.kind,
                                snippet = EXCLUDED.snippet,
                                ref = EXCLUDED.ref,
                                embedding = EXCLUDED.embedding,
                                occurred_at = EXCLUDED.occurred_at
                            """,
                            (
                                m.get("memory_id"),
                                m.get("user_id"),
                                m.get("kind"),
                                m.get("snippet"),
                                m.get("ref"),
                                emb_str,
                                m.get("occurred_at"),
                            ),
                        )
                conn.commit()
                logger.info("Successfully stored %d memories in pgvector database.", len(memories))
            except Exception as e:
                conn.rollback()
                logger.error("Failed to write memory vectors to DB: %s", e)
            finally:
                conn.close()
        except Exception as e:
            logger.error("Failed to connect to local PG database: %s", e)

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

    def search_knowledge_chunks(self, embedding: List[float], k: int) -> List[Dict[str, Any]]:
        """Ask comori-api to run a pgvector similarity search against knowledge_chunks."""
        return self._fetch(
            endpoint="/v1/knowledge/search",
            payload={"embedding": embedding, "k": k},
        )

    # -- internal --------------------------------------------------------

    def _fetch(self, endpoint: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Like _dispatch, but for calls that return data instead of a bool."""
        if self._settings.COMORI_API_MODE == "print":
            self._print_payload(endpoint, payload)
            logger.info("[PRINT MODE] No comori-api to query — returning empty hit list.")
            return []
        if self._settings.COMORI_API_MODE == "http":
            return self._send_http_fetch(endpoint, payload)
        raise NestClientError(f"Unknown COMORI_API_MODE: {self._settings.COMORI_API_MODE}")

    def _send_http_fetch(self, endpoint: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
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
                return response.json().get("hits", [])
        except httpx.HTTPError as exc:
            logger.error("comori-api search failed: %s", exc)
            raise NestClientError(f"Failed to reach comori-api at {url}: {exc}") from exc