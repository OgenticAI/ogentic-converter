"""Pydantic v2 models: Shield entity input, reversal mapping, conversion result."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Policy(StrEnum):
    """Substitution policy. Picks the default style for organisation names and salts the seed."""

    LEGAL = "legal"
    CLINICAL = "clinical"
    FINANCIAL = "financial"
    GENERIC = "generic"


class ShieldEntity(BaseModel):
    """One entity from ``ogentic-shield analyze --output json``.

    ``start``/``end`` are Unicode code-point offsets into the analysed text (Python
    ``str`` indices), not byte or UTF-16 offsets. Extra Shield fields are ignored.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    category: str
    category_group: str = ""
    confidence: float = 1.0
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str | None = Field(default=None, repr=False)


class MappingEntry(BaseModel):
    """One synthetic value and the original it replaced."""

    model_config = ConfigDict(frozen=True)

    synthetic: str = Field(min_length=1)
    original: str
    category: str


class ReversalMapping(BaseModel):
    """Synthetic -> original table for one conversion call.

    It contains the original identifiers, so treat it as sensitive: keep it in
    memory, or store it separately from the replica with restricted permissions.
    """

    version: int = 1
    entries: list[MappingEntry] = Field(default_factory=list, repr=False)


class ConversionResult(BaseModel):
    """Output of :func:`ogentic_converter.convert`.

    ``mapping`` is excluded from ``repr()`` so printing or logging a result never
    shows the original values next to the replica.
    """

    replica: str
    mapping: ReversalMapping = Field(repr=False)
    converted_count: int
    unconverted_categories: list[str]
    policy: Policy
    corpus_version: str
