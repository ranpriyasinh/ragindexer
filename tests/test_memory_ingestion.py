"""
Unit tests for Pipeline 2 (User Memory Ingestion & PHI Defensive Checking).
"""
from __future__ import annotations

from typing import List

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.request import MemoryKind, MemoryTurn
from app.services.embeddings import EmbeddingProvider
from app.services.memory_ingestion import MemoryIngestionError, MemoryIngestionService
from app.services.phi import PHISanitizer, PHISafetyViolationError


class DummyEmbeddingProvider(EmbeddingProvider):
    """Fast mock embedding provider for unit tests."""

    @property
    def dimension(self) -> int:
        return 384

    @property
    def name(self) -> str:
        return "mock_test_provider"

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.1] * self.dimension for _ in texts]


def test_phi_sanitizer_detects_raw_phi() -> None:
    """Tests that PHISanitizer detects raw email and phone patterns."""
    raw_snippet = "Contact patient at john.doe@example.com or 555-123-4567."
    violations = PHISanitizer.detect_phi(raw_snippet)
    assert "email" in violations
    assert "phone" in violations

    with pytest.raises(PHISafetyViolationError) as exc_info:
        PHISanitizer.assert_phi_free(raw_snippet)
    assert "email" in exc_info.value.detected_types


def test_phi_sanitizer_cleans_valid_text() -> None:
    """Tests that PHISanitizer passes clean text without errors."""
    clean_snippet = "User reported improved energy after 30 minutes of walking."
    assert PHISanitizer.detect_phi(clean_snippet) == []
    PHISanitizer.assert_phi_free(clean_snippet)


def test_memory_ingestion_service_success() -> None:
    """Tests MemoryIngestionService with mock embeddings."""
    service = MemoryIngestionService(embedding_provider=DummyEmbeddingProvider())
    turns = [
        MemoryTurn(
            user_id="usr_test123",
            kind=MemoryKind.MESSAGE,
            snippet="User prefers low-carb options for dinner.",
            ref="msg_001",
        )
    ]
    result = service.ingest_memory_turns(turns)
    assert result["memories_added"] == 1
    assert result["memories_skipped"] == 0
    assert result["dispatched"] is True


def test_memory_ingestion_service_phi_failure() -> None:
    """Tests MemoryIngestionService raises MemoryIngestionError on PHI violation."""
    service = MemoryIngestionService(embedding_provider=DummyEmbeddingProvider())
    turns = [
        MemoryTurn(
            user_id="usr_test123",
            kind=MemoryKind.FACT,
            snippet="User email is jane.smith@hospital.org",
        )
    ]
    with pytest.raises(MemoryIngestionError):
        service.ingest_memory_turns(turns)


def test_api_memory_ingest_endpoint() -> None:
    """Integration test for POST /api/v1/ingest memory branch."""
    client = TestClient(app)
    payload = {
        "type": "memory",
        "turns": [
            {
                "user_id": "usr_api_test",
                "kind": "message",
                "snippet": "User consistently tracks 8 hours of sleep per night.",
                "ref": "msg_api_01",
            }
        ],
    }
    response = client.post("/api/v1/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "memory"
    assert data["memories_added"] == 1
    assert data["dispatched"] is True
