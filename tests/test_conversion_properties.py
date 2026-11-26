"""Properties 2-5 and 7: consistency, collision-freedom, determinism, no leakage, span merging."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys

import pytest

from ogentic_converter import ConversionError, convert, load_shield_entities
from ogentic_converter.generators import load_corpus

from .helpers import FIXTURES, entities, entity

SURNAMES = ["Castellanos", "Okonjo", "Vandersloot", "Pettigrew", "Marchbanks", "Quillfeather", "Brannigan", "Oduya"]


# ── 2. Within-call consistency ───────────────────────────────────────────────


def test_same_original_maps_to_same_synthetic_everywhere() -> None:
    text = "Maria Okonjo met Ana Ruiz. Later Maria Okonjo left."
    result = convert(
        text,
        [entity(text, "Maria Okonjo", "PERSON", 0), entity(text, "Ana Ruiz", "PERSON"),
         entity(text, "Maria Okonjo", "PERSON", 1)],
        seed=11,
    )  # fmt: skip
    synthetic = result.replica.split(" met ")[0]
    assert result.replica.count(synthetic) == 2


def test_unflagged_repeats_and_bare_surnames_are_replaced_too() -> None:
    text = "R. Castellanos signed. Ms. Castellanos and R. Castellanos agreed."
    result = convert(text, [entity(text, "R. Castellanos", "PERSON")], seed=2)
    assert "Castellanos" not in result.replica
    synthetic_surname = result.replica.split(" ")[1]
    assert result.replica.count(synthetic_surname) == 3


def test_lone_given_name_seen_elsewhere_stays_a_given_name() -> None:
    text = "Maria Okonjo arrived. Maria said hello."
    result = convert(text, entities(text, ("Maria Okonjo", "PERSON")) + [entity(text, "Maria", "PERSON", 1)], seed=4)
    first_given = result.replica.split(" ")[0]
    assert result.replica.count(first_given) == 2 and first_given in load_corpus().given_any


# ── 3. Collision-free ────────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", range(25))
def test_distinct_originals_get_distinct_synthetics(seed: int) -> None:
    text = " ".join(f"Mr. {name} spoke." for name in SURNAMES)
    result = convert(text, [entity(text, name, "PERSON") for name in SURNAMES], seed=seed)
    synthetics = [e.synthetic for e in result.mapping.entries]
    assert len(set(synthetics)) == len(synthetics) == len(SURNAMES)


@pytest.mark.parametrize("seed", range(40))
def test_synthetic_never_equals_a_value_present_in_the_input(seed: int) -> None:
    corpus = load_corpus()
    # The input already mentions corpus surnames; none of them may be picked as a replacement.
    present = list(corpus.surnames[:120])
    text = "Panel: " + ", ".join(present) + ". Plaintiff Castellanos."
    result = convert(text, [entity(text, "Castellanos", "PERSON")], seed=seed)
    synthetic = result.mapping.entries[0].synthetic
    assert synthetic not in present and synthetic in corpus.surnames


def test_forced_collision_is_resolved_deterministically() -> None:
    # Many distinct SSNs share one call: every one must get its own value, the same way every run.
    ssns = [f"{100 + i}-{10 + i}-{1000 + i}" for i in range(60)]
    text = " ".join(f"SSN {s}." for s in ssns)
    first = convert(text, [entity(text, s, "SSN") for s in ssns], seed=99)
    second = convert(text, [entity(text, s, "SSN") for s in reversed(ssns)], seed=99)
    assert len({e.synthetic for e in first.mapping.entries}) == 60
    assert first == second


# ── 4. Deterministic ─────────────────────────────────────────────────────────


def _fixture() -> tuple[str, list[dict[str, object]]]:
    text = (FIXTURES / "shield_legal.txt").read_text(encoding="utf-8")
    return text, json.loads((FIXTURES / "shield_legal.json").read_text(encoding="utf-8"))["entities"]


def test_same_inputs_and_seed_give_identical_output() -> None:
    text, ents = _fixture()
    shuffled = list(ents)
    random.Random(0).shuffle(shuffled)
    assert convert(text, ents, "legal", seed=42) == convert(text, shuffled, "legal", seed=42)


def test_seed_and_policy_change_the_output() -> None:
    text, ents = _fixture()
    base = convert(text, ents, "legal", seed=42).replica
    assert convert(text, ents, "legal", seed=43).replica != base
    assert convert(text, ents, "clinical", seed=42).replica != base


def test_no_seed_draws_a_fresh_seed_per_call() -> None:
    text, ents = _fixture()
    assert len({convert(text, ents).replica for _ in range(5)}) > 1


def test_golden_vector_is_stable_across_python_versions() -> None:
    """Pinned output: draws use HMAC-SHA256, not random/hash(), so this must never drift."""
    text, ents = _fixture()
    result = convert(text, ents, "legal", seed=42)
    assert result.replica == (FIXTURES / "golden_legal_seed42.txt").read_text(encoding="utf-8")


def test_reproducible_under_a_different_hash_seed() -> None:
    script = (
        "import json,sys; from ogentic_converter import convert;"
        "t=open(sys.argv[1],encoding='utf-8').read(); e=json.load(open(sys.argv[2]))['entities'];"
        "r=convert(t,e,'legal',seed=42); sys.stdout.write(r.model_dump_json())"
    )
    outputs = set()
    for hash_seed in ("0", "1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        args = [sys.executable, "-c", script, str(FIXTURES / "shield_legal.txt"), str(FIXTURES / "shield_legal.json")]
        outputs.add(subprocess.run(args, env=env, capture_output=True, check=True, text=True).stdout)
    assert len(outputs) == 1


def test_seeded_loop_of_random_inputs_reproduces() -> None:
    rng = random.Random(2026)
    corpus = load_corpus()
    for _ in range(200):
        names = rng.sample(SURNAMES, 3)
        ssn = f"{rng.randint(100, 899)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
        text = f"{names[0]} told {names[1]} and {names[2]} that SSN {ssn} is wrong."
        ents = [entity(text, n, "PERSON") for n in names] + [entity(text, ssn, "SSN")]
        seed = rng.randint(0, 2**32)
        assert convert(text, ents, seed=seed) == convert(text, list(reversed(ents)), seed=seed)
    assert corpus.version == "1"


# ── 5. No leakage ────────────────────────────────────────────────────────────

LEAK_CASES = [
    ("José Müller 😊 SSN 412-71-3359", [("José Müller", "PERSON"), ("412-71-3359", "SSN")]),
    ("👩🏽‍⚖️ Zoë Ångström (zoe.angstrom@acme-legal.com) 📞 (415) 555-2671",
     [("Zoë Ångström", "PERSON"), ("zoe.angstrom@acme-legal.com", "EMAIL_ADDRESS"),
      ("(415) 555-2671", "PHONE_NUMBER")]),
    ("Café note — Renée O'Brien-Núñez, DOB 03/14/1978, SSN 523-45-6789 ✅",
     [("Renée O'Brien-Núñez", "PERSON"), ("03/14/1978", "DATE_OF_BIRTH"), ("523-45-6789", "SSN")]),
]  # fmt: skip


@pytest.mark.parametrize(("text", "pairs"), LEAK_CASES)
@pytest.mark.parametrize("seed", range(10))
def test_no_original_value_survives(text: str, pairs: list[tuple[str, str]], seed: int) -> None:
    result = convert(text, entities(text, *pairs), seed=seed)
    for value, _category in pairs:
        assert value not in result.replica
    for emoji in ("😊", "📞", "✅", "👩🏽‍⚖️"):
        assert text.count(emoji) == result.replica.count(emoji)


def test_real_shield_fixture_has_no_leak() -> None:
    text, ents = _fixture()
    result = convert(text, load_shield_entities({"entities": ents}), "legal", seed=7)
    for value in ("Castellanos", "Okafor", "Maria", "412-71-3359", "523-45-6789", "José", "Müller",
                  "acme-legal.com", "03/14/1978", "01234"):  # fmt: skip
        assert value not in result.replica
    assert result.replica.startswith("PRIVILEGED AND CONFIDENTIAL. Attorney-client communication.")
    assert "deposition" in result.replica and result.unconverted_categories == []


def test_utf16_offsets_are_rejected_not_misapplied() -> None:
    text = "😊 R. Castellanos signed."
    bad = {"text": "R. Castellanos", "category": "PERSON", "start": 3, "end": 17}  # UTF-16 units, not code points
    with pytest.raises(ConversionError, match="code points"):
        convert(text, [bad], seed=1)


# ── 7. Overlapping Shield spans ──────────────────────────────────────────────


def test_overlapping_spans_are_merged_into_their_union() -> None:
    text = "Client Maria Castellanos-Okonjo called."
    first = {"category": "PERSON", "start": 7, "end": 24}  # "Maria Castellanos"
    second = {"category": "PERSON", "start": 13, "end": 31}  # "Castellanos-Okonjo"
    result = convert(text, [first, second], seed=3)
    assert result.converted_count == 1
    for fragment in ("Maria", "Castellanos", "Okonjo"):
        assert fragment not in result.replica
    assert result.replica.startswith("Client ") and result.replica.endswith(" called.")


def test_overlap_with_unhandled_category_still_replaces_the_union() -> None:
    text = "Account R. Castellanos 4111111111111111 end."
    person = entity(text, "R. Castellanos", "PERSON")
    card = {"category": "CREDIT_CARD", "start": person["start"] + 3, "end": text.index(" end")}
    result = convert(text, [person, card], seed=3)
    assert "4111" not in result.replica and "Castellanos" not in result.replica


def test_marker_containing_an_identifier_does_not_shield_it() -> None:
    text = "Attorney-client communication with R. Castellanos follows."
    marker = {"category": "COUNSEL_COMMUNICATION", "start": 0, "end": text.index(" follows")}
    result = convert(text, [marker, entity(text, "R. Castellanos", "PERSON")], seed=3)
    assert result.replica.startswith("Attorney-client communication with ") and "Castellanos" not in result.replica


# ── Input validation (failure paths) ─────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        {"category": "PERSON", "start": 5, "end": 99},
        {"category": "PERSON", "start": 4, "end": 4},
        {"category": "PERSON", "start": 0, "end": 3, "text": "Bob"},
    ],
)
def test_bad_offsets_raise(bad: dict[str, object]) -> None:
    with pytest.raises(ConversionError):
        convert("Hi Ann.", [bad], seed=1)


def test_errors_never_echo_content() -> None:
    with pytest.raises(ConversionError) as caught:
        load_shield_entities([{"category": "PERSON", "start": "SECRET-412-71-3359", "end": 2}])
    assert "SECRET" not in str(caught.value)


@pytest.mark.parametrize("source", ["not json", "[1, 2]", '{"entities": "x"}', b"42"])
def test_bad_entity_payloads_raise(source: str | bytes) -> None:
    with pytest.raises(ConversionError):
        load_shield_entities(source)


def test_unknown_policy_raises() -> None:
    with pytest.raises(ConversionError, match="unknown policy"):
        convert("Hi.", [], policy="medical")


def test_empty_input_round_trips() -> None:
    result = convert("", [], seed=1)
    assert result.replica == "" and result.mapping.entries == [] and result.converted_count == 0


def test_digits_inside_a_merged_name_union_are_replaced() -> None:
    text = "Ref R. Castellanos 4471 filed."
    first = entity(text, "R. Castellanos", "PERSON")
    second = entity(text, "Castellanos 4471", "PERSON")
    result = convert(text, [first, second], seed=3)
    assert "4471" not in result.replica and "Castellanos" not in result.replica
    assert result.replica.endswith(" filed.")
