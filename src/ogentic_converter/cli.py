"""``ogentic-converter`` command line.

stdout carries only the requested text (replica or restored text), byte for byte.
The mapping goes to its own file, created owner-only and never overwritten.
Errors and warnings go to stderr and never quote input content.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from . import __version__
from .core import convert, load_shield_entities, restore
from .errors import ConversionError
from .models import Policy, ReversalMapping

_PROG = "ogentic-converter"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "convert":
            return _convert(args)
        return _restore(args)
    except (ConversionError, OSError, UnicodeDecodeError) as exc:
        _error(_describe(exc))
    except ValidationError:
        _error("the mapping file is not a valid ogentic-converter mapping")
    return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=_PROG, description="Synthetic-replica conversion for Shield entities.")
    parser.add_argument("--version", action="version", version=f"{_PROG} {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    conv = commands.add_parser("convert", help="text on stdin -> synthetic replica on stdout")
    conv.add_argument("--entities", required=True, type=Path, help="ogentic-shield analyze --output json file")
    conv.add_argument("--policy", default=Policy.GENERIC.value, choices=[p.value for p in Policy])
    conv.add_argument("--seed", type=int, default=None, help="integer seed for a reproducible replica")
    conv.add_argument("--mapping", required=True, type=Path, help="new file to write the reversal mapping to")

    rest = commands.add_parser("restore", help="model reply on stdin -> original values on stdout")
    rest.add_argument("--mapping", required=True, type=Path, help="mapping file written by convert")
    return parser


def _convert(args: argparse.Namespace) -> int:
    text = _read_stdin()
    entities = load_shield_entities(args.entities.read_bytes())
    result = convert(text, entities, policy=args.policy, seed=args.seed)
    _write_private(args.mapping, result.mapping.model_dump_json(indent=2))
    if result.unconverted_categories:
        _warn("left unconverted (not supported): " + ", ".join(result.unconverted_categories))
    _write_stdout(result.replica)
    return 0


def _restore(args: argparse.Namespace) -> int:
    mapping = ReversalMapping.model_validate_json(args.mapping.read_bytes())
    _write_stdout(restore(_read_stdin(), mapping))
    return 0


def _read_stdin() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


def _write_stdout(text: str) -> None:
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


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


def _error(message: str) -> None:
    print(f"{_PROG}: error: {message}", file=sys.stderr)


def _warn(message: str) -> None:
    print(f"{_PROG}: warning: {message}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
