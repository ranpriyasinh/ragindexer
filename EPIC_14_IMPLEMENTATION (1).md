# Epic 14 — Knowledge Base & RAG Layer
## `comori-rag-indexer` — Implementation Plan (Source of Truth)

**Status:** Ready to build. This document is the source of truth for `comori-rag-indexer`. Any dev on this repo should be able to follow it without needing to ask what goes where.

**Services involved:**
| Service | Role | Status |
|---|---|---|
| `comori-rag-indexer` | Extraction, chunking, embedding, decoding. **All endpoints for this epic live here.** | **This repo — build now** |
| `comori-api` (NestJS) | Sole DB owner. Inserts vectors, runs similarity search. | **Not built yet** — see §5 |
| `comori-va` | Orchestrator agent. Calls this repo + `comori-api`. Owns intent classification, guardrails, response generation. | Existing repo, unchanged by this doc |

---

## 1. The core decision this doc locks in

**One endpoint for ingestion.** Not two. `POST /api/v1/ingest` accepts either a knowledge document (PDF/MD) or a conversation turn, and branches internally based on a `type` field. There is no `/knowledge/ingest` vs `/memory/ingest` split anymore — that was the previous draft and is now wrong.

**Every endpoint needed for this epic lives inside `comori-rag-indexer`.** `comori-api` is called *by* this repo (for writes) and *by* `comori-va` (for search) — it does not expose anything this repo needs to duplicate.

**`comori-api` doesn't exist yet.** Every place this repo would call it, it instead **prints the exact payload to the terminal** (structured JSON log) and returns a fake-success response with the same shape `comori-api` will eventually return. This lets ingestion be built, tested, and demoed end-to-end today. Swapping the print client for a real HTTP client later is a one-line config change — see §5.2.

---

## 2. Ingestion flow — one endpoint, two branches

```
POST /api/v1/ingest
```

**Every request carries a `type` field.** That's the only thing that decides which pipeline runs.

### Branch A — `type = "knowledge"` (PDF or Markdown file)
```
Content-Type: multipart/form-data
Fields:
  type: "knowledge"
  file: <upload — .pdf or .md>
  domain: "nutrition"                 -- nutrition|physical_activity|sleep|stress|metabolic_science|longevity|general
  evidence_tier: "tier1"              -- tier1|tier2|tier3
  source: "Ben-Yacov 2021 · Diabetes Care"
  corpus_version: "v0.1.0"
  topic_tags: "glucose,insulin_sensitivity"   -- comma-separated in form data
```
Flow: extract text → clean → chunk (~400 tokens, 50-token overlap) → embed each chunk → hash each chunk for idempotency → build one `knowledge_chunks` payload per chunk → hand each to the `comori-api` client (§5) → collect results → respond with a summary.

### Branch B — `type = "memory"` (a conversation turn)
```
Content-Type: application/json
Body:
{
  "type": "memory",
  "user_id": "usr_...",
  "kind": "message",                  -- message|event|intervention|fact
  "snippet": "...",                   -- must already be PHI-scrubbed by comori-va before it reaches here
  "ref": "msg_...",
  "occurred_at": "2026-07-20T10:03:00Z"
}
```
Flow: defensive PHI-pattern check → embed the snippet (single vector, no chunking) → build one `memory_vectors` payload → hand to the `comori-api` client → respond.

### Where the branch happens in code
```
app/api/routes/ingest.py         # the single route, reads `type`, delegates
        │
        ├── type == "knowledge" → app/pipelines/knowledge/ingest.py
        └── type == "memory"    → app/pipelines/memory/ingest.py
```
The route itself contains **no business logic** — it parses the request, picks a pipeline module, calls it, returns what it gives back. Both pipeline modules end by calling `app/clients/comori_api_client.py`, never the DB directly (there is no DB access anywhere in this repo).

---

## 3. Consumption (query) flow — exactly as agreed, three hops

This is `comori-va`'s flow, but documented here because `comori-rag-indexer` supplies two of the three steps.

```
1. comori-va decides to use knowledge data → calls its own knowledge_search MCP tool
2. comori-va rewrites the user's query (per config/knowledge.md — agent-side, not this repo)
3. comori-va calls THIS REPO:  POST /api/v1/embed/query   { "text": "<rewritten query>" }
                                → returns { "embedding": [...], "model": "..." }
4. comori-va calls comori-api (NestJS) directly with that embedding → comori-api runs the
   pgvector similarity search → returns top-k raw chunks/snippets + scores
5. comori-va calls THIS REPO again:  POST /api/v1/decode   { "hits": [...top-k raw results...] }
                                → returns plain-language, formatted context ready for the composer
6. comori-va uses that context to generate the final response
```

`comori-rag-indexer` only ever participates in steps 3 and 5. It never sees the top-k search call itself (step 4) — that goes straight from `comori-va` to `comori-api`.

### Endpoints this repo exposes for the query flow

**`POST /api/v1/embed/query`** — stateless, no DB, no caching needed here.
```
Request:  { "text": "..." }
Response: { "embedding": [0.0123, ...], "model": "all-MiniLM-L6-v2", "dimension": 384 }
```

**`POST /api/v1/decode`** — turns raw hits from `comori-api` into plain, composer-ready context.
```
Request:
{
  "purpose": "knowledge_search" | "memory_recall",
  "hits": [
    { "chunk_id": "...", "content": "...", "score": 0.83, "source": "...", "domain": "..." }
  ]
}
Response:
{
  "context": "formatted / cleaned text ready for the LLM prompt",
  "citations": [ { "source": "...", "label": "..." } ]
}
```
Exact formatting rules (truncation budget, citation style) should be filled in once `comori-va`'s composer team specifies the shape it wants — leave this endpoint's internals simple (pass-through + light cleanup) until then, but keep the contract stable.




## 5. `comori-api` integration — build the payload now, wire the API later

### 5.1 Exact payload shapes (mirrors `DATA_ARCHITECTURE.md`, Domain M, verbatim)

These are the two payload shapes this repo must produce. Copy this table into `docs/payload_contract.md` unmodified — it is the contract `comori-api`'s team needs to implement against.

**`knowledge_chunks` insert payload** (one per chunk, sent from `pipelines/knowledge/ingest.py`):
```json
{
  "chunk_id": "sha256:9f8a...",        // hasher.py output — idempotency key, comori-api upserts on conflict
  "source": "Ben-Yacov 2021 · Diabetes Care",
  "domain": "nutrition",
  "evidence_tier": "tier1",
  "topic_tags": ["glucose", "insulin_sensitivity"],
  "content": "chunk text, <=400 tokens",
  "embedding": [0.0123, "...", 0.0456],  // length = active provider's dimension (384 today, 1536 later)
  "corpus_version": "v0.1.0"
}
```
Not sent — `comori-api` derives these itself: `indexed_at` (DB default `now()`), and all of `knowledge_corpus_meta` (`doc_count`, `chunk_count`, `domains`, `gaps_flagged`, `last_ingested_at` — recomputed by `comori-api` after each successful insert, not pushed by this repo).

**`memory_vectors` insert payload** (one per turn, sent from `pipelines/memory/ingest.py`):
```json
{
  "memory_id": "mem_3f2e1a...",         // UUID generated in this repo, so retries are idempotent
  "user_id": "usr_...",
  "kind": "message",
  "snippet": "PHI-scrubbed text",
  "ref": "msg_...",
  "embedding": [0.0123, "...", 0.0456],
  "occurred_at": "2026-07-20T10:03:00Z"
}
```
Not sent — `created_at` (DB default `now()`).

### 5.2 The stub client (active now)

```python
# app/clients/print_client.py
class PrintComoriApiClient(ComoriApiClient):
    def insert_knowledge_chunk(self, payload: dict) -> dict:
        log.info("COMORI_API_CALL", target="POST /internal/knowledge/chunks", payload=payload)
        print(json.dumps({"target": "POST /internal/knowledge/chunks", "payload": payload}, indent=2))
        return {"status": "printed", "chunk_id": payload["chunk_id"]}

    def insert_memory_vector(self, payload: dict) -> dict:
        log.info("COMORI_API_CALL", target="POST /internal/memory/vectors", payload=payload)
        print(json.dumps({"target": "POST /internal/memory/vectors", "payload": payload}, indent=2))
        return {"status": "printed", "memory_id": payload["memory_id"]}
```

`app/clients/factory.py` reads `COMORI_API_MODE` (`print` today, `http` once `comori-api` exists) and hands back the right implementation. **Every pipeline module calls the client through this factory — never imports `print_client` or `http_client` directly.** That's what makes the eventual switch a one-line env change instead of a code change.

`app/clients/http_client.py` should still be written now (as a skeleton hitting the endpoints in §5.1), just not switched on by default — so when `comori-api` is ready, it's a config flip plus filling in real auth headers, not a new module.

### 5.3 What to verify during this phase
- Run a real PDF/MD file through `POST /api/v1/ingest` (Branch A) and through Branch B with a sample conversation turn.
- Confirm the printed JSON for both matches §5.1 exactly, field-for-field.
- Confirm `chunk_id` is stable (re-running the same file produces the same hash) and `memory_id` is a fresh UUID each time.
- This becomes the acceptance test for AI-14.1's "idempotent, safe to re-run" criterion, even before `comori-api` exists.

---

## 6. Embedding model — MiniLM now, OpenAI later, minimal-change design

**Active today:** `sentence-transformers/all-MiniLM-L6-v2`, **384 dimensions**, runs locally, no API cost.
**Planned:** OpenAI `text-embedding-3-small`, **1536 dimensions**, needs `OPENAI_API_KEY`.

```python
# app/embeddings/base.py
class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int: ...
    @abstractmethod
    def embed_text(self, text: str) -> list[float]: ...
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```
`minilm_provider.py` and `openai_provider.py` both implement this. `app/embeddings/factory.py` reads `EMBEDDING_PROVIDER=minilm|openai` and returns the active one. **No code outside `embeddings/` ever hardcodes a dimension number or a model name** — pipelines and payload builders read `provider.dimension` and include it in the response of `/api/v1/embed/query` (see §3), but never assume a fixed length.

**Important caveat — flag this to whoever builds `comori-api`'s schema:** switching `EMBEDDING_PROVIDER` is a one-line config change in *this* repo, but it is **not** a safe live toggle for the system as a whole. MiniLM (384-dim) and OpenAI (1536-dim) vectors are not comparable to each other and Postgres's `VECTOR(N)` column is a fixed dimension. Switching providers means:
1. `comori-api`'s `VECTOR(1536)` column definitions in `DATA_ARCHITECTURE.md` already assume the *future* OpenAI dimension — so today's MiniLM output (384-dim) **will not fit that column as-is**.
2. Practically: either (a) `comori-api`'s schema stays a placeholder until the switch happens and this phase only proves the payload shape/print output, not a real insert — which is fine, since there's no real DB call yet — or (b) if a dev wants to spin up a real Postgres locally to test inserts before `comori-api` exists, the column must be declared `VECTOR(384)` for now and migrated to `VECTOR(1536)` (full re-embed + re-index, not a schema-only change) when the switch happens.
3. Either way: **the switch from MiniLM to OpenAI is always a full re-ingestion of the corpus and all memory vectors, never an in-place conversion.** Put this in `docs/corpus_governance.md` so it isn't forgotten.

---

## 7. Branching strategy

Trunk-based, story-ID-driven, kept deliberately simple for a small greenfield service.

- **`main`** — protected. Always deployable. No direct pushes. Requires: PR approval (≥1 reviewer), green CI, and a manual confirmation that any change touching §5.1 payload shapes has an updated `docs/payload_contract.md` in the same PR.
- **Feature branches** — one per backlog story, named after its ID:
  `feature/AI-14.1-ingestion-pipeline`, `feature/AI-14.3-embed-and-decode-endpoints`, `feature/AI-14.5-seed-launch-corpus`, `feature/AI-2.7-memory-branch`, etc.
  Branch off latest `main`, keep it short-lived (days, not weeks) — this repo has no long-running `develop` branch; `main` is the integration branch.
- **Commit messages** reference the story ID: `AI-14.1: add PDF/MD extraction + chunker`.
- **PRs squash-merge** into `main`. PR description must state: which branch (A/B) it touches, whether it changes the payload contract, and whether it changes the active embedding provider or `comori-api` client mode.
- **Tags** — cut a `v0.x.y` tag at the end of each phase (see §8), not per-PR.
- **Config-only flips** (`EMBEDDING_PROVIDER`, `COMORI_API_MODE`) are still PRs, even though they're one line — they change runtime behavior for the whole service and need the same review gate as code.

---

## 8. Build sequence

| Phase | Ships | Notes |
|---|---|---|
| 0 | `POST /api/v1/ingest`, Branch A (knowledge) fully working against `print_client` | AI-14.1 |
| 0 | `POST /api/v1/ingest`, Branch B (memory) fully working against `print_client` | AI-2.7 write side |
| 0 | `embeddings/` module with MiniLM active, OpenAI provider written but not wired on | §6 |
| 1 | `POST /api/v1/embed/query` and `POST /api/v1/decode` | §3 |
| 1 | AI-14.5 — launch corpus run through Branch A, printed payloads spot-checked against §5.1 | needs Phase 0 |
| 2 | `http_client.py` wired on, real calls to `comori-api` once it exists | needs `comori-api`'s endpoints built |
| 2 | AI-14.8 — governance doc finalized (incl. the MiniLM→OpenAI re-ingestion caveat from §6) | — |

**Explicitly not in this repo, unchanged from before:** AI-14.7 (intent classifier — `comori-va` planner), AI-14.2 (`knowledge.md` config — `comori-va`), AI-14.6 (clinical guardrail — `comori-va` policy_filter), MCP tool registration (AI-1.7 — `comori-va`), and the actual similarity search query (runs inside `comori-api`, never in this repo).

---

## 9. Open items still needing an answer

1. **`comori-api`'s real endpoint paths/auth** — §5.1 is this repo's expectation; needs sign-off once `comori-api` work starts.
2. **Batch vs per-chunk writes** — right now Branch A calls the client once per chunk. If `comori-api` will accept a batch array, that's a meaningful efficiency win worth building for from day one instead of retrofitting.
3. **`cohort_filter` evaluation point** — still unresolved: at search time in `comori-api`, or post-filtered in `comori-va`. Doesn't block this repo but blocks `comori-va`'s Phase 1 wiring.
4. **Local test DB for `comori-api` integration testing** — if anyone wants to spin one up before `comori-api` is built, use `VECTOR(384)` (matching MiniLM) per §6, not `VECTOR(1536)`.
