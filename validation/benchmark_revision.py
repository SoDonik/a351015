#!/usr/bin/env python3
"""Record fresh subprocess wall time and per-child maximum RSS.

The benchmark also checks the observed outputs.  Each timed row is one fresh
process, with stdout/stderr preserved.  The original DP row is explicitly a
batch through n=16, and the unchanged C++ and verifier rows are batches for
n=17..20.  The n=100 polynomial row is a scalability/certificate check, not an
independent proof of the new term's numerical minimality.

This release adaptation records portable command paths and runtime versions.
The report, raw logs, build products, and temporary files are all written
under the directory containing --output. The preceding validation report
is still read from validation/results/validation.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_revision import EXPECTED, brute_lower_bound, raw_runs, require, sha256

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "validation" / "results"


def portable_command(command: list[str]) -> list[str]:
    """Describe the executed command without private installation paths."""
    result = []
    for index, item in enumerate(command):
        if item == sys.executable:
            result.append("python3")
        elif Path(item).is_absolute():
            path = Path(item)
            result.append(str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else
                          path.name if index == 0 else item)
        else:
            result.append(item)
    return result


def measured_process(label: str, command: list[str], environment: dict[str, str],
                     results_directory: Path) -> dict:
    stdout_path = results_directory / f"{label}.stdout.txt"
    stderr_path = results_directory / f"{label}.stderr.txt"
    start_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        child = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr)
        waited_pid, status, usage = os.wait4(child.pid, 0)
        require(waited_pid == child.pid, "wait4 returned another process")
        child.returncode = os.waitstatus_to_exitcode(status)
    elapsed = time.perf_counter() - started
    # getrusage/wait4 expose bytes on macOS and KiB on Linux. Preserve the raw
    # field and units as well as the normalized bytes, without using the
    # cumulative RUSAGE_CHILDREN maximum.
    raw_rss = usage.ru_maxrss
    rss_unit = "bytes" if sys.platform == "darwin" else "KiB"
    rss_bytes = raw_rss if sys.platform == "darwin" else raw_rss * 1024
    return {
        "label": label, "command": portable_command(command), "working_directory": ".",
        "started_utc": start_utc, "returncode": child.returncode,
        "wall_seconds": elapsed, "user_seconds": usage.ru_utime,
        "system_seconds": usage.ru_stime, "maximum_rss_raw": raw_rss,
        "maximum_rss_raw_unit": rss_unit, "maximum_rss_bytes": rss_bytes,
        "maximum_rss_mib": rss_bytes / (1024 * 1024),
        "measurement": "One fresh subprocess; os.wait4 child rusage, not cumulative RUSAGE_CHILDREN",
        "stdout": str(stdout_path.relative_to(ROOT)),
        "stderr": str(stderr_path.relative_to(ROOT)),
        "stdout_sha256": sha256(stdout_path), "stderr_sha256": sha256(stderr_path),
    }


def stdout_of(record: dict) -> str:
    return (ROOT / record["stdout"]).read_text(encoding="utf-8")


def certificate(n: int, value: int, word: str, ordered_types=None) -> dict:
    require(word == (format(value, "b") if n else ""), f"integer-word mismatch n={n}")
    runs = raw_runs(word)
    require(len(runs) == len(set(runs)) == n, f"distinct run certificate failed n={n}")
    require(len(word) == brute_lower_bound(n), f"minimum-length certificate failed n={n}")
    if ordered_types is not None:
        require(tuple(map(tuple, ordered_types)) == runs, f"ordered types differ n={n}")
    if n < len(EXPECTED):
        require(value == EXPECTED[n], f"recorded term differs n={n}")
    return {"n": n, "value": str(value), "length": len(word),
            "word_sha256": hashlib.sha256(word.encode()).hexdigest()}


def verify_polynomial_output(record: dict, n: int) -> dict:
    rows = json.loads(stdout_of(record))
    require(isinstance(rows, list) and len(rows) == 1, "expected one polynomial JSON result")
    row = rows[0]
    require(row["n"] == n and row["length"] == len(row["word"]), "polynomial metadata differs")
    result = certificate(n, int(row["value"]), row["word"], row["run_types"])
    result["scope"] = ("Recorded table value and raw-decoded structural certificate"
                       if n < len(EXPECTED) else
                       "Scalability only: raw-decoded structural certificate; no independent minimality check")
    return result


def verify_python_dp_output(record: dict) -> dict:
    rows = re.findall(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s*$", stdout_of(record), re.MULTILINE)
    require(len(rows) == 17 and [int(n) for n, _length, _value in rows] == list(range(17)),
            "Python DP batch must return each n=0..16 exactly once in order")
    values = {int(n): (int(length), int(value)) for n, length, value in rows}
    require(set(values) == set(range(17)), "Python DP batch did not return n=0..16")
    for n, (length, value) in values.items():
        require(value == EXPECTED[n], f"Python DP value differs n={n}")
        require(length == brute_lower_bound(n), f"Python DP length differs n={n}")
        certificate(n, value, format(value, "b") if n else "")
    require("All structural certificates and recorded-term checks passed." in stdout_of(record),
            "Python DP did not report its own checks passing")
    return {"n_inclusive": [0, 16], "cases": len(values),
            "method": "Unchanged Python subset DP and its own certificate checks", "status": "passed"}


def verify_cpp_output(record: dict) -> dict:
    pattern = r"^n=(\d+) length=(\d+) value=(\d+)\nbinary=([01]+)\norder=(.*)$"
    rows = re.findall(pattern, stdout_of(record), re.MULTILINE)
    require(len(rows) == 4 and [int(row[0]) for row in rows] == list(range(17, 21)),
            "C++ batch did not return n=17..20")
    checked = []
    for n_text, length_text, value_text, word, order in rows:
        n = int(n_text)
        require(int(length_text) == len(word), f"C++ length metadata differs n={n}")
        ordered = [(int(v), int(count)) for v, count in re.findall(r"\((\d+),(\d+)\)", order)]
        checked.append(certificate(n, int(value_text), word, ordered))
    return {"n_inclusive": [17, 20], "cases": len(rows), "records": checked,
            "method": "Unchanged specialized q=8 C++ subset DP", "status": "passed"}


def verify_prefix_output(record: dict) -> dict:
    text = stdout_of(record)
    rows = re.findall(r"^a\((\d+)\) = (\d+)$", text, re.MULTILINE)
    require([int(n) for n, _value in rows] == list(range(17, 21)), "prefix verifier range differs")
    for n, value in rows:
        require(int(value) == EXPECTED[int(n)], f"prefix verifier target differs n={n}")
    require(text.count("PASS: positive certificate") == 4 and text.count("lexicographically-smaller") == 4,
            "prefix verifier did not complete all certificate/minimality checks")
    require("All independent prefix audits passed" in text, "prefix verifier success message absent")
    return {"n_inclusive": [17, 20], "cases": len(rows), "status": "passed",
            "method": "Unchanged prefix automaton with boundary enumeration and recursive label-count completion"}


def read_cpu_information() -> dict:
    info = {"machine": platform.machine(), "processor": platform.processor()}
    if sys.platform == "darwin":
        for key in ("machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"):
            result = subprocess.run(["/usr/sbin/sysctl", "-n", key], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                info[key] = result.stdout.strip()
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS / "benchmarks.json")
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to(RESULTS.resolve()), "output must remain under validation/results")
    require(hasattr(os, "wait4") and sys.platform in ("darwin", "linux"), "supported POSIX host required")
    results_directory = output.parent
    results_directory.mkdir(parents=True, exist_ok=True)
    build = results_directory / "build"
    build.mkdir(exist_ok=True)
    temporary = results_directory / "temporary"
    temporary.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["TMPDIR"] = str(temporary)
    report = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(), "cpu": read_cpu_information(),
        "command": ["python3", "validation/benchmark_revision.py", "--output", str(output.relative_to(ROOT))],
        "path_convention": "Commands use package-relative paths and executable names; python and compiler.version identify the actual tools.",
        "results_directory": str(results_directory.relative_to(ROOT)),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in
                          [Path(__file__).resolve(), ROOT / "validation" / "validate_revision.py",
                           *(ROOT / "code").glob("*.py"), ROOT / "code" / "a351015_fast_exact.cpp"]},
        "benchmarks": [],
        "limits": ["One run per job, including interpreter/process startup and requested output.",
                   "Times depend on host load and are descriptive, not asymptotic evidence.",
                   "Maximum RSS includes interpreter/runtime and process memory; it is not live Python heap size.",
                   "Python DP through16, C++17..20, and verifier17..20 are batch measurements.",
                   "The n=100 result is a scalability/certificate check, not independent numerical minimality verification."],
    }
    start = time.perf_counter()
    try:
        prior = json.loads((RESULTS / "validation.json").read_text())
        require(prior["status"] == "passed", "independent validation has not passed")
        for filename, digest in prior["source_sha256"].items():
            require(sha256(ROOT / filename) == digest, f"source changed since independent validation: {filename}")
        report["independent_validation_sha256"] = sha256(RESULTS / "validation.json")
        compiler = shutil.which("clang++") or shutil.which("g++")
        require(compiler is not None, "no C++ compiler found")
        version = subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True)
        report["compiler"] = {"executable": Path(compiler).name, "version": version.stdout.strip()}
        executable = build / "a351015_fast"
        compile_command = [compiler, "-O3", "-std=c++17", str(ROOT / "code" / "a351015_fast_exact.cpp"),
                           "-o", str(executable)]
        compilation = measured_process("cpp_build", compile_command, environment, results_directory)
        report["compilation"] = compilation
        require(compilation["returncode"] == 0, "C++ build failed; see recorded stderr")
        report["compiled_binary_sha256"] = sha256(executable)
        jobs = (
            ("polynomial_n20", [sys.executable, "code/a351015_polynomial.py", "--n", "20", "--json"],
             lambda row: verify_polynomial_output(row, 20)),
            ("polynomial_n100", [sys.executable, "code/a351015_polynomial.py", "--n", "100", "--json"],
             lambda row: verify_polynomial_output(row, 100)),
            ("python_dp_through16", [sys.executable, "code/a351015_exact.py", "--max-n", "16"],
             verify_python_dp_output),
            ("cpp_dp_17_20", [str(executable)], verify_cpp_output),
            ("prefix_verifier_17_20", [sys.executable, "code/a351015_independent_verify.py", "17", "18", "19", "20"],
             verify_prefix_output),
        )
        for label, command, verify in jobs:
            print(f"RUN {label}", flush=True)
            record = measured_process(label, command, environment, results_directory)
            report["benchmarks"].append(record)
            require(record["returncode"] == 0, f"{label} failed; see recorded output")
            record["validation"] = verify(record)
            print(f"PASS {label}: {record['wall_seconds']:.6f} s, {record['maximum_rss_mib']:.3f} MiB maximum RSS", flush=True)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
        traceback.print_exc()
    report["elapsed_seconds"] = time.perf_counter() - start
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Evidence: {output}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
