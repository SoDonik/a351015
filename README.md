# OEIS A351015: exact length formula and polynomial construction

Programs and reproducible checks for [OEIS A351015](https://oeis.org/A351015),
the smallest k such that the k-th composition in standard order
([A066099](https://oeis.org/A066099)) has exactly n distinct runs.
They accompany the paper *Distinct Runs in Standard-Order Compositions:
An Exact Length Formula and a Polynomial Construction* by Daniyal Kadirbekov.

## Results in brief

- The binary length of a(n) is the sum of the n smallest products v*l over
  ordered pairs of positive integers (v, l), counted with multiplicity. These
  are the partial sums of [A061017](https://oeis.org/A061017); the length
  sequence itself is [A397890](https://oeis.org/A397890).
- a(n) can be computed in time polynomial in n. The construction, suggested by
  an anonymous referee, tests whether a binary prefix extends to a qualifying
  word of minimum length, and appends the least possible next bit.
- The terms are computed through a(20) and checked by several separate
  methods, listed below.
- log2 a(n) ~ n^2 / (2 log n).

## Compute terms

Use Python 3.10 or later; the Python programs need only the standard library.
Run these commands from the repository root:

```sh
python3 -B code/a351015_polynomial.py --max-n 20 --details
python3 -B code/a351015_polynomial.py --n 100 --json
```

The default range is 0 through 20. `--n` selects one index, `--details` prints
the binary words and ordered run types, and `--json` emits the binary word,
encoding length, and ordered run types. Decimal values in JSON are strings so a
JSON reader cannot round a large integer. For example, the program returns
`a(4) = 155` with binary word `10011011` and encoding length 8.

`PrefixOracle(n).feasible(prefix)` tests for a completion to any qualifying
word of minimum encoding length. It does not require the prefix to belong to
the least such word: for n = 2 it accepts `11`, whose completion `110` is larger
than the least word `101`.

## Programs

| Program | Role |
|---|---|
| `code/a351015_polynomial.py` | Greedy bit-by-bit construction using the prefix test. |
| `code/a351015_exact.py` | Original subset dynamic program. |
| `code/a351015_fast_exact.cpp` | Original C++ program, specialized to indices 17 through 20. |
| `code/a351015_independent_verify.py` | Original prefix automaton with boundary enumeration and recursive label completion. |

The three original programs are byte-for-byte identical to those at commit
[`74bed98`](https://github.com/SoDonik/a351015/tree/74bed98a778c46017ad676e892b4309b35d57015)
(July 20, 2026). The header of `code/a351015_polynomial.py` records its
attribution and mathematical dependencies.

## Check the package first

```sh
python3 -B validation/verify_package.py
```

`PACKAGE_MANIFEST.json` lists the size and SHA-256 hash of every supplied file
except itself. The command above confirms that the files are unchanged; it does
not check the mathematics.

Rerunning the commands below replaces the supplied report files. To keep them,
run the checks in a separate copy of the repository.

## Reproduce the checks

These commands need macOS or Linux. The benchmark also needs `clang++` or `g++`
with C++17 and `unsigned __int128` support; it compiles the C++ program locally.

```sh
python3 -B validation/validate_revision.py
python3 -B validation/benchmark_revision.py
python3 -B validation/second_audit/audit_code.py
```

Run them in this order: the benchmark reads the core report, and the expanded
audit reads the benchmark logs. The audit also writes scratch files under
`tmp/second_audit/`.

- The core validation covers the table through n = 20, 3711 label-count cases,
  9216 optional-boundary cases, input edge cases, the original dynamic program
  through n = 12, and the original verifier through n = 20 with 19 valid but
  nonminimal controls. Its direct integer scan stops at a(7) = 281975.
- The benchmark runs each case in one fresh process, including startup and
  output; C++ compilation is measured separately. Maximum resident memory comes
  from that child's `os.wait4` record. It also checks the original Python
  dynamic program through n = 16 and the C++ program for n = 17 through 20.
  Times describe the machine and its load, not asymptotic complexity.
- The expanded audit compares the prefix test with all 1,118,797 binary strings
  of lengths 0 through L(n), for n = 1 through 7, using languages obtained by
  decoding every integer through 524287. It also checks all 27874 nonempty
  boundary subsets for cutoffs 1 through 100, and sampled larger indices through
  n = 66 with the original verifier.

Checks that use the structural theorem (the characterization of minimum-length
run-type sets) depend on that theorem; they are not unrestricted integer searches.

Two further checks have their own drivers:

```sh
python3 -B validation/oct21/run_independent.py --max-n 120 --exact-max-n 20 --exhaustive-max-n 6
python3 -B validation/oct21/run_raw_scan.py --output validation/results/raw_scan_rerun
```

- The first compares a separately written implementation with the polynomial
  program for every index from 0 through 120. It also runs an exact search
  through n = 20 that enumerates boundary subsets and orders labels recursively,
  without either capacity formula, and compares raw-decoded languages through
  n = 6. The separate implementation follows the same lemmas, so agreement
  checks the code, not the lemmas. Its hash was recorded before the polynomial
  program was read, in
  `validation/results/oct21/independent/precomparison_implementation.json`.
  The comparison driver and the exact search were written afterwards.
- The second visits all 4,503,885,792 integers from 0 through
  a(10) = 4503885791, inclusive. It updates the composition after each binary
  increment and uses no structural theorem or capacity formula. Controls compare
  the update with full decoding for every integer from 0 through 1048575 and at
  explicit carry boundaries, including the crossing of 2^32. It needs a C11
  compiler, writes to a new output directory, and refuses to replace an existing
  report. See [the scan description](validation/oct21/raw_scan_README.md) for the
  update rule and its scope.

## Supplied evidence

All reports below were generated on October 21, 2026.

| Report | Contents |
|---|---|
| [Core validation](validation/results/validation.json) | Table certificates, small exhaustive tests, and comparisons with the original programs. |
| [Benchmark](validation/results/benchmarks.json) | The five measurements in the paper's timing table. |
| [Expanded audit](validation/results/second_audit/code_audit.json) | Complete small prefix languages, boundary subsets, and sampled larger indices. |
| [Separate implementation](validation/results/oct21/independent/run_report.json) | Agreement through n = 120, exact search through n = 20, and 70,223 raw-language prefix checks including n = 0. |
| [Exhaustive scan](validation/results/oct21/raw_scan/completed/report.json) | Every integer through a(10), with decoder controls and the original output; the full scan took 33.39 seconds. |

The benchmark ran on an Apple M4 with 16 GiB of RAM, macOS 26.5, Python 3.14.7,
and Apple clang 17.0.0. Each report records its commands, source hashes, and
the actual software versions.

`PROVENANCE.json` records the source hashes and the small changes made to the
check scripts so that they run from this repository; the exact patches and a
function-identity comparison are in `provenance/`. The numerical programs are
unchanged. Compiled executables are not included; rerunning the drivers builds
them locally, and the reports record the hashes of the binaries used.

## Repository history

- [`1e61016`](https://github.com/SoDonik/a351015/tree/1e61016cd2258050d0bf7a54125886b424132ff1)
  (July 14, 2026): the original programs, already containing a(17) through a(20).
- [`74bed98`](https://github.com/SoDonik/a351015/tree/74bed98a778c46017ad676e892b4309b35d57015)
  (July 20, 2026): the original programs at the repository root, with the July
  preprint [`paper.pdf`](https://github.com/SoDonik/a351015/blob/74bed98a778c46017ad676e892b4309b35d57015/paper.pdf).
- [`529ebf5`](https://github.com/SoDonik/a351015/tree/529ebf5fb36d3f17b0c1382dd2cb52407ee04df6)
  (October 22, 2026): the polynomial construction and the checks above. The
  three original programs moved unchanged into `code/`. The July preprint is no
  longer on the main branch and remains available at `74bed98`.

To reproduce a stated result exactly, use the fixed commit that the paper
cites rather than the latest version of the main branch.

## License

MIT; see [`LICENSE`](LICENSE).

## Author

Daniyal Kadirbekov: [OEIS profile](https://oeis.org/wiki/User:Daniyal_Kadirbekov),
[A397506](https://oeis.org/A397506)
