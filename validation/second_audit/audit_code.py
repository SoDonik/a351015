#!/usr/bin/env python3
"""Portable numerical portion of the second source audit.

Run after the release validation and benchmark commands. Private workspace
preservation and manuscript checks are excluded; numerical tests remain.
All generated files are below validation/results/second_audit or
tmp/second_audit. The producer sources are never changed.
Python 3.10 is sufficient; decimal-safeguard probes run when that feature
is available (Python 3.11+).
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import heapq
import importlib.util
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "validation/results/second_audit"
TEMP = ROOT / "tmp/second_audit"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def raw_runs_integer(value):
    """Use gaps between set-bit positions, read from the low end.

    This does not split binary strings, call either earlier decoder, or
    consult a run inventory. Reverse the resulting runs to restore order.
    """
    reversed_runs = []
    last_position = -1
    while value:
        low = value & -value
        position = low.bit_length() - 1
        part = position - last_position
        if reversed_runs and reversed_runs[-1][0] == part:
            label, count = reversed_runs[-1]
            reversed_runs[-1] = (label, count + 1)
        else:
            reversed_runs.append((part, 1))
        last_position = position
        value ^= low
    return tuple(reversed(reversed_runs))


def rectangular_costs(n):
    return sorted(v * length for v in range(1, n + 1)
                  for length in range(1, n + 1))[:n]




def check_raw_languages(producer, verifier, validation):
    bounds = {n: sum(rectangular_costs(n)) for n in range(1, 8)}
    languages = {n: [] for n in bounds}
    first = {}
    last = (1 << max(bounds.values())) - 1
    for value in range(1, last + 1):
        count = len(set(raw_runs_integer(value)))
        if count <= 7:
            first.setdefault(count, value)
            if value.bit_length() == bounds[count]:
                languages[count].append(value)
    require(first == {n: validation.EXPECTED[n] for n in bounds}, "fresh raw first occurrences")
    rows = []
    old_checker_positive = old_checker_negative = 0
    deepest_rejected_branch = 0
    for n, values in languages.items():
        require(min(values) == first[n] and first[n].bit_length() == bounds[n], f"raw length {n}")
        words = [format(value, "b") for value in values]
        prefixes = {word[:length] for word in words for length in range(len(word) + 1)}
        oracle = producer.PrefixOracle(n)
        queries = positive = leading_zero = 0
        for length in range(bounds[n] + 1):
            for bits in range(1 << length):
                prefix = format(bits, f"0{length}b") if length else ""
                expected = prefix in prefixes
                require(oracle.feasible(prefix) == expected, f"all-prefix mismatch n={n}, P={prefix!r}")
                queries += 1
                positive += expected
                leading_zero += bool(prefix) and prefix[0] == "0"
        verifier.PrefixAudit.can_finish.cache_clear()
        verifier.labels_can_follow.cache_clear()
        audit = verifier.PrefixAudit(n)
        for value in values:
            try:
                audit.audit_claim(value)
            except AssertionError as error:
                require(value != first[n], f"original checker false negative n={n}")
                require("smaller completable prefix exists" in str(error),
                        f"valid raw word rejected for the wrong reason n={n}: {error}")
                position = int(re.search(r"at bit (\d+)", str(error)).group(1))
                deepest_rejected_branch = max(deepest_rejected_branch, position)
                old_checker_negative += 1
            else:
                require(value == first[n], f"original checker false positive n={n}, value={value}")
                old_checker_positive += 1
        rows.append({"n": n, "length": bounds[n], "raw_words": len(values),
                     "prefix_queries": queries, "feasible_prefixes": positive,
                     "leading_zero_queries": leading_zero, "minimum": str(first[n]),
                     "language_sha256": hashlib.sha256("\n".join(sorted(words)).encode()).hexdigest()})
        print(f"PASS raw language and every prefix n={n}: {len(values)} words, {queries} queries", flush=True)
    verifier.PrefixAudit.can_finish.cache_clear()
    verifier.labels_can_follow.cache_clear()
    return {"raw_integer_scan_inclusive": [1, last], "positive_integers_examined": last,
            "zero_handled_separately": True, "n_inclusive": [1, 7], "rows": rows,
            "total_prefix_queries": sum(r["prefix_queries"] for r in rows),
            "original_checker_positive_cases": old_checker_positive,
            "original_checker_valid_nonminimal_cases": old_checker_negative,
            "deepest_nonminimal_rejection_bit": deepest_rejected_branch,
            "limits": "Complete raw languages and arbitrary-prefix coverage stop at n=7, length 19."}


def schedule_labels(counts):
    """Construct a word using the largest available label count.

    Success is certified by the returned word. No capacity inequality or
    producer helper is consulted. Failed examples are separately certified
    below by a necessary separator count.
    """
    heap = [(-count, label) for label, count in counts.items() if count]
    heapq.heapify(heap)
    held = None
    word = []
    while heap:
        negative, label = heapq.heappop(heap)
        word.append(label)
        negative += 1
        if held is not None:
            heapq.heappush(heap, held)
        held = (negative, label) if negative else None
    return tuple(word) if held is None else None


def check_boundary_formula(producer):
    rows = []
    subsets = metadata = witnesses = 0
    impossible = []
    for q in range(1, 101):
        pairs = [(v, length) for v in range(1, q + 1) for length in range(1, q + 1)]
        forced = tuple(pair for pair in pairs if math.prod(pair) < q)
        boundary = tuple(pair for pair in pairs if math.prod(pair) == q)
        successes = Counter()
        forced_counts = Counter(v for v, _ in forced)
        for mask in range(1, 1 << len(boundary)):
            selected = [boundary[i] for i in range(len(boundary)) if mask >> i & 1]
            counts = forced_counts + Counter(v for v, _ in selected)
            ordering = schedule_labels(counts)
            n = len(forced) + len(selected)
            subsets += 1
            if ordering is not None:
                require(Counter(ordering) == counts, f"heap witness loses labels at q={q}")
                require(all(a != b for a, b in zip(ordering, ordering[1:])), f"heap witness joins q={q}")
                successes[len(selected)] += 1
                witnesses += 1
            else:
                biggest = max(counts.values())
                require(biggest > n - biggest + 1, f"uncertified heap failure q={q}")
                impossible.append({"q": q, "n": n, "selected": selected})
        for choose in range(1, len(boundary) + 1):
            n = len(forced) + choose
            expected = math.comb(len(boundary) - (n < 2 * q - 1), choose)
            require(successes[choose] == expected, f"feasible-subset formula q={q}, r={choose}")
            oracle = producer.PrefixOracle(n)
            expected_length = sum(math.prod(pair) for pair in forced) + choose * q
            require((oracle.q, oracle.forced, oracle.boundary, oracle.choose, oracle.length) ==
                    (q, forced, boundary, choose, expected_length), f"metadata q={q}, r={choose}")
            require(oracle._type_count == len(forced) + len(boundary), "dense universe size")
            indices = {oracle._type_offsets[v] + length - 1 for v, length in forced + boundary}
            require(indices == set(range(len(indices))), "dense type indices are not a bijection")
            require(oracle.feasible("1") and oracle.feasible(""), f"empty/first prefix q={q}, r={choose}")
            metadata += 1
            rows.append({"q": q, "n": n, "choose": choose, "candidate_subsets": math.comb(len(boundary), choose),
                         "feasible_subsets": successes[choose], "length": expected_length})
    require([(r["q"], r["n"]) for r in impossible] == [(2, 2), (3, 4), (4, 6)], "exception list")
    return {"q_inclusive": [1, 100], "n_inclusive": [1, rows[-1]["n"]],
            "nonempty_boundary_subsets_examined": subsets, "certified_ordering_witnesses": witnesses,
            "all_cutoff_and_choice_metadata_cases": metadata, "infeasible_subsets": impossible,
            "rows": rows, "method": "All boundary subsets; explicit unequal-neighbor schedules for successes; separator impossibility witnesses for failures."}


def old_prefix_feasible(audit, prefix):
    frontier = {(0, 0, -1, 0)}
    for bit in prefix:
        frontier = audit.step(frontier, bit)
        if not frontier:
            return False
    return bool(frontier)


def check_larger_prefixes(producer, verifier):
    ns = sorted(set(range(8, 21)) | {21, 23, 24, 27, 28, 29, 30, 32, 35, 36, 37, 38, 41,
                                   42, 45, 46, 50, 51, 52, 53, 58, 59, 60, 61, 63, 66})
    rng = random.Random(35101520261019)
    rows = []
    for n in ns:
        value, word, runs = producer.exact_term(n)
        require(raw_runs_integer(value) == runs and len(runs) == len(set(runs)) == n, f"raw n={n}")
        require(len(word) == sum(rectangular_costs(n)), f"length n={n}")
        reversed_word = "".join(("1" + "0" * (v - 1)) * count for v, count in reversed(runs))
        verifier.PrefixAudit.can_finish.cache_clear()
        verifier.labels_can_follow.cache_clear()
        audit = verifier.PrefixAudit(n)
        audit.audit_claim(value)
        oracle = producer.PrefixOracle(n)
        prefixes = set()
        for sample in (word, reversed_word):
            for k in (0, 1, 2, len(word) // 4, len(word) // 2, 3 * len(word) // 4,
                      len(word) - 8, len(word) - 1, len(word)):
                prefixes.add(sample[:max(0, k)])
            prefixes.add(sample + "0")
            for _ in range(12):
                k = rng.randrange(1, len(sample) + 1)
                position = rng.randrange(k)
                prefix = sample[:k]
                prefixes.add(prefix[:position] + str(1 - int(prefix[position])) + prefix[position + 1:])
        prefixes.update("".join(rng.choice("01") for _ in range(rng.randrange(len(word) + 1)))
                        for _ in range(12))
        for prefix in sorted(prefixes):
            require(oracle.feasible(prefix) == old_prefix_feasible(audit, prefix),
                    f"independent automaton prefix n={n}, prefix={prefix!r}")
        suffix_queries = suffix_completions = 0
        suffix_rows = []
        for sample in (word, reversed_word):
            for remaining in (0, 1, 4, 7):
                fixed = sample[:len(sample) - remaining] if remaining else sample
                for prefix in (fixed, fixed[:-1] + str(1 - int(fixed[-1]))):
                    count = 0
                    for tail in range(1 << remaining):
                        candidate = (int(prefix, 2) << remaining) | tail
                        count += len(set(raw_runs_integer(candidate))) == n
                        suffix_completions += 1
                    require(oracle.feasible(prefix) == bool(count),
                            f"raw suffix oracle n={n}, remaining={remaining}, prefix={prefix!r}")
                    suffix_queries += 1
                    suffix_rows.append({"remaining_bits": remaining, "raw_valid_completions": count})
        rows.append({"n": n, "q": oracle.q, "length": len(word),
                     "word_sha256": hashlib.sha256(word.encode()).hexdigest(),
                     "independent_minimality_audit": "passed", "arbitrary_prefix_samples": len(prefixes),
                     "raw_suffix_queries": suffix_queries, "raw_suffix_completions_decoded": suffix_completions,
                     "suffix_rows": suffix_rows})
        print(f"PASS sampled prefixes and independent minimality n={n}, q={oracle.q}", flush=True)
    verifier.PrefixAudit.can_finish.cache_clear()
    verifier.labels_can_follow.cache_clear()
    return {"indices": ns, "seed": 35101520261019, "rows": rows,
            "arbitrary_prefix_samples": sum(row["arbitrary_prefix_samples"] for row in rows),
            "raw_suffix_queries": sum(row["raw_suffix_queries"] for row in rows),
            "raw_suffix_completions_decoded": sum(row["raw_suffix_completions_decoded"] for row in rows),
            "limits": "Larger arbitrary prefixes are sampled, not exhaustively covered. The independent automaton still relies on the structural theorem. Raw suffix comparisons enumerate only the stated last 0, 1, 4, or 7 bits. n=100 is not independently minimized."}


def check_edges_and_decimal(producer):
    checked = 0
    for function in (producer.PrefixOracle, producer.minimum_length, producer.exact_term):
        for value, kind in ((True, TypeError), (False, TypeError), (1.0, TypeError),
                            ("1", TypeError), (None, TypeError), (-1, ValueError)):
            try:
                function(value)
            except kind:
                checked += 1
            else:
                raise AssertionError(f"input type accepted: {function.__name__}, {value!r}")
    bad = [
        (producer.labels_can_follow, ([],), ValueError),
        (producer.labels_can_follow, ((0, True),), TypeError),
        (producer.labels_can_follow, ((0, 1.0),), TypeError),
        (producer.labels_can_follow, ((0, 1), True), TypeError),
        (producer.labels_can_follow, ((0, 1), -1), ValueError),
        (producer.boundary_can_finish, ((0, 1), (True,), 1), TypeError),
        (producer.boundary_can_finish, ((0, 1), (1,), True), TypeError),
        (producer.boundary_can_finish, ((0, 1), (1,), 1.0), TypeError),
        (producer.boundary_can_finish, ((0, 1), (1, 1), -1), ValueError),
    ]
    for function, args, kind in bad:
        try:
            function(*args)
        except kind:
            checked += 1
        else:
            raise AssertionError(f"helper accepted malformed input: {args!r}")
    require(producer.labels_can_follow((0,)) and producer.boundary_can_finish((0,), iter(()), 0), "empty labels")
    require(not producer.boundary_can_finish((0,), (), -1), "negative boundary")
    require(producer.boundary_can_finish((0, 0, 0), iter((1, 2)), 2), "generator optional labels")
    require(producer.PrefixOracle(2).feasible("110") and producer.exact_term(2)[1] == "101",
            "feasible means any minimum-length completion, not a prefix of the least word")
    decimal_records = []
    has_safeguard = hasattr(sys, "get_int_max_str_digits")
    old_limit = sys.get_int_max_str_digits() if has_safeguard else None
    try:
        if has_safeguard:
            sys.set_int_max_str_digits(640)
        patterns = ["0", "1", "9" * 9, "1" + "0" * 9, "1" + "0" * 639,
                    "1" + "0" * 640, "1234567890" * 80, "9" * 4301,
                    "1" + "0" * 4991 + "987654321"]
        for expected in patterns:
            value = 0
            for character in expected:
                value = 10 * value + ord(character) - 48
            limit_before = sys.get_int_max_str_digits() if has_safeguard else None
            require(producer._decimal(value) == expected, f"decimal fallback for {len(expected)} digits")
            require(not has_safeguard or sys.get_int_max_str_digits() == limit_before,
                    "producer changed decimal safeguard")
            decimal_records.append({"digits": len(expected), "sha256": hashlib.sha256(expected.encode()).hexdigest()})
    finally:
        if has_safeguard:
            sys.set_int_max_str_digits(old_limit)
    return {"extra_invalid_argument_cases": checked, "extra_valid_edge_cases": 5,
            "feasible_semantics_example": {"n": 2, "accepted_full_word": "110", "least_word": "101",
                                           "meaning": "Any qualifying minimum-length completion"},
            "decimal_test_limit": 640 if has_safeguard else None, "decimal_records": decimal_records,
            "decimal_safeguard_available": has_safeguard,
            "global_decimal_limit_preserved_by_producer": True,
            "limits": "_decimal is private and production callers supply nonnegative integers; negative out-of-domain behavior is probed separately."}


def check_runtime_and_cli(producer):
    source_files = [Path(__file__), *sorted((ROOT / "code").glob("*.py")), ROOT / "validation/validate_revision.py",
                    ROOT / "validation/benchmark_revision.py"]
    for path in source_files:
        ast.parse(path.read_text(), feature_version=(3, 10))
    records = []
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(TEMP)}
    for name in ("python3.10", "python3.11", "python3.12", "python3.14"):
        executable = shutil.which(name)
        if executable is None:
            records.append({"requested_runtime": name, "available": False})
            continue
        code = ("import importlib.util,sys,json; "
                "s=importlib.util.spec_from_file_location('p','code/a351015_polynomial.py'); "
                "p=importlib.util.module_from_spec(s); s.loader.exec_module(p); "
                "v,w,r=p.exact_term(20); "
                "print(json.dumps({'python':sys.version,'value20':str(v),'length20':len(w),"
                "'decimal5001':p._decimal(10**5000)==('1'+'0'*5000)}))")
        command = [executable, "-B", "-c", code]
        result = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True, timeout=30)
        require(result.returncode == 0, f"runtime smoke check {name}: {result.stderr}")
        checked = json.loads(result.stdout)
        require(checked["value20"] == "5090566682637483446698432134911" and checked["length20"] == 103
                and checked["decimal5001"], f"runtime result {name}")
        records.append({"requested_runtime": name, "available": True, "command": [name, *command[1:]], **checked})
    cli = []
    for arguments, status in ((["--n", "-1"], 2), (["--max-n", "-1"], 2),
                              (["--n", "2", "--max-n", "2"], 2), (["--n", "1.5"], 2),
                              (["--max-n", "0", "--json"], 0), (["--n", "2", "--json", "--details"], 0)):
        command = [sys.executable, "-B", "code/a351015_polynomial.py", *arguments]
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=15)
        require(result.returncode == status, f"CLI status {arguments}")
        if status == 0:
            rows = json.loads(result.stdout)
            n = 0 if "--max-n" in arguments else 2
            require(len(rows) == 1 and rows[0]["n"] == n and isinstance(rows[0]["value"], str), "CLI JSON")
        cli.append({"arguments": arguments, "returncode": result.returncode})
    private_negative = ""
    negative_code = ("import importlib.util,sys; s=importlib.util.spec_from_file_location('p','code/a351015_polynomial.py'); "
                     "p=importlib.util.module_from_spec(s); s.loader.exec_module(p); sys.set_int_max_str_digits(640); "
                     "p._decimal(-(10**700))")
    if hasattr(sys, "set_int_max_str_digits"):
        try:
            result = subprocess.run([sys.executable, "-B", "-c", negative_code], cwd=ROOT, env=environment,
                                    capture_output=True, text=True, timeout=0.5)
            private_negative = f"returned {result.returncode}"
        except subprocess.TimeoutExpired:
            private_negative = "timeout; negative divmod eventually reaches -1 and never terminates"
    else:
        private_negative = "not probed; this runtime has no decimal-conversion safeguard"
    return {"python310_grammar_files": [str(path.relative_to(ROOT)) for path in source_files],
            "runtime_smoke_checks": records, "cli_checks": cli,
            "python310_limit": "No Python 3.10 interpreter is installed; grammar/API source inspection is not a 3.10 runtime test.",
            "private_negative_decimal_probe": private_negative}


def check_harness_controls(validation, benchmark, producer):
    class AlwaysYes:
        labels_can_follow = staticmethod(lambda *args: True)
        boundary_can_finish = staticmethod(lambda *args: True)
    controls = []
    for name, test in (("suffix_counts", validation.check_suffix_counts),
                       ("boundary_counts", validation.check_boundary_counts)):
        try:
            test(AlwaysYes)
        except AssertionError as error:
            controls.append({"check": name, "deliberately_wrong_helper_detected": True, "message": str(error)})
        else:
            raise AssertionError(f"harness accepted unconditional helper: {name}")
    # A narrow diagnostic of the historical output parser. Do not modify
    # either the actual old output or the original subset-DP producer.
    original = (ROOT / "validation/results/python_dp_through16.stdout.txt").read_text()
    contradictory = " 8 23 4617712\n" + original
    path = TEMP / "contradictory_python_dp.stdout.txt"
    path.write_text(contradictory)
    try:
        benchmark.verify_python_dp_output({"stdout": str(path.relative_to(ROOT))})
    except AssertionError:
        duplicate_accepted = False
    else:
        duplicate_accepted = True
    require(not duplicate_accepted, "benchmark parser accepted a contradictory duplicate row")
    return {"mutation_controls": controls,
            "contradictory_duplicate_dp_row_accepted": duplicate_accepted,
            "duplicate_row_probe": str(path.relative_to(ROOT)),
            "impact": "The original real output has exactly 17 unique rows and is valid. The added uniqueness/order guard now rejects the contradictory duplicate before dictionary construction."}


def check_wait4(benchmark):
    directory = RESULTS / "wait4_probe"
    directory.mkdir(exist_ok=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(TEMP)}
    high = benchmark.measured_process("large_child", [sys.executable, "-B", "-c",
        "x=bytearray(64*1024*1024); x[::4096]=b'1'*len(x[::4096]); print(len(x))"], env, directory)
    low = benchmark.measured_process("small_child", [sys.executable, "-B", "-c", "print('small')"], env, directory)
    require(high["returncode"] == low["returncode"] == 0, "wait4 probe process failure")
    require(high["maximum_rss_bytes"] > low["maximum_rss_bytes"] + 32 * 1024**2,
            "RSS probes did not distinguish separate child high-water marks")
    return {"large_then_small": [high, low], "separate_child_maxima_demonstrated": True,
            "limits": "A one-host probe confirms these two measurements; it is not a cross-platform OS test."}


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    TEMP.mkdir(parents=True, exist_ok=True)
    producer = load("second_producer", "code/a351015_polynomial.py")
    verifier = load("second_original_verifier", "code/a351015_independent_verify.py")
    validation = load("validate_revision", "validation/validate_revision.py")
    benchmark = load("second_benchmark", "validation/benchmark_revision.py")
    paths = [Path(__file__), *sorted((ROOT / "code").glob("*.*")),
             ROOT / "validation/validate_revision.py", ROOT / "validation/benchmark_revision.py"]
    report = {"status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "platform": platform.platform(),
              "command": ["python3", "validation/second_audit/audit_code.py"], "working_directory": ".",
              "path_convention": "Commands use package-relative paths and runtime executable names; actual runtime versions are recorded.",
              "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in paths}, "checks": {},
              "limits": ["Finite tests supplement the mathematical proof.",
                         "Private workspace-history, manuscript-table, and historical-file preservation checks are outside this public numerical harness.",
                         "No independent numerical minimality check of n=100 is claimed."]}
    started = time.perf_counter()
    jobs = (
        ("wait4_separate_children", lambda: check_wait4(benchmark)),
        ("api_and_decimal", lambda: check_edges_and_decimal(producer)),
        ("runtime_and_cli", lambda: check_runtime_and_cli(producer)),
        ("harness_controls", lambda: check_harness_controls(validation, benchmark, producer)),
        ("complete_raw_languages", lambda: check_raw_languages(producer, verifier, validation)),
        ("feasible_boundary_subset_formula", lambda: check_boundary_formula(producer)),
        ("larger_prefix_samples", lambda: check_larger_prefixes(producer, verifier)),
    )
    try:
        for name, function in jobs:
            stage = time.perf_counter()
            report["checks"][name] = function()
            report["checks"][name]["elapsed_seconds"] = time.perf_counter() - stage
            print(f"PASS {name}", flush=True)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        traceback.print_exc()
    report["elapsed_seconds"] = time.perf_counter() - started
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["source_unchanged_during_run"] = all(digest(ROOT / path) == value for path, value in report["source_sha256"].items())
    if not report["source_unchanged_during_run"]:
        report["status"] = "failed"
    output = RESULTS / "code_audit.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Evidence: {output}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
