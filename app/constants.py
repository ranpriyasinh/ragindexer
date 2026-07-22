"""
Constants for talking to comori-api (NestJS).

Endpoint paths only — the base URL is environment-driven (COMORI_API_BASE_URL
in .env, read via os.getenv in app/clients/nest_client.py) since it changes
between dev/staging/production.
"""
from __future__ import annotations

KNOWLEDGE_CHUNKS_ENDPOINT = "/api/knowledge/chunks"
MEMORY_VECTORS_ENDPOINT = "/v1/memory/vectors"
KNOWLEDGE_SEARCH_ENDPOINT = "/v1/knowledge/search"
MEMORY_SEARCH_ENDPOINT = "/v1/memory/search"
