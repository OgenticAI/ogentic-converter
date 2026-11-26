"""Format-preserving synthetic value generators, one per entity kind.

Each generator takes the original value and a :class:`Draw` and returns a synthetic
value of the same kind and shape. Uniqueness and collision checks are the caller's
job (see ``core._Assigner``); generators only produce candidates.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from importlib.resources import files

from .models import Policy
from .seeding import Draw

_DIGITS = frozenset("0123456789")


class NoSyntheticForm(Exception):
    """The value has no shape this generator recognises, so it is left unconverted."""


@dataclass(frozen=True)
class Corpus:
    version: str
    given_feminine: tuple[str, ...]
    given_masculine: tuple[str, ...]
    surnames: tuple[str, ...]
    streets: tuple[str, ...]
    towns: tuple[str, ...]

    @property
    def given_any(self) -> tuple[str, ...]:
        return self.given_feminine + self.given_masculine


@lru_cache(maxsize=1)
def load_corpus() -> Corpus:
    """The bundled, versioned synthetic corpus. Read from package data; never from the network."""
    raw = json.loads((files("ogentic_converter") / "data" / "corpus_v1.json").read_text("utf-8"))
    return Corpus(
        version=str(raw["version"]),
        given_feminine=tuple(raw["given_feminine"]),
        given_masculine=tuple(raw["given_masculine"]),
        surnames=tuple(raw["surnames"]),
        streets=tuple(raw["streets"]),
        towns=tuple(raw["towns"]),
    )


@dataclass(frozen=True)
class GenContext:
    policy: Policy
    category: str
    date_shift_days: int


def match_case(template: str, word: str) -> str:
    """Render ``word`` in the letter case of ``template`` (UPPER, lower or as-is)."""
    if template.isupper() and len(template) > 1:
        return word.upper()
    if template.islower():
        return word.lower()
    return word


def _fill_digits(template: str, digits: str) -> str:
    replacement = iter(digits)
    return "".join(next(replacement) if ch in _DIGITS else ch for ch in template)


def _digit_count(value: str) -> int:
    return sum(ch in _DIGITS for ch in value)


# ── Phone ────────────────────────────────────────────────────────────────────

_AREA_CODES = ("202", "206", "212", "303", "312", "404", "415", "503", "512", "617", "702", "808")


def phone(value: str, draw: Draw, ctx: GenContext) -> str:
    """NANP numbers become ``AAA-555-01XX`` (the range reserved for fiction), same punctuation."""
    digits = [ch for ch in value if ch in _DIGITS]
    if len(digits) == 10 or (len(digits) == 11 and digits[0] == "1"):
        trunk = "1" if len(digits) == 11 else ""
        return _fill_digits(value, f"{trunk}{draw.choice(_AREA_CODES)}55501{draw.digits(2)}")
    return _international_phone(value, draw)


def _international_phone(value: str, draw: Draw) -> str:
    # ponytail: non-NANP numbers keep the country code and get random digits; there is no
    # reserved fictional range per country, so a random number can in principle be real.
    if not _digit_count(value):
        raise NoSyntheticForm
    match = re.match(r"\s*\+(\d{1,3})", value)
    kept = len(match.group(1)) if match else 0
    count = _digit_count(value) - kept
    return _fill_digits(value, (match.group(1) if match else "") + draw.digits(count))


# ── SSN ──────────────────────────────────────────────────────────────────────


def ssn(value: str, draw: Draw, ctx: GenContext) -> str:
    """Area 900-999 is never issued as an SSN; group 01-49 is also outside every ITIN range."""
    count = _digit_count(value)
    if count == 9:
        return _fill_digits(value, f"{draw.between(900, 999)}{draw.between(1, 49):02d}{draw.between(1, 9999):04d}")
    if not count:
        raise NoSyntheticForm
    return _fill_digits(value, "9" + draw.digits(count - 1))


# ── Codes: case numbers, Bates numbers, insurance IDs ────────────────────────


def scramble_digits(value: str, draw: Draw, ctx: GenContext) -> str:
    """Replace every digit, keep letters and punctuation (``2:24-cv-01234`` -> ``7:91-cv-40417``)."""
    count = _digit_count(value)
    if not count:
        raise NoSyntheticForm
    return _fill_digits(value, draw.digits(count))


def scramble_alphanumeric(value: str, draw: Draw, ctx: GenContext) -> str:
    """Replace every letter and digit, keep case and punctuation (``ABC000123`` -> ``QFW482019``)."""
    if not any(ch.isalnum() for ch in value):
        raise NoSyntheticForm
    return "".join(_scramble_char(ch, draw) for ch in value)


def _scramble_char(ch: str, draw: Draw) -> str:
    if ch in _DIGITS:
        return str(draw.below(10))
    if ch.isalpha():
        letter = chr(ord("A") + draw.below(26))
        return letter if ch.isupper() else letter.lower()
    return ch


# ── Dates ────────────────────────────────────────────────────────────────────

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{4}|\d{1,2})([/.\-])(\d{1,2})\2(\d{4}|\d{2})(?!\d)")
_MONTH_DAY_YEAR = re.compile(r"(?<![A-Za-z])([A-Za-z]{3,9})(\.?)(\s+)(\d{1,2})(st|nd|rd|th)?(,?\s+)(\d{4})(?!\d)")
_DAY_MONTH_YEAR = re.compile(r"(?<!\d)(\d{1,2})(st|nd|rd|th)?(\s+)([A-Za-z]{3,9})(\.?)(,?\s+)(\d{4})(?!\d)")


def shifted_date(value: str, draw: Draw, ctx: GenContext) -> str:
    """Shift the date in ``value`` by the call's day offset, keeping its exact format."""
    for pattern, render in (
        (_NUMERIC_DATE, _shift_numeric),
        (_MONTH_DAY_YEAR, _shift_month_day_year),
        (_DAY_MONTH_YEAR, _shift_day_month_year),
    ):
        for match in pattern.finditer(value):
            try:
                replacement = render(match, ctx.date_shift_days)
            except (ValueError, OverflowError):
                continue
            return value[: match.start()] + replacement + value[match.end() :]
    raise NoSyntheticForm


def _full_year(text: str) -> int:
    # Fixed pivot (not today's date) so the output never depends on the wall clock.
    year = int(text)
    if len(text) <= 2:
        return year + (1900 if year >= 30 else 2000)
    return year


def _render_number(original: str, number: int) -> str:
    if len(original) == 4:
        return f"{number:04d}"
    if len(original) == 2:
        return f"{number % 100:02d}"
    return str(number)


def _shift_numeric(match: re.Match[str], shift: int) -> str:
    first, sep, middle, last = match.groups()
    if len(first) == 4:
        order = ("y", "m", "d")
    elif int(first) > 12:
        order = ("d", "m", "y")
    else:
        order = ("m", "d", "y")
    parts = dict(zip(order, (first, middle, last), strict=True))
    shifted = date(_full_year(parts["y"]), int(parts["m"]), int(parts["d"])) + timedelta(days=shift)
    values = {"y": shifted.year, "m": shifted.month, "d": shifted.day}
    return sep.join(_render_number(parts[key], values[key]) for key in order)


def _month_index(token: str) -> int:
    lowered = token.lower()
    for index, name in enumerate(_MONTHS):
        if name.lower() == lowered or (len(lowered) >= 3 and name.lower().startswith(lowered)):
            return index + 1
    raise ValueError("not a month")


def _render_month(original: str, month: int) -> str:
    name = _MONTHS[month - 1]
    is_full = original.lower() == _MONTHS[_month_index(original) - 1].lower()
    return match_case(original, name if is_full else name[:3])


def _ordinal(day: int, original_suffix: str | None) -> str:
    if not original_suffix:
        return ""
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return match_case(original_suffix, suffix)


def _shift_month_day_year(match: re.Match[str], shift: int) -> str:
    month, dot, space, day, suffix, sep, year = match.groups()
    shifted = date(int(year), _month_index(month), int(day)) + timedelta(days=shift)
    rendered_day = _render_number(day, shifted.day) + _ordinal(shifted.day, suffix)
    return f"{_render_month(month, shifted.month)}{dot}{space}{rendered_day}{sep}{shifted.year:04d}"


def _shift_day_month_year(match: re.Match[str], shift: int) -> str:
    day, suffix, space, month, dot, sep, year = match.groups()
    shifted = date(int(year), _month_index(month), int(day)) + timedelta(days=shift)
    rendered_day = _render_number(day, shifted.day) + _ordinal(shifted.day, suffix)
    return f"{rendered_day}{space}{_render_month(month, shifted.month)}{dot}{sep}{shifted.year:04d}"


# ── Email ────────────────────────────────────────────────────────────────────

_RESERVED_DOMAINS = ("example.com", "example.org", "example.net")  # RFC 2606


def email(value: str, draw: Draw, ctx: GenContext) -> str:
    """A synthetic local part at an RFC 2606 reserved domain, in the original local-part style."""
    local, at, _domain = value.rpartition("@")
    if not at or not local:
        raise NoSyntheticForm
    corpus = load_corpus()
    given = draw.choice(corpus.given_any).lower()
    surname = draw.choice(corpus.surnames).lower().replace("-", "")
    if "." in local:
        new_local = f"{given}.{surname}"
    elif "_" in local:
        new_local = f"{given}_{surname}"
    elif any(ch in _DIGITS for ch in local):
        new_local = f"{given[0]}{surname}{draw.between(1, 99)}"
    else:
        new_local = f"{given[0]}{surname}"
    return f"{new_local}@{draw.choice(_RESERVED_DOMAINS)}"


# ── Location ─────────────────────────────────────────────────────────────────

_STREET_SUFFIXES = frozenset(
    "st street ave avenue rd road blvd boulevard ln lane dr drive ct court way pl place ter terrace "
    "pkwy parkway hwy highway cir circle sq square".split()
)
_US_STATES = frozenset(
    "alabama alaska arizona arkansas california colorado connecticut delaware florida georgia hawaii idaho "
    "illinois indiana iowa kansas kentucky louisiana maine maryland massachusetts michigan minnesota "
    "mississippi missouri montana nebraska nevada ohio oklahoma oregon pennsylvania tennessee texas utah "
    "vermont virginia washington wisconsin wyoming".split()
) | {"new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota",
     "rhode island", "south carolina", "south dakota", "west virginia", "district of columbia"}  # fmt: skip
_STREET_ADDRESS = re.compile(r"(\d+)([A-Za-z]?)(\s+)(.+)")
_STATE_ZIP = re.compile(r"(?:[A-Z]{2}\s+)?\d{5}(?:-\d{4})?")


def location(value: str, draw: Draw, ctx: GenContext) -> str:
    """Comma-separated parts: street addresses, towns and ZIPs are replaced; US states are kept."""
    pieces = re.split(r"(\s*,\s*)", value)
    return "".join(piece if index % 2 else _location_part(piece, draw) for index, piece in enumerate(pieces))


def _location_part(part: str, draw: Draw) -> str:
    stripped = part.strip()
    if not stripped or re.fullmatch(r"[A-Z]{2}", stripped) or stripped.lower() in _US_STATES:
        return part
    lead = part[: len(part) - len(part.lstrip())]
    trail = part[len(part.rstrip()) :]
    return lead + _replace_location_core(stripped, draw) + trail


def _replace_location_core(text: str, draw: Draw) -> str:
    street = _STREET_ADDRESS.fullmatch(text)
    if street:
        return _street_address(street, draw)
    if _STATE_ZIP.fullmatch(text) or _digit_count(text):
        return _fill_digits(text, draw.digits(_digit_count(text)))
    return match_case(text, draw.choice(load_corpus().towns))


def _street_address(match: re.Match[str], draw: Draw) -> str:
    number, unit_letter, space, rest = match.groups()
    words = rest.split()
    suffix = words[-1] if len(words) > 1 and words[-1].lower().rstrip(".") in _STREET_SUFFIXES else "St"
    new_number = str(draw.between(1, 9)) + draw.digits(len(number) - 1)
    return f"{new_number}{unit_letter}{space}{match_case(rest, draw.choice(load_corpus().streets))} {suffix}"


# ── Organisations: institutions and law firms ────────────────────────────────

_ORG_TYPE_WORDS = frozenset(
    "llp llc l.l.c. pllc p.c. pc p.a. inc inc. corp corp. corporation co co. company ltd ltd. plc group partners "
    "associates hospital hospitals clinic clinics medical center centre health healthcare general memorial "
    "regional community children's university college school institute bank bancorp capital trust fund funds "
    "financial holdings foundation law firm attorneys advisors management securities insurance of the "
    "and & practice services".split()
)
_LAW_FIRM_MARKERS = frozenset({"llp", "pllc", "p.c.", "law", "attorneys", "associates", "p.a."})
_DEFAULT_ORG_SUFFIX = {
    Policy.LEGAL: "LLP",
    Policy.CLINICAL: "Medical Center",
    Policy.FINANCIAL: "Capital",
    Policy.GENERIC: "Group",
}


def organisation(value: str, draw: Draw, ctx: GenContext) -> str:
    """Replace the distinctive stem, keep type words (``Harrowgate General Hospital`` -> ``Fairhaven General …``)."""
    words = value.split()
    lead = _count_type_words(words)
    tail = _count_type_words(list(reversed(words[lead:])))
    stem = words[lead : len(words) - tail]
    kept_tail = words[len(words) - tail :]
    if not stem:  # every word is a type word ("General Hospital"): prefix a new stem
        lead, kept_tail = 0, words
    lowered = {word.lower().strip(",") for word in words}
    is_law_firm = ctx.category == "LAW_FIRM_NAME" or bool(lowered & _LAW_FIRM_MARKERS)
    new_stem = _org_stem(stem, draw, is_law_firm)
    if not lead and not kept_tail:
        suffix = "LLP" if is_law_firm else _DEFAULT_ORG_SUFFIX[ctx.policy]
        kept_tail = [suffix]
    result = " ".join([*words[:lead], new_stem, *kept_tail])
    return result.upper() if value.isupper() else result


def _count_type_words(words: list[str]) -> int:
    count = 0
    for word in words:
        if word.lower().strip(",") not in _ORG_TYPE_WORDS:
            break
        count += 1
    return count


def _org_stem(stem: list[str], draw: Draw, is_law_firm: bool) -> str:
    corpus = load_corpus()
    connectors = [word for word in stem if word in {"&", "and"}]
    if connectors:
        return f" {connectors[0]} ".join(draw.choice(corpus.surnames) for _ in range(2))
    if is_law_firm:
        return draw.choice(corpus.surnames)
    single_word_towns = [town for town in corpus.towns if " " not in town]
    return draw.choice(single_word_towns)


# ── Person names ─────────────────────────────────────────────────────────────

_HONORIFICS = frozenset(
    "mr mrs ms miss mx dr prof judge hon justice sir dame rev fr patient client counsel attorney "
    "officer det sgt capt lt nurse".split()
)
_MASCULINE_HONORIFICS = frozenset({"mr", "sir", "fr"})
_FEMININE_HONORIFICS = frozenset({"mrs", "ms", "miss", "dame"})
_NAME_SUFFIXES = frozenset("jr sr ii iii iv md m.d esq phd ph.d dds rn np cpa lcsw".split())
_PARTICLES = frozenset("de del della di da van von der den la le du dos das bin ibn al".split())
_EDGE_PUNCTUATION = ",;:()\"'"


@dataclass(frozen=True)
class NameToken:
    """One whitespace-delimited token of a name. ``role`` is keep/given/surname/initial/digits."""

    text: str
    role: str
    lead: str = ""
    trail: str = ""


def parse_name(value: str, single_token_role: str = "surname") -> list[NameToken]:
    """Split a name into tokens and assign roles: last name token is the surname."""
    tokens = [_classify_token(raw) for raw in re.split(r"(\s+)", value)]
    name_positions = [index for index, token in enumerate(tokens) if token.role == "name"]
    roles = _name_roles(tokens, name_positions, single_token_role)
    return [
        NameToken(token.text, roles.get(index, token.role), token.lead, token.trail)
        for index, token in enumerate(tokens)
    ]


def name_gender(tokens: list[NameToken]) -> str:
    for token in tokens:
        key = token.text.lower().rstrip(".")
        if key in _MASCULINE_HONORIFICS:
            return "masculine"
        if key in _FEMININE_HONORIFICS:
            return "feminine"
    return "any"


def _classify_token(raw: str) -> NameToken:
    core = raw.strip(_EDGE_PUNCTUATION)
    if not core or raw.isspace():
        return NameToken(raw, "keep")
    lead = raw[: raw.index(core)]
    trail = raw[raw.index(core) + len(core) :]
    key = core.lower().rstrip(".")
    if key in _HONORIFICS or key in _NAME_SUFFIXES or (key in _PARTICLES and core.islower()):
        role = "keep"
    elif re.fullmatch(r"[A-Za-z]\.?", core):
        role = "initial"
    elif any(ch.isalpha() for ch in core):
        role = "name"
    elif any(ch in _DIGITS for ch in core):
        role = "digits"
    else:
        role = "keep"
    return NameToken(core, role, lead, trail)


def _name_roles(tokens: list[NameToken], positions: list[int], single_token_role: str) -> dict[int, str]:
    if not positions:
        return {}
    if len(positions) == 1:
        has_honorific = any(token.text.lower().rstrip(".") in _HONORIFICS for token in tokens)
        return {positions[0]: "surname" if has_honorific else single_token_role}
    if tokens[positions[0]].trail.startswith(","):  # "Castellanos, Maria"
        return {index: "surname" if index == positions[0] else "given" for index in positions}
    return {index: "surname" if index == positions[-1] else "given" for index in positions}
