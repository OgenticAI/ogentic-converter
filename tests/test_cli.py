"""Property 8 and the CLI contract: stdout carries only the replica; the mapping goes to its own file."""

from __future__ import annotations

import io
import json
import stat
import sys
from pathlib import Path

import pytest

from ogentic_converter import ReversalMapping, convert
from ogentic_converter.cli import main

from .helpers import FIXTURES, entity

TEXT = (FIXTURES / "shield_legal.txt").read_text(encoding="utf-8")
ENTITIES = FIXTURES / "shield_legal.json"


class _Stdout:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()


def run(monkeypatch: pytest.MonkeyPatch, args: list[str], stdin: str) -> tuple[int, bytes]:
    out = _Stdout()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8"))))
    monkeypatch.setattr(sys, "stdout", out)
    return main(args), out.buffer.getvalue()


def test_convert_writes_replica_to_stdout_and_mapping_to_private_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping_path = tmp_path / "out.json"
    args = ["convert", "--entities", str(ENTITIES), "--policy", "legal", "--seed", "42", "--mapping", str(mapping_path)]
    code, stdout = run(monkeypatch, args, TEXT)
    expected = convert(TEXT, json.loads(ENTITIES.read_text())["entities"], "legal", seed=42)
    assert code == 0
    assert stdout == expected.replica.encode("utf-8")  # byte-exact, no trailing newline, nothing else
    assert ReversalMapping.model_validate_json(mapping_path.read_text()) == expected.mapping
    assert stat.S_IMODE(mapping_path.stat().st_mode) == 0o600
    for entry in expected.mapping.entries:
        assert entry.original.encode("utf-8") not in stdout
    assert capsys.readouterr().err == ""


def test_trailing_newlines_and_crlf_survive_byte_exact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    text = "Hi R. Castellanos\r\n\r\n"
    entities_path = tmp_path / "e.json"
    entities_path.write_text(json.dumps({"entities": [entity(text, "R. Castellanos", "PERSON")]}))
    code, stdout = run(
        monkeypatch, ["convert", "--entities", str(entities_path), "--mapping", str(tmp_path / "m.json")], text
    )
    assert code == 0 and stdout.endswith(b"\r\n\r\n") and stdout.startswith(b"Hi ") and b"Castellanos" not in stdout


def test_convert_refuses_to_overwrite_mapping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping_path = tmp_path / "out.json"
    mapping_path.write_text("keep me")
    code, stdout = run(monkeypatch, ["convert", "--entities", str(ENTITIES), "--mapping", str(mapping_path)], TEXT)
    assert code == 1 and stdout == b""
    assert mapping_path.read_text() == "keep me"
    assert "refusing to overwrite" in capsys.readouterr().err


def test_restore_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mapping_path = tmp_path / "out.json"
    _, replica = run(monkeypatch, ["convert", "--entities", str(ENTITIES), "--mapping", str(mapping_path)], TEXT)
    code, restored = run(monkeypatch, ["restore", "--mapping", str(mapping_path)], replica.decode("utf-8"))
    assert code == 0 and restored.decode("utf-8") == TEXT


def test_unconverted_categories_warn_on_stderr_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "Card 4111 1111 1111 1111."
    entities_path = tmp_path / "e.json"
    entities_path.write_text(json.dumps([entity(text, "4111 1111 1111 1111", "CREDIT_CARD")]))
    code, stdout = run(
        monkeypatch, ["convert", "--entities", str(entities_path), "--mapping", str(tmp_path / "m.json")], text
    )
    err = capsys.readouterr().err
    assert code == 0 and stdout == text.encode() and "CREDIT_CARD" in err and "4111" not in err


@pytest.mark.parametrize(
    ("entities_json", "message"),
    [
        ("not json", "not valid JSON"),
        ('{"entities": [{"category": "PERSON", "start": 0, "end": 9999}]}', "outside the text"),
        ('{"entities": [{"category": "PERSON", "start": 0, "end": 5, "text": "SECRETVALUE"}]}', "code points"),
    ],
)
def test_bad_input_fails_on_stderr_without_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entities_json: str,
    message: str,
) -> None:
    entities_path = tmp_path / "e.json"
    entities_path.write_text(entities_json)
    mapping_path = tmp_path / "m.json"
    code, stdout = run(monkeypatch, ["convert", "--entities", str(entities_path), "--mapping", str(mapping_path)], TEXT)
    err = capsys.readouterr().err
    assert code == 1 and stdout == b"" and message in err
    assert "SECRETVALUE" not in err and "Castellanos" not in err
    assert not mapping_path.exists()


def test_missing_and_invalid_mapping_files_fail_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout = run(monkeypatch, ["restore", "--mapping", str(tmp_path / "missing.json")], "x")
    assert code == 1 and stdout == b"" and "No such file" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text('{"entries": [{"synthetic": "A"}]}')
    code, stdout = run(monkeypatch, ["restore", "--mapping", str(bad)], "x")
    assert code == 1 and stdout == b"" and "mapping file is invalid" in capsys.readouterr().err


def test_non_utf8_stdin_fails_cleanly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out = _Stdout()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"\xff\xfe bad")))
    monkeypatch.setattr(sys, "stdout", out)
    assert main(["convert", "--entities", str(ENTITIES), "--mapping", str(tmp_path / "m.json")]) == 1
    assert out.buffer.getvalue() == b""


def test_result_repr_never_shows_the_mapping() -> None:
    result = convert(TEXT, json.loads(ENTITIES.read_text())["entities"], "legal", seed=42)
    for shown in (repr(result), str(result), repr(result.mapping)):
        assert "Castellanos" not in shown and "412-71-3359" not in shown
