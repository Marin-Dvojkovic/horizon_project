# Horizon repair pipeline — presentation notes

Two diagrams live next to this file:

- **`horizon_workflow_simple.svg`** — one-slide overview (5 stages, left → right). *Caption: "The Horizon repair pipeline: dirty table + FDs in, cleaned table out — one linear-time, streaming pass."*
- **`horizon_workflow_detailed.svg`** — backup/appendix slide showing what happens inside each stage. *Caption: "Inside each stage: the key steps, the paper section, and the function that implements it."*

Both are self-contained SVGs — insert directly into a slide (Insert → Pictures); in PowerPoint you can right-click → *Group → Ungroup* to recolor or edit individual boxes.

---

## Big picture (opening slide / speaker note)

Horizon (Rezig et al., VLDB 2021) is a data cleaner driven by **functional dependencies** (FDs) — rules like `zip → state` that say rows agreeing on the left must agree on the right. Given a dirty table and its FDs, it produces a repaired table that satisfies the FDs. Its two ideas: (1) instead of making the *fewest* changes, it picks repairs that keep the **most frequent value patterns** in the data, which gives better accuracy; and (2) it does this in **linear time with a single streaming pass**, so it scales to millions of rows. Our re-implementation is the Python library in `horizon/`; one call — `run_horizon()` — runs the whole pipeline.

---

## Stage 1 — Inputs
**What:** Load the FDs and stream in the dirty table. FDs come from `fds.csv` or `fds.txt`; the table is read in memory-bounded batches (~8 MB), and every cell is kept as a string so values like `"5"` are never silently rewritten to `"5.0"`.
**Code:** `load_fds()`, `iter_table_batches()` in `horizon/utils/loaders.py`.

## Stage 2 — Order the FDs (static analysis) · paper §4–5.1
**What:** Decide *which order* to apply the FDs in. We build a small graph of the *attributes*, condense it into its strongly-connected components (Tarjan) so cycles become single nodes, then topologically sort it (Kahn's algorithm). Attributes with no incoming edge are **bound** (their values are trusted as given); everything else is **free** (to be determined). Each FD gets an execution order, and FDs inside a cycle are flagged.
**Why it matters:** The traversal order is what lets a single forward pass resolve every FD correctly, including chains where one FD's output feeds the next.
**Code:** `get_ordered_fds()` in `horizon/static_fd_analysis.py`.

## Stage 3 — Build the FD pattern graph · paper §3.2–3.3
**What:** One streaming pass over the data counts how often each `LHS → RHS` value pairing occurs (its **support**). From these we build a graph where nodes are `(column, value)` pairs and edges carry a **quality** score. Quality rewards not just a pattern's own support but the support of the patterns it leads to: `quality = (support + Σ downstream support) / (reachable + 1)`. One-off values on source columns are dropped (nothing to choose), and cyclic FDs are added as back-edges.
**Why it matters:** This graph is where a repair is *chosen from* — high-quality edges are the frequent, well-supported patterns we want repairs to land on.
**Code:** `FDPatternGraph` in `horizon/fd_pattern_graph.py`.

## Stage 4 — Repair the tuples · paper §5.2
**What:** Stream the table again; for each row, walk the FDs in the order from Stage 2 and pick a clean value for each right-hand side using a four-step cascade:
1. **Cache** — if we already repaired this left-hand value, reuse that result (keeps the output consistent).
2. **Already set** — if the same attribute was fixed earlier in this row, reuse that value.
3. **Pass-through** — a source value we deliberately dropped from the graph has no alternative, so keep it.
4. **Best edge** — otherwise ask the pattern graph for the highest-quality edge (`choose_best_next_edge`).
Each repaired batch is written straight to disk, so memory stays flat regardless of table size.
**Code:** `repair_dirty_data()` and `repair_tuple()` in `horizon/horizon.py`.

## Stage 5 — Output & evaluation · paper §6.1
**What:** The run writes `{dataset}_cleaned_data.csv`, a `{dataset}_statistics.json` with per-stage timings, and optionally `{dataset}_final_pattern_expressions.txt` (the lineage: which patterns produced each repaired row). Separately, when ground truth is available, we score the repair with precision, recall, and F1 by comparing clean / dirty / cleaned cell-by-cell.
**Code:** output in `horizon/horizon.py`; `evaluate_repair()` in `eval/effectiveness_eval.py`.

---

## One-line-per-stage cheat sheet (for a compact slide)

| # | Stage | Does | Function | Paper |
|---|-------|------|----------|-------|
| 1 | Inputs | load FDs, stream dirty table as strings | `load_fds`, `iter_table_batches` | — |
| 2 | Order FDs | attribute graph → SCC (Tarjan) → topo sort → bound/free + order | `get_ordered_fds` | §4–5.1 |
| 3 | FD pattern graph | count support → `(col,val)` graph, quality-weighted edges | `FDPatternGraph` | §3.2–3.3 |
| 4 | Repair tuples | per row/FD, pick highest-quality edge (with cache/consistency) | `repair_dirty_data`, `repair_tuple` | §5.2 |
| 5 | Output & eval | cleaned CSV + stats + lineage; precision/recall/F1 | `run_horizon`, `evaluate_repair` | §6.1 |

**Talking point:** the whole thing is one entry point, `run_horizon()` — order once, build the graph in one pass, repair in one streaming pass. That linear, streaming design is exactly why Horizon scales where minimality-based cleaners stall.
