# comori-rag-indexer

Handles text parsing, chunking, embedding generation, and decoding for the Comori RAG stack.
Does **not** connect to the database directly — `comori-api` (NestJS) owns all writes and
similarity search.

## Architecture

- **Ingestion (Branch A — knowledge):** PDF/MD upload → extract → chunk (~400 tokens, 50 overlap)
  → embed → content-hash `chunk_id` → push to `comori-api`
- **Ingestion (Branch B — memory):** PHI-scrubbed conversation turns → embed → UUID `memory_id`
  → push to `comori-api`
- **Query flow:** `comori-va` calls `POST /api/v1/embed/query` to embed a query, then
  `comori-api` performs the HNSW cosine similarity search, then `comori-va` calls
  `POST /api/v1/decode` here to clean/format the returned hits.

## Project structure
app/
├── api/ # FastAPI routers (health, knowledge, memory)
├── clients/ # comori-api client (print/http mode abstraction)
├── models/ # Pydantic request/response schemas
├── services/ # parser, chunker, embeddings, ingestion, search
├── config.py # env-driven settings
├── main.py # FastAPI entrypoint
└── utils.py
scripts/ # CLI seeding scripts

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # if present — configure EMBEDDING_PROVIDER, COMORI_API_MODE, etc.
uvicorn app.main:app --reload --port 8000
```

## Configuration

| Variable | Values | Description |
|---|---|---|
| `EMBEDDING_PROVIDER` | `minilm` \| `openai` | Active embedding backend (MiniLM is default, 384-dim) |
| `COMORI_API_MODE` | `print` \| `http` | Log payloads locally vs. send to `comori-api` |
| `COMORI_API_URL` | URL | Required when `COMORI_API_MODE=http` |
| `COMORI_API_KEY` | string | Auth token for `comori-api` |
| `CHUNK_TOKEN_SIZE` | int, default `400` | Tokens per chunk |
| `CHUNK_TOKEN_OVERLAP` | int, default `50` | Overlap between chunks |

## Endpoints

- `GET /health` — service + provider status
- `POST /api/v1/ingest` — unified ingestion (knowledge via multipart, memory via JSON)
- `POST /api/v1/embed/query` — embed a query string
- `POST /api/v1/decode` — format/clean raw similarity-search hits

## Scripts

```bash
python scripts/seed_corpus.py --manifest ./launch_docs/manifest.json
python scripts/seed_conversation.py --file ./sample_turns.json
```