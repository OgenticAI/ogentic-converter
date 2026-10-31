"""``--json`` mode: one JSON object in on stdin, one out on stdout, nothing written to disk."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ogentic_converter import convert
from ogentic_converter.cli import main

from .helpers import FIXTURES, entity

TEXT = (FIXTURES / "shield_legal.txt").read_text(encoding="utf-8")
SHIELD = json.loads((FIXTURES / "shield_legal.json").read_text(encoding="utf-8"))


def cli(args: list[str], stdin: bytes, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "ogentic_converter.cli", *args], input=stdin, capture_output=True, cwd=cwd
    )


def request(**fields: Any) -> bytes:
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


def test_convert_then_restore_round_trips_byte_exactly(tmp_path: Path) -> None:
    text = TEXT + "\r\n\ttrailing whitespace kept  \n"
    converted = cli(["convert", "--json"], request(text=text, entities=SHIELD, policy="legal", seed=42), tmp_path)
    assert converted.returncode == 0, converted.stderr
    result = json.loads(converted.stdout)
    assert set(result) == {"replica", "mapping", "converted_count", "unconverted_categories"}
    assert "Castellanos" not in result["replica"]

    restored = cli(["restore", "--json"], request(text=result["replica"], mapping=result["mapping"]), tmp_path)
    assert restored.returncode == 0, restored.stderr
    assert json.loads(restored.stdout) == {"text": text}
    assert list(tmp_path.iterdir()) == []  # nothing written to disk


def test_output_matches_the_python_api(tmp_path: Path) -> None:
    out = cli(["convert", "--json"], request(text=TEXT, entities=SHIELD["entities"], policy="legal", seed=42), tmp_path)
    expected = convert(TEXT, SHIELD["entities"], "legal", seed=42)
    assert json.loads(out.stdout) == {
        "replica": expected.replica,
        "mapping": expected.mapping.model_dump(mode="json"),
        "converted_count": expected.converted_count,
        "unconverted_categories": expected.unconverted_categories,
    }


def test_entities_without_text_work_from_offsets_alone(tmp_path: Path) -> None:
    bare = [{k: v for k, v in e.items() if k != "text"} for e in SHIELD["entities"]]
    without = cli(["convert", "--json"], request(text=TEXT, entities=bare, policy="legal", seed=42), tmp_path)
    with_text = cli(["convert", "--json"], request(text=TEXT, entities=SHIELD, policy="legal", seed=42), tmp_path)
    assert without.returncode == 0 and without.stdout == with_text.stdout


def test_text_mismatch_is_still_checked_when_present(tmp_path: Path) -> None:
    bad = [{"category": "PERSON", "start": 0, "end": 5, "text": "SECRETVALUE"}]
    out = cli(["convert", "--json"], request(text=TEXT, entities=bad), tmp_path)
    assert out.returncode == 1 and out.stdout == b"" and b"code points" in out.stderr and b"SECRET" not in out.stderr


def test_defaults_are_generic_policy_and_random_seed(tmp_path: Path) -> None:
    payload = request(text=TEXT, entities=SHIELD)
    first, second = (json.loads(cli(["convert", "--json"], payload, tmp_path).stdout) for _ in range(2))
    assert first["replica"] != second["replica"]


@pytest.mark.parametrize(
    ("command", "flags"),
    [
        ("convert", ["--mapping", "out.json"]),
        ("convert", ["--entities", "e.json"]),
        ("convert", ["--seed", "1"]),
        ("restore", ["--mapping", "out.json"]),
    ],
)
def test_json_with_file_flags_is_a_usage_error(tmp_path: Path, command: str, flags: list[str]) -> None:
    out = cli([command, "--json", *flags], request(text=TEXT, entities=SHIELD), tmp_path)
    assert out.returncode == 2 and out.stdout == b"" and b"--json cannot be combined" in out.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("command", ["convert", "restore"])
@pytest.mark.parametrize(
    "stdin",
    [
        b'{"text": "R. Castellanos SSN 412-71-3359", ',  # truncated
        b"not json at all: R. Castellanos",
        b'["R. Castellanos"]',
        b'{"text": "R. Castellanos", "unexpected": "412-71-3359"}',
        b"\xff\xfe",
    ],
)
def test_malformed_requests_fail_with_empty_stdout(tmp_path: Path, command: str, stdin: bytes) -> None:
    out = cli([command, "--json"], stdin, tmp_path)
    assert out.returncode == 1 and out.stdout == b""
    assert b"Castellanos" not in out.stderr and b"412-71-3359" not in out.stderr and out.stderr


def test_bad_entity_inside_request_is_sanitised(tmp_path: Path) -> None:
    payload = request(text=TEXT, entities=[{"category": "PERSON", "start": "SECRET-412-71-3359", "end": 2}])
    out = cli(["convert", "--json"], payload, tmp_path)
    assert out.returncode == 1 and out.stdout == b"" and b"entity 0 is invalid" in out.stderr
    assert b"SECRET" not in out.stderr


def test_file_mode_still_requires_its_flags(tmp_path: Path) -> None:
    out = cli(["convert"], TEXT.encode(), tmp_path)
    assert out.returncode == 2 and out.stdout == b"" and b"--entities, --mapping required" in out.stderr


def test_help_warns_that_json_stdout_carries_originals(tmp_path: Path) -> None:
    for command in ("convert", "restore"):
        out = cli([command, "--help"], b"", tmp_path)
        assert b"ORIGINAL values" in out.stdout and b"Never redirect it to a file" in out.stdout


class _Stdout:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()


def test_in_process_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same contract through main(), so coverage sees the JSON paths."""
    text = "Hi R. Castellanos 😊"
    payload = request(text=text, entities=[entity(text, "R. Castellanos", "PERSON")], seed=1)

    def run(args: list[str], stdin: bytes) -> tuple[int, bytes]:
        out = _Stdout()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin)))
        monkeypatch.setattr(sys, "stdout", out)
        return main(args), out.buffer.getvalue()

    code, converted = run(["convert", "--json"], payload)
    result = json.loads(converted)
    assert code == 0 and result["converted_count"] == 1 and result["unconverted_categories"] == []
    code, restored = run(["restore", "--json"], request(text=result["replica"], mapping=result["mapping"]))
    assert code == 0 and json.loads(restored) == {"text": text}
