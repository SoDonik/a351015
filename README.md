# OEIS A351015: a length formula and new terms

Companion code and preprint for a short note on **OEIS [A351015](https://oeis.org/A351015)**
— the smallest k whose standard-order composition has n distinct runs.

The note proves an exact formula for the binary length of a(n) (the partial sums of
[A061017](https://oeis.org/A061017)), shows the lower bound is always attained, gives an
exact algorithm, extends the sequence with terms through a(16), and derives
log₂ a(n) ∼ n² / (2 log n).

## Files
- `paper.pdf` — the note (7 pages).
- `a351015_exact.py` — reproducible computation (Python standard library only).

## Reproduce
```bash
python a351015_exact.py --max-n 16
```
Add `--details` to print the binary words and run-type orderings.
Verifies the structural certificate and all recorded terms through a(16).

## Author
Daniyal Kadirbekov — [OEIS profile](https://oeis.org/wiki/User:Daniyal_Kadirbekov)
