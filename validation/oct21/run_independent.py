#!/usr/bin/env python3
"""Reproduce the independent October 21 implementation and search checks.

Release adaptation: command metadata is portable, hostname is omitted, and
the manuscript originally read is identified by its retained SHA-256 rather
than a runtime dependency on the private draft file. Numerical checks unchanged.

Run from the package directory:
  python3 validation/oct21/run_independent.py --max-n 120 \
      --exact-max-n 20 --exhaustive-max-n 6

The polynomial implementation was written and hashed before the producer
was read.  The producer is run only as a separate comparison subprocess.
The exact finite-state search below uses explicit boundary subsets and
recursive label orderings, without either capacity inequality.  It relies
on the manuscript's minimum-type-set proposition, not on the prefix test.
Raw-definition checks decode every tested integer/word directly and rely
on neither the type-set proposition nor the capacity lemmas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import shlex
import subprocess
import sys
import time
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from independent_prefix import PrefixConstruction

REVISION = Path(__file__).resolve().parents[2]
OUTPUT = REVISION / "validation/results/oct21/independent"
MANUSCRIPT_READ_SHA256 = "3fe9161f286bca488a62ad72254820e545d715bfa8c8e0b473cfab6173f15b74"


def dump(name: str, value: object) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(json.dumps(value, indent=2) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definition_runs(word: str) -> tuple[tuple[int, int], ...]:
    """Read bits sequentially, separately from the polynomial split decoder."""
    if not word:
        return ()
    if word[0] != "1" or any(bit not in "01" for bit in word):
        raise ValueError("invalid complete positive binary encoding")
    parts: list[int] = []
    current_part = 0
    for bit in word:
        if bit == "1":
            if current_part:
                parts.append(current_part)
            current_part = 1
        else:
            current_part += 1
    parts.append(current_part)
    runs: list[tuple[int, int]] = []
    for value in parts:
        if runs and runs[-1][0] == value:
            runs[-1] = (value, runs[-1][1] + 1)
        else:
            runs.append((value, 1))
    return tuple(runs)


def generate_independent(max_n: int) -> list[dict[str, object]]:
    records = []
    for n in range(max_n + 1):
        oracle = PrefixConstruction(n)
        start = time.perf_counter()
        word = oracle.least_word()
        elapsed = time.perf_counter() - start
        runs = definition_runs(word)
        assert len(runs) == len(set(runs)) == n
        assert len(word) == oracle.data.bit_length
        records.append({
            "n": n, "word": word, "value": str(int(word, 2) if word else 0),
            "length": len(word), "run_types": runs,
            "elapsed_seconds": elapsed, "prefix_queries": oracle.queries,
            "active_proposals": oracle.active_proposals,
        })
        if n % 10 == 0 or n == max_n:
            print(f"Independent construction: n={n}, length={len(word)}, seconds={elapsed:.6f}", flush=True)
    dump("independent_terms.json", records)
    return records


def compare_producer(records: list[dict[str, object]]) -> dict[str, object]:
    command = [sys.executable, "code/a351015_polynomial.py", "--max-n",
               str(len(records) - 1), "--json"]
    start = time.perf_counter()
    completed = subprocess.run(command, cwd=REVISION, text=True, capture_output=True)
    elapsed = time.perf_counter() - start
    (OUTPUT / "producer_stdout.json").write_text(completed.stdout)
    (OUTPUT / "producer_stderr.txt").write_text(completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError(f"producer exited {completed.returncode}: {completed.stderr}")
    producer_records = json.loads(completed.stdout)
    assert len(producer_records) == len(records)
    comparisons = []
    for independent, producer in zip(records, producer_records):
        row = {
            "n": independent["n"],
            "integer_equal": int(independent["value"]) == int(producer["value"]),
            "decimal_string_equal": independent["value"] == producer["value"],
            "binary_string_equal": independent["word"] == producer["word"],
            "length_equal": independent["length"] == producer["length"],
            "raw_decoded_runs_equal": list(map(list, independent["run_types"])) == producer["run_types"],
        }
        assert independent["n"] == producer["n"]
        assert all(value for key, value in row.items() if key != "n"), row
        comparisons.append(row)
    result = {
        "command": shlex.join(["python3", *command[1:]]), "cwd": ".",
        "returncode": completed.returncode, "elapsed_seconds": elapsed,
        "indices": list(range(len(records))), "comparisons": comparisons,
        "stdout": "producer_stdout.json", "stderr": "producer_stderr.txt",
        "scope": "Same proved polynomial algorithm, separately implemented; agreement is not an independent proof of the lemmas.",
    }
    dump("producer_comparison.json", result)
    print(f"Producer comparison: all {len(records)} integer and binary-string equalities passed.", flush=True)
    return result


def independently_enumerated_type_sets(n: int):
    """Derive the cutoff from a sorted square, not the polynomial module."""
    if n == 0:
        yield ()
        return
    pairs = [(v, ell) for v in range(1, n + 1) for ell in range(1, n + 1)]
    pairs.sort(key=lambda pair: (pair[0] * pair[1], pair))
    q = pairs[n - 1][0] * pairs[n - 1][1]
    forced = tuple(pair for pair in pairs if pair[0] * pair[1] < q)
    boundary = tuple(pair for pair in pairs if pair[0] * pair[1] == q)
    for selected in combinations(boundary, n - len(forced)):
        yield tuple(sorted(forced + selected))


def exact_type_language_minimum(types: tuple[tuple[int, int], ...]):
    """Find a finite encoding language's minimum, without count inequalities.

    A state records a residual type mask, an active whole type, and the next
    bit within that type.  At every bit retain all states with the least bit
    that has some completion.  Completion is decided solely by exhaustive
    recursive ordering of remaining value counts (memoized), not by R1/R2.
    All types of one value are interchangeable for this yes/no order query;
    their identities and differing blocks are retained by the bit automaton.
    """
    if not types:
        return "", {"label_states": 1, "type_mask_states": 1, "automaton_peak": 1}
    labels = tuple(sorted({v for v, _ in types}))
    label_number = {value: i for i, value in enumerate(labels)}
    label_indices = tuple(label_number[value] for value, _ in types)
    blocks = tuple(("1" + "0" * (value - 1)) * copies for value, copies in types)

    @lru_cache(maxsize=None)
    def can_order(counts: tuple[int, ...], previous: int) -> bool:
        if not any(counts):
            return True
        # There are deliberately no maximum-count or capacity shortcuts.
        for label, count in enumerate(counts):
            if label != previous and count:
                remainder = list(counts)
                remainder[label] -= 1
                if can_order(tuple(remainder), label):
                    return True
        return False

    @lru_cache(maxsize=None)
    def counts_of(mask: int) -> tuple[int, ...]:
        counts = [0] * len(labels)
        while mask:
            bit = mask & -mask
            index = bit.bit_length() - 1
            counts[label_indices[index]] += 1
            mask ^= bit
        return tuple(counts)

    def start_blocks(mask: int, previous: int):
        for index, label in enumerate(label_indices):
            bit = 1 << index
            if mask & bit and label != previous:
                remaining = mask ^ bit
                if can_order(counts_of(remaining), label):
                    yield (remaining, index, 0)

    full_mask = (1 << len(types)) - 1
    if not can_order(counts_of(full_mask), -1):
        return None, {
            "label_states": can_order.cache_info().currsize,
            "type_mask_states": counts_of.cache_info().currsize,
            "automaton_peak": 0,
        }
    states = set(start_blocks(full_mask, -1))
    peak = len(states)
    word = ""
    total_length = sum(len(block) for block in blocks)
    terminal = (0, -1, 0)
    for position in range(total_length):
        assert states and terminal not in states
        bit = min(blocks[index][offset] for _, index, offset in states)
        word += bit
        successors = set()
        for remaining, index, offset in states:
            if blocks[index][offset] != bit:
                continue
            if offset + 1 < len(blocks[index]):
                successors.add((remaining, index, offset + 1))
            elif remaining:
                successors.update(start_blocks(remaining, label_indices[index]))
            else:
                assert position == total_length - 1
                successors.add(terminal)
        states = successors
        peak = max(peak, len(states))
    assert states == {terminal}
    return word, {
        "label_states": can_order.cache_info().currsize,
        "type_mask_states": counts_of.cache_info().currsize,
        "automaton_peak": peak,
    }


def exact_search(max_n: int, polynomial_records: list[dict[str, object]]):
    records = []
    for n in range(max_n + 1):
        started = time.perf_counter()
        searches = []
        words = []
        for types in independently_enumerated_type_sets(n):
            word, stats = exact_type_language_minimum(types)
            searches.append({"types": types, "word": word, **stats})
            if word is not None:
                words.append(word)
        minimum = min(words)
        elapsed = time.perf_counter() - started
        assert minimum == polynomial_records[n]["word"], n
        assert len(set(definition_runs(minimum))) == n
        records.append({
            "n": n, "word": minimum, "value": str(int(minimum, 2) if minimum else 0),
            "length": len(minimum), "binary_string_equal": True,
            "integer_equal": True, "elapsed_seconds": elapsed,
            "candidate_type_sets": searches,
        })
    result = {
        "scope": "Exact finite-state search over all structurally admissible type sets, with memoized recursive label ordering. Uses the structural proposition; uses neither capacity formula, the rearrangement inequalities, nor the arbitrary-prefix parser.",
        "indices": list(range(max_n + 1)), "records": records,
        "elapsed_seconds_sum": sum(row["elapsed_seconds"] for row in records),
    }
    dump("exact_search.json", result)
    print(f"Formula-free exact ordering search: all indices 0..{max_n} agree.", flush=True)
    return result


def definition_checks(max_n: int, polynomial_records: list[dict[str, object]]):
    start = time.perf_counter()
    upper = int(polynomial_records[max_n]["value"])
    first = {}
    for value in range(upper + 1):
        word = bin(value)[2:] if value else ""
        distinct = len(set(definition_runs(word)))
        first.setdefault(distinct, value)
    for n in range(max_n + 1):
        assert first[n] == int(polynomial_records[n]["value"]), (n, first)
    scan_seconds = time.perf_counter() - start
    cases = []
    for n in range(max_n + 1):
        start = time.perf_counter()
        length = first[n].bit_length()
        if n == 0:
            language = [""]
            words_decoded = 1
        else:
            language = []
            words_decoded = 1 << (length - 1)
            for value in range(1 << (length - 1), 1 << length):
                word = bin(value)[2:]
                if len(set(definition_runs(word))) == n:
                    language.append(word)
        true_prefixes = {word[:size] for word in language for size in range(len(word) + 1)}
        oracle = PrefixConstruction(n)
        tested = 0
        for size in range(length + 1):
            for value in range(1 << size):
                prefix = format(value, f"0{size}b") if size else ""
                expected = prefix in true_prefixes
                assert oracle.feasible(prefix) == expected, (n, prefix, expected)
                tested += 1
        for invalid in ("2", "10x", " 1", "1\n", "1" * (length + 1), "0" * (length + 1)):
            assert not oracle.feasible(invalid), (n, invalid)
        cases.append({
            "n": n, "length_from_raw_first_occurrence": length,
            "complete_positive_words_decoded": words_decoded,
            "qualifying_words": len(language), "true_prefixes": len(true_prefixes),
            "binary_prefixes_checked": tested,
            "additional_invalid_or_overlong_prefixes_checked": 6,
            "language_sha256": hashlib.sha256("\n".join(language).encode()).hexdigest(),
            "elapsed_seconds": time.perf_counter() - start,
        })
    examples = [
        {"n": 2, "prefix": "11", "expected": True, "reason": "The current final part can grow to value 2.", "completion": "110"},
        {"n": 6, "prefix": "101", "expected": True, "reason": "Eventual active type (2,2) absorbs the preceding fixed part 2.", "completion": "101011001110111"},
        {"n": 4, "prefix": "1001100", "expected": False, "reason": "Any active type repeats the already completed type (3,1)."},
        {"n": 5, "prefix": "100110010", "expected": False, "reason": "The completed type (3,1) occurs twice; absorbing the last fixed run would exceed the cutoff."},
    ]
    for example in examples:
        assert PrefixConstruction(example["n"]).feasible(example["prefix"]) == example["expected"]
        if "completion" in example:
            word = example["completion"]
            assert word.startswith(example["prefix"])
            assert len(set(definition_runs(word))) == example["n"]
            assert len(word) == PrefixConstruction(example["n"]).data.bit_length
    result = {
        "scope": "Every integer in the stated scan range and every positive word of each stated length are decoded from the raw definition. Every binary prefix up to that length, including leading-zero strings, is compared with the complete raw language. No structural restriction or capacity criterion is used to build these languages.",
        "scan": {"inclusive_lower": 0, "inclusive_upper": upper,
                 "integers_decoded": upper + 1, "first_occurrences": first,
                 "elapsed_seconds": scan_seconds},
        "prefix_languages": cases,
        "total_binary_prefixes_checked": sum(row["binary_prefixes_checked"] for row in cases),
        "examples": examples,
    }
    dump("definition_checks.json", result)
    print(f"Raw definition: {upper + 1} integers and {result['total_binary_prefixes_checked']} binary prefixes checked.", flush=True)
    return result


def dp_example():
    def describe(types):
        @lru_cache(maxsize=None)
        def suffix(unused, previous):
            if not unused:
                return ""
            alternatives = []
            for run in unused:
                value, copies = run
                if value != previous:
                    rest = tuple(candidate for candidate in unused if candidate != run)
                    tail = suffix(rest, value)
                    if tail is not None:
                        alternatives.append(("1" + "0" * (value - 1)) * copies + tail)
            return min(alternatives, default=None)

        def branches(unused, previous):
            results = []
            for run in unused:
                if run[0] == previous:
                    continue
                rest = tuple(candidate for candidate in unused if candidate != run)
                tail = suffix(rest, run[0])
                block = ("1" + "0" * (run[0] - 1)) * run[1]
                results.append({"first_type": run, "block": block, "tail": tail,
                                "candidate_word": None if tail is None else block + tail})
            return results

        word = suffix(types, 0)
        trace = []
        if word is not None:
            remaining, previous = types, 0
            while remaining:
                choices = branches(remaining, previous)
                optimum = suffix(remaining, previous)
                chosen = next(choice for choice in choices if choice["candidate_word"] == optimum)
                trace.append({"unused": remaining, "previous": previous, "branches": choices,
                              "chosen": chosen["first_type"], "minimum_suffix": optimum})
                remaining = tuple(run for run in remaining if run != chosen["first_type"])
                previous = chosen["first_type"][0]
        return {"types": types, "minimum_word": word, "initial_branches": branches(types, 0),
                "trace": trace, "cached_states": suffix.cache_info().currsize}

    good = describe(((1, 1), (1, 2), (2, 1), (3, 1)))
    bad = describe(((1, 1), (1, 2), (1, 3), (2, 1)))
    assert good["minimum_word"] == "10011011"
    assert int(good["minimum_word"], 2) == 155
    assert bad["minimum_word"] is None
    result = {"feasible_boundary_choice": good, "infeasible_boundary_choice": bad,
              "displayed_concatenation": "100|1|10|11", "integer_value": 155}
    dump("dp_example_n4.json", result)
    return result


def host_report():
    queries = []
    for key in ("machdep.cpu.brand_string", "hw.model", "hw.memsize", "hw.physicalcpu", "hw.logicalcpu"):
        command = ["/usr/sbin/sysctl", "-n", key]
        try:
            result = subprocess.run(command, text=True, capture_output=True)
            queries.append({"command": shlex.join(command), "returncode": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
        except OSError as error:
            queries.append({"command": shlex.join(command), "error": str(error)})
    return {"python": sys.version, "python_executable_alias": "python3",
            "platform": platform.platform(),
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "hardware_queries": queries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-n", type=int, default=120)
    parser.add_argument("--exact-max-n", type=int, default=20)
    parser.add_argument("--exhaustive-max-n", type=int, default=6)
    args = parser.parse_args()
    if not 0 <= args.exhaustive_max_n <= 6:
        parser.error("the raw-definition guard permits indices only through 6")
    if not 0 <= args.exact_max_n <= args.max_n or args.exhaustive_max_n > args.max_n:
        parser.error("check ranges must fit within --max-n")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    report = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "invocation": shlex.join(["python3", "validation/oct21/run_independent.py",
                                  "--max-n", str(args.max_n),
                                  "--exact-max-n", str(args.exact_max_n),
                                  "--exhaustive-max-n", str(args.exhaustive_max_n)]),
        "cwd": ".",
        "path_convention": "Commands use package-relative paths and python3 as the runtime alias; host.python records the actual runtime version.",
        "manuscript_sha256_used_to_implement": MANUSCRIPT_READ_SHA256,
        "source_sha256": {str(path.relative_to(REVISION)): file_hash(path) for path in (
            REVISION / "code/a351015_polynomial.py",
            REVISION / "validation/oct21/independent_prefix.py",
            Path(__file__).resolve())},
        "host": host_report(),
    }
    dump("run_started.json", report)
    records = generate_independent(args.max_n)
    dp_example()
    exact = exact_search(args.exact_max_n, records)
    definitions = definition_checks(args.exhaustive_max_n, records)
    comparison = compare_producer(records)
    report.update({
        "status": "PASS", "elapsed_seconds_total": time.perf_counter() - started,
        "independent_indices": list(range(args.max_n + 1)),
        "independent_construction_elapsed_seconds_sum": sum(row["elapsed_seconds"] for row in records),
        "producer_elapsed_seconds": comparison["elapsed_seconds"],
        "exact_search_indices": exact["indices"],
        "exact_search_elapsed_seconds_sum": exact["elapsed_seconds_sum"],
        "raw_scan_inclusive_upper": definitions["scan"]["inclusive_upper"],
        "definition_binary_prefixes_checked": definitions["total_binary_prefixes_checked"],
        "n100_bitlength": records[100]["length"] if args.max_n >= 100 else None,
        "max_rss_self_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "max_rss_children_native_units": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "rss_units": "bytes on macOS; kilobytes on Linux",
        "measurement_caveat": "One run. Per-term independent and exact-search timings exclude setup/output; producer timing includes its fresh subprocess startup/output. These are descriptive and not speed-comparison benchmarks. RSS is a process-lifetime high-water mark, not a per-term measurement.",
        "reports": ["precomparison_implementation.json", "independent_terms.json",
                    "producer_comparison.json", "producer_stdout.json", "producer_stderr.txt",
                    "exact_search.json", "definition_checks.json", "dp_example_n4.json"],
    })
    dump("run_report.json", report)
    print(json.dumps({key: report[key] for key in (
        "status", "elapsed_seconds_total", "n100_bitlength", "definition_binary_prefixes_checked")}), flush=True)


if __name__ == "__main__":
    main()
