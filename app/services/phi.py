"""
Defensive Protected Health Information (PHI) checker & sanitizer.

Per spec rule XC1 & Branch B requirements:
Memory snippets passing into comori-rag-indexer must be free of raw PHI
(emails, phone numbers, SSNs, precise IP addresses). This module provides
defensive validation and redaction before embeddings are generated.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Pattern, Tuple

logger = logging.getLogger("comori-rag-indexer.phi")


class PHISafetyViolationError(ValueError):
    """Raised when unscrubbed raw PHI is detected in a memory snippet."""

    def __init__(self, message: str, detected_types: List[str]) -> None:
        super().__init__(message)
        self.detected_types = detected_types


class PHISanitizer:
    """Enterprise defensive PHI checking engine."""

    PATTERNS: Dict[str, Pattern[str]] = {
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "phone": re.compile(
            r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
        ),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    }

    @classmethod
    def detect_phi(cls, text: str) -> List[str]:
        """Scans text and returns a list of detected PHI category names."""
        if not text:
            return []

        detected: List[str] = []
        for category, pattern in cls.PATTERNS.items():
            if pattern.search(text):
                detected.append(category)

        return detected

    @classmethod
    def assert_phi_free(cls, text: str) -> None:
        """
        Defensively asserts that text contains no raw PHI.
        
        Raises:
            PHISafetyViolationError if any PHI patterns match.
        """
        violations = cls.detect_phi(text)
        if violations:
            msg = (
                f"Defensive PHI check failed. Unscrubbed PHI pattern(s) detected: "
                f"{', '.join(violations)}. Snippet must be scrubbed prior to ingestion."
            )
            logger.warning(msg)
            raise PHISafetyViolationError(msg, detected_types=violations)

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, List[str]]:
        """
        Redacts raw PHI patterns in text with placeholder tags.
        
        Returns:
            Tuple of (sanitized_text, list_of_redacted_categories)
        """
        if not text:
            return text, []

        redacted_categories: List[str] = []
        sanitized = text

        for category, pattern in cls.PATTERNS.items():
            if pattern.search(sanitized):
                redacted_categories.append(category)
                sanitized = pattern.sub(f"<{category}>", sanitized)

        if redacted_categories:
            logger.info("PHI auto-sanitized categories: %s", redacted_categories)

        return sanitized, redacted_categories
