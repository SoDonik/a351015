# OEIS A351015: a length formula and new terms

Companion code and preprint for a note on **OEIS [A351015](https://oeis.org/A351015)**
— the smallest k whose standard-order composition ([A066099](https://oeis.org/A066099))
has exactly n distinct runs.

The note gives an exact formula for the binary length of a(n) — the partial sums of
[A061017](https://oeis.org/A061017) — shows the lower bound is always attained,
gives an exact algorithm, extends the sequence with terms through a(16), and derives
log₂ a(n) ∼ n² / (2 log n).

Terms a(10)–a(16) are contributed to OEIS A351015. The note computes terms through a(20); these larger terms rest on the length theorem (Theorem 2.2) — there is no brute-force check at that scale, and a(17)–a(20) are cross-checked by an independent verifier included here.

## Files
- `paper.pdf` — the note.
- `a351015_exact.py` — exact structural computation (Python standard library only);
  verifies the certificate and all recorded terms through a(16).
- `a351015_fast_exact.cpp` — faster C++ producer for larger n (optional).
- `a351015_independent_verify.py` — independent prefix-language checker that
  re-verifies claimed terms without reusing the producer's method (optional).

## Reproduce
```bash
python a351015_exact.py --max-n 16
```
Add `--details` to print the binary words and run-type orderings.

For the independent cross-check of individual terms:
```bash
python a351015_independent_verify.py
```

## Author
Daniyal Kadirbekov — [OEIS profile](https://oeis.org/wiki/User:Daniyal_Kadirbekov),
[A397506](https://oeis.org/A397506)
