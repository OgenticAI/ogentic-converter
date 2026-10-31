"""Seed engine: every synthetic choice is a pure function of (seed, policy, label).

Draws come from HMAC-SHA256 rather than :mod:`random`, whose ``choice``/``randint``
algorithms are not guaranteed stable across Python versions, and rather than the
builtin ``hash()``, which is salted per process. The output therefore depends only
on the seed, the policy and the value being replaced: never on entity order, dict
order, ``PYTHONHASHSEED`` or the wall clock.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

_KEY_DOMAIN = "ogentic-converter/template/v1"


def derive_key(seed: int, policy: str) -> bytes:
    """The HMAC key for one call. The seed acts as a secret key; see README "Seeds"."""
    return f"{_KEY_DOMAIN}|{seed}|{policy}".encode()


def random_seed() -> int:
    """A fresh unpredictable seed, used when the caller supplies none."""
    return secrets.randbits(64)


class Draw:
    """A deterministic stream of choices for one label (e.g. one original value + probe)."""

    def __init__(self, key: bytes, label: str) -> None:
        self._key = key
        self._label = label.encode("utf-8")
        self._counter = 0

    def below(self, bound: int) -> int:
        """An integer in ``[0, bound)``. Modulo bias is < 2**-200 for the bounds used here."""
        message = self._label + b"\x00" + self._counter.to_bytes(8, "big")
        self._counter += 1
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return int.from_bytes(digest, "big") % bound

    def between(self, low: int, high: int) -> int:
        """An integer in ``[low, high]``."""
        return low + self.below(high - low + 1)

    def choice(self, options: Sequence[T]) -> T:
        return options[self.below(len(options))]

    def digits(self, count: int) -> str:
        return "".join(str(self.below(10)) for _ in range(count))
