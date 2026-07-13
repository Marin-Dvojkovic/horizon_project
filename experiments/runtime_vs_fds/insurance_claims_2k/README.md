# Runtime vs. number of FDs — insurance_claims_2k

## The question

Same curiosity as the hospital_2k experiment, on another small dataset: with the
data fixed, does runtime trend upward as FDs are added, and does the small-data
stage split (graph-build vs. repair) look the same?

## Setup

`insurance_claims_2k` = ~2k rows, **11 FDs**, one cyclic pair
(`max_torque ⇄ max_power`). Notable: `model` is a **hub** — six FDs share it as
LHS (`model → engine_type / airbags / width / length / is_power_steering /
max_power`). Data held fixed at the full 2k rows; FD count grows 1 → 11. For each
count `k` we draw random `k`-subsets (distinct where `C(11, k)` allows, repeats
once exhausted), run **30 rounds**, drop the first, keep **29**.

## Files

| file | what it is |
|------|------------|
| `results.csv` | one row per kept round: `n_fds, round, n_attrs, fds, order_secs, graph_secs, repair_secs, total_secs` (319 rows = 11 counts × 29) |
| `runtime_vs_attrs.png` | total runtime vs. distinct attributes touched, colored by #FDs |

Produced by `notebooks/runtime_vs_fds_insurance_claims_2k.ipynb`.

## Insights

**1. Clear, roughly linear upward trend.**
Average total climbs from ~72 ms (1 FD) to ~270 ms (11 FDs), about **+20 ms per
added FD**. Plotted against #attributes (the smoother view) the mean line rises
steadily. The trend is unmistakable.

| #FDs | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|------|---|---|---|---|---|---|---|---|---|----|----|
| total (ms) | 72 | 85 | 120 | 159 | 189 | 150 | 209 | 226 | 217 | 243 | 270 |
| graph (ms) | 16 | 27 | 55 | 81 | 98 | 66 | 116 | 127 | 111 | 127 | 145 |
| repair (ms) | 56 | 57 | 65 | 78 | 90 | 83 | 92 | 98 | 106 | 115 | 124 |
| order (ms) | 0.4 | 0.4 | 0.5 | 0.6 | 0.6 | 0.6 | 0.6 | 0.7 | 0.7 | 0.7 | 0.8 |

**2. Same small-data stage split as hospital_2k: graph-build overtakes repair.**
Graph-build grows ~16 → 145 ms (≈9×) and passes repair, which grows only ~56 →
124 ms (≈2×). Identical pattern to hospital_2k — on ~2k rows the per-tuple repair
loop is cheap and grows slowly, while graph-build (cost ∝ #FDs / pattern-edges)
dominates. Ordering stays negligible (~0.4–0.8 ms). This confirms the small-data
behavior isn't a hospital quirk.

**3. Per-#FDs means wobble (k=6 dips, k=9 dips) — because here FD cost is
*heterogeneous*.**
Unlike a clean monotone rise, k=6 (150 ms) sits below k=5 (189 ms). Reason: the
`model` hub FD is far more expensive to build patterns for (many distinct model
values → many nodes/edges) than a thin FD like `region_code → region_density`. So a
random 6-subset that happens to include few `model`-FDs is cheaper than a 5-subset
loaded with them. With only 29 sampled subsets out of `C(11,6)=462`, that
composition luck still shows through in the per-count mean. **Takeaway: at fixed
data size, *which* FDs you add matters as much as *how many* — a hub attribute
costs more than a peripheral one.** (The #attributes x-axis smooths this, since it
groups by columns actually touched.)

**4. No unorderable draws.** The `max_torque ⇄ max_power` cycle (and subsets
containing it) ordered fine every time, so nothing was silently dropped.

## Caveats

- Absolute times are tens–hundreds of ms; this is about *shape*, not headline
  numbers.
- Per-count means carry subset-composition variance (insight 3), not just timing
  noise — the trend is the signal, individual bumps are sampling.
- Small-data stage split (graph > repair) does **not** carry to production scale;
  at millions of rows repair dominates (see the service_tickets experiment).

## Reproduce

```
uv run jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 \
  notebooks/runtime_vs_fds_insurance_claims_2k.ipynb
```

Knobs in the notebook's `config` cell: `SAMPLE_ROWS`, `N_ROUNDS`, `SEED`.
