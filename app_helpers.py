"""Building blocks for the Horizon demo app (`app.py`).

The app is a pure consumer of the existing pipeline and eval code; all the
awkward wiring lives here so `app.py` stays readable.

Import note: the pipeline modules under `horizon/` use *flat* imports
(`import utils.loaders`, `from fd_pattern_graph import ...`) and so need
`horizon/` itself on `sys.path`, while `eval`/`inject` use *package* imports
(`from horizon.fds.fd import ...`) and need the repo root. We put the repo root
first (so `import horizon` resolves to the package `eval` expects), keep
`horizon/` on the path for the flat names, and load `horizon/horizon.py` by file
path under a private name to dodge the package/module name clash on `horizon`.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import matplotlib

matplotlib.use("Agg")  # headless: igraph renders the FD/SCC PNGs, no GUI backend

REPO = Path(__file__).resolve().parent
HZN = REPO / "horizon"
DATASETS = REPO / "datasets"


def _bootstrap_path() -> None:
    # repo root before horizon/ so `import horizon` -> package (eval needs it)
    for p in (str(HZN), str(REPO)):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, str(HZN))
    sys.path.insert(0, str(REPO))


_pipeline: ModuleType | None = None


def pipeline() -> ModuleType:
    """Load `horizon/horizon.py` by path (its flat imports resolve via HZN)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline
    _bootstrap_path()
    spec = importlib.util.spec_from_file_location(
        "horizon_pipeline", HZN / "horizon.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _pipeline = mod
    return mod


# ----- dataset discovery -------------------------------------------------------


def discover_datasets() -> list[str]:
    """Category-A tables: a folder with both clean.csv and injected/."""
    if not DATASETS.exists():
        return []
    found = [
        d.name
        for d in sorted(DATASETS.iterdir())
        if (d / "clean.csv").exists()
        and ((d / "injected").is_dir() or (d / "dirty.csv").exists)
    ]
    # surface the paper-faithful benchmark first
    found.sort(key=lambda n: (n != "hospital_170k", n))
    return found


def injected_options(dataset: str) -> dict[str, list[int | None]]:
    """Available {errortype: [rates]} from the files actually on disk."""
    inj = DATASETS / dataset / "injected"
    if not inj.exists():
        return {"e1": [None]}
    out: dict[str, list[int]] = {}
    for f in sorted(inj.glob("*_r*.csv")):
        etype, _, rate = f.stem.partition("_r")
        if rate.isdigit():
            out.setdefault(etype, []).append(int(rate))
    for etype in out:
        out[etype].sort()
    return out


# ----- the run ----------------------------------------------------------------


def run_pipeline(
    dataset: str,
    errortype: str,
    rate: int | None,
    on_stage=None,
    on_repair_progress=None,
) -> dict:
    """Run the real Horizon pipeline end-to-end and score it against clean.csv.

    `on_stage(label, done, total)` (optional) is called as each stage finishes,
    so the UI can show clean progress instead of raw logs. `on_repair_progress(frac)`
    (optional) is driven by the pipeline's own "Repaired X/Y tuples" log lines to
    fill a progress bar during the repair loop. Returns everything the UI needs:
    ordered FDs, the pattern graph, per-tuple pattern expressions, the three
    aligned frames, the §6.1 metrics, and the wall-clock `elapsed` seconds.
    """
    import json
    import logging
    import re
    import time

    import polars as pl

    pipe = pipeline()
    from fd_pattern_graph import FDPatternGraph
    from static_fd_analysis import get_ordered_fds

    from eval.effectiveness_eval import evaluate_repair

    ds_dir: Path = DATASETS / dataset
    fds_path: Path = ds_dir / "fds.csv"
    clean_path: Path = ds_dir / "clean.csv"
    dirty_path: Path = ds_dir / "dirty.csv"
    if rate is not None:
        dirty_path = ds_dir / "injected" / f"{errortype}_r{rate:02d}.csv"
    output_dir: Path = REPO / "output"
    output_dir.mkdir(exist_ok=True)

    TOTAL_STAGES = 6
    state = {"done": 0}

    def stage(label: str) -> None:
        state["done"] += 1
        if on_stage:
            on_stage(label, state["done"], TOTAL_STAGES)

    start = time.perf_counter()

    set_of_fds = pipe.load_fds(ds_dir, dirty_path)
    stage(f"Loaded {len(set_of_fds)} functional dependencies")

    ordered_fds = get_ordered_fds(set_of_fds, dataset, output_dir)
    stage(f"Computed FD traversal order ({len(ordered_fds)} groups)")

    graph = FDPatternGraph(str(dirty_path), set_of_fds)
    stage("Built FD pattern graph")

    dirty = pipe.load_data(dirty_path)
    stage(f"Loaded injected table ({len(dirty):,} rows)")

    # tap the pipeline's own "Repaired X/Y tuples" logs to fill a progress bar
    hzn_logger = logging.getLogger("horizon")
    prev_level = hzn_logger.level
    handler = None
    if on_repair_progress:
        pat = re.compile(r"Repaired (\d+)/(\d+) tuples")

        class _ProgressHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                m = pat.search(record.getMessage())
                if m:
                    on_repair_progress(int(m.group(1)) / int(m.group(2)))

        handler = _ProgressHandler()
        hzn_logger.setLevel(logging.INFO)
        hzn_logger.addHandler(handler)
    try:
        cleaned, pattern_expressions = pipe.repair_dirty_data(
            dirty_path, ordered_fds, graph
        )
    finally:
        if handler:
            hzn_logger.removeHandler(handler)
            hzn_logger.setLevel(prev_level)
    stage(f"Repaired {len(dirty):,} tuples")

    clean = pl.read_csv(clean_path, infer_schema_length=0)
    clean = clean.rename({c: c.strip().lower() for c in clean.columns})
    metrics = evaluate_repair(clean, dirty, cleaned)
    stage("Scored repair against ground truth")

    elapsed = time.perf_counter() - start

    # structured graph description the pipeline wrote alongside the PNGs
    graph_json = output_dir / f"{dataset}_graph.json"
    graph_data = (
        json.loads(graph_json.read_text(encoding="utf-8"))
        if graph_json.exists()
        else None
    )

    return {
        "set_of_fds": set_of_fds,
        "ordered_fds": ordered_fds,
        "bound_attributes": set(set_of_fds.bound_attributes),
        "graph": graph,
        "pattern_expressions": pattern_expressions,
        "clean": clean,
        "dirty": dirty,
        "cleaned": cleaned,
        "metrics": metrics,
        "dataset": dataset,
        "errortype": errortype,
        "rate": rate,
        "elapsed": elapsed,
        "graph_data": graph_data,
        "graph_pngs": _graph_png_paths(output_dir, dataset),
    }


def _graph_png_paths(output_dir: Path, dataset: str) -> dict[str, Path]:
    """The schema-level graph images `get_ordered_fds` writes (if present)."""
    names = {
        "FD graph": f"{dataset}_fd_graph.png",
        "Strongly connected components": f"{dataset}_fd_graph_components.png",
        "SCC graph (traversal DAG)": f"{dataset}_scc_fd_graph.png",
    }
    return {k: output_dir / v for k, v in names.items() if (output_dir / v).exists()}


# ----- native graph rendering from the saved structured data ------------------
# No fixed font/arrow sizes: the chart is drawn with use_container_width so the
# whole SVG scales to the app and text/arrows stay proportional.

_NODE_STYLE = (
    '  node [shape=box, style="rounded,filled", fillcolor="#cfe0f3", '
    'color="#5b8fb9", fontname="Helvetica"];'
)
_EDGE_STYLE = '  edge [color="#9aa0a6"];'


def fd_graph_dot(data: dict) -> str:
    """Graphviz DOT for the FD graph from `graph_data`.

    Attributes are nodes, each FD a directed edge; any strongly connected
    component (cycle) of more than one node is wrapped in a dashed cluster.
    """
    lines = [
        "digraph FD {",
        # cap the drawing to a screen-sized box so the whole graph fits without
        # scrolling; graphviz scales the layout (and text) down to fit
        '  rankdir=LR; size="10,5.5"; ratio="compress"; bgcolor="white";',
        _NODE_STYLE,
        _EDGE_STYLE,
    ]
    for node in data["nodes"]:
        safe = node["label"].replace('"', "'")
        lines.append(f'  {node["id"]} [label="{safe}"];')
    for i, members in enumerate(data["sccs"]):
        if len(members) > 1:  # cyclic component -> outline it
            lines.append(f"  subgraph cluster_scc_{i} {{")
            lines.append(
                '    style="dashed"; color="#d1495b"; '
                'label="strongly connected"; fontcolor="#d1495b";'
            )
            lines.append("    " + "; ".join(str(m) for m in members) + ";")
            lines.append("  }")
    for edge in data["edges"]:
        label = (
            f'[label="{edge["order"]}", color=black]'
            if edge["order"] is not None
            else "[style=dashed, color=grey]"
        )
        lines.append(f"  {edge['source']} -> {edge['target']} {label};")
    lines.append("}")
    return "\n".join(lines)


def scc_order_dot(data: dict) -> str:
    """Graphviz DOT for the SCC condensation in traversal order from `graph_data`."""
    so = data["scc_order"]
    lines = [
        "digraph SCC {",
        # cap the drawing so the whole graph fits on screen without scrolling
        '  rankdir=LR; size="10,5.5"; ratio="compress"; bgcolor="white";',
        _NODE_STYLE,
        _EDGE_STYLE,
    ]
    for i, node in enumerate(so["nodes"]):
        safe = node["label"].replace('"', "'")
        cyclic = ' color="#d1495b"' if len(node["members"]) > 1 else ""
        lines.append(f'  {i} [label="{safe}"{cyclic}];')
    for edge in so["edges"]:
        label = (
            f'[label="{edge["order"]}", color=black]'
            if edge["order"] != ""
            else "[style=dashed, color=grey]"
        )
        lines.append(f"  {edge['source']} -> {edge['target']} {label};")
    lines.append("}")
    return "\n".join(lines)


# ----- dataset characterization (paper Table 1) -------------------------------


def characterize(result: dict) -> dict:
    """Table-1-style properties of the clean (ground-truth) table and its FDs.

    Dataset metrics describe the *clean* table (its intrinsic redundancy etc.),
    not the injected one. Attribute overlap is computed over the attributes that
    appear in the FDs (see `eval.fd_eval.attribute_overlap`).
    """
    from eval.dataset_eval import characterize_dataset
    from eval.fd_eval import attribute_overlap

    return {
        **characterize_dataset(result["clean"]),
        "attribute_overlap": attribute_overlap(list(result["set_of_fds"])),
    }


def format_fds(result: dict) -> list[tuple[str, bool]]:
    """(text, is_composite) per FD, e.g. ("facility_id → address", False)."""
    out: list[tuple[str, bool]] = []
    for fd in result["set_of_fds"]:
        lhs = fd.lhs if isinstance(fd.lhs, tuple) else (fd.lhs,)
        out.append((f"{', '.join(lhs)} → {fd.rhs}", len(lhs) > 1))
    return out


def fd_columns(result: dict) -> set[str]:
    """Attributes touched by the FDs.

    Derived from the FD list directly: `SetOfFDs.unique_attributes` is computed
    once at construction and stays empty when FDs are added incrementally (as
    `load_fds` does), so we recompute from the FDs.
    """
    cols: set[str] = set()
    for fd in result["set_of_fds"]:
        cols.update(fd.get_attributes())
    return cols


# ----- diff table -------------------------------------------------------------


def build_diff_rows(result: dict, limit: int = 300):
    """Long-format table of every changed cell: row, column, values, status.

    status: "fixed" (changed and now matches clean) / "wrong" (changed but
    still != clean) / "still dirty?" (unchanged but != clean — repair left it).
    Only FD-involved columns are inspected; those are the only cells repaired.
    """
    import pandas as pd

    clean, dirty, cleaned = result["clean"], result["dirty"], result["cleaned"]
    cols = [
        c
        for c in fd_columns(result)
        if c in clean.columns and c in dirty.columns and c in cleaned.columns
    ]
    rows = []
    for c in cols:
        cl, dy, cd = clean[c], dirty[c], cleaned[c]
        changed = cd.ne_missing(dy)
        for i in range(len(cd)):
            if not changed[i]:
                continue
            correct = cd[i] == cl[i]
            rows.append(
                {
                    "row": i,
                    "column": c,
                    "clean (truth)": cl[i],
                    "dirty": dy[i],
                    "repaired": cd[i],
                    "status": "✅ fixed" if correct else "❌ wrong",
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["row", "column"]).reset_index(drop=True)
    return df.head(limit), len(df)
