#!/usr/bin/env python3
"""Compute OEIS A351015 by an exact polynomial binary-prefix oracle.

Algorithm: the anonymous referee's report dated October 18, 2026, Section 2,
including the preceding-value criterion (R1), optional-boundary test (R2),
and arbitrary-binary-prefix construction. Implementation: OpenAI Codex,
prepared for the author's review. This file makes no claim of priority for
the algorithm and imports none of the earlier producing or verifying programs.

The mathematical input is the characterization of minimum-length run-type
sets: every type (v, l) with v*l < q is required once, and exactly r types
with v*l == q are selected once. Adjacent run values must differ. A prefix
can end partway through a part or a run; this program explicitly tries every
possible eventual active run type before applying the count-capacity test.

For one term, the straightforward construction uses O(n*L*(L+n)) elementary
operations, where L is the minimum binary length. This is not a bit-operation
bound. Only the Python standard library is required; Python 3.10 or later.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from itertools import groupby


RunType = tuple[int, int]


def _nonnegative_index(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError("n must be an integer")
    if n < 0:
        raise ValueError("n must be nonnegative")


def _validated_counts(counts: Sequence[int], previous_value: int) -> tuple[int, ...]:
    result = tuple(counts)
    if not result:
        raise ValueError("counts must include the zero-value sentinel")
    for count in result:
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError("counts must be integers")
        if count < 0:
            raise ValueError("counts must be nonnegative")
    if result[0] != 0:
        raise ValueError("counts[0] must be zero")
    if not isinstance(previous_value, int) or isinstance(previous_value, bool):
        raise TypeError("previous_value must be an integer")
    if not 0 <= previous_value < len(result):
        raise ValueError("previous_value is outside the count array")
    return result


def labels_can_follow(counts: Sequence[int], previous_value: int = 0) -> bool:
    """Apply (R1) to label counts indexed by value, with counts[0] == 0.

    The result says whether every supplied label can be used once without
    equal neighbors, starting with a value different from previous_value.
    The value 0 means that there is no preceding run. Malformed arguments
    raise TypeError or ValueError; empty remaining multisets are feasible.
    """
    checked = _validated_counts(counts, previous_value)
    total = sum(checked)
    return all(
        2 * count <= total + (value != previous_value)
        for value, count in enumerate(checked)
        if value != 0
    )


def _boundary_capacity(
    forced_counts: Sequence[int],
    optional_values: Iterable[int],
    remaining_boundary: int,
    previous_value: int,
) -> bool:
    """Apply (R2) to already validated internal data, without enumeration."""
    # A prefix can already have used too many boundary types. This test must
    # precede calculation of capacities from the number of remaining runs.
    if remaining_boundary < 0:
        return False
    total = sum(forced_counts) + remaining_boundary
    ordinary_capacity = (total + 1) // 2
    preceding_capacity = total // 2
    for value, count in enumerate(forced_counts):
        capacity = preceding_capacity if value == previous_value else ordinary_capacity
        if count > capacity:
            return False
    available_slots = sum(
        forced_counts[value]
        < (preceding_capacity if value == previous_value else ordinary_capacity)
        for value in optional_values
    )
    return remaining_boundary <= available_slots


def boundary_can_finish(
    forced_counts: Sequence[int],
    optional_values: Iterable[int],
    remaining_boundary: int,
    previous_value: int = 0,
) -> bool:
    """Apply (R2), choosing exactly remaining_boundary optional value labels.

    forced_counts uses the same zero-sentinel convention as labels_can_follow.
    Each optional value must be a distinct positive index into forced_counts:
    the cost-q boundary has at most one type per value. A negative integer
    remaining_boundary returns False. Malformed arguments raise TypeError or
    ValueError. No boundary subsets or label permutations are enumerated.
    """
    checked = _validated_counts(forced_counts, previous_value)
    if not isinstance(remaining_boundary, int) or isinstance(remaining_boundary, bool):
        raise TypeError("remaining_boundary must be an integer")
    optional = tuple(optional_values)
    seen = [False] * len(checked)
    for value in optional:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("optional values must be integers")
        if not 0 < value < len(checked):
            raise ValueError("optional value is outside the positive count indices")
        if seen[value]:
            raise ValueError("optional values must be distinct")
        seen[value] = True
    return _boundary_capacity(checked, optional, remaining_boundary, previous_value)


def _decode_parts(prefix: str) -> list[int]:
    """Decode a validated positive prefix; its last part is still unfinished."""
    parts: list[int] = []
    for bit in prefix:
        if bit == "1":
            parts.append(1)
        else:
            parts[-1] += 1
    return parts


def _group_runs(parts: Sequence[int]) -> tuple[RunType, ...]:
    return tuple((value, sum(1 for _ in run)) for value, run in groupby(parts))


class PrefixOracle:
    """Exact extendability oracle for arbitrary binary prefixes of a(n).

    Public metadata: q is the cost cutoff; forced and boundary are tuples of
    run types; choose is the number of boundary types required; length is L(n).
    At n == 0 these are 0, (), (), 0, and 0, respectively.

    feasible(prefix) raises TypeError for a non-string and ValueError for any
    character other than '0' or '1'. Well-formed binary strings that begin
    with '0' or exceed length are infeasible. The empty prefix is feasible;
    when n == 0 it is the only feasible prefix.
    """

    def __init__(self, n: int) -> None:
        _nonnegative_index(n)
        self.n = n
        if n == 0:
            self.q = 0
            self.forced: tuple[RunType, ...] = ()
            self.boundary: tuple[RunType, ...] = ()
            self.choose = 0
            self.length = 0
        else:
            q = 1
            while sum(q // value for value in range(1, q + 1)) < n:
                q += 1
            self.q = q
            self.forced = tuple(
                (value, multiplicity)
                for value in range(1, q + 1)
                for multiplicity in range(1, (q - 1) // value + 1)
            )
            self.boundary = tuple(
                (value, q // value)
                for value in range(1, q + 1)
                if q % value == 0
            )
            self.choose = n - len(self.forced)
            self.length = (
                sum(value * multiplicity for value, multiplicity in self.forced)
                + q * self.choose
            )

        self._types = self.forced + self.boundary
        # Dense indices for every type of cost <= q give deterministic array
        # access. Within each value v, the index of (v,l) is offset[v] + l - 1.
        offsets = [0] * (self.q + 1)
        type_count = 0
        for value in range(1, self.q + 1):
            offsets[value] = type_count
            type_count += self.q // value
        self._type_offsets = tuple(offsets)
        self._type_count = type_count
        forced_counts = [0] * (self.q + 1)
        for value, _multiplicity in self.forced:
            forced_counts[value] += 1
        self._forced_counts = tuple(forced_counts)

    def feasible(self, prefix: str) -> bool:
        """Return whether a minimum-cost full word begins with prefix.

        The last decoded part is not treated as complete. For each eventual
        active type (v,l), h counts trailing fixed parts equal to that eventual
        v, which need not equal the current size of the last decoded part.
        """
        if not isinstance(prefix, str):
            raise TypeError("prefix must be a string")
        if any(bit not in "01" for bit in prefix):
            raise ValueError("prefix must contain only '0' and '1'")
        if len(prefix) > self.length or prefix.startswith("0"):
            return False
        if not prefix:
            return True

        parts = _decode_parts(prefix)
        current_size = parts[-1]
        fixed_parts = parts[:-1]
        for active in self._types:
            value, multiplicity = active
            if value < current_size:
                continue

            # h uses the eventual value, not current_size: for prefix '101',
            # active (2,2) absorbs the fixed part 2 and the unfinished part 1.
            split = len(fixed_parts)
            while split > 0 and fixed_parts[split - 1] == value:
                split -= 1
            h = len(fixed_parts) - split
            if multiplicity < h + 1:
                continue
            completed = _group_runs(fixed_parts[:split])

            # Reject duplicates before recording a second occurrence in C.
            # Converting the run list directly to a set would lose this fact;
            # a dense Boolean array instead records the used type indices.
            used = [False] * self._type_count
            forced_counts = list(self._forced_counts)
            remaining_boundary = self.choose
            valid = True
            for run_type in (*completed, active):
                run_value, run_length = run_type
                cost = run_value * run_length
                if cost > self.q:
                    valid = False
                    break
                index = self._type_offsets[run_value] + run_length - 1
                if used[index]:
                    valid = False
                    break
                used[index] = True
                if cost < self.q:
                    forced_counts[run_value] -= 1
                else:
                    remaining_boundary -= 1
            if not valid:
                continue
            if remaining_boundary < 0:
                continue
            optional_values = (
                run_value
                for run_value, run_length in self.boundary
                if not used[self._type_offsets[run_value] + run_length - 1]
            )
            if _boundary_capacity(forced_counts, optional_values, remaining_boundary, value):
                return True
        return False


def minimum_length(n: int) -> int:
    """Return the sum of the n smallest ordered-pair products v*l."""
    return PrefixOracle(n).length


def exact_term(n: int) -> tuple[int, str, tuple[RunType, ...]]:
    """Return a(n), its binary word, and its canonical ordered run types."""
    oracle = PrefixOracle(n)
    if n == 0:
        return 0, "", ()
    word = "1"
    if not oracle.feasible(word):
        raise RuntimeError("the minimum-cost language is unexpectedly empty")
    while len(word) < oracle.length:
        with_zero = word + "0"
        if oracle.feasible(with_zero):
            word = with_zero
        else:
            word += "1"
            if not oracle.feasible(word):
                raise RuntimeError("neither next bit has a feasible completion")
    ordering = _group_runs(_decode_parts(word))
    if len(ordering) != n or len(set(ordering)) != n:
        raise RuntimeError("constructed word fails the distinct-run certificate")
    return int(word, 2), word, ordering


def _decimal(value: int) -> str:
    """Format without changing Python's global decimal-conversion safeguard."""
    try:
        return str(value)
    except ValueError:
        # Python 3.11+ can limit int-to-decimal conversions. Base-10^9 pieces
        # remain below that limit and keep large exact CLI results printable.
        pieces: list[int] = []
        while value:
            value, piece = divmod(value, 1_000_000_000)
            pieces.append(piece)
        return str(pieces[-1]) + "".join(f"{piece:09d}" for piece in reversed(pieces[:-1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    indices = parser.add_mutually_exclusive_group()
    indices.add_argument("--max-n", type=int, default=20,
                         help="compute indices 0 through this value (default: 20)")
    indices.add_argument("--n", type=int, help="compute only this index")
    parser.add_argument("--details", action="store_true",
                        help="also print binary words and ordered run types")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="emit a JSON array including all certificates; values are decimal strings")
    args = parser.parse_args()
    last = args.n if args.n is not None else args.max_n
    if last < 0:
        parser.error("indices must be nonnegative")
    selected = (args.n,) if args.n is not None else range(args.max_n + 1)

    records: list[dict[str, object]] = []
    if not args.json_output:
        print(" n  bit-length  a(n)")
        print("--  ----------  ----------------------")
    for n in selected:
        value, word, ordering = exact_term(n)
        decimal_value = _decimal(value)
        if args.json_output:
            records.append({
                "n": n,
                "length": len(word),
                "value": decimal_value,
                "word": word,
                "run_types": ordering,
            })
        else:
            print(f"{n:2d}  {len(word):10d}  {decimal_value}")
            if args.details:
                print(f"    binary: {word}")
                print(f"    runs:   {ordering}")
    if args.json_output:
        print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
