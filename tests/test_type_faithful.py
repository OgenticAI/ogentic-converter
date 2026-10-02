"""Property 1: every identifier is replaced by a realistic value of the same kind and shape."""

from __future__ import annotations

import re
from datetime import date

import pytest

from ogentic_converter import convert
from ogentic_converter.generators import load_corpus

from .helpers import entities, entity

CORPUS = load_corpus()


def one(text: str, value: str, category: str, policy: str = "generic", seed: int = 1) -> str:
    """Convert a text holding one entity and return the synthetic value that replaced it."""
    result = convert(text, [entity(text, value, category)], policy=policy, seed=seed)
    prefix, suffix = text.split(value, 1)
    assert result.replica.startswith(prefix) and result.replica.endswith(suffix)
    return result.replica[len(prefix) : len(result.replica) - len(suffix)]


@pytest.mark.parametrize("seed", range(20))
def test_initial_plus_surname_keeps_shape(seed: int) -> None:
    synthetic = one("Dear R. Castellanos, thanks.", "R. Castellanos", "PERSON", seed=seed)
    initial, surname = synthetic.split(" ")
    assert re.fullmatch(r"[A-Z]\.", initial) and initial != "R."
    assert surname in CORPUS.surnames


@pytest.mark.parametrize("seed", range(20))
def test_single_surname_stays_single_surname(seed: int) -> None:
    synthetic = one("Ask Castellanos today.", "Castellanos", "PERSON", seed=seed)
    assert synthetic in CORPUS.surnames


def test_full_name_with_honorific_and_suffix() -> None:
    synthetic = one("Seen by Dr. Maria Castellanos, MD today.", "Dr. Maria Castellanos, MD", "PROVIDER_NAME")
    title, given, surname, suffix = synthetic.split(" ")
    assert (title, suffix) == ("Dr.", "MD")
    assert given in CORPUS.given_any and surname.rstrip(",") in CORPUS.surnames


def test_honorific_picks_matching_given_name_pool() -> None:
    assert one("Mr. Ravi Okonjo called.", "Mr. Ravi Okonjo", "PERSON").split(" ")[1] in CORPUS.given_masculine
    assert one("Mrs. Ada Okonjo called.", "Mrs. Ada Okonjo", "PERSON").split(" ")[1] in CORPUS.given_feminine


def test_upper_case_name_stays_upper_case() -> None:
    synthetic = one("PLAINTIFF MARIA CASTELLANOS v. STATE", "MARIA CASTELLANOS", "PERSON")
    assert synthetic.isupper() and len(synthetic.split(" ")) == 2


def test_surname_first_order_is_kept() -> None:
    synthetic = one("Witness: Castellanos, Maria.", "Castellanos, Maria", "PERSON")
    surname, given = synthetic.split(", ")
    assert surname in CORPUS.surnames and given in CORPUS.given_any


@pytest.mark.parametrize("seed", range(10))
def test_email_uses_reserved_domain_and_local_style(seed: int) -> None:
    synthetic = one("Write to jane.doe@acme-legal.com now.", "jane.doe@acme-legal.com", "EMAIL_ADDRESS", seed=seed)
    assert re.fullmatch(r"[a-z]+\.[a-z]+@example\.(com|org|net)", synthetic)


@pytest.mark.parametrize(
    ("original", "pattern"),
    [
        ("(415) 555-2671", r"\(\d{3}\) 555-01\d\d"),
        ("415.555.2671", r"\d{3}\.555\.01\d\d"),
        ("+1 415 555 2671", r"\+1 \d{3} 555 01\d\d"),
        ("4155552671", r"\d{3}55501\d\d"),
    ],
)
def test_nanp_phone_is_fictional_and_keeps_format(original: str, pattern: str) -> None:
    assert re.fullmatch(pattern, one(f"Call {original} today.", original, "PHONE_NUMBER"))


def test_international_phone_keeps_country_code_and_format() -> None:
    synthetic = one("Call +44 20 7946 0958 today.", "+44 20 7946 0958", "PHONE_NUMBER")
    assert re.fullmatch(r"\+44 \d\d \d{4} \d{4}", synthetic) and synthetic != "+44 20 7946 0958"


@pytest.mark.parametrize("seed", range(30))
def test_ssn_uses_never_issued_area_and_keeps_format(seed: int) -> None:
    synthetic = one("SSN 412-71-3359 on file.", "412-71-3359", "SSN", seed=seed)
    area, group, serial = synthetic.split("-")
    assert 900 <= int(area) <= 999 and 1 <= int(group) <= 49 and len(serial) == 4


def test_ssn_label_is_kept_and_undashed_format_preserved() -> None:
    text = "Record: SSN 412713359."
    result = convert(text, [entity(text, "SSN 412713359", "US_SSN")], seed=3)
    assert re.fullmatch(r"Record: SSN 9\d{8}\.", result.replica)
    assert [e.original for e in result.mapping.entries] == ["412713359"]


@pytest.mark.parametrize(
    ("original", "fmt"),
    [
        ("03/14/1978", "%m/%d/%Y"),
        ("1978-03-14", "%Y-%m-%d"),
        ("14.03.1978", "%d.%m.%Y"),
    ],
)
def test_numeric_date_of_birth_is_shifted_in_same_format(original: str, fmt: str) -> None:
    from datetime import datetime

    synthetic = one(f"DOB: {original}.", original, "DATE_OF_BIRTH")
    shifted = datetime.strptime(synthetic, fmt).date()
    assert 30 <= abs((shifted - date(1978, 3, 14)).days) <= 365 + 64


@pytest.mark.parametrize(
    ("original", "pattern"),
    [
        ("March 14, 1978", r"[A-Z][a-z]+ \d{1,2}, 19\d\d"),
        ("14th Mar 1978", r"\d{1,2}(st|nd|rd|th) [A-Z][a-z]{2} 19\d\d"),
        ("3/14/78", r"\d{1,2}/\d{1,2}/\d\d"),
    ],
)
def test_textual_and_short_dates_keep_their_style(original: str, pattern: str) -> None:
    synthetic = one(f"Born {original} in winter.", original, "DATE_OF_BIRTH")
    assert re.fullmatch(pattern, synthetic) and synthetic != original


def test_one_date_shift_per_call_preserves_intervals() -> None:
    text = "DOB 01/10/1980 and DOB 01/20/1980."
    result = convert(text, entities(text, ("01/10/1980", "DATE_OF_BIRTH"), ("01/20/1980", "DATE_OF_BIRTH")), seed=5)
    first, second = re.findall(r"\d\d/\d\d/\d{4}", result.replica)
    from datetime import datetime

    gap = datetime.strptime(second, "%m/%d/%Y") - datetime.strptime(first, "%m/%d/%Y")
    assert gap.days == 10


def test_case_number_keeps_letters_and_punctuation() -> None:
    synthetic = one("Re 24-cv-01234 filing.", "24-cv-01234", "CASE_NUMBER")
    assert re.fullmatch(r"\d\d-cv-\d{5}", synthetic) and synthetic != "24-cv-01234"


@pytest.mark.parametrize("category", ["BATES_NUMBER", "INSURANCE_ID"])
def test_codes_keep_length_case_and_punctuation(category: str) -> None:
    synthetic = one("Ref ABC000123 / XKH-4471-889 end.", "XKH-4471-889", category)
    assert re.fullmatch(r"[A-Z]{3}-\d{4}-\d{3}", synthetic) and synthetic != "XKH-4471-889"


def test_street_address_location() -> None:
    original = "100 Main Street, Springfield, IL 62701"
    synthetic = one(f"Lives at {original}.", original, "LOCATION")
    street, town, state_zip = synthetic.split(", ")
    assert re.fullmatch(r"\d{3} [A-Z][a-z]+ Street", street) and "Main" not in street
    assert town in CORPUS.towns and re.fullmatch(r"IL \d{5}", state_zip) and state_zip != "IL 62701"


def test_spelled_out_state_is_kept() -> None:
    assert one("From Springfield, Illinois originally.", "Springfield, Illinois", "LOCATION").endswith(", Illinois")


def test_institution_keeps_type_words() -> None:
    synthetic = one("Admitted to Harrowgate General Hospital.", "Harrowgate General Hospital", "INSTITUTION_NAME")
    assert synthetic.endswith(" General Hospital") and not synthetic.startswith("Harrowgate")


def test_law_firm_keeps_connector_and_suffix() -> None:
    synthetic = one("Counsel: Pellham & Corrigan LLP.", "Pellham & Corrigan LLP", "LAW_FIRM_NAME")
    first, rest = synthetic.split(" & ")
    assert first in CORPUS.surnames and rest.endswith(" LLP") and rest[: -len(" LLP")] in CORPUS.surnames


@pytest.mark.parametrize(
    ("policy", "suffix"),
    [("legal", "LLP"), ("clinical", "Medical Center"), ("financial", "Capital"), ("generic", "Group")],
)
def test_policy_sets_default_organisation_style(policy: str, suffix: str) -> None:
    assert one("Funded by Acme.", "Acme", "INSTITUTION_NAME", policy=policy).endswith(suffix)


def test_unhandled_category_is_left_unchanged_and_reported() -> None:
    text = "Card 4111 1111 1111 1111 for R. Castellanos."
    result = convert(text, entities(text, ("4111 1111 1111 1111", "CREDIT_CARD"), ("R. Castellanos", "PERSON")), seed=1)
    assert "4111 1111 1111 1111" in result.replica and "Castellanos" not in result.replica
    assert result.unconverted_categories == ["CREDIT_CARD"]


def test_unparseable_value_of_handled_kind_is_reported_not_invented() -> None:
    text = "DOB unknown here."
    result = convert(text, [entity(text, "unknown", "DATE_OF_BIRTH")], seed=1)
    assert result.replica == text and result.unconverted_categories == ["DATE_OF_BIRTH"]


@pytest.mark.parametrize("marker", ["PRIVILEGE_MARKER", "COURT_FILING", "COUNSEL_COMMUNICATION"])
def test_classification_markers_are_not_replaced_or_reported(marker: str) -> None:
    text = "PRIVILEGED AND CONFIDENTIAL note."
    result = convert(text, [entity(text, "PRIVILEGED AND CONFIDENTIAL", marker)], seed=1)
    assert result.replica == text and result.unconverted_categories == [] and result.converted_count == 0
