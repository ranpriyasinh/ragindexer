"""
CLI script: seed the knowledge corpus from a directory of PDF/Markdown docs.

Usage:
    python scripts/seed_corpus.py --dir ./launch_docs \
        --source "Ben-Yacov 2021 · Diabetes Care" \
        --domain metabolic_science --evidence-tier tier1 --tags glucose,diabetes

For batch seeding of multiple distinct sources, prefer a manifest file:
    python scripts/seed_corpus.py --manifest ./launch_docs/manifest.json

manifest.json format:
[
  {
    "path": "ben-yacov-2021.pdf",
    "source": "Ben-Yacov 2021 · Diabetes Care",
    "domain": "metabolic_science",
    "evidence_tier": "tier1",
    "topic_tags": ["glucose", "diabetes"]
  }
]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.request import KnowledgeIngestMetadata  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402


def seed_from_manifest(manifest_path: Path, service: IngestionService) -> None:
    entries = json.loads(manifest_path.read_text())
    base_dir = manifest_path.parent

    docs_processed = chunks_added = chunks_skipped = 0
    for entry in entries:
        doc_path = base_dir / entry["path"]
        metadata = KnowledgeIngestMetadata(
            source=entry["source"],
            domain=entry["domain"],
            evidence_tier=entry["evidence_tier"],
            topic_tags=entry.get("topic_tags", []),
            corpus_version=entry.get("corpus_version"),
        )
        raw_bytes = doc_path.read_bytes()
        result = service.ingest_knowledge_document(doc_path.name, raw_bytes, metadata)
        print(f"[seed_corpus] {doc_path.name}: {result}")
        docs_processed += result["docs_processed"]
        chunks_added += result["chunks_added"]
        chunks_skipped += result["chunks_skipped"]

    print(
        f"\nSummary: docs_processed={docs_processed} "
        f"chunks_added={chunks_added} chunks_skipped={chunks_skipped}"
    )


def seed_single(
    path: Path,
    source: str,
    domain: str,
    evidence_tier: str,
    tags: list[str],
    service: IngestionService,
) -> None:
    metadata = KnowledgeIngestMetadata(
        source=source, domain=domain, evidence_tier=evidence_tier, topic_tags=tags
    )
    raw_bytes = path.read_bytes()
    result = service.ingest_knowledge_document(path.name, raw_bytes, metadata)
    print(f"[seed_corpus] {path.name}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the knowledge corpus.")
    parser.add_argument("--manifest", type=Path, help="Path to a manifest.json batch file")
    parser.add_argument("--file", type=Path, help="Single document path")
    parser.add_argument("--source", type=str, help="Source label, required with --file")
    parser.add_argument("--domain", type=str, help="Domain enum value, required with --file")
    parser.add_argument(
        "--evidence-tier", type=str, help="tier1|tier2|tier3, required with --file"
    )
    parser.add_argument("--tags", type=str, default="", help="Comma-separated topic tags")
    args = parser.parse_args()

    service = IngestionService()

    if args.manifest:
        seed_from_manifest(args.manifest, service)
    elif args.file:
        if not (args.source and args.domain and args.evidence_tier):
            parser.error("--file requires --source, --domain, and --evidence-tier")
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        seed_single(args.file, args.source, args.domain, args.evidence_tier, tags, service)
    else:
        parser.error("Provide either --manifest or --file")


if __name__ == "__main__":
    main()
