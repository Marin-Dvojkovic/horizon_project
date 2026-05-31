# Eval — dataset selection metrics

## Purpose

Define the metrics used to *choose* which datasets we benchmark the Horizon re-implementation against, and lay out how the code for those metrics is organised and tested. This document is the spec; the `.py` files in `eval/` should mirror it 1:1.

## Goal

Reproduce the **characterisation axes** of Table 1 in `harness/horizon.md` so a new candidate dataset can be scored on the same dimensions the paper uses and slotted next to `Tax`, `Hospital`, `Parking`, `DataX`. We use the paper's metric *definitions*, not its numerical values — we use different FDs, so the numbers won't (and don't need to) match.

Metrics intended for **cross-dataset comparison** are normalised and size-independent. Denormalised forms exist only where the threshold value itself carries the meaning (e.g. `avg_frequency`, where `≤ 5` reads naturally as "a value appears ≤5 times on average").

## Metrics

Two input shapes — keep the split.

### From the data instance (`pl.DataFrame`)
Lives in `dataset_eval.py`.

| Metric | Definition | Range | Status |
|---|---|---|---|
| `column_redundancy(series)` | `log(N / n_unique) / log(N)` — log-scale duplication factor; both low- and high-cardinality columns spread across the range | `[0, 1]` | **rewrite** (replaces `avg_redundancy_col`) |
| `avg_redundancy(df)` | mean of `column_redundancy(col)` across columns | `[0, 1]` | **rewrite** (replaces `avg_redundancy_df` / `_df_2`, removes the duplicate) |
| `avg_value_length(df)` | mean length of stringified non-null values, averaged across columns | `[0, ∞)` — not bounded, but size-independent | port to polars, keep semantics |
| `avg_frequency(series)` | `non_null_count / unique_count` — average number of times a value appears in the column (denormalised; the paper's `avgRed`) | `[1, N]` | **new**, helper for the next row |
| `low_redundancy_col_count(df, threshold=5)` | # columns whose `avg_frequency` is ≤ threshold | `[0, n_cols]` | **new** — uses the denormalised metric so the threshold reads naturally. Default `5` matches paper Table 1 |
| `n_rows(df)`, `n_cols(df)` | shape | — | **new**, trivial |

Two redundancy formulas live side-by-side on purpose:
- `column_redundancy` (log-scale, in `[0, 1]`) → fed into `avg_redundancy(df)` for *cross-dataset comparison*.
- `avg_frequency` (denormalised, in `[1, N]`) → fed into `low_redundancy_col_count` because the *threshold itself* is what carries the meaning here.

Plus one aggregator:
- `characterize_dataset(df) -> dict` — returns all of the above in one call. Lives in `dataset_eval.py`.

### From the FD set (`list[FunctionalDependency]`)
Lives in `fd_eval.py`.

| Metric | Definition | Status |
|---|---|---|
| `attribute_overlap(fds)` | `(total_attr_occurrences − unique_attrs) / total_attr_occurrences` over all LHS+RHS positions | done, keep as-is |
| `fd_interaction_cases(fds)` | classify every unordered FD pair under the conditions below; return `set[str]` of the IC labels that fire anywhere in the FD set (e.g. `{"IC1", "IC3"}`) | **new** |

**LHS is treated as a set of attributes**, RHS as a single attribute (canonical form, §3.1). The four cases generalise cleanly to set operations on `(X, Y)` and `(X', Y')`:

| Case | Paper (single-attr) | Set-based condition |
|---|---|---|
| **IC1** shared LHS, different RHS | `A→B, A→C` | `X ∩ X' ≠ ∅` and `Y ≠ Y'` |
| **IC2** shared RHS | `A→C, B→C` | `Y = Y'` |
| **IC3** chain | `A→B, B→C` | `Y ∈ X'` or `Y' ∈ X` — holds for at least one direction of the pair |
| **IC4** cycle | `A→B, B→A` | `Y ∈ X'` and `Y' ∈ X` |

Paper covers composite LHS at the framework level (§3.1, §3.2 define FDs as `X → Y` with `X, Y ⊆ A`); §4.1 only illustrates the cases for single-attribute LHS for readability. The set-based table above is the operational definition we use.

Implementation note: compute `frozenset(fd.lhs)` on the fly inside `fd_interaction_cases`. The four cases are **not mutually exclusive** under composite LHS — e.g. `{A}→B, {A,B}→C` satisfies both IC1 (`X ∩ X' = {A}`) and IC3 (`B ∈ X'`). For a `set[str]`-returning function this is fine; we union across pairs.

> Aside (not for this PR): `FunctionalDependency.__eq__` is tuple-based, so `FD(("A","B"), "C") ≠ FD(("B","A"), "C")` even though they're set-theoretically the same FD. Doesn't affect IC checks (we frozenset internally) but worth fixing in the core class later.

Plus one aggregator:
- `characterize_fds(fds) -> dict` — returns all of the above in one call. Lives in `fd_eval.py`.

### Top-level entry point

`report.py` exposes `characterize(df, fds) -> dict` — calls `characterize_dataset(df)` and `characterize_fds(fds)` and merges them. A notebook can do `pl.DataFrame([characterize(load(t), load_fds(t)) for t in tables])` for side-by-side comparison. The per-input-shape functions (`characterize_dataset`, `characterize_fds`) cover the dataset-only and FDs-only cases.

## Code layout

```
eval/
├── metrics.md            # this doc
├── __init__.py           # re-export the public metric functions
├── dataset_eval.py       # metrics over pl.DataFrame
├── fd_eval.py            # metrics over list[FunctionalDependency]
└── report.py             # characterize(df, fds) -> dict
```

### Conventions
- **Polars**, not pandas, inside `eval/`. `pyproject.toml` needs `polars` added before any code change — pandas stays elsewhere in the repo for now.
- One metric = one top-level function. No classes.
- Input types stay narrow: `pl.Series` / `pl.DataFrame` / `list[FunctionalDependency]`.
- Null handling: drop nulls before counting; document it in the docstring.
- No I/O inside `eval/`. Loading is the caller's job.

## Tests

Goal: a single `uv run pytest` after any change tells us whether the metrics still behave.

### Setup (prerequisite, not done yet)
- Add `pytest` and `polars` to `pyproject.toml` (pytest in `[dependency-groups].dev`, polars in `[project].dependencies`), then `uv sync`.
- Delete `tests/test_dummy.py` once the first real test lands.

### Layout
```
tests/
├── test_dataset_eval.py
└── test_fd_eval.py
```

### Test style
- Inline fixtures: tiny `pl.DataFrame`s and FD lists built in the test body. No CSVs on disk.
- One test per metric covers: (a) a hand-computed expected value on a 3–5 row example, (b) the empty-input edge case, (c) the all-null / null-mixed edge case where relevant.
- For `fd_interaction_cases`, one test per IC using a minimal single-attribute 2-FD fixture that triggers that case in isolation, plus at least one composite-LHS test where multiple cases fire on the same pair.
- No mocking. Pure functions over in-memory data.
