# DATA_ARCHITECTURE — Epic 14 Excerpt

**Source:** extracted from the full `DATA_ARCHITECTURE.md`, scoped to only what's needed to build Epic 14 (`comori-rag-indexer` + the `comori-api` payload contract in `docs/payload_contract.md`). This is the only architecture reference this repo's devs need — the full document is not shared.

---

## 1. Vector storage convention

```
-- pgvector vector(1536); HNSW index, cosine ops (knowledge_chunks, memory_vectors).
```

```
| Store | What lives there |
|---|---|
| PostgreSQL | The system of record. |
| pgvector (same Postgres) | memory_vectors, knowledge_chunks — HNSW indexes, cosine ops |
```
No new infrastructure is introduced for this epic — same Postgres instance, pgvector extension, HNSW indexes.

---

## 2. Schema — Domain M: Semantic Memory & Knowledge

*`memory_vectors`, `knowledge_chunks`, `knowledge_corpus_meta`, `knowledge_retrievals`*

```sql
CREATE TABLE memory_vectors (   -- AI-2.7: per-user semantic recall
  memory_id  TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users,
  kind TEXT,   -- message|event|intervention|fact
  snippet TEXT,               -- PHI-scrubbed (AI-2.7 / 11.4)
  ref TEXT,                   -- back-pointer to source row
  embedding  VECTOR(1536),
  occurred_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON memory_vectors USING hnsw (embedding vector_cosine_ops);

CREATE TABLE knowledge_chunks (  -- shared, versioned — NOT user data
  chunk_id     TEXT PRIMARY KEY,  -- content hash (idempotent ingest)
  source       TEXT,              -- "Ben-Yacov 2021 · Diabetes Care"
  domain       TEXT,              -- nutrition|physical_activity|sleep|stress|metabolic_science|longevity|general
  evidence_tier TEXT,             -- tier1|tier2|tier3
  topic_tags   TEXT[],
  content      TEXT,              -- ≤400 tokens
  embedding    VECTOR(1536),
  corpus_version TEXT,
  indexed_at   TIMESTAMPTZ DEFAULT now());
CREATE INDEX ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE knowledge_corpus_meta (
  corpus_version TEXT PRIMARY KEY,
  doc_count INT, chunk_count INT, domains JSONB,
  gaps_flagged TEXT[], last_ingested_at TIMESTAMPTZ);

CREATE TABLE knowledge_retrievals (  -- audit log
  retrieval_id TEXT PRIMARY KEY, user_id TEXT,
  original_query TEXT, rewritten_query TEXT, domain TEXT,
  k INT, chunk_ids TEXT[], corpus_version TEXT,
  trace_id TEXT, created_at TIMESTAMPTZ DEFAULT now());
```

**Note on `VECTOR(1536)`:** this is the target dimension for the planned OpenAI `text-embedding-3-small` model. If MiniLM (384-dim) is used first, the column must temporarily be declared `VECTOR(384)` in any local test DB — see the embedding-provider caveat in the implementation plan. Switching dimensions later is a full re-ingest, never an in-place migration.

---

## 3. Events relevant to this epic

| Event | Emitter | Canonical table | Downstream |
|---|---|---|---|
| MEMORY_REDACTED | `forget_item` | `redactions` + tombstones | Cascades to `memory_vectors`, summaries, LangSmith (≤24h) |
| KNOWLEDGE_RETRIEVED | `knowledge_search` | `knowledge_retrievals` | Audit log only; reads (not writes) chunks |

---

## 4. MCP tools reading these tables (owned by `comori-va`, not this repo)

| Tool | Tables read | Notes |
|---|---|---|
| `retrieve_relevant_memories` | `memory_vectors` (HNSW) | PHI-scrubbed snippets only |
| `knowledge_search` | `knowledge_chunks` (HNSW) → logs to `knowledge_retrievals` | Reads corpus; writes audit row; output passes clinical guardrail |
| `knowledge_index_status` | `knowledge_corpus_meta` | Coverage + gaps |

---

## 5. Cross-cutting rules that apply to this epic

| # | Concern | Rule |
|---|---|---|
| XC1 | PHI scrubbing at the process boundary | email→`<email>`, phone→`<phone>`, names→`<person>`, raw CGM→bucket, precise geo→region. Wired at SDK layer; cannot opt out (AI-11.4). Applies to every `memory_vectors.snippet` before it reaches this repo. |
| XC3 | Redaction cascades | `forget_item` / account erasure propagates to `memory_vectors` (delete), among other tables. `cascaded_to[]` proves GDPR erasure. This repo doesn't implement the cascade (no DB access) but its output (`memory_id`) must be traceable so `comori-api` can execute it. |
| XC5 | Writes are idempotent & at-least-once | Redelivered writes never double-apply. This is why `knowledge_chunks.chunk_id` is a content hash and why this repo generates a stable `memory_id` per turn (see the payload contract). |
| XC6 | Scope enforced at the fabric, not the prompt | `user_id` comes from the session token at the MCP gateway, never from anything the LLM wrote. A tool physically cannot read/write another user's rows — relevant to `memory_vectors` search being strictly scoped to the requesting `user_id`. |

---

## 6. Epic/table ownership mapping

| Table(s) | Epic | Story | Priority / notes |
|---|---|---|---|
| `memory_vectors` | AI-2 | AI-2.7 | P2 · semantic recall; PHI-scrubbed |
| `knowledge_chunks`, `_corpus_meta`, `_retrievals` | AI-14 | ingestion + `knowledge_search` | P1 |

---

## 7. Reference-table note

```
These are deployed via git/ingestion, read by tools, never written by the agent:
usda_foods · gi_gl_table · population_priors · intervention_catalog ·
knowledge_chunks / knowledge_corpus_meta · lessons
```
`knowledge_chunks` and `knowledge_corpus_meta` are explicitly called out as deployed via the ingestion pipeline (this repo → `comori-api`) — the running agent (`comori-va`) only ever reads them, never writes them directly.
