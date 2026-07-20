"""
CLI script: seed memory_vectors from a JSON file of PHI-scrubbed conversation turns.

Usage:
    python scripts/seed_conversation.py --file ./sample_turns.json

sample_turns.json format:
[
  {
    "user_id": "usr_123",
    "kind": "message",
    "snippet": "User reported feeling more energetic after switching to Zone 2 cardio.",
    "ref": "msg_9f2a",
    "occurred_at": "2026-06-01T10:00:00Z"
  }
]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.request import MemoryTurn  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed memory_vectors from a JSON turns file.")
    parser.add_argument("--file", type=Path, required=True, help="Path to turns JSON file")
    args = parser.parse_args()

    raw_entries = json.loads(args.file.read_text())
    turns = [MemoryTurn.model_validate(entry) for entry in raw_entries]

    service = IngestionService()
    result = service.ingest_memory_turns(turns)

    print(f"[seed_conversation] {result}")


if __name__ == "__main__":
    main()
