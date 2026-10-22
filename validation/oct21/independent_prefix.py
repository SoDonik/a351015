#!/usr/bin/env python3
"""Separate implementation of the revised manuscript's prefix construction.

Implemented on 2026-10-21 after reading the complete manuscript, before
reading or importing code/a351015_polynomial.py.  The manuscript read had
SHA-256 3fe9161f286bca488a62ad72254820e545d715bfa8c8e0b473cfab6173f15b74.

This is implementation independence, not independence from the mathematical
results: the cutoff structure, boundary capacity lemma, and arbitrary-prefix
proposition are used exactly as stated in that manuscript.

No producer or previous verifier modules are imported.  All arithmetic and
binary encodings use Python's unbounded integers and strings.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from typing import Iterable

Run = tuple[int, int]


@dataclass(frozen=True)
class Cutoff:
    n: int
    q: int
    forced: frozenset[Run]
    boundary: frozenset[Run]
    boundary_needed: int
    bit_length: int


def cutoff(n: int) -> Cutoff:
    """Enumerate successive product layers until the nth pair is reached."""
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    if n == 0:
        return Cutoff(0, 0, frozenset(), frozenset(), 0, 0)
    earlier: set[Run] = set()
    earlier_weight = 0
    q = 0
    while True:
        q += 1
        layer = {(v, q // v) for v in range(1, q + 1) if q % v == 0}
        if len(earlier) + len(layer) >= n:
            r = n - len(earlier)
            return Cutoff(n, q, frozenset(earlier), frozenset(layer),
                          r, earlier_weight + r * q)
        earlier.update(layer)
        earlier_weight += q * len(layer)


def grouped(parts: Iterable[int]) -> tuple[Run, ...]:
    return tuple((value, sum(1 for _ in equal_parts))
                 for value, equal_parts in groupby(parts))


class PrefixConstruction:
    """A binary-prefix oracle and the manuscript's bit-by-bit minimum."""

    def __init__(self, n: int):
        self.data = cutoff(n)
        self.universe = self.data.forced | self.data.boundary
        self.active_choices = tuple(sorted(self.universe))
        self.queries = 0
        self.active_proposals = 0

    def _completed_set(self, completed: tuple[Run, ...]) -> frozenset[Run] | None:
        distinct = frozenset(completed)
        if len(distinct) != len(completed) or not distinct <= self.universe:
            return None
        return distinct

    def _suffix_exists(self, consumed: frozenset[Run], preceding: int) -> bool:
        """Implement the boundary-capacity lemma for complete consumed types."""
        boundary_left = self.data.boundary_needed - len(consumed & self.data.boundary)
        if boundary_left < 0:
            return False
        forced_left = self.data.forced - consumed
        forced_counts = Counter(v for v, _ in forced_left)
        run_count = len(forced_left) + boundary_left
        previous_capacity = run_count // 2
        other_capacity = (run_count + 1) // 2
        for value, count in forced_counts.items():
            capacity = previous_capacity if value == preceding else other_capacity
            if count > capacity:
                return False
        eligible = 0
        for value, _ in self.data.boundary - consumed:
            capacity = previous_capacity if value == preceding else other_capacity
            if forced_counts[value] < capacity:
                eligible += 1
        return boundary_left <= eligible

    def feasible(self, prefix: str) -> bool:
        """Test an arbitrary prefix, including leading-zero and empty strings."""
        self.queries += 1
        if not isinstance(prefix, str):
            return False
        if len(prefix) > self.data.bit_length or set(prefix) - {"0", "1"}:
            return False
        if not prefix:
            return True
        if prefix[0] != "1":
            return False

        # A split at every 1 determines each current part length.  Only the
        # final part may still gain zeros; all preceding parts are fixed.
        parts = tuple(1 + len(zero_tail) for zero_tail in prefix.split("1")[1:])
        current_value = parts[-1]
        fixed_runs = grouped(parts[:-1])
        ordinary_completed = self._completed_set(fixed_runs)
        absorbed_completed = self._completed_set(fixed_runs[:-1]) if fixed_runs else None

        for active in self.active_choices:
            value, copies = active
            if value < current_value:
                continue
            self.active_proposals += 1

            # The active type can absorb the trailing fixed run only when its
            # eventual value, rather than the current final-part value, agrees.
            if fixed_runs and fixed_runs[-1][0] == value:
                preceding_copies = fixed_runs[-1][1]
                completed = absorbed_completed
            else:
                preceding_copies = 0
                completed = ordinary_completed
            if copies < preceding_copies + 1 or completed is None:
                continue
            if active in completed:
                continue
            if self._suffix_exists(completed | {active}, value):
                return True
        return False

    def least_word(self) -> str:
        if self.data.n == 0:
            return ""
        word = "1"
        while len(word) < self.data.bit_length:
            word += "0" if self.feasible(word + "0") else "1"
        if not self.feasible(word):
            raise AssertionError("the greedy construction ended at an infeasible word")
        return word


def least_word(n: int) -> str:
    return PrefixConstruction(n).least_word()


def a(n: int) -> int:
    word = least_word(n)
    return int(word, 2) if word else 0
