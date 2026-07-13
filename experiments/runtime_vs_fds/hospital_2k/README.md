# Runtime vs. number of FDs — hospital_2k

## The question

Same curiosity as `runtime_vs_fds_service_tickets`, on a *tiny* dataset: with the
data fixed, does runtime show a clean trend as you add more FDs — and does it look
different from the big-data case?

## Setup

`hospital_2k` = ~2k rows, **8 FDs** (one cyclic pair, `measure_id ⇄ measure_name`).
Data held fixed at the full 2k rows; FD count grows from 1 to 8. For each count `k`
we draw random `k`-subsets (distinct where `C(8, k)` allows, repeats once
exhausted), run **30 rounds**, drop the first (warm-up), keep **29**. Because each
run is sub-second, 29 rounds is cheap and averages out most of the timing noise —
which is exactly what you need to see a trend on such small numbers.

## Files

| file | what it is |
|------|------------|
| `results.csv` | one row per kept round: `n_fds, round, n_attrs, fds, order_secs, graph_secs, repair_secs, total_secs` (232 rows = 8 counts × 29) |
| `runtime_vs_attrs.png` | total runtime vs. distinct attributes touched, colored by #FDs |

Produced by `notebooks/runtime_vs_fds_hospital_2k.ipynb`.

## Insights

**1. Yes — there is a clear, near-linear trend, even at 2k rows.**
Average total climbs monotonically from ~63 ms (1 FD) to ~273 ms (8 FDs), roughly
**+30 ms per added FD**. With 29 rounds averaged, the mean line is smooth and never
dips — the trend is real, not noise.

| #FDs | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|------|---|---|---|---|---|---|---|---|
| total (ms) | 63 | 117 | 154 | 180 | 188 | 213 | 239 | 273 |
| graph (ms) | 17 | 48 | 78 | 101 | 110 | 123 | 138 | 158 |
| repair (ms) | 45 | 69 | 75 | 79 | 78 | 89 | 101 | 114 |
| order (ms) | 0.4 | 0.5 | 0.6 | 0.6 | 0.6 | 0.6 | 0.7 | 0.7 |

**2. The interesting part: here graph-build dominates, not repair — the opposite of
service_tickets.**
On service_tickets (1M rows) repair was ~90% of the time and drove everything. On
hospital_2k the composition **flips**: graph-build grows ~17 → 158 ms (≈9×) and
overtakes repair, which grows only ~45 → 114 ms (≈2.5×). Why: repair cost is
"per-tuple work × #rows", and with just 2k rows that's cheap and grows slowly.
Graph-build cost scales with the number of FDs/pattern-edges and is largely
independent of the small row count, so on tiny data it becomes the bottleneck. So
**which stage dominates depends on data size**, but *both* grow with #FDs, so the
total-vs-#FDs trend holds either way.

**3. Ordering is free.** The static analysis (§4–5) stays ~0.4–0.7 ms at every
count — negligible, same as on the big dataset.

**4. No unorderable draws.** The cyclic `measure_id ⇄ measure_name` pair (and
subsets containing it) ordered fine every time, so no draws were silently dropped —
the averages are unbiased.

## Caveats

- **Absolute times are tiny (tens–hundreds of ms)**, so this is about *shape*, not
  headline numbers. The per-round scatter is proportionally larger than on big
  data; the 29-round averaging is what makes the trend legible.
- Because the dataset is only ~2k rows, don't read the stage split as
  representative of production scale — at scale repair dominates again (see the
  service_tickets experiment).

## Reproduce

```
uv run jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 \
  notebooks/runtime_vs_fds_hospital_2k.ipynb
```

Knobs in the notebook's `config` cell: `SAMPLE_ROWS`, `N_ROUNDS`, `SEED`.
