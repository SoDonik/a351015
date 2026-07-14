#!/usr/bin/env python3
"""Independent prefix-language verifier for claimed A351015 terms.

This is deliberately *not* the suffix-minimizing recurrence used by
``a351015_exact.py`` or ``a351015_fast_exact.cpp``.  It treats every
minimum-length composition as a word in a finite prefix language.  For each
bit of a claimed word it retains every extendable automaton state producing
that prefix.  Whenever the claimed bit is 1, it separately asks whether a 0
at that position has any completion.  If none does at every such position,
no lexicographically smaller word in the language exists.

The verifier uses the minimum-length structural theorem proved in the
accompanying manuscript:

* n distinct run types have total cost at least the sum of the n least
  products v*l;
* equality forces each cheaper type once and the required number of types at
  the boundary product;
It independently reconstructs the theorem's finite forced/boundary type data.
Completion of a partial prefix is decided by a separate exact recursion on
the remaining *value counts*, without optimizing or comparing binary suffixes.

Boundary subsets are exhaustively enumerated: the four product-8 boundary
types give 4, 6, 4, and 1 choices for n=17, 18, 19, and 20 respectively.

Only the Python standard library is required.  Typical invocation:

    python a351015_independent_verify.py
    python a351015_independent_verify.py 20
"""

from __future__ import annotations

import argparse
import itertools
import time
from functools import lru_cache


CLAIMS = {
    17: 303421421018735347335039,
    18: 77675883218955741073080191,
    19: 19885026103583920149103476607,
    20: 5090566682637483446698432134911,
}

RunType = tuple[int, int]
# State: (used-type mask, preceding/current value, active type, next bit offset).
# active == -1 means that the state is exactly between two run blocks.
State = tuple[int, int, int, int]


def require(condition: bool, message: str) -> None:
    """Raise an exception even when Python is run with optimization enabled."""
    if not condition:
        raise AssertionError(message)


def block(run_type: RunType) -> str:
    """Return the standard binary block for one run of type (v,l)."""
    value, multiplicity = run_type
    return ("1" + "0" * (value - 1)) * multiplicity


def decode_runs(word: str) -> tuple[RunType, ...]:
    """Decode a binary word directly into its canonical consecutive runs."""
    require(bool(word) and word[0] == "1", "not a positive binary expansion")
    parts: list[int] = []
    for bit in word:
        if bit == "1":
            parts.append(1)
        else:
            require(bool(parts), "zero before the first part")
            parts[-1] += 1

    runs: list[RunType] = []
    for value, group in itertools.groupby(parts):
        runs.append((value, sum(1 for _ in group)))
    return tuple(runs)


def minimum_structure(n: int) -> tuple[int, tuple[RunType, ...], tuple[RunType, ...], int, int]:
    """Return q, forced types, boundary types, number selected, and lower bound."""
    require(n >= 1, "n must be positive")
    q = 1
    while sum(q // value for value in range(1, q + 1)) < n:
        q += 1

    forced = tuple(
        (value, multiplicity)
        for value in range(1, q + 1)
        for multiplicity in range(1, q + 1)
        if value * multiplicity < q
    )
    boundary = tuple(
        (value, q // value) for value in range(1, q + 1) if q % value == 0
    )
    choose = n - len(forced)
    lower_bound = sum(value * multiplicity for value, multiplicity in forced) + q * choose

    # Audit the order-statistic calculation without relying on a sequence table.
    sample = sorted(
        value * multiplicity
        for value in range(1, q + 1)
        for multiplicity in range(1, q + 1)
        if value * multiplicity <= q
    )
    require(len(sample) >= n, "cost sample is too short")
    require(sum(sample[:n]) == lower_bound, "minimum-cost calculation disagrees")
    require(0 < choose <= len(boundary), "invalid boundary count")
    return q, forced, boundary, choose, lower_bound


@lru_cache(maxsize=None)
def labels_can_follow(counts: tuple[int, ...], previous_value: int) -> bool:
    """Exactly decide whether the remaining value labels can follow ``previous``.

    This Boolean first-label recursion is intentionally separate from the
    producer's type-mask recurrence: types of one value are interchangeable
    here because this test asks only whether adjacent block values can differ.
    It neither constructs nor minimizes a binary word.
    """
    require(bool(counts) and counts[0] == 0, "value-count sentinel must be zero")
    require(0 <= previous_value < len(counts), "previous value is out of range")
    if not any(counts[1:]):
        return True
    for value in range(1, len(counts)):
        if value == previous_value or counts[value] == 0:
            continue
        reduced = list(counts)
        reduced[value] -= 1
        if labels_can_follow(tuple(reduced), value):
            return True
    return False


class PrefixAudit:
    """Nondeterministic prefix automaton for every minimum-cost candidate."""

    def __init__(self, n: int) -> None:
        q, forced, boundary, choose, lower_bound = minimum_structure(n)
        self.n = n
        self.q = q
        self.choose = choose
        self.lower_bound = lower_bound
        self.types = forced + boundary
        self.words = tuple(block(run_type) for run_type in self.types)
        self.values = tuple(run_type[0] for run_type in self.types)
        self.forced_count = len(forced)
        self.forced_mask = (1 << self.forced_count) - 1
        self.all_mask = (1 << len(self.types)) - 1
        self.boundary_mask = self.all_mask ^ self.forced_mask

        # Small static lists avoid repeatedly inspecting all masks in the
        # completion test.  q=8 gives 16 forced and four boundary types.
        self.forced_indices = tuple(range(self.forced_count))
        self.boundary_indices = tuple(range(self.forced_count, len(self.types)))

    @lru_cache(maxsize=None)
    def can_finish(self, used: int, previous_value: int) -> bool:
        """Whether some choice/order of all still-required blocks can finish.

        This is a Boolean label-count test, not an optimization recurrence.
        Every still-available boundary subset of the required size is tried.
        For a fixed subset, ``labels_can_follow`` exhausts the possible next
        values by count; it never examines a binary suffix.
        """
        if used & ~self.all_mask:
            return False
        if (used & self.forced_mask) == self.forced_mask:
            forced_remaining: tuple[int, ...] = ()
        else:
            forced_remaining = tuple(
                i for i in self.forced_indices if not (used >> i) & 1
            )

        used_boundary = (used & self.boundary_mask).bit_count()
        needed = self.choose - used_boundary
        if needed < 0:
            return False
        available_boundary = tuple(
            i for i in self.boundary_indices if not (used >> i) & 1
        )
        if needed > len(available_boundary):
            return False

        for selected in itertools.combinations(available_boundary, needed):
            counts = [0] * (self.q + 1)
            for index in forced_remaining:
                counts[self.values[index]] += 1
            for index in selected:
                counts[self.values[index]] += 1
            if labels_can_follow(tuple(counts), previous_value):
                return True
        return False

    def step(self, frontier: set[State], wanted_bit: str) -> set[State]:
        """Advance every state by one bit and discard states with no completion."""
        result: set[State] = set()
        for used, previous_value, active, offset in frontier:
            if active >= 0:
                word = self.words[active]
                if word[offset] != wanted_bit:
                    continue
                if offset + 1 == len(word):
                    candidate = (used, previous_value, -1, 0)
                else:
                    candidate = (used, previous_value, active, offset + 1)
                if self.can_finish(used, previous_value):
                    result.add(candidate)
                continue

            # Every run block begins with 1, so a 0 cannot start a block.
            if wanted_bit == "0":
                continue
            used_boundary = (used & self.boundary_mask).bit_count()
            for index, value in enumerate(self.values):
                bit = 1 << index
                if used & bit or value == previous_value:
                    continue
                if bit & self.boundary_mask and used_boundary == self.choose:
                    continue
                next_used = used | bit
                if not self.can_finish(next_used, value):
                    continue
                if len(self.words[index]) == 1:
                    candidate = (next_used, value, -1, 0)
                else:
                    candidate = (next_used, value, index, 1)
                result.add(candidate)
        return result

    def is_terminal(self, state: State) -> bool:
        used, _previous, active, _offset = state
        return (
            active == -1
            and (used & self.forced_mask) == self.forced_mask
            and (used & self.boundary_mask).bit_count() == self.choose
        )

    def audit_claim(self, value: int) -> dict[str, object]:
        """Verify positivity, the length lower bound, and prefix minimality."""
        cache_at_start = self.can_finish.cache_info().currsize
        label_cache_at_start = labels_can_follow.cache_info().currsize
        word = bin(value)[2:]
        require(value > 0, "target must be positive")
        require(value.bit_length() == self.lower_bound, "target misses length lower bound")

        # Positive/certificate half, decoded from the claimed integer itself.
        runs = decode_runs(word)
        require(len(runs) == self.n, f"target has {len(runs)} runs, expected {self.n}")
        require(len(set(runs)) == self.n, "target repeats a run type")
        require(all(runs[i][0] != runs[i + 1][0] for i in range(len(runs) - 1)),
                "decoded adjacent runs have equal values")
        require("".join(block(run_type) for run_type in runs) == word,
                "decoded blocks do not reconstruct target")

        forced_set = set(self.types[: self.forced_count])
        boundary_set = set(self.types[self.forced_count :])
        run_set = set(runs)
        require(forced_set <= run_set, "target omits a forced minimum-cost type")
        require(len(run_set & boundary_set) == self.choose,
                "target has the wrong number of boundary types")
        require(run_set <= forced_set | boundary_set,
                "target uses a type above the minimum-cost boundary")

        # Prefix-minimality half.  At a claimed 1, a live alternative obtained
        # by writing 0 would be a concrete witness that the claim is too large.
        frontier: set[State] = {(0, 0, -1, 0)}
        require(self.can_finish(0, 0), "minimum-cost language is unexpectedly empty")
        checked_zero_branches = 0
        max_frontier = 1
        state_total = 1
        for position, wanted in enumerate(word, start=1):
            if wanted == "1":
                smaller = self.step(frontier, "0")
                require(
                    not smaller,
                    f"smaller completable prefix exists at bit {position}: {word[:position-1]}0",
                )
                checked_zero_branches += 1
            frontier = self.step(frontier, wanted)
            require(frontier, f"claimed prefix becomes infeasible at bit {position}")
            max_frontier = max(max_frontier, len(frontier))
            state_total += len(frontier)

        terminal = {state for state in frontier if self.is_terminal(state)}
        require(frontier == terminal, "claimed word ends before or after a complete candidate")
        return {
            "word": word,
            "runs": runs,
            "zero_branches": checked_zero_branches,
            "terminal_states": len(terminal),
            "max_frontier": max_frontier,
            "state_visits": state_total,
            "completion_states": self.can_finish.cache_info().currsize - cache_at_start,
            "label_states": labels_can_follow.cache_info().currsize - label_cache_at_start,
        }


def verify_one(n: int, value: int) -> None:
    started = time.perf_counter()
    audit = PrefixAudit(n)
    result = audit.audit_claim(value)
    elapsed = time.perf_counter() - started
    runs = result["runs"]
    require(isinstance(runs, tuple), "internal run-certificate type error")
    print(f"a({n}) = {value}")
    print(
        f"  PASS: positive certificate has {len(runs)} distinct runs; "
        f"length {audit.lower_bound} is the cost lower bound"
    )
    print(
        f"  PASS: at {result['zero_branches']} target-1 positions, no "
        f"lexicographically-smaller 0-alternative had a completion"
    )
    print(
        f"  prefix states: max {result['max_frontier']:,}; "
        f"visited {result['state_visits']:,}; "
        f"completion states {result['completion_states']:,}; "
        f"label-count states {result['label_states']:,}"
    )
    print(f"  terminal parses: {result['terminal_states']}; time {elapsed:.3f} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "n",
        type=int,
        nargs="*",
        choices=sorted(CLAIMS),
        help="indices to verify (default: 17 18 19 20)",
    )
    args = parser.parse_args()
    selected = args.n or sorted(CLAIMS)
    overall = time.perf_counter()
    for n in selected:
        verify_one(n, CLAIMS[n])
    print(f"All independent prefix audits passed in {time.perf_counter() - overall:.3f} s.")


if __name__ == "__main__":
    main()
