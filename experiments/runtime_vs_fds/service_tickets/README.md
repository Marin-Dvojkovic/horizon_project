# Runtime vs. number of FDs — service_tickets (1M rows)

## The question

How does Horizon's runtime change as you give it **more functional dependencies
(FDs)**, with the amount of data held fixed?

The sibling experiment (`notebooks/runtime_service_tickets.ipynb`) fixes the FDs
and grows the rows — that shows Horizon is linear in the number of *rows*. This
one does the opposite: it fixes the data at a **1M-row sample** and grows the
number of FDs from **1 up to all 10**, to see the cost of each additional rule.

## Setup in one paragraph

`service_tickets_21m` has 10 FDs. For each FD-count `k` (1…10) we pick **random**
subsets of `k` FDs — random because *which* FDs you pick changes how they interact
(the four §4.1 interaction cases), and we want a representative average rather than
one lucky/unlucky combination. For each `k` we run 4 rounds, throw away the first
(cold cache / warm-up), and keep 3. Every kept round runs the full pipeline and
records three separately-timed stages plus their total.

## Files

| file | what it is |
|------|------------|
| `results.csv` | one row per kept round: `n_fds, round, n_attrs, fds, order_secs, graph_secs, repair_secs, total_secs` (30 rows = 10 counts × 3 rounds) |
| `runtime_vs_attrs.png` | the plot: total runtime vs. number of distinct attributes the FDs touch, colored by #FDs |

Produced by `notebooks/runtime_vs_fds_service_tickets.ipynb`. Re-running it
regenerates both files here.

## How to read the plot

- **X-axis** = number of distinct *columns* (attributes) the chosen FDs reference.
  More FDs generally means more columns, but not always 1-to-1 (three rules all
  ending in `borough` add rules without adding many new columns) — that's why at a
  given x you can see dots of different colors.
- **Y-axis** = total wall-clock seconds for that run.
- **Color** = how many FDs were in that run.
- **Black line** = average runtime at each attribute count.

## The three stages (what's actually being timed)

Horizon runs in three phases; we time each so we can see where the time goes:

1. **order** — the static analysis (§4–5): build the FD graph, find cycles, decide
   the order to process FDs. Depends only on the *rules*, not the data.
2. **graph** — build the FD-pattern graph (§3): scan the data once and record, for
   every rule, which value-combinations occur and how often.
3. **repair** — the actual cleaning (§5.2): walk every one of the 1M tuples and,
   for each, resolve each FD to its best-supported pattern.

## Insights (the point of the experiment)

**1. Runtime grows roughly linearly with the number of FDs.**
Average total goes ~8.9 s (1 FD) → ~44.4 s (10 FDs) — about **+4 s per added FD**,
in a near-straight line. Adding a rule adds a roughly fixed, predictable amount of
work; there's no blow-up as rules pile up or start interacting. This is the "linear
by design" claim from the paper, seen along the *rules* axis instead of the rows
axis.

Average total per FD-count:

| #FDs | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|------|---|---|---|---|---|---|---|---|---|----|
| total (s) | 8.9 | 9.3 | 15.3 | 18.4 | 23.2 | 27.0 | 30.1 | 35.5 | 39.7 | 44.4 |

**2. Repair is where all the time goes, and it's what scales.**
At 10 FDs, repair is ~40 s of the ~44 s total (**~90%**). Graph-build is small and
jumpy (~0.05–6 s, mostly noise). Ordering is effectively free (~1 ms) at every
count — the static analysis is negligible. So "runtime vs #FDs" is really "repair
time vs #FDs": each extra rule means one more per-tuple decision across all 1M
rows.

**3. There is a fixed cost floor of ~5–9 s even at 1 FD.**
One rule still costs several seconds because the repair step **re-reads the whole
1M-row table every run regardless of how many columns the rule uses**. That read
is a constant offset baked into every point. So on the plot: the *slope* is the
real per-FD compute cost, and the *intercept* (~a handful of seconds) is mostly
just IO. Don't read the 1-FD number as "one rule costs 9 s of thinking" — most of
that is loading data.

**4. The scatter at a fixed #FDs is expected, not a bug.**
Points at the same #FDs differ because (a) different random rule subsets touch
different numbers of columns and different interaction cases, and (b) disk/cache
timing noise (e.g. the three 1-FD runs came out 4.9 / 10.5 / 11.1 s despite doing
identical-width work). Averaging over 3 rounds smooths this, but with only 3 kept
rounds the wobble is still visible.

**5. No rule subset was unorderable.**
The only cyclic pair (`agency ⇄ agency name`) never broke the ordering step, so
every random draw was usable and the averages aren't biased by silently-dropped
subsets.

## Caveats

- **Repair's IO offset** inflates the low-#FD end and flattens the apparent slope
  a little. To see the pure algorithmic cost, look at `order_secs + graph_secs`
  (IO-free) instead of `total_secs`.
- **1M rows, not 21M.** These are relative-scaling numbers on a sample, chosen so
  the full 40-round sweep finishes in ~25 min. Absolute times at 21M would be
  ~21× larger; the *shape* (linear in #FDs, repair-dominated) is what carries over.
- **3 kept rounds** is enough to see the trend, not to pin down each point tightly.

## Reproduce

```
uv run jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 \
  notebooks/runtime_vs_fds_service_tickets.ipynb
```

Knobs live in the notebook's `config` cell: `SAMPLE_ROWS`, `N_ROUNDS`, `SEED`.
