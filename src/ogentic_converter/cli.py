"""``ogentic-converter`` command line.

File mode (default): stdout carries only the requested text (replica or restored
text), byte for byte; the mapping goes to its own file, created owner-only and never
overwritten.

JSON mode (``--json``, opt-in): one JSON object in on stdin, one JSON object out on
stdout, and no file is written. That stdout carries the original values, for a parent
process that keeps the mapping in memory.

In both modes errors and warnings go to stderr, never quote input content, and
nothing is written to stdout on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from . import __version__
from .core import convert, load_shield_entities, restore
from .errors import ConversionError
from .models import Policy, ReversalMapping

_PROG = "ogentic-converter"
_ModelT = TypeVar("_ModelT", bound=BaseModel)

_JSON_WARNING = (
    "--json: stdout carries the ORIGINAL values (the reversal mapping). It is meant for a parent\n"
    "process that holds them in memory. Never redirect it to a file or a log."
)
_CONVERT_EPILOG = f"""\
file mode (default):
  stdin: text; stdout: replica only; --mapping: new 0600 file with the reversal mapping.

json mode (--json):
  stdin:  {{"text": str, "entities": <Shield analyze JSON or entity list>,
           "policy": "legal"|"clinical"|"financial"|"generic", "seed": int|null}}
  stdout: {{"replica": str, "mapping": <ReversalMapping>, "converted_count": int,
           "unconverted_categories": [str]}}
  No file is written; --entities, --mapping, --policy and --seed are rejected.

{_JSON_WARNING}
"""
_RESTORE_EPILOG = f"""\
file mode (default):
  stdin: model reply; stdout: restored text; --mapping: file written by convert.

json mode (--json):
  stdin:  {{"text": str, "mapping": <ReversalMapping>}}
  stdout: {{"text": str}}
  --mapping is rejected.

{_JSON_WARNING}
"""


class _JsonConvertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    entities: dict[str, Any] | list[Any]
    policy: Policy = Policy.GENERIC
    seed: int | None = None


class _JsonRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    mapping: ReversalMapping


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    _check_mode(parser, args)
    try:
        if args.command == "convert":
            return _convert_json() if args.json else _convert(args)
        return _restore_json() if args.json else _restore(args)
    except (ConversionError, OSError, UnicodeDecodeError) as exc:
        _error(_describe(exc))
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PROG, description="Synthetic-replica conversion for Shield entities.")
    parser.add_argument("--version", action="version", version=f"{_PROG} {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    formatter = argparse.RawDescriptionHelpFormatter

    conv = commands.add_parser(
        "convert", help="text -> synthetic replica", epilog=_CONVERT_EPILOG, formatter_class=formatter
    )
    conv.add_argument("--entities", type=Path, help="ogentic-shield analyze --output json file (file mode)")
    conv.add_argument("--policy", choices=[p.value for p in Policy], help="default: generic (file mode)")
    conv.add_argument("--seed", type=int, help="integer seed for a reproducible replica (file mode)")
    conv.add_argument("--mapping", type=Path, help="new file to write the reversal mapping to (file mode)")
    conv.add_argument("--json", action="store_true", help="JSON request on stdin, JSON result on stdout; see below")

    rest = commands.add_parser(
        "restore", help="model reply -> original values", epilog=_RESTORE_EPILOG, formatter_class=formatter
    )
    rest.add_argument("--mapping", type=Path, help="mapping file written by convert (file mode)")
    rest.add_argument("--json", action="store_true", help="JSON request on stdin, JSON result on stdout; see below")
    return parser


def _check_mode(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Exactly one channel for the mapping: --json and the file flags never mix (usage error, exit 2)."""
    file_flags = ("entities", "mapping", "policy", "seed") if args.command == "convert" else ("mapping",)
    given = [f"--{flag}" for flag in file_flags if getattr(args, flag) is not None]
    if args.json and given:
        parser.error(f"{args.command}: --json cannot be combined with {', '.join(given)}")
    required = ("entities", "mapping") if args.command == "convert" else ("mapping",)
    missing = [f"--{flag}" for flag in required if getattr(args, flag) is None]
    if not args.json and missing:
        parser.error(f"{args.command}: {', '.join(missing)} required (or use --json)")


# ── file mode ────────────────────────────────────────────────────────────────


def _convert(args: argparse.Namespace) -> int:
    text = _read_stdin()
    entities = load_shield_entities(args.entities.read_bytes())
    result = convert(text, entities, policy=args.policy or Policy.GENERIC, seed=args.seed)
    _write_private(args.mapping, result.mapping.model_dump_json(indent=2))
    _warn_unconverted(result.unconverted_categories)
    _write_stdout(result.replica)
    return 0


def _restore(args: argparse.Namespace) -> int:
    mapping = _validated(ReversalMapping, args.mapping.read_bytes(), "the mapping file")
    _write_stdout(restore(_read_stdin(), mapping))
    return 0


# ── json mode ────────────────────────────────────────────────────────────────


def _convert_json() -> int:
    request = _validated(_JsonConvertRequest, sys.stdin.buffer.read(), "the JSON request")
    entities = load_shield_entities(request.entities)
    result = convert(request.text, entities, policy=request.policy, seed=request.seed)
    _warn_unconverted(result.unconverted_categories)
    _write_json(
        {
            "replica": result.replica,
            "mapping": result.mapping.model_dump(mode="json"),
            "converted_count": result.converted_count,
            "unconverted_categories": result.unconverted_categories,
        }
    )
    return 0


def _restore_json() -> int:
    request = _validated(_JsonRestoreRequest, sys.stdin.buffer.read(), "the JSON request")
    _write_json({"text": restore(request.text, request.mapping)})
    return 0


# ── I/O helpers ──────────────────────────────────────────────────────────────


def _validated(model: type[_ModelT], raw: bytes, what: str) -> _ModelT:
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:  # the default message echoes input values: report field paths only
        errors = exc.errors(include_input=False)
        fields = sorted({".".join(map(str, error["loc"])) for error in errors if error["loc"]})
        if any(error["type"] == "json_invalid" for error in errors):
            detail = "not valid JSON"
        else:
            detail = f"fields: {', '.join(fields)}" if fields else "expected a JSON object"
        raise ConversionError(f"{what} is invalid ({detail})") from None


def _read_stdin() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


def _write_stdout(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def _write_json(payload: dict[str, Any]) -> None:
    _write_stdout(json.dumps(payload, ensure_ascii=False))


def _write_private(path: Path, content: str) -> None:
    """Create ``path`` with mode 0600; fail if it already exists (O_EXCL, no symlink follow-through)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        raise ConversionError(f"refusing to overwrite existing mapping file: {path}") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, ConversionError):
        return str(exc)
    if isinstance(exc, UnicodeDecodeError):
        return "input is not valid UTF-8"
    if isinstance(exc, OSError):
        return f"{exc.strerror or 'I/O error'}: {exc.filename}" if exc.filename else (exc.strerror or "I/O error")
    return "unexpected error"


def _warn_unconverted(categories: list[str]) -> None:
    if categories:
        print(f"{_PROG}: warning: left unconverted (not supported): {', '.join(categories)}", file=sys.stderr)


def _error(message: str) -> None:
    print(f"{_PROG}: error: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
