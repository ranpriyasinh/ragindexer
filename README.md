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
- [Seeding Scripts](#seeding-scripts)
- [Development Notes](#development-notes)

---

## Architecture

### Ingestion Flow

A single unified endpoint, `POST /api/v1/ingest`, handles two branches:

- **Branch A — Knowledge** (`type=knowledge`, multipart form data)
  PDF/Markdown upload → extract text → clean → chunk (~400 tokens, 50-token overlap) →
  embed chunks → generate content-hash `chunk_id` (idempotent) → push to `comori-api`.

- **Branch B — Memory** (`type=memory`, JSON body)
  PHI-scrubbed conversation turns → embed → generate UUID-based `memory_id` → push to `comori-api`.

`comori-api` is not fully built yet, so this service supports a **print mode**
(`COMORI_API_MODE=print`) that logs the outbound payload to the console instead of making a
network call. Switch to `COMORI_API_MODE=http` once `comori-api` is ready to receive traffic.

### Query Flow

1. `comori-va` calls `POST /api/v1/embed/query` on this service to embed a user query.
2. `comori-va` passes that embedding to `comori-api`, which performs the HNSW cosine
   similarity search against `pgvector`.
3. `comori-va` sends the raw hits back to `POST /api/v1/decode` on this service, which
   formats and cleans the text for presentation.

This service never talks to `comori-api`'s database directly — all reads and writes to
`knowledge_chunks` and `memory_vectors` go through `comori-api`.

---

## Project Structure
ragindexer/
├── app/
│ ├── api/
│ │ ├── health.py # GET /health
│ │ ├── knowledge.py # POST /api/v1/ingest, /embed/query, /decode
│ │ └── memory.py # Branch B (memory) ingestion logic
│ ├── clients/
│ │ └── nest_client.py # Abstracts all comori-api communication (print/http mode)
│ ├── models/
│ │ ├── request.py # Pydantic request schemas
│ │ └── response.py # Pydantic response schemas
│ ├── services/
│ │ ├── chunker.py # Token-based chunking with overlap
│ │ ├── embeddings.py # Embedding provider abstraction (MiniLM / OpenAI)
│ │ ├── ingestion.py # Orchestrates Branch A + Branch B ingestion
│ │ ├── parser.py # PDF/Markdown text extraction
│ │ └── search.py # Query embedding + decode/formatting of hits
│ ├── config.py # Env-driven settings
│ ├── main.py # FastAPI entrypoint
│ └── utils.py # Content hashing, id generation
├── scripts/
│ ├── seed_conversation.py # CLI: seed memory_vectors from a JSON turns file
│ └── seed_corpus.py # CLI: seed knowledge_chunks from PDF/MD docs
├── requirements.txt
└── .gitignore
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

All configuration is sourced from environment variables (`.env` file supported).

| Variable | Type | Default | Description |
|---|---|---|---|
| `EMBEDDING_PROVIDER` | `minilm` \| `openai` | `minilm` | Active embedding backend. MiniLM (`all-MiniLM-L6-v2`, 384-dim) is the only active provider today; OpenAI is implemented but disabled by default. |
| `OPENAI_API_KEY` | string | `None` | Required only if `EMBEDDING_PROVIDER=openai`. |
| `OPENAI_EMBEDDING_MODEL` | string | `text-embedding-3-small` | OpenAI embedding model name. |
| `COMORI_API_MODE` | `print` \| `http` | `print` | `print` logs the outbound payload to stdout instead of making a network call. `http` sends a real POST request. |
| `COMORI_API_URL` | URL | `None` | Base URL for `comori-api`. Required when `COMORI_API_MODE=http`. |
| `COMORI_API_KEY` | string | `None` | Bearer token sent to `comori-api` when in `http` mode. |
| `CHUNK_TOKEN_SIZE` | int | `400` | Target tokens per chunk. |
| `CHUNK_TOKEN_OVERLAP` | int | `50` | Token overlap between adjacent chunks. |
| `CORPUS_VERSION` | string | `v0.1.0` | Default corpus version tag applied to ingested chunks, if not specified per-document. |
| `APP_NAME` | string | `comori-rag-indexer` | Service name, shown in `/health` and API docs. |
| `HTTP_TIMEOUT_SECONDS` | float | `15.0` | Timeout for outbound HTTP calls to `comori-api`. |

Example `.env`:

```env
EMBEDDING_PROVIDER=minilm
COMORI_API_MODE=print
COMORI_API_URL=
COMORI_API_KEY=
CHUNK_TOKEN_SIZE=400
CHUNK_TOKEN_OVERLAP=50
CORPUS_VERSION=v0.1.0
```

---

## Endpoints

### `GET /health`
Returns service status, active embedding provider, vector dimension, and current `comori-api` mode.

### `POST /api/v1/ingest`
Unified ingestion endpoint. Behavior depends on content type:

**Knowledge (Branch A)** — `multipart/form-data`:
```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "type=knowledge" \
  -F "file=@paper.pdf" \
  -F 'metadata={"source":"Ben-Yacov 2021 · Diabetes Care","domain":"metabolic_science","evidence_tier":"tier1","topic_tags":["glucose","diabetes"]}'
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
  embedding      VECTOR(384),       -- 384 dim for MiniLM (active provider)
  corpus_version TEXT,
  indexed_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE memory_vectors (
  memory_id   TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  kind        TEXT,                 -- message|event|intervention|fact
  snippet     TEXT,
  ref         TEXT,
  embedding   VECTOR(384),
  occurred_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Seeding Scripts

### Seed the knowledge corpus
```bash
# Single document
python scripts/seed_corpus.py --file ./ben-yacov-2021.pdf \
  --source "Ben-Yacov 2021 · Diabetes Care" \
  --domain metabolic_science --evidence-tier tier1 --tags glucose,diabetes

# Batch, via manifest.json
python scripts/seed_corpus.py --manifest ./launch_docs/manifest.json
```

### Seed conversation memory
```bash
python scripts/seed_conversation.py --file ./sample_turns.json
```

---

## Development Notes

- **Embedding dimension is never hardcoded.** Always read `.dimension` from the active
  `EmbeddingProvider` instance — this keeps the codebase provider-agnostic if the embedding
  model changes later.
- **Idempotency:** `chunk_id` is derived from a SHA-256 hash of chunk content. Re-ingesting
  the same document produces the same `chunk_id`s, so `comori-api` can safely upsert without
  creating duplicates.
- **No direct database access.** All `comori-api` communication is isolated inside
  `app/clients/nest_client.py`. Nothing else in this codebase should talk to Postgres/pgvector.