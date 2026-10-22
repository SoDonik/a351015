#!/usr/bin/env python3
"""Reproduce an exhaustive definition-only A351015 scan, with controls.

The C source maintains the exact composition after binary increments.  This
runner compares its counts with a separate, from-scratch Python definition
decoder before running a single full scan.  The default interval is every
integer from 0 through 4,503,885,791, inclusive.  No producer module is imported.

Use --controls-only for a quick check without the large scan.  Choose a fresh
--output directory for each run; an existing report is never overwritten.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name("raw_scan.c")
DEFAULT_LAST = 4_503_885_791
UINT64_MAX = (1 << 64) - 1
EXPECTED_FIRST = (0, 1, 5, 27, 155, 1655, 18039, 281975,
                  4617711, 138835439, 4503885791)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def companion_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def definition_runs(value: int) -> tuple[tuple[int, int], ...]:
    """Read the complete binary word left to right, then group equal parts."""
    if value == 0:
        return ()
    parts: list[int] = []
    for bit in format(value, "b"):
        if bit == "1":
            parts.append(1)
        else:
            parts[-1] += 1
    runs: list[tuple[int, int]] = []
    for part in parts:
        if runs and runs[-1][0] == part:
            prior_value, copies = runs[-1]
            runs[-1] = (prior_value, copies + 1)
        else:
            runs.append((part, 1))
    return tuple(runs)


def definition_count(value: int) -> int:
    return len(set(definition_runs(value)))


def command_record(command: list[str], output: Path, label: str,
                   environment: dict[str, str], records: list[dict]) -> bytes:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               check=False)
    stdout = output / f"{label}.stdout"
    stderr = output / f"{label}.stderr.txt"
    stdout.write_bytes(completed.stdout)
    stderr.write_bytes(completed.stderr)
    record = {
        "label": label, "command": command, "cwd": ". (companion root)",
        "returncode": completed.returncode,
        "wall_seconds": time.perf_counter() - started,
        "stdout": stdout.name, "stdout_sha256": digest(stdout),
        "stderr": stderr.name, "stderr_sha256": digest(stderr),
    }
    records.append(record)
    require(completed.returncode == 0, f"{label} failed: {completed.stderr.decode(errors='replace')}")
    return completed.stdout


def hardware() -> dict:
    result: dict = {
        "platform": platform.platform(), "system": platform.system(),
        "release": platform.release(), "machine": platform.machine(),
        "python": sys.version, "python_executable": sys.executable,
        "logical_cpu_count": os.cpu_count(),
    }
    if platform.system() == "Darwin":
        for key in ("machdep.cpu.brand_string", "hw.memsize", "hw.ncpu"):
            completed = subprocess.run(["/usr/sbin/sysctl", "-n", key],
                                       capture_output=True, text=True, check=False)
            result[key] = {"returncode": completed.returncode,
                           "stdout": completed.stdout.strip(),
                           "stderr": completed.stderr.strip()}
    elif Path("/proc/cpuinfo").is_file():
        cpu_lines = Path("/proc/cpuinfo").read_text().splitlines()
        result["cpu_model_fields"] = [line for line in cpu_lines
                                      if line.startswith(("model name", "Hardware"))][:1]
        if Path("/proc/meminfo").is_file():
            result["memory_total_field"] = Path("/proc/meminfo").read_text().splitlines()[0]
    return result


def boundary_intervals() -> list[tuple[int, int]]:
    # The small exhaustive interval already covers low boundaries.  Keeping
    # the later windows separate records the tested carries explicitly.
    intervals = [(max(0, (1 << bit) - 65), min(UINT64_MAX, (1 << bit) + 65))
                 for bit in range(1, 64)]
    intervals.extend([
        ((1 << 32) - 257, (1 << 32) + 257),
        (DEFAULT_LAST - 65, DEFAULT_LAST + 65),
        (UINT64_MAX - 130, UINT64_MAX),
    ])
    return sorted(set(intervals))


def run_controls(executables: list[tuple[str, Path]], last: int, output: Path,
                 environment: dict[str, str], records: list[dict]) -> dict:
    started = time.perf_counter()
    reference = bytes(definition_count(value) for value in range(last + 1))
    first: dict[int, int] = {}
    for value, count in enumerate(reference):
        first.setdefault(count, value)
    require(all(first.get(n) == value for n, value in enumerate(EXPECTED_FIRST)
                if value <= last), "Python definition decoder disagrees with recorded small minima")
    reference_path = output / "python_counts_0_to_control_end.bin"
    reference_path.write_bytes(reference)
    for label, executable in executables:
        actual = command_record([companion_path(executable), "--counts", "0", str(last)],
                                output, f"{label}_small_counts", environment, records)
        require(actual == reference, f"{label}: small exhaustive count stream differs")

    windows = []
    for index, (begin, end) in enumerate(boundary_intervals()):
        expected = bytes(definition_count(value) for value in range(begin, end + 1))
        for label, executable in executables:
            actual = command_record([companion_path(executable), "--counts", str(begin), str(end)],
                                    output, f"{label}_boundary_{index:02d}", environment, records)
            require(actual == expected, f"{label}: boundary stream differs at [{begin}, {end}]")
        windows.append({"interval_inclusive": [str(begin), str(end)],
                        "integers": end - begin + 1,
                        "definition_counts_sha256": hashlib.sha256(expected).hexdigest()})

    examples = [0, 1, 2, 3, 5, 27, 45, 155,
                int("101" * 20, 2), int("11" + "0" * 31 + "1" * 31, 2),
                (1 << 63), UINT64_MAX]
    example_rows = []
    for index, value in enumerate(examples):
        expected = definition_count(value)
        for label, executable in executables:
            actual = command_record([companion_path(executable), "--counts", str(value), str(value)],
                                    output, f"{label}_example_{index:02d}", environment, records)
            require(actual == bytes([expected]), f"{label}: example differs for {value}")
        example_rows.append({"value": str(value), "binary": format(value, "b") if value else "",
                             "maximal_runs": definition_runs(value), "rho": expected})
    require(definition_runs(45) == ((2, 1), (1, 1), (2, 1), (1, 1)),
            "duplicate-type negative control was not constructed correctly")
    require(definition_count(45) == 2 != len(definition_runs(45)),
            "duplicate occurrences were not distinguished from distinct run types")
    require(definition_count(27) == 3 != len({v for v, _ell in definition_runs(27)}),
            "run lengths were not distinguished in the statistic")

    rejected_arguments = [[], ["--scan"], ["--scan", "-1"], ["--scan", "+1"],
                          ["--scan", "1x"], ["--scan", ""], ["--scan", str(UINT64_MAX)],
                          ["--scan", str(UINT64_MAX + 1)], ["--counts", "2", "1"],
                          ["--counts", "0", str(UINT64_MAX + 1)], ["--bogus", "0"]]
    rejections = []
    for label, executable in executables:
        for arguments in rejected_arguments:
            completed = subprocess.run([companion_path(executable), *arguments], cwd=ROOT, env=environment,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            require(completed.returncode == 2 and not completed.stdout,
                    f"{label}: invalid input was not rejected: {arguments!r}")
            rejections.append({"executable": label, "arguments": arguments,
                               "returncode": completed.returncode})
    return {
        "status": "passed", "wall_seconds": time.perf_counter() - started,
        "reference": "Full binary-string decoding from left to right, grouping equal parts, then set of run types",
        "small_interval_inclusive": [0, last], "small_integers": last + 1,
        "small_count_stream": reference_path.name,
        "small_count_stream_sha256": digest(reference_path),
        "small_first_occurrences": [{"n": n, "value": str(value)} for n, value in sorted(first.items())],
        "boundary_intervals": windows, "boundary_integer_queries": sum(row["integers"] for row in windows),
        "boundary_intervals_can_overlap": True, "examples": example_rows,
        "negative_controls": ["45 has four maximal runs but only two distinct types",
                              "27 has two distinct part values but three distinct run types"],
        "invalid_argument_rejections": rejections,
        "builds_compared": [label for label, _executable in executables],
    }


def run_full_scan(executable: Path, last: int, output: Path,
                  environment: dict[str, str]) -> dict:
    require(hasattr(os, "wait4") and sys.platform in ("darwin", "linux"),
            "Per-process measurement currently supports macOS/Linux os.wait4")
    command = [companion_path(executable), "--scan", str(last)]
    stdout = output / "scan.stdout.json"
    stderr = output / "scan.stderr.txt"
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    with stdout.open("wb") as out_stream, stderr.open("wb") as err_stream:
        child = subprocess.Popen(command, cwd=ROOT, env=environment,
                                 stdout=out_stream, stderr=err_stream)
        waited_pid, status, usage = os.wait4(child.pid, 0)
        require(waited_pid == child.pid, "wait4 returned a different child")
        child.returncode = os.waitstatus_to_exitcode(status)
    elapsed = time.perf_counter() - started
    require(child.returncode == 0, f"full scan failed with exit status {child.returncode}")
    summary = json.loads(stdout.read_text())
    require(summary["interval_inclusive"] == ["0", str(last)], "wrong scanned interval")
    require(int(summary["integers_visited"]) == last + 1, "wrong inclusive integer count")
    rows = summary["first_occurrences"]
    require(len({row["n"] for row in rows}) == len(rows), "duplicate first-occurrence indices")
    require(sum(int(row["occurrences"]) for row in rows) == last + 1,
            "histogram does not cover every visited integer")
    first = {row["n"]: int(row["value"]) for row in rows}
    expected = {n: value for n, value in enumerate(EXPECTED_FIRST) if value <= last}
    require(all(first.get(n) == value for n, value in expected.items()),
            "first occurrences disagree with recorded A351015 table")
    if last == DEFAULT_LAST:
        require(first == expected and summary["maximum_rho_observed"] == 10,
                "unexpected first-occurrence indices in the full target interval")
    require(tuple(map(tuple, summary["last_maximal_runs"])) == definition_runs(last),
            "final maintained composition disagrees with full decoding")
    raw_rss = usage.ru_maxrss
    rss_units = "bytes" if sys.platform == "darwin" else "KiB"
    rss_bytes = raw_rss if sys.platform == "darwin" else 1024 * raw_rss
    return {
        "status": "passed", "command": command, "cwd": ". (companion root)",
        "started_utc": started_utc, "finished_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": child.returncode, "wall_seconds": elapsed,
        "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime,
        "maximum_rss_raw": raw_rss, "maximum_rss_raw_unit": rss_units,
        "maximum_rss_bytes": rss_bytes, "maximum_rss_mib": rss_bytes / (1024 * 1024),
        "measurement": "One fresh subprocess; wall time includes launch/output, excludes compilation and controls; os.wait4 per-child usage",
        "stdout": stdout.name, "stdout_sha256": digest(stdout),
        "stderr": stderr.name, "stderr_sha256": digest(stderr), "summary": summary,
        "algorithm": "Exhaustive definition-only incremental scan; every integer is visited; composition updated after binary +1",
        "independence": "Uses neither producer code, minimum-length theorem, nor rearrangement/capacity inequalities",
        "limitation": "Finite exhaustive verification only, through the stated inclusive endpoint; counts are maintained incrementally rather than decoded from scratch at each integer",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "validation" / "results" / "oct21" / "raw_scan")
    parser.add_argument("--end", type=int, default=DEFAULT_LAST)
    parser.add_argument("--control-end", type=int, default=(1 << 20) - 1)
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument("--sanitizers", default="undefined,bounds",
                        choices=("undefined,bounds", "address,undefined"),
                        help="Sanitizer build used for controls; address sanitizer may be unavailable on some host toolchains")
    args = parser.parse_args()
    require(0 <= args.end < UINT64_MAX, "--end must be in [0, UINT64_MAX)")
    require(0 <= args.control_end <= 10_000_000, "--control-end must be in [0, 10000000]")
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / "validation" / "results"),
            "--output must be inside this companion tree's validation/results directory")
    require(not (output / "report.json").exists(), "Choose a fresh --output directory; report.json already exists")
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "tmp"
    temporary.mkdir(exist_ok=True)
    environment = dict(os.environ, TMPDIR=str(temporary), PYTHONDONTWRITEBYTECODE="1")
    compiler = shutil.which("clang") or shutil.which("cc") or shutil.which("gcc")
    require(compiler is not None, "A C11 compiler is required")
    records: list[dict] = []
    report: dict = {
        "status": "running", "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "controls_only" if args.controls_only else "controls_and_exhaustive_scan",
        "sanitizer_configuration": args.sanitizers,
        "source_sha256": {str(SOURCE.relative_to(ROOT)): digest(SOURCE),
                          str(Path(__file__).resolve().relative_to(ROOT)): digest(Path(__file__))},
        "hardware": hardware(), "commands": records,
        "provenance": "Fresh OpenAI Codex implementation from the composition definition; no external reviewer's source or results used as evidence",
    }
    report_path = output / "report.json"
    try:
        compiler_version = command_record([compiler, "--version"], output, "compiler_version",
                                          environment, records).decode(errors="replace")
        report["compiler_version"] = compiler_version
        optimized = output / "raw_scan"
        sanitized = output / "raw_scan_sanitized"
        common = [compiler, "-std=c11", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-pedantic"]
        command_record([*common, "-O3", companion_path(SOURCE), "-o", companion_path(optimized)],
                       output, "compile_optimized", environment, records)
        command_record([*common, "-O1", "-g", f"-fsanitize={args.sanitizers}",
                        "-fno-omit-frame-pointer", companion_path(SOURCE), "-o", companion_path(sanitized)],
                       output, "compile_sanitized", environment, records)
        report["executable_sha256"] = {optimized.name: digest(optimized), sanitized.name: digest(sanitized)}
        print(f"Checking both builds against direct decoding on 0..{args.control_end} and carry boundaries.", flush=True)
        report["controls"] = run_controls([("optimized", optimized), ("sanitized", sanitized)],
                                           args.control_end, output, environment, records)
        print("All direct-decoder, carry-boundary, duplicate-type, and invalid-input controls passed.", flush=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        if not args.controls_only:
            print(f"Starting the single exhaustive scan over every integer 0..{args.end}, inclusive.", flush=True)
            report["full_scan"] = run_full_scan(optimized, args.end, output, environment)
            print(f"Full scan passed in {report['full_scan']['wall_seconds']:.6f} seconds.", flush=True)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["source_sha256_at_finish"] = {
            str(SOURCE.relative_to(ROOT)): digest(SOURCE),
            str(Path(__file__).resolve().relative_to(ROOT)): digest(Path(__file__)),
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(report_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
