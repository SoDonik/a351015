#!/usr/bin/env python3
"""Independent, finite checks of the referee's A351015 construction.

Release adaptation of the local validation harness. Run from this package
directory with python3 -B. The original programs are checked against hashes
from the fixed public baseline commit; private baseline copies are not needed.
This harness writes only its requested JSON evidence file under validation/
results.  Its raw composition language and recursive ordering
oracles do not call the producer's capacity tests.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import platform
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "validation" / "results"
EXPECTED = (
    0, 1, 5, 27, 155, 1655, 18039, 281975, 4617711,
    138835439, 4503885791, 279381792735, 17876500338655,
    1144081370306527, 73222145385127871, 9296594182239903679,
    1189966115078053658495, 303421421018735347335039,
    77675883218955741073080191, 19885026103583920149103476607,
    5090566682637483446698432134911,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "code" / filename)
    require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def raw_runs(word: str) -> tuple[tuple[int, int], ...]:
    """Decode by the zero gaps after successive 1s, then group equal parts."""
    if not word:
        return ()
    require(word[0] == "1" and set(word) <= {"0", "1"}, "invalid raw word")
    parts = [1 + len(gap) for gap in word.split("1")[1:]]
    runs: list[tuple[int, int]] = []
    for part in parts:
        if runs and runs[-1][0] == part:
            value, count = runs.pop()
            runs.append((value, count + 1))
        else:
            runs.append((part, 1))
    return tuple(runs)


def run_count(value: int) -> int:
    return len(set(raw_runs(format(value, "b")))) if value else 0


def brute_lower_bound(n: int) -> int:
    """Use a rectangular list of products, without a divisor-count formula."""
    products = sorted(v * length for v in range(1, n + 1)
                      for length in range(1, n + 1))
    return sum(products[:n])


@lru_cache(maxsize=None)
def brute_labels(counts: tuple[int, ...], previous: int) -> bool:
    """Exhaust all possible next labels; no separator/capacity inequality."""
    if sum(counts) == 0:
        return True
    for label, multiplicity in enumerate(counts):
        if label and multiplicity and label != previous:
            remaining = list(counts)
            remaining[label] -= 1
            if brute_labels(tuple(remaining), label):
                return True
    return False


def check_raises(function, args, exception_types, description: str) -> str:
    try:
        function(*args)
    except exception_types as error:
        return type(error).__name__
    except Exception as error:
        raise AssertionError(f"{description}: unexpected {type(error).__name__}") from error
    raise AssertionError(f"{description}: no expected exception")


def check_raw_prefix_languages(producer) -> dict:
    """Compare every binary prefix, not just prefixes of accepted words."""
    bounds = {n: brute_lower_bound(n) for n in range(1, 6)}
    languages: dict[int, set[str]] = {n: set() for n in bounds}
    first: dict[int, int] = {}
    scan_end = (1 << max(bounds.values())) - 1
    for value in range(1, scan_end + 1):
        word = format(value, "b")
        count = len(set(raw_runs(word)))
        first.setdefault(count, value)
        if count in languages and len(word) == bounds[count]:
            languages[count].add(word)

    rows = []
    total_queries = 0
    for n in range(1, 6):
        require(first[n] == EXPECTED[n], f"raw first occurrence differs for n={n}")
        require(first[n].bit_length() == bounds[n], f"raw minimum length differs for n={n}")
        language = languages[n]
        require(bool(language), f"empty raw language n={n}")
        prefixes = {word[:length] for word in language
                    for length in range(len(word) + 1)}
        oracle = producer.PrefixOracle(n)
        queries = feasible_queries = leading_zero_queries = 0
        for length in range(bounds[n] + 1):
            for value in range(1 << length):
                prefix = format(value, f"0{length}b") if length else ""
                expected = prefix in prefixes
                actual = oracle.feasible(prefix)
                require(actual == expected,
                        f"raw prefix mismatch n={n}, prefix={prefix!r}, expected={expected}")
                queries += 1
                feasible_queries += int(expected)
                leading_zero_queries += int(bool(prefix) and prefix[0] == "0")
        total_queries += queries
        rows.append({
            "n": n, "length": bounds[n], "minimum": str(first[n]),
            "raw_words_at_minimum_length": len(language),
            "all_binary_prefix_queries": queries,
            "feasible_prefixes": feasible_queries,
            "leading_zero_queries": leading_zero_queries,
            "language_sha256": hashlib.sha256("\n".join(sorted(language)).encode()).hexdigest(),
        })
    require(producer.PrefixOracle(2).feasible("11"),
            "unfinished part counterexample: prefix 11 must extend to 110 for n=2")
    require(producer.PrefixOracle(6).feasible("1001101"),
            "eventual active value counterexample: n=6, prefix 1001101 must be feasible")
    require(len(set(raw_runs("100110101110111"))) == 6,
            "n=6 counterexample completion has wrong distinct types")
    return {"raw_integer_scan_inclusive": [1, scan_end],
            "n_inclusive": [1, 5], "total_binary_prefix_queries": total_queries,
            "definition": "All strings of every length 0 through L(n), including those starting 0",
            "unfinished_part_example": {"n": 2, "prefix": "11", "completion": "110"},
            "eventual_value_example": {"n": 6, "prefix": "1001101", "completion": "100110101110111"},
            "rows": rows}


def check_suffix_counts(producer) -> dict:
    checked = 0
    for labels in range(5):
        for multiplicities in itertools.product(range(5), repeat=labels):
            counts = (0,) + multiplicities
            for previous in range(labels + 1):
                expected = brute_labels(counts, previous)
                actual = producer.labels_can_follow(counts, previous)
                require(actual == expected,
                        f"suffix mismatch counts={counts}, previous={previous}")
                checked += 1
    return {"cases": checked, "positive_label_counts": [0, 4],
            "each_multiplicity_inclusive": [0, 4],
            "previous_values": "0 and every positive label",
            "reference": "Exhaustive recursive first-label ordering, memoized"}


def check_boundary_counts(producer) -> dict:
    checked = 0
    labels = (1, 2, 3)
    for multiplicities in itertools.product(range(4), repeat=len(labels)):
        forced = (0,) + multiplicities
        for flags in itertools.product((False, True), repeat=len(labels)):
            optional = tuple(label for label, selected in zip(labels, flags) if selected)
            for required in range(-1, len(optional) + 2):
                for previous in range(len(labels) + 1):
                    expected = False
                    if 0 <= required <= len(optional):
                        for subset in itertools.combinations(optional, required):
                            counts = list(forced)
                            for label in subset:
                                counts[label] += 1
                            if brute_labels(tuple(counts), previous):
                                expected = True
                                break
                    actual = producer.boundary_can_finish(forced, optional, required, previous)
                    require(actual == expected,
                            f"boundary mismatch forced={forced}, optional={optional}, "
                            f"required={required}, previous={previous}")
                    checked += 1
    return {"cases": checked, "positive_labels": list(labels),
            "each_forced_multiplicity_inclusive": [0, 3],
            "optional_values": "Every subset of {1,2,3}",
            "required": "-1 through optional_count + 1", "previous_values": [0, 1, 2, 3],
            "reference": "Enumerate each boundary subset, then recursively order its labels"}


def check_input_edges(producer) -> dict:
    cases = []
    for n in range(6):
        oracle = producer.PrefixOracle(n)
        require(oracle.feasible(""), f"empty prefix rejected for n={n}")
        cases.append(f"n={n}: empty prefix")
        for prefix in ("0", "00", "01", "0" + "1" * oracle.length,
                       "1" * (oracle.length + 1), "1" + "0" * oracle.length):
            require(not oracle.feasible(prefix), f"invalid/overlength prefix accepted n={n}: {prefix}")
            cases.append(f"n={n}: reject {prefix!r}")
        for prefix in ("2", "10x", "1 0", "\n", "0x"):
            kind = check_raises(oracle.feasible, (prefix,), (ValueError,), "nonbinary prefix")
            cases.append(f"n={n}: {prefix!r} raises {kind}")
        for prefix in (None, 1, b"1", ("1",)):
            kind = check_raises(oracle.feasible, (prefix,), (TypeError,), "nonstr prefix")
            cases.append(f"n={n}: {prefix!r} raises {kind}")
    zero = producer.PrefixOracle(0)
    require((zero.q, zero.forced, zero.boundary, zero.choose, zero.length) == (0, (), (), 0, 0),
            "n=0 structure")
    require(producer.exact_term(0) == (0, "", ()), "n=0 term")
    require(producer.minimum_length(0) == 0, "n=0 length")
    for function in (producer.PrefixOracle, producer.exact_term, producer.minimum_length):
        for n in (-1, -10):
            check_raises(function, (n,), (ValueError,), "negative n")
            cases.append(f"{function.__name__}({n}) rejects")
        for n in (1.5, "2", None):
            check_raises(function, (n,), (TypeError, ValueError), "noninteger n")
            cases.append(f"{function.__name__}({n!r}) rejects")
    bad_helpers = (
        (producer.labels_can_follow, ((1, 0), 0), "nonzero sentinel"),
        (producer.labels_can_follow, ((0, -1), 0), "negative count"),
        (producer.labels_can_follow, ((0, 1), 2), "previous label out of range"),
        (producer.boundary_can_finish, ((0, 1), (1, 1), 1, 0), "duplicate optional label"),
        (producer.boundary_can_finish, ((0, 1), (0,), 1, 0), "optional sentinel"),
        (producer.boundary_can_finish, ((0, 1), (2,), 1, 0), "optional label out of range"),
    )
    for function, args, description in bad_helpers:
        check_raises(function, args, (TypeError, ValueError), description)
        cases.append(description)
    return {"cases": len(cases) + 3, "checks": cases,
            "additional_zero_checks": ["empty structure", "empty exact term", "zero minimum length"]}


def check_table_and_certificates(producer) -> tuple[dict, list]:
    records = []
    certificates = []
    for n, expected in enumerate(EXPECTED):
        value, word, ordered_types = producer.exact_term(n)
        require(value == expected, f"a({n}) differs: {value} != {expected}")
        require(len(word) == brute_lower_bound(n), f"length mismatch for n={n}")
        require(producer.minimum_length(n) == len(word), f"minimum_length differs for n={n}")
        runs = raw_runs(word)
        require(tuple(ordered_types) == runs, f"returned ordering differs from raw decoding for n={n}")
        require(len(runs) == len(set(runs)) == n, f"wrong number of distinct run types for n={n}")
        require(word == (format(value, "b") if n else ""), f"integer-word mismatch for n={n}")
        oracle = producer.PrefixOracle(n)
        require(oracle.feasible(word), f"returned word rejected for n={n}")
        records.append({"n": n, "value": str(value), "length": len(word),
                        "word": word, "run_types": list(map(list, runs))})
        certificates.append((value, word, runs))
    return {"n_inclusive": [0, 20], "cases": len(records), "records": records}, certificates


def check_old_python_dp(old_dp, certificates, max_n: int) -> dict:
    records = []
    for n in range(max_n + 1):
        start = time.perf_counter()
        certificate = old_dp.exact_term(n)
        old_dp.verify(n, *certificate)
        require(certificate == certificates[n], f"unchanged Python DP disagrees for n={n}")
        records.append({"n": n, "value": str(certificate[0]),
                        "elapsed_seconds": time.perf_counter() - start})
    return {"n_inclusive": [0, max_n], "records": records,
            "method": "Unchanged subset-mask suffix-minimizing recurrence"}


def check_old_prefix_verifier(verifier, certificates) -> dict:
    records = []
    rejected = []
    for n in range(1, len(certificates)):
        value, word, runs = certificates[n]
        verifier.PrefixAudit.can_finish.cache_clear()
        verifier.labels_can_follow.cache_clear()
        audit = verifier.PrefixAudit(n)
        result = audit.audit_claim(value)
        require(result["word"] == word and result["runs"] == runs, f"old verifier certificate n={n}")
        records.append({"n": n, "zero_branches": result["zero_branches"],
                        "max_frontier": result["max_frontier"],
                        "state_visits": result["state_visits"],
                        "completion_states": result["completion_states"],
                        "label_states": result["label_states"],
                        "terminal_states": result["terminal_states"]})
        if n >= 2:
            reversed_word = "".join(("1" + "0" * (v - 1)) * count
                                    for v, count in reversed(runs))
            alternative = int(reversed_word, 2)
            require(alternative > value and len(reversed_word) == len(word),
                    f"reversed alternative not larger at n={n}")
            require(len(set(raw_runs(reversed_word))) == n, f"invalid negative control n={n}")
            try:
                audit.audit_claim(alternative)
            except AssertionError as error:
                require("smaller completable prefix exists" in str(error),
                        f"negative control failed for another reason n={n}: {error}")
                rejected.append({"n": n, "value": str(alternative), "reason": str(error)})
            else:
                raise AssertionError(f"old verifier accepted a nonminimal valid word n={n}")
    verifier.PrefixAudit.can_finish.cache_clear()
    verifier.labels_can_follow.cache_clear()
    return {"n_inclusive": [1, 20], "positive_cases": len(records), "records": records,
            "negative_same_length_valid_cases": len(rejected), "negative_controls": rejected,
            "method": "Unchanged nondeterministic bit-prefix automaton; boundary subsets enumerated; "
                      "completion by recursive value-count ordering, not the new capacity formula",
            "dependency": "Relies on the minimum-length and equality characterization theorems"}


def check_raw_first_occurrences(max_n: int) -> dict:
    found = {0: 0}
    last = EXPECTED[max_n]
    for value in range(1, last + 1):
        count = run_count(value)
        if count <= max_n and count not in found:
            found[count] = value
    require(found == {n: EXPECTED[n] for n in range(max_n + 1)}, "raw first occurrences disagree")
    return {"integer_scan_inclusive": [0, last], "n_inclusive": [0, max_n],
            "integers_examined": last + 1, "first_occurrences": {str(n): str(v) for n, v in sorted(found.items())},
            "method": "Every integer decoded directly; no structural theorem or producer used"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dp-through", type=int, default=12, choices=range(0, 18))
    parser.add_argument("--raw-through", type=int, default=7, choices=range(0, 9))
    parser.add_argument("--output", type=Path, default=RESULTS / "validation.json")
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(RESULTS.resolve()), "output must remain under validation/results")
    started = time.perf_counter()
    report = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "command": ["python3", "validation/validate_revision.py",
                    "--dp-through", str(args.dp_through), "--raw-through", str(args.raw_through),
                    "--output", str(output.relative_to(ROOT))],
        "working_directory": ".",
        "path_convention": "Commands use package-relative paths and python3 as the runtime alias; python records the actual runtime version.",
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in
                          [Path(__file__).resolve(), *(ROOT / "code").glob("*.py"),
                           ROOT / "code" / "a351015_fast_exact.cpp"]},
        "checks": {},
        "limits": ["Finite checks supplement, and do not replace, the mathematical proof.",
                   "Fresh raw scanning stops at the stated bound; no historical larger scan is claimed.",
                   "Agreement of structurally restricted algorithms still depends on the structural theorem."],
    }
    try:
        producer = load_module("revision_polynomial", "a351015_polynomial.py")
        old_dp = load_module("revision_old_dp", "a351015_exact.py")
        verifier = load_module("revision_old_prefix", "a351015_independent_verify.py")
        checks = report["checks"]
        original_names = ("a351015_exact.py", "a351015_independent_verify.py", "a351015_fast_exact.cpp")
        public_baseline = {
            "a351015_exact.py": "581abad8fdbcb220341aed32629fcfcbff15e1321feff310b0a3701a938a7e25",
            "a351015_independent_verify.py": "e30d3356f9cc8f103aa4afb767aa780b1343fa74fa6eebc1c61625fe2ba706ce",
            "a351015_fast_exact.cpp": "1df991c17c3f0ae9279c31ac07c82e9b445136c1373ea21ef41f8c7f1342df95",
        }
        for filename in original_names:
            require(sha256(ROOT / "code" / filename) == public_baseline[filename],
                    f"original program differs from the public baseline: {filename}")
        checks["original_programs_unchanged"] = {
            "files": list(original_names), "comparison": "SHA-256 against the fixed public baseline",
            "repository": "https://github.com/SoDonik/a351015",
            "commit": "74bed98a778c46017ad676e892b4309b35d57015",
            "source_sha256": public_baseline,
        }
        jobs = (
            ("input_edges", lambda: check_input_edges(producer)),
            ("suffix_counts", lambda: check_suffix_counts(producer)),
            ("boundary_counts", lambda: check_boundary_counts(producer)),
            ("all_small_binary_prefixes", lambda: check_raw_prefix_languages(producer)),
        )
        for name, run in jobs:
            stage = time.perf_counter()
            checks[name] = run()
            checks[name]["elapsed_seconds"] = time.perf_counter() - stage
            print(f"PASS {name}", flush=True)
        checks["table_and_certificates"], certificates = check_table_and_certificates(producer)
        print("PASS table_and_certificates n=0..20", flush=True)
        checks["unchanged_python_dp"] = check_old_python_dp(old_dp, certificates, args.dp_through)
        print(f"PASS unchanged_python_dp n=0..{args.dp_through}", flush=True)
        checks["unchanged_prefix_verifier"] = check_old_prefix_verifier(verifier, certificates)
        print("PASS unchanged_prefix_verifier n=1..20 and 19 nonminimal valid controls", flush=True)
        checks["raw_first_occurrences"] = check_raw_first_occurrences(args.raw_through)
        print(f"PASS raw_first_occurrences n=0..{args.raw_through}", flush=True)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        traceback.print_exc()
    report["elapsed_seconds"] = time.perf_counter() - started
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence: {output}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
