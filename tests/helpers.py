"""Test helpers. All sample data is synthetic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def entity(text: str, value: str, category: str, occurrence: int = 0) -> dict[str, Any]:
    """A Shield-shaped entity for the ``occurrence``-th appearance of ``value`` (code-point offsets)."""
    start = -1
    for _ in range(occurrence + 1):
        start = text.index(value, start + 1)
    return {
        "text": value,
        "category": category,
        "category_group": "PII",
        "confidence": 1.0,
        "start": start,
        "end": start + len(value),
    }


def entities(text: str, *pairs: tuple[str, str]) -> list[dict[str, Any]]:
    return [entity(text, value, category) for value, category in pairs]
