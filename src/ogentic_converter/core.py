"""Template-mode conversion: ``convert()`` builds a synthetic replica, ``restore()`` maps a reply back.

Pipeline for one call:

1. Validate Shield's entities against the text (code-point offsets, matching ``text``).
2. Drop classification signals (privilege markers etc.); merge overlapping identifier
   spans into their union so no sensitive character is ever left outside a span.
3. Assign one synthetic value per distinct original, in sorted order, probing until
   the candidate is unused and absent from the input (collision-free, order-stable).
4. Replace every occurrence of each converted value, including repeats Shield did not
   flag, and surnames seen inside flagged names.
5. Refuse to return a replica in which any converted original still appears.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .errors import ConversionError
from .generators import (
    GenContext,
    NameToken,
    NoSyntheticForm,
    email,
    load_corpus,
    location,
    match_case,
    name_gender,
    organisation,
    parse_name,
    phone,
    scramble_alphanumeric,
    scramble_digits,
    shifted_date,
    ssn,
)
from .models import ConversionResult, MappingEntry, Policy, ReversalMapping, ShieldEntity
from .seeding import Draw, derive_key, random_seed

NAME_CATEGORIES = frozenset({"PERSON", "PATIENT_NAME", "PROVIDER_NAME", "EXECUTIVE_NAME"})

#: Shield category -> generator kind. Anything not listed (and not a signal) is left unchanged
#: and reported in ``ConversionResult.unconverted_categories``.
KIND_BY_CATEGORY: dict[str, str] = {
    **dict.fromkeys(NAME_CATEGORIES, "name"),
    "EMAIL_ADDRESS": "email",
    "PHONE_NUMBER": "phone",
    "SSN": "ssn",
    "US_SSN": "ssn",
    "DATE_OF_BIRTH": "date",
    "CASE_NUMBER": "case",
    "BATES_NUMBER": "code",
    "INSURANCE_ID": "code",
    "LOCATION": "location",
    "INSTITUTION_NAME": "organisation",
    "LAW_FIRM_NAME": "organisation",
}

#: Categories that classify the text rather than identify anyone. Never replaced, never reported.
SIGNAL_CATEGORIES = frozenset(
    {
        "PRIVILEGE_MARKER",
        "COURT_FILING",
        "COUNSEL_COMMUNICATION",
        "WORK_PRODUCT",
        "LITIGATION_MARKER",
        "DISTRIBUTION_RESTRICTION",
        "MNPI_MARKER",
        "INSIDER_MARKER",
        "MA_ACTIVITY",
        "PSYCHOTHERAPY_NOTE_MARKER",
        "SESSION_MARKER",
        "MINOR_CLIENT_MARKER",
        "CLINICAL_RISK_FLAG",
        "TRAUMA_INDICATOR",
    }
)

_GENERATORS: dict[str, Callable[[str, Draw, GenContext], str]] = {
    "email": email,
    "phone": phone,
    "ssn": ssn,
    "date": shifted_date,
    "case": scramble_digits,
    "code": scramble_alphanumeric,
    "location": location,
    "organisation": organisation,
}

#: Kinds whose spans may start with a label ("SSN 412-…", "DOB: 03/14/…") that is kept as-is.
_LABELLED_KINDS = frozenset({"email", "phone", "ssn", "date", "case", "code"})
_LABEL = re.compile(  # used with .match(text, pos): anchored at pos, so no "^"
    r"(?:(?:ssn|ss#|social security(?:\s+(?:no\.?|number))?|dob|d\.o\.b\.?|date of birth|born|tel\.?|phone|"
    r"ph\.?|mobile|cell|fax|e-?mail|case\s+(?:no\.?|number)|bates(?:\s+(?:no\.?|number))?|member\s+id|"
    r"policy\s+(?:no\.?|number)|id|no\.)(?:\s*[:#]\s*|\s+))+",
    re.IGNORECASE,
)
_MAX_PROBES = 64
_LETTERS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


@dataclass(frozen=True)
class _Span:
    start: int  # start of the replaceable value (after any label)
    end: int
    category: str
    kind: str | None


def load_shield_entities(source: str | bytes | Mapping[str, Any] | Sequence[Any]) -> list[ShieldEntity]:
    """Parse ``ogentic-shield analyze --output json`` output (or a bare entity list)."""
    data: Any = source
    if isinstance(data, str | bytes):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ConversionError(f"entities are not valid JSON (line {exc.lineno}, column {exc.colno})") from None
    if isinstance(data, Mapping):
        data = data.get("entities")
    if not isinstance(data, Sequence) or isinstance(data, str | bytes):
        raise ConversionError("expected Shield analyze JSON (an object with 'entities') or a list of entities")
    return [_parse_entity(index, item) for index, item in enumerate(data)]


def _parse_entity(index: int, item: Any) -> ShieldEntity:
    if isinstance(item, ShieldEntity):
        return item
    try:
        return ShieldEntity.model_validate(item)
    except ValidationError as exc:  # the default message echoes input values: never show it
        fields = ", ".join(".".join(map(str, error["loc"])) or "entity" for error in exc.errors())
        raise ConversionError(f"entity {index} is invalid ({fields})") from None


def convert(
    text: str,
    entities: Sequence[ShieldEntity | Mapping[str, Any]],
    policy: Policy | str = Policy.GENERIC,
    seed: int | None = None,
) -> ConversionResult:
    """Replace every identifier entity in ``text`` with a realistic synthetic value.

    Same text + entities + policy + seed gives an identical result. With ``seed=None``
    a fresh random seed is used, so repeated calls give different replicas.
    """
    resolved = _resolve_policy(policy)
    parsed = load_shield_entities(list(entities))
    _check_offsets(text, parsed)
    key = derive_key(random_seed() if seed is None else int(seed), resolved.value)
    return _Conversion(text, key, resolved, _identifier_spans(parsed)).run()


def restore(text: str, mapping: ReversalMapping) -> str:
    """Put the original values back wherever a synthetic value appears in ``text``.

    Longest synthetic first, whole words only, one pass: overlapping values cannot
    corrupt each other and unrelated text is untouched.
    """
    originals = {entry.synthetic: entry.original for entry in mapping.entries}
    if not originals:
        return text
    pattern = _alternation(originals)
    return pattern.sub(lambda match: originals[match.group(0)], text)


def _resolve_policy(policy: Policy | str) -> Policy:
    try:
        return Policy(policy)
    except ValueError:
        choices = ", ".join(member.value for member in Policy)
        raise ConversionError(f"unknown policy; expected one of: {choices}") from None


def _check_offsets(text: str, entities: list[ShieldEntity]) -> None:
    for index, entity in enumerate(entities):
        if not 0 <= entity.start < entity.end <= len(text):
            raise ConversionError(f"entity {index} ({entity.category}) has offsets outside the text")
        if entity.text is not None and text[entity.start : entity.end] != entity.text:
            raise ConversionError(
                f"entity {index} ({entity.category}) offsets do not match its text; "
                "Shield offsets must be Unicode code points into this exact input"
            )


def _identifier_spans(entities: list[ShieldEntity]) -> list[_Span]:
    """Merge overlapping identifier entities into their union; signals are dropped."""
    identifiers = sorted(
        (entity for entity in entities if entity.category not in SIGNAL_CATEGORIES),
        key=lambda entity: (entity.start, entity.end, entity.category),
    )
    groups: list[list[ShieldEntity]] = []
    for entity in identifiers:
        if groups and entity.start < max(member.end for member in groups[-1]):
            groups[-1].append(entity)
        else:
            groups.append([entity])
    return [_span_for(group) for group in groups]


def _span_for(group: list[ShieldEntity]) -> _Span:
    start, end = min(e.start for e in group), max(e.end for e in group)
    lead = max(
        group,
        key=lambda e: (e.category in KIND_BY_CATEGORY, e.end - e.start, e.confidence, e.category),
    )
    kind = KIND_BY_CATEGORY.get(lead.category)
    if kind is not None and len({KIND_BY_CATEGORY.get(e.category, e.category) for e in group}) > 1:
        kind = "code"  # a union of different kinds has no single shape: scramble every letter and digit
    return _Span(start, end, lead.category, kind)


def _bounded(value: str) -> str:
    """Regex for ``value`` as a whole word: no word character may touch either end."""
    head = r"(?<!\w)" if re.match(r"\w", value[0]) else ""
    tail = r"(?!\w)" if re.match(r"\w", value[-1]) else ""
    return f"(?:{head}{re.escape(value)}{tail})"


def _alternation(values: Mapping[str, Any] | set[str], flags: int = 0) -> re.Pattern[str]:
    ordered = sorted(values, key=lambda value: (-len(value), value))
    return re.compile("|".join(_bounded(value) for value in ordered), flags)


class _Conversion:
    """State for one ``convert()`` call. Never outlives it."""

    def __init__(self, text: str, key: bytes, policy: Policy, spans: list[_Span]) -> None:
        self._text = text
        self._key = key
        self._policy = policy
        self._spans = [self._trim_label(span) for span in spans]
        self._names = self._parse_names()
        self._originals = self._original_values()
        self._original_pattern = _alternation(self._originals, re.IGNORECASE) if self._originals else None
        self._used: set[str] = set()
        self._token_synthetics: dict[tuple[str, str], str] = {}
        self._name_parts: dict[tuple[str, str], str] = {}  # (original surface, role) -> synthetic surface
        self._date_shift = self._base_date_shift()

    # ── set-up ───────────────────────────────────────────────────────────────

    def _trim_label(self, span: _Span) -> _Span:
        if span.kind not in _LABELLED_KINDS:
            return span
        label = _LABEL.match(self._text, span.start, span.end)
        if not label or label.end() >= span.end:
            return span
        return _Span(label.end(), span.end, span.category, span.kind)

    def _value(self, span: _Span) -> str:
        return self._text[span.start : span.end]

    def _parse_names(self) -> dict[str, list[NameToken]]:
        values = sorted({self._value(span) for span in self._spans if span.kind == "name"})
        parsed = {value: parse_name(value) for value in values}
        full_names = [tokens for tokens in parsed.values() if sum(t.role in {"given", "surname"} for t in tokens) > 1]
        surnames = {t.text.casefold() for tokens in full_names for t in tokens if t.role == "surname"}
        givens = {t.text.casefold() for tokens in full_names for t in tokens if t.role == "given"} - surnames
        for value, tokens in parsed.items():  # a lone "Maria" seen elsewhere as a given name stays a given name
            named = [t for t in tokens if t.role in {"given", "surname"}]
            if len(named) == 1 and named[0].role == "surname" and named[0].text.casefold() in givens:
                parsed[value] = parse_name(value, single_token_role="given")
        return parsed

    def _original_values(self) -> set[str]:
        values = {self._value(span) for span in self._spans if span.kind is not None}
        parts = {t.text for tokens in self._names.values() for t in tokens if t.role in {"given", "surname"}}
        return values | parts

    def _base_date_shift(self) -> int:
        draw = Draw(self._key, "date-shift")
        return draw.between(30, 365) * draw.choice((-1, 1))

    # ── assignment ───────────────────────────────────────────────────────────

    def run(self) -> ConversionResult:
        synthetics, unconverted = self._assign_all()
        replacements = self._replacements(synthetics)
        replica = self._apply(replacements)
        self._assert_no_leak(replica, synthetics)
        return ConversionResult(
            replica=replica,
            mapping=self._mapping(synthetics),
            converted_count=len(replacements),
            unconverted_categories=sorted(unconverted),
            policy=self._policy,
            corpus_version=load_corpus().version,
        )

    def _assign_all(self) -> tuple[dict[str, tuple[str, str]], set[str]]:
        """original value -> (synthetic, category), plus the categories left unconverted."""
        first_span: dict[str, _Span] = {}
        unconverted: set[str] = set()
        for span in self._spans:
            if span.kind is None:
                unconverted.add(span.category)
            else:
                first_span.setdefault(self._value(span), span)
        synthetics: dict[str, tuple[str, str]] = {}
        for value in sorted(first_span):  # sorted: the result never depends on entity order
            span = first_span[value]
            try:
                synthetics[value] = (self._synthetic_for(value, span), span.category)
            except NoSyntheticForm:
                unconverted.add(span.category)
        return synthetics, unconverted

    def _synthetic_for(self, value: str, span: _Span) -> str:
        if span.kind == "name":
            return self._name_synthetic(value)
        generate = _GENERATORS[str(span.kind)]

        def candidate(attempt: int) -> str:
            ctx = GenContext(self._policy, span.category, self._date_shift + attempt)
            return generate(value, Draw(self._key, f"{span.kind}|{value}|{attempt}"), ctx)

        return self._probe(value, candidate)

    def _probe(self, original: str, candidate: Callable[[int], str]) -> str:
        """First candidate that is unused and absent from the input. Probe order: attempt 0, 1, 2, ..."""
        for attempt in range(_MAX_PROBES):
            synthetic = candidate(attempt)
            if self._acceptable(synthetic, original):
                self._used.add(synthetic)
                return synthetic
        raise ConversionError("could not find a collision-free synthetic value; the input is too large for the corpus")

    def _acceptable(self, synthetic: str, original: str) -> bool:
        if not synthetic or synthetic in self._used or synthetic.casefold() == original.casefold():
            return False
        if re.search(_bounded(synthetic), self._text, re.IGNORECASE):
            return False
        return not (self._original_pattern and self._original_pattern.search(synthetic))

    # ── names ────────────────────────────────────────────────────────────────

    def _name_synthetic(self, value: str) -> str:
        tokens = self._names[value]
        if not any(t.role in {"given", "surname", "initial"} for t in tokens):
            raise NoSyntheticForm
        gender = name_gender(tokens)
        synthetic = "".join(t.lead + self._name_token(t, gender) + t.trail for t in tokens)
        self._used.add(synthetic)
        return synthetic

    def _name_token(self, token: NameToken, gender: str) -> str:
        if token.role == "keep":
            return token.text
        if token.role == "digits":
            ctx = GenContext(self._policy, "PERSON", self._date_shift)
            return scramble_digits(token.text, Draw(self._key, f"name|digits|{token.text}"), ctx)
        if token.role == "initial":
            letter = self._token_synthetic("initial", token.text[0].upper(), _LETTERS)
            return match_case(token.text[0], letter) + token.text[1:]
        corpus = load_corpus()
        pool = corpus.surnames if token.role == "surname" else _given_pool(gender)
        synthetic = match_case(token.text, self._token_synthetic(token.role, token.text, pool))
        self._name_parts[(token.text, token.role)] = synthetic
        return synthetic

    def _token_synthetic(self, role: str, original: str, pool: Sequence[str]) -> str:
        key = (role, original.casefold())
        if key not in self._token_synthetics:
            label = f"name|{role}|{original.casefold()}"
            self._token_synthetics[key] = self._probe(
                original, lambda attempt: Draw(self._key, f"{label}|{attempt}").choice(pool)
            )
        return self._token_synthetics[key]

    # ── replica, mapping, leak check ─────────────────────────────────────────

    def _replacements(self, synthetics: dict[str, tuple[str, str]]) -> dict[tuple[int, int], str]:
        replacements: dict[tuple[int, int], str] = {}
        for span in self._spans:
            value = self._value(span)
            if span.kind is not None and value in synthetics:
                replacements[(span.start, span.end)] = synthetics[value][0]
        self._propagate(replacements, self._propagation_targets(synthetics))
        return replacements

    def _propagation_targets(self, synthetics: dict[str, tuple[str, str]]) -> dict[str, str]:
        targets = {value: synthetic for value, (synthetic, _category) in synthetics.items()}
        for (original, role), synthetic in self._name_parts.items():
            if role == "surname":
                targets.setdefault(original, synthetic)
        return targets

    def _propagate(self, replacements: dict[tuple[int, int], str], targets: dict[str, str]) -> None:
        """Replace repeats Shield did not flag. Skips anything overlapping an already-replaced span."""
        if not targets:
            return
        taken = list(replacements)
        for match in _alternation(targets).finditer(self._text):
            if not any(match.start() < end and start < match.end() for start, end in taken):
                replacements[(match.start(), match.end())] = targets[match.group(0)]

    def _apply(self, replacements: dict[tuple[int, int], str]) -> str:
        pieces: list[str] = []
        cursor = 0
        for (start, end), synthetic in sorted(replacements.items()):
            pieces.extend((self._text[cursor:start], synthetic))
            cursor = end
        pieces.append(self._text[cursor:])
        return "".join(pieces)

    def _mapping(self, synthetics: dict[str, tuple[str, str]]) -> ReversalMapping:
        entries: dict[str, MappingEntry] = {}
        pairs = [(synthetic, original, category) for original, (synthetic, category) in synthetics.items()]
        pairs += [(synthetic, original, "PERSON") for (original, _role), synthetic in self._name_parts.items()]
        for synthetic, original, category in pairs:
            existing = entries.get(synthetic)
            if existing is not None and existing.original != original:
                raise ConversionError("internal error: one synthetic value assigned to two originals")
            entries.setdefault(synthetic, MappingEntry(synthetic=synthetic, original=original, category=category))
        return ReversalMapping(entries=[entries[key] for key in sorted(entries)])

    def _assert_no_leak(self, replica: str, synthetics: dict[str, tuple[str, str]]) -> None:
        protected = set(synthetics) | {original for original, role in self._name_parts if role == "surname"}
        if protected and _alternation(protected).search(replica):
            raise ConversionError("an original value survived conversion; refusing to return the replica")


def _given_pool(gender: str) -> tuple[str, ...]:
    corpus = load_corpus()
    if gender == "masculine":
        return corpus.given_masculine
    if gender == "feminine":
        return corpus.given_feminine
    return corpus.given_any
