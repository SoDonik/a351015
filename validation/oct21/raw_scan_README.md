# Exhaustive definition-only scan

`raw_scan.c` visits each integer in the requested inclusive interval and
maintains the number of distinct maximal run types in its composition.
It uses no minimum-length theorem, rearrangement criterion, capacity
inequality, or polynomial producer code. `run_raw_scan.py` supplies
independent decoder controls, compiles the source, runs the scan, and
records its actual output and measurements.

The complete binary word of every integer is **not** decoded again during
the large scan. The program instead updates the exact composition after
each increment. This is still an exhaustive scan: it visits every integer
and computes its statistic, without pruning or skipping intervals.

## Why the increment is exact

Suppose the binary expansion of `k` ends in `t` ones. Its composition ends
in `t` parts equal to 1. If an earlier part remains, call it `v`; it is at
least 2 because the bit before those trailing ones is zero. Adding one
replaces that zero by one and the `t` trailing ones by zeros. Therefore
the composition changes from

```text
prefix, v, 1, ..., 1  ->  prefix, v - 1, t + 1
              t copies
```

If the binary expansion consists entirely of ones, adding one produces
the single part `t + 1`. This also treats `k = 0` as an empty composition.
The implementation updates maximal runs after each append, merging equal
adjacent values, and keeps occurrence counts for each run type. The
number of types with nonzero occurrence count is exactly the statistic.

Starting at zero and applying this transition once between consecutive
integers proves that the maintained composition is the correct one at
each visit. Recording the first visit of each statistic gives its least
integer within the scanned interval.

## Reproduction

The runner requires Python 3.10 or later, a C11 compiler supporting the
chosen sanitizer flags, and macOS or Linux for per-process resource
measurement. It uses only Python's standard library. Run these commands
from the companion directory, using a fresh output directory each time:

```sh
python3 -B validation/oct21/run_raw_scan.py --controls-only --output validation/results/raw_scan_controls
python3 -B validation/oct21/run_raw_scan.py --output validation/results/raw_scan_rerun
```

The second command scans every integer from 0 through 4,503,885,791,
inclusive: 4,503,885,792 integers. Compilation and controls run before the
timed scan. Existing reports are never overwritten. The `--end` option
can select a shorter inclusive scan, and `--control-end` selects the end
of the small exhaustive decoder comparison.

The default control build uses `-fsanitize=undefined,bounds`, while the
large scan uses the optimized build with assertions enabled. The option
`--sanitizers address,undefined` requests an address-sanitized control
build on a compatible toolchain. On the original macOS 26.5 host, the
address-sanitizer runtime stalled in initialization before the program's
`main` function. The completed evidence therefore uses undefined-behavior
and bounds sanitizers, and makes no claim that address-sanitizer controls
passed. The failed attempt and its diagnostic sample are retained in the
author's local revision history.

The successful controls compare both C builds with a separate Python
decoder that reads the entire binary word, forms its parts, groups equal
parts into maximal runs, and counts the set of types. They cover every
integer from 0 through 2^20 - 1; windows around powers of two through
2^63; the 2^32 crossing; the endpoint 4,503,885,791; the largest unsigned
64-bit integer; explicit examples with duplicate types; and malformed
command-line inputs. Boundary windows overlap, so their query counts are
not counts of distinct additional integers.

## Evidence and scope

`validation/results/oct21/raw_scan/completed/report.json` binds the
completed run to the C source and Python runner hashes. It records actual
commands relative to the companion root, compiler and host information,
decoder controls, and the full scan's interval, coverage count, first
occurrences, histogram, and final composition. Raw process output and its
hashes are retained alongside that report. The scan's wall time includes
process launch and output, but excludes compilation and controls; peak
memory is the individual child's `os.wait4` measurement.

This finite check confirms the first occurrences through `a(10)` when run
to the default endpoint. It does not exhaustively verify later terms and
does not replace the general proofs. The source and driver were written
by OpenAI Codex for this revision; no external reviewer's unpublished
program or timing was reused as evidence.
