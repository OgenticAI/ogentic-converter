"""Property 6: restore() maps synthetic values in a model reply back to the originals."""

from __future__ import annotations

from ogentic_converter import MappingEntry, ReversalMapping, convert, restore

from .helpers import entities


def mapping(*pairs: tuple[str, str]) -> ReversalMapping:
    return ReversalMapping(entries=[MappingEntry(synthetic=s, original=o, category="PERSON") for s, o in pairs])


def test_round_trip_through_a_model_style_reply() -> None:
    text = "R. Castellanos (SSN 412-71-3359) emailed jane.doe@acme-legal.com."
    pairs = [("R. Castellanos", "PERSON"), ("412-71-3359", "SSN"), ("jane.doe@acme-legal.com", "EMAIL_ADDRESS")]
    result = convert(text, entities(text, *pairs), seed=8)
    by_original = {e.original: e.synthetic for e in result.mapping.entries}
    reply = (
        f"Summary: {by_original['R. Castellanos']} wrote from {by_original['jane.doe@acme-legal.com']}; "
        f"{by_original['Castellanos']} should confirm SSN {by_original['412-71-3359']}."
    )
    assert restore(reply, result.mapping) == (
        "Summary: R. Castellanos wrote from jane.doe@acme-legal.com; Castellanos should confirm SSN 412-71-3359."
    )


def test_values_the_model_omitted_are_simply_absent() -> None:
    table = mapping(("Ana Hartwell", "Maria Okafor"), ("Leo Pryce", "José Müller"))
    assert restore("Only Ana Hartwell replied.", table) == "Only Maria Okafor replied."


def test_unrelated_text_is_untouched_byte_for_byte() -> None:
    reply = "Nothing to see 😊 — ünïcödé\r\n  spacing\tkept "
    assert restore(reply, mapping(("Ana Hartwell", "Maria Okafor"))) == reply


def test_longest_match_first_for_overlapping_values() -> None:
    table = mapping(("Hartwell", "Castellanos"), ("S. Hartwell", "R. Castellanos"), ("Hartwell & Pryce LLP", "X LLP"))
    reply = "S. Hartwell of Hartwell & Pryce LLP; Hartwell agreed."
    assert restore(reply, table) == "R. Castellanos of X LLP; Castellanos agreed."


def test_whole_words_only() -> None:
    table = mapping(("Lee", "Okafor"))
    assert restore("Leeds and Lee and Fleet", table) == "Leeds and Okafor and Fleet"


def test_originals_are_not_re_substituted() -> None:
    table = mapping(("Ana", "Bea"), ("Bea", "Cy"))  # one pass: Ana -> Bea must not become Cy
    assert restore("Ana met Bea", table) == "Bea met Cy"


def test_empty_mapping_returns_text_unchanged() -> None:
    assert restore("Hello", ReversalMapping()) == "Hello"


def test_token_used_as_given_and_surname_restores_both_ways() -> None:
    text = "Jordan Okonjo met Ann Jordan."
    result = convert(text, entities(text, ("Jordan Okonjo", "PERSON"), ("Ann Jordan", "PERSON")), seed=6)
    parts = {e.synthetic: e.original for e in result.mapping.entries if " " not in e.synthetic}
    assert sorted(o for o in parts.values() if o == "Jordan") == ["Jordan", "Jordan"]
    assert restore(" / ".join(parts), result.mapping) == " / ".join(parts.values())
