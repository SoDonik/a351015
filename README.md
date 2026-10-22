# A351015: polynomial construction and reproducible checks

This package implements the anonymous referee's polynomial construction for
[OEIS A351015](https://oeis.org/A351015). The construction tests whether a binary
prefix has a completion of minimum encoding length and then chooses the least
possible next bit. The producer header records its
attribution and mathematical dependencies.

The four programs in `code/` are copied without changes from the reviewed
revision workspace. The three earlier programs also match public commit
[`74bed98a778c46017ad676e892b4309b35d57015`](https://github.com/SoDonik/a351015/tree/74bed98a778c46017ad676e892b4309b35d57015).
That commit identifies the earlier programs; it is not the version identifier
of this new package. The containing repository's eventual release commit
identifies this package.

## Compute terms

Use Python 3.10 or later; the Python programs need only the standard library.
Run these commands from this directory:

```sh
python3 -B code/a351015_polynomial.py --max-n 20 --details
python3 -B code/a351015_polynomial.py --n 100 --json
```

The default range is 0 through 20. `--n` selects one index, and `--json` includes
the binary word, encoding length, and ordered run types. Decimal values in JSON
are strings so a JSON reader cannot round a large integer. For example, the
program returns `a(4) = 155` with binary word `10011011` and encoding length 8.

`PrefixOracle(n).feasible(prefix)` tests for a completion to any qualifying
word of minimum encoding length. It does not require the prefix to belong to
the least such word: for n = 2 it accepts `11`, whose completion `110` is larger
than the least word `101`.

| Program | Role |
|---|---|
| `code/a351015_polynomial.py` | Greedy construction using the referee's prefix test. |
| `code/a351015_exact.py` | Original subset dynamic program. |
| `code/a351015_fast_exact.cpp` | Original C++ program specialized to indices 17 through 20. |
| `code/a351015_independent_verify.py` | Original prefix automaton with boundary enumeration and recursive label completion. |

## Reproduce the checks

Run the following commands in order. The first two write their primary reports
under `validation/results/`; the expanded audit also writes scratch files under
`tmp/second_audit/`.

```sh
python3 -B validation/validate_revision.py
python3 -B validation/benchmark_revision.py
python3 -B validation/second_audit/audit_code.py
```

The benchmark needs macOS or Linux and `clang++` or `g++` with C++17 and
`unsigned __int128` support. It compiles the C++ program locally. Each benchmark
row measures one fresh process, including startup and requested output; C++
compilation is measured separately. Maximum resident memory comes from that
child's `os.wait4` record. Times describe the machine and load at the recorded
run, and are not evidence for asymptotic complexity.

The core validation covers the table through n = 20, 3711 label-count cases,
9216 optional-boundary cases, input edges, the original dynamic program through
n = 12, and the original verifier through n = 20 with 19 valid nonminimal
controls. Its direct integer scan stops at `a(7) = 281975`.

The expanded audit compares the prefix test with all 1,118,797 binary strings
of lengths 0 through L(n), for n = 1 through 7. It obtains these complete
languages by raw decoding through integer 524287. It also checks all 27874
nonempty boundary subsets for cutoffs 1 through 100, and selected larger
indices through n = 66 using the earlier verifier. These larger checks depend
on the theorem characterizing minimum-length run-type sets; they are not
unrestricted integer searches. The separate n = 100 benchmark checks a raw
run certificate and scalability, and does not itself independently establish
numerical minimality.

Two additional October 21 checks have their own drivers:

```sh
python3 -B validation/oct21/run_independent.py --max-n 120 --exact-max-n 20 --exhaustive-max-n 6
python3 -B validation/oct21/run_raw_scan.py --output validation/results/raw_scan_rerun
```

The first driver compares a separately written implementation with the producer
for every index from 0 through 120. It also performs an exact search through
n = 20 using boundary-subset enumeration and recursive label ordering without
either capacity formula, plus raw-language checks through n = 6. The independent
implementation follows the same manuscript lemmas; agreement does not provide
an independent proof of those lemmas. The original implementation hash was
recorded before reading the producer and is retained in
`validation/results/oct21/independent/precomparison_implementation.json`.
That record applies to `independent_prefix.py`; the comparison driver and its
separate exact search were written after producer inspection.

The second driver visits all 4,503,885,792 integers from 0 through
`a(10) = 4503885791`, inclusive. It updates the exact composition after each
binary increment and uses no structural theorem or capacity formula. Controls
compare the update method against full decoding for integers 0 through
1048575 and explicit carry boundaries. The original complete run is retained
unchanged under `validation/results/oct21/raw_scan/completed/`. Its sources,
raw output, source hashes, actual timing, and memory measurements are included.
See [the scan description](validation/oct21/raw_scan_README.md) for the update
identity, sanitizer coverage, and exact scope. A C11 compiler is required.

These extended drivers use macOS or Linux process/resource facilities. The
independent runner writes under `validation/results/oct21/independent/`;
use a separate package copy to retain the bundled results. The raw scan
requires a new output directory and refuses to replace an existing report.

Default commands replace the report files from a previous run. To retain
bundled evidence, run in a separate copy of this package. The first two
commands also accept `--output validation/results/your-run/report.json`.
The benchmark still requires the core report at `validation/results/validation.json`.
The expanded audit expects the default benchmark logs, so run all three in a
separate copy when preserving a complete earlier run.

## Evidence and provenance

The clean-copy reproduction completed successfully on October 21, 2026.
The following reports are included:

| Report | Evidence |
|---|---|
| [Core validation](validation/results/validation.json) | Table certificates, small exhaustive tests, and earlier-program comparisons. |
| [Benchmark](validation/results/benchmarks.json) | The fresh five-row measurement used for the revised manuscript's timing table. |
| [Expanded numerical audit](validation/results/second_audit/code_audit.json) | Complete small prefix languages, boundary subsets, and larger sampled checks. |
| [Independent implementation](validation/results/oct21/independent/run_report.json) | Agreement through n = 120, exact structural search through n = 20, and 70,223 raw-language prefix checks including n = 0. |
| [Exhaustive scan](validation/results/oct21/raw_scan/completed/report.json) | Every integer through a(10), with decoder controls and original output. |

The benchmark ran on an Apple M4 with 16 GiB RAM, macOS 26.5, Python 3.14.7,
and Apple clang 17.0.0. Its report records the actual measurement conditions.
The raw-scan report is copied without changes from its completed local run.
The other reports were generated in an isolated copy of this package whose
path contains spaces, without the private manuscript or workspace archives.

`PROVENANCE.json` records the source hashes and the release-only harness
adaptations; exact patches and a function-identity comparison are in
`provenance/`. The numerical programs are unchanged. The harnesses use the fixed
public program hashes instead of private baseline files and record commands
with package-relative paths and executable names. Actual Python, compiler,
and operating-system versions remain in the reports.

The expanded public audit omits checks of the private manuscript, earlier
workspace snapshots, and historical build files. Its numerical checks are
retained. Reports generated here are fresh release-package evidence and are
separate from the historical measurements retained in the author's workspace.
`PACKAGE_MANIFEST.json` binds the packaged files to their SHA-256 hashes. Before
rerunning commands that replace evidence files, check the supplied package with:

```sh
python3 -B validation/verify_package.py
```

Compiled executables and temporary caches are not bundled. Rerunning the
drivers creates them locally. Recorded binary hashes identify the executables
used for the measurements. Binary count streams in the scan evidence are data,
not executable files.

The `LICENSE` file is an unchanged copy of the MIT license at the fixed public
baseline commit. This directory belongs alongside the earlier repository files;
it does not replace the root manuscript or earlier computational history.
