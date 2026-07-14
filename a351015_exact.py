#!/usr/bin/env python3
"""Exact structural computation for OEIS A351015.

For a run consisting of l copies of the part v, the run type is (v, l)
and its contribution to the sum of the composition is v*l.  The standard
binary encoding of a composition has that same length.  Therefore a
composition with n distinct run types has length at least the sum of the n
smallest products v*l, counted by ordered pairs (v, l).

The theorem in the accompanying manuscript proves that this lower bound is
always attainable.  At the minimum length, this program enumerates the
possible choices at the boundary product and uses an exact bitmask dynamic
program to find the lexicographically least binary encoding.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
from itertools import combinations, groupby


EXPECTED = [
    0,
    1,
    5,
    27,
    155,
    1655,
    18039,
    281975,
    4617711,
    138835439,
    4503885791,
    279381792735,
    17876500338655,
    1144081370306527,
    73222145385127871,
    9296594182239903679,
    1189966115078053658495,
    303421421018735347335039,
]


def _require(condition: bool, message: str) -> None:
    """Raise on a failed check.

    Used instead of ``assert`` so that verification is not silently disabled
    when the program is run under ``python -O``.
    """
    if not condition:
        raise AssertionError(message)


def composition(k: int) -> tuple[int, ...]:
    """Decode k into the k-th composition in standard order (A066099)."""
    if k == 0:
        return ()
    parts: list[int] = []
    for bit in bin(k)[2:]:
        if bit == "1":
            parts.append(1)
        else:
            parts[-1] += 1
    return tuple(parts)


def distinct_run_types(parts: tuple[int, ...]) -> set[tuple[int, int]]:
    """Return the set of run types (value, multiplicity)."""
    return {(value, sum(1 for _ in run)) for value, run in groupby(parts)}


def block(run_type: tuple[int, int]) -> str:
    """Binary block encoding one run type (v,l)."""
    value, multiplicity = run_type
    return ("1" + "0" * (value - 1)) * multiplicity


def divisor_summatory(q: int) -> int:
    """Number of ordered positive pairs (v,l) with v*l <= q."""
    return sum(q // value for value in range(1, q + 1))


def boundary_for(n: int) -> tuple[int, list[tuple[int, int]], list[tuple[int, int]], int]:
    """Return cutoff q, forced types, boundary types, and number to select."""
    if n < 1:
        raise ValueError("n must be positive")
    q = 1
    while divisor_summatory(q) < n:
        q += 1
    forced = [
        (value, multiplicity)
        for value in range(1, q + 1)
        for multiplicity in range(1, q + 1)
        if value * multiplicity < q
    ]
    boundary = [(value, q // value) for value in range(1, q + 1) if q % value == 0]
    choose = n - len(forced)
    return q, forced, boundary, choose


def least_word_for_types(types: tuple[tuple[int, int], ...]) -> tuple[str, tuple[tuple[int, int], ...]] | None:
    """Find the least valid concatenation of a fixed set of distinct run types."""
    full_mask = (1 << len(types)) - 1

    @lru_cache(maxsize=None)
    def solve(mask: int, previous_value: int) -> tuple[str, tuple[tuple[int, int], ...]] | None:
        if mask == full_mask:
            return "", ()
        best: tuple[str, tuple[tuple[int, int], ...]] | None = None
        for index, run_type in enumerate(types):
            if mask & (1 << index) or run_type[0] == previous_value:
                continue
            tail = solve(mask | (1 << index), run_type[0])
            if tail is None:
                continue
            candidate = block(run_type) + tail[0], (run_type,) + tail[1]
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best

    return solve(0, 0)


def exact_term(n: int) -> tuple[int, str, tuple[tuple[int, int], ...]]:
    """Compute a(n) exactly using the minimum-length theorem and lexicographic DP."""
    if n == 0:
        return 0, "", ()
    q, forced, boundary, choose = boundary_for(n)
    best: tuple[str, tuple[tuple[int, int], ...]] | None = None
    for selected in combinations(boundary, choose):
        types = tuple(forced + list(selected))
        candidate = least_word_for_types(types)
        if candidate is not None and (best is None or candidate[0] < best[0]):
            best = candidate
    if best is None:
        raise RuntimeError(f"no minimum-length construction found for n={n}, boundary={q}")
    return int(best[0], 2), best[0], best[1]


def minimum_length(n: int) -> int:
    """Sum of the first n entries of A061017."""
    if n == 0:
        return 0
    q, forced, _boundary, choose = boundary_for(n)
    return sum(value * multiplicity for value, multiplicity in forced) + choose * q


def verify(n: int, value: int, word: str, ordering: tuple[tuple[int, int], ...]) -> None:
    """Check the structural certificate returned for a(n)."""
    if n == 0:
        _require(value == 0 and word == "" and ordering == (), "n=0 certificate")
        return
    _require(value == int(word, 2), "word does not encode value")
    _require(word == bin(value)[2:], "word is not the binary expansion of value")
    _require(len(word) == minimum_length(n) == value.bit_length(), "length mismatch")
    parts = composition(value)
    run_types = distinct_run_types(parts)
    _require(len(run_types) == n, "wrong number of distinct run types")
    _require(run_types == set(ordering), "ordering does not match run types")
    _require(len(ordering) == len(set(ordering)) == n, "ordering not distinct")
    _require(all(ordering[i][0] != ordering[i + 1][0] for i in range(n - 1)),
             "adjacent runs share a value")
    _require("".join(block(run_type) for run_type in ordering) == word,
             "blocks do not reconstruct the word")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-n", type=int, default=16, help="largest index to compute (default: 16)")
    parser.add_argument("--details", action="store_true", help="also print binary words and run-type orderings")
    args = parser.parse_args()
    if args.max_n < 0:
        parser.error("--max-n must be nonnegative")

    print(" n  bit-length  a(n)")
    print("--  ----------  ----------------------")
    for n in range(args.max_n + 1):
        value, word, ordering = exact_term(n)
        verify(n, value, word, ordering)
        if n < len(EXPECTED):
            _require(value == EXPECTED[n], f"a({n})={value} != expected {EXPECTED[n]}")
        print(f"{n:2d}  {minimum_length(n):10d}  {value}")
        if args.details and n:
            print(f"    binary: {word}")
            print(f"    runs:   {ordering}")
    print("All structural certificates and recorded-term checks passed.")


if __name__ == "__main__":
    main()
