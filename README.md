# comori-rag-indexer

Handles text parsing, chunking, embedding generation, and decoding for the Comori RAG stack.
This service does **not** connect to the database directly — `comori-api` (NestJS) owns all
database writes and similarity search.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup](#setup)
- [Configuration](#configuration)
- [Endpoints](#endpoints)
- [Data Model Reference](#data-model-reference)
- [Development Notes](#development-notes)

---

## Architecture

### Ingestion Flow

A single unified endpoint, `POST /api/v1/ingest`, handles two branches:

- **Branch A — Knowledge** (`type=knowledge`, JSON body)
  Already-extracted document text (from comori-api's PDF/Markdown parsing) → clean →
  chunk (~400 tokens, 50-token overlap) → embed chunks → generate content-hash `chunk_id`
  (idempotent) → `POST` to comori-api's `/api/knowledge/chunks`.

- **Branch B — Memory** (`type=memory`, JSON body)
  PHI-scrubbed conversation turns → embed → generate UUID-based `memory_id` → push to `comori-api`.

`comori-api`'s base URL is env-driven (`COMORI_API_BASE_URL`) so it can point at dev, staging,
or production; endpoint paths are fixed constants in `app/constants.py`.

### Query Flow

1. `comori-va` calls `POST /api/v1/embed/query` on this service to embed a user query.
2. `comori-va` passes that embedding to `comori-api`, which performs the HNSW cosine
   similarity search against `pgvector`.
3. `comori-va` sends the raw hits back to `POST /api/v1/decode` on this service, which
   formats and cleans the text for presentation.

This service never talks to `comori-api`'s database directly — all reads and writes to
`knowledge_chunks` and `memory_vectors` go through `comori-api`'s HTTP endpoints.

---

## Project Structure
```
ragindexer/
├── app/
│ ├── api/
│ │ ├── health.py # GET /health
│ │ ├── knowledge.py # POST /api/v1/ingest, /embed/query, /decode, /retrieve
│ │ └── memory.py # Branch B (memory) ingestion logic
│ ├── clients/
│ │ └── nest_client.py # Abstracts all comori-api HTTP communication
│ ├── services/
│ │ ├── chunker.py # Token-based chunking with overlap
│ │ ├── embeddings.py # OpenAI embedding provider (text-embedding-3-small)
│ │ ├── ingestion.py # Orchestrates Branch A + Branch B ingestion
│ │ ├── parser.py # PDF/Markdown text extraction
│ │ └── search.py # Query embedding + decode/formatting of hits
│ ├── constants.py # comori-api endpoint paths
│ ├── __init__.py # Loads .env (python-dotenv) before any app.* module runs
│ └── main.py # FastAPI entrypoint
├── schema/
│ ├── request.py # Pydantic request schemas
│ └── response.py # Pydantic response schemas
├── utils.py # Content hashing, id generation
├── requirements.txt
└── .gitignore
```
---

## Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/ranpriyasinh/ragindexer.git
cd ragindexer

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate      # on Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env          # create this if it doesn't exist yet — see Configuration below

# 5. Run the service
uvicorn app.main:app --reload --port 8000
```

Once running, visit `http://localhost:8000/docs` for interactive API docs (Swagger UI),
or `http://localhost:8000/health` for a quick status check.

---

## Configuration

There is no settings class — every value is read directly via `os.getenv(...)` at the point
of use, straight from the process environment. `app/__init__.py` loads `.env` (via
`python-dotenv`) before any other `app.*` module runs, so `.env` is the only place to edit.
Endpoint *paths* (e.g. `/api/knowledge/chunks`) are fixed constants in `app/constants.py`, but
the `comori-api` *base URL* is env-driven so it can differ across dev/staging/production.

| Variable | Type | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | string | `None` | Required — this service embeds via OpenAI `text-embedding-3-small`. |
| `OPENAI_EMBEDDING_MODEL` | string | `text-embedding-3-small` | OpenAI embedding model name (1536-dim). |
| `COMORI_API_BASE_URL` | URL | `https://api-dev.comori.io/` | Base URL for `comori-api`. Override per environment. |
| `COMORI_API_KEY` | string | `None` | Bearer token sent to `comori-api` on every request. |
| `CHUNK_TOKEN_SIZE` | int | `400` | Target tokens per chunk. |
| `CHUNK_TOKEN_OVERLAP` | int | `50` | Token overlap between adjacent chunks. |
| `CORPUS_VERSION` | string | `v0.1.0` | Default corpus version tag applied to ingested chunks, if not specified per-document. |
| `APP_NAME` | string | `comori-rag-indexer` | Service name, shown in `/health` and API docs. |
| `HTTP_TIMEOUT_SECONDS` | float | `15.0` | Timeout for outbound HTTP calls to `comori-api`. |

Example `.env`:

```env
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
COMORI_API_BASE_URL=https://api-dev.comori.io/
COMORI_API_KEY=
CHUNK_TOKEN_SIZE=400
CHUNK_TOKEN_OVERLAP=50
CORPUS_VERSION=v0.1.0
```

---

## Endpoints

### `GET /health`
Returns service status, active embedding provider, and vector dimension.

### `POST /api/v1/ingest`
Unified ingestion endpoint. Behavior depends on the `type` field in the JSON body:

**Knowledge (Branch A)**:
```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Full extracted text from the PDF/Markdown document...",
    "source": "ADA Standards of Care 2026",
    "domain": "NUTRITION",
    "evidenceTier": "TIER1",
    "topicTags": ["glucose", "insulin", "diet"],
    "corpusVersion": "v1"
  }'
```
This chunks + embeds the text, then `POST`s the resulting chunks to comori-api's
`/api/knowledge/chunks`:
```json
{
  "chunks": [
    {
      "chunkId": "sha256:...",
      "source": "ADA Standards of Care 2026",
      "domain": "NUTRITION",
      "evidenceTier": "TIER1",
      "topicTags": ["glucose", "insulin", "diet"],
      "content": "...",
      "embedding": [0.921231, 0.984951, "..."],
      "corpusVersion": "v1"
    }
  ]
}
```

**Memory (Branch B)** — `application/json`:
```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "type": "memory",
    "turns": [
      {
        "user_id": "usr_123",
        "kind": "message",
        "snippet": "User reported feeling more energetic after switching to Zone 2 cardio.",
        "ref": "msg_9f2a",
        "occurred_at": "2026-06-01T10:00:00Z"
      }
    ]
  }'
```

### `POST /api/v1/embed/query`
Embeds a query string for downstream similarity search.
```bash
curl -X POST http://localhost:8000/api/v1/embed/query \
  -H "Content-Type: application/json" \
  -d '{"query": "exercise type metabolic health glucose insulin sensitivity"}'
```

### `POST /api/v1/decode`
Formats/cleans raw hits returned by `comori-api`'s similarity search.
```bash
curl -X POST http://localhost:8000/api/v1/decode \
  -H "Content-Type: application/json" \
  -d '{
    "hits": [
      {"id": "sha256:abc123", "score": 0.82, "content": "  Zone 2 training improves...  ", "source": "Ben-Yacov 2021", "domain": "metabolic_science", "evidence_tier": "tier1"}
    ]
  }'
```

---

## Data Model Reference

This service does not own these tables — `comori-api` does. Included here for context on the
payload shapes this service produces.

```sql
CREATE TABLE knowledge_chunks (
  chunk_id       TEXT PRIMARY KEY,  -- Content hash (sha256:...)
  source         TEXT,
  domain         TEXT,              -- nutrition|physical_activity|sleep|stress|metabolic_science|longevity|general
  evidence_tier  TEXT,              -- tier1|tier2|tier3
  topic_tags     TEXT[],
  content        TEXT,              -- ≤400 tokens
  embedding      VECTOR(1536),      -- 1536 dim for text-embedding-3-small
  corpus_version TEXT,
  indexed_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE memory_vectors (
  memory_id   TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  kind        TEXT,                 -- message|event|intervention|fact
  snippet     TEXT,
  ref         TEXT,
  embedding   VECTOR(1536),
  occurred_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Development Notes

- **comori-api base URL is env-driven** (`COMORI_API_BASE_URL` in `.env`, read via
  `os.getenv` in `app/clients/nest_client.py`), defaulting to `https://api-dev.comori.io/`
  if unset. Endpoint paths live in `app/constants.py`.
  Only `/api/knowledge/chunks` is a confirmed live route today — the memory/search endpoints
  used by `push_memory_vectors` / `search_knowledge_chunks` / `search_memory_vectors` are
  defined locally in `app/clients/nest_client.py` pending sign-off from the comori-api team.
- **Embedding dimension is never hardcoded.** Always read `.dimension` from the active
  `EmbeddingProvider` instance — this keeps the codebase provider-agnostic if the embedding
  model changes later.
- **Idempotency:** `chunk_id` is derived from a SHA-256 hash of chunk content. Re-ingesting
  the same document produces the same `chunk_id`s, so `comori-api` can safely upsert without
  creating duplicates.
- **No direct database access.** All `comori-api` communication is isolated inside
  `app/clients/nest_client.py`, which always POSTs over HTTP. Nothing else in this codebase
  should talk to Postgres/pgvector.
