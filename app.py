"""Horizon demo — an interactive front-end over the FD repair pipeline.

Run with:  uv run streamlit run app.py

Pick a Category-A dataset and a BART-injected error file, run the real Horizon
pipeline live (§3-5), and inspect repair quality (§6.1) and the FD/SCC graphs
(§4.2/§5.1). No numbers are faked: the live log is the pipeline's own logging,
and the metrics come straight from `eval.effectiveness_eval`.
"""

import streamlit as st

import app_helpers as h

PAPER_URL = "https://www.vldb.org/pvldb/vol14/p2546-rezig.pdf"

ABOUT_MD = f"""
### What is this?

**Horizon** is a linear-time data-cleaning algorithm that repairs violations of
**functional dependencies** (FDs) — rules like `zip_code → state` that say rows
agreeing on the left must agree on the right. Instead of making the fewest
possible edits, Horizon picks repairs that preserve the *most frequent patterns*
in the data, which empirically yields better repairs.

This app is a from-scratch Python reimplementation, with an interface to run it
live and inspect what it does.

### The paper

[*Horizon: Scalable Dependency-driven Data Cleaning*]({PAPER_URL}) — El Kindi
Rezig, Mourad Ouzzani, Walid G. Aref, Ahmed K. Elmagarmid, Ahmed R. Mahmood,
Michael Stonebraker. **PVLDB 14(11): 2546–2554, 2021.**

### How the app works

1. **Pick a dataset** in the sidebar. Each has a clean ground-truth table and
   versions with synthetic errors injected (via BART) at several rates.
2. **Choose an error type and rate**, then press **▶ Run Horizon**.
3. The pipeline runs end-to-end and streams its real progress: it orders the FDs
   (§5.1), builds the **FD pattern graph** weighting each pattern by support
   (§3.2–3.3), then chases the graph to repair every tuple (§5.2).
4. **Inspect the result**: precision / recall / F1 against the clean table, the
   exact cells that changed, and the FD & SCC graphs.

← **Configure a run in the sidebar to begin.**
"""

st.set_page_config(page_title="Horizon — FD Data Cleaning", layout="wide")
st.title("Horizon — Dependency-driven Data Cleaning")
st.caption("A from-scratch reimplementation of Horizon (Rezig et al., VLDB 2021).")

ERROR_TYPE_NAMES = {
    "e1": "Type 1 — active-domain errors",
    "e2": "Type 2 — incl. outliers",
}


def error_type_label(et: str) -> str:
    return ERROR_TYPE_NAMES.get(et, et)


datasets = h.discover_datasets()
if not datasets:
    st.error(
        "No Category-A datasets found under `datasets/` (need clean.csv + injected/ or clean.csv + dirty.csv)."
    )
    st.stop()

# ----- sidebar controls -------------------------------------------------------

with st.sidebar:
    st.header("Run configuration")
    dataset = st.selectbox("Dataset", datasets, index=0)
    options = h.injected_options(dataset)
    errortype = st.radio(
        "Error type",
        list(options.keys()),
        format_func=error_type_label,
        help=(
            "Type 1: FD-detectable errors using other values from the column "
            "(harder to repair). Type 2: may include outliers, not always "
            "FD-detectable (§6.1)."
        ),
    )
    rates = options[errortype]
    rate = (
        st.select_slider("Error rate (% of cells)", options=rates, value=rates[0])
        if len(rates) > 1
        else rates[0]
    )
    if rate is None:
        st.caption(
            "Only the default error rate is available (no information about rate)."
        )
    elif len(rates) == 1:
        st.caption(f"Only a {rate}% file is available for this error type.")
    run = st.button("▶ Run Horizon", type="primary", use_container_width=True)

key = (dataset, errortype, rate)

# ----- run --------------------------------------------------------------------

# the six pipeline stages, in order; index 4 is the row-repair loop
STEP_LABELS = [
    "Load functional dependencies",
    "Compute FD traversal order",
    "Build FD pattern graph",
    "Load injected table",
    "Repair rows (chase the graph)",
    "Score against ground truth",
]
REPAIR_IDX = 4

if run:
    st.session_state.pop(key, None)  # force a fresh run
    with st.status("Running Horizon pipeline…", expanded=True) as status:
        steps_ph = st.empty()
        bar_ph = st.empty()
        state = {"done": 0, "labels": {}}

        def render_steps() -> None:
            rows = []
            for i, generic in enumerate(STEP_LABELS):
                if i < state["done"]:
                    rows.append(f"✅ &nbsp; {state['labels'].get(i, generic)}")
                elif i == state["done"]:
                    rows.append(f"🔄 &nbsp; **{generic}…**")
                else:
                    rows.append(f"⬜ &nbsp; {generic}")
            steps_ph.markdown("  \n".join(rows))

        def on_stage(label: str, done: int, total: int) -> None:
            state["labels"][done - 1] = label
            state["done"] = done
            status.update(label=f"Step {done}/{total}: {label}", expanded=True)
            render_steps()
            if done - 1 == REPAIR_IDX:  # repair finished -> top off the bar
                bar_ph.progress(1.0, text="Rows cleaned ✓")

        def on_repair_progress(frac: float) -> None:
            pct = int(min(frac, 1.0) * 100)
            bar_ph.progress(min(frac, 1.0), text=f"🧹 Cleaning rows… {pct}%")

        render_steps()  # initial paint: first step spinning, rest pending
        try:
            result = h.run_pipeline(
                dataset,
                errortype,
                rate,
                on_stage=on_stage,
                on_repair_progress=on_repair_progress,
            )
            st.session_state[key] = result
            bar_ph.empty()
            render_steps()  # final paint: all ticked
            status.update(
                label=f"Done in ~{result['elapsed']:.1f}s ✓",
                state="complete",
                expanded=True,
            )
        except Exception as e:  # surface the failure, don't swallow it
            status.update(label="Pipeline failed", state="error")
            st.exception(e)
            st.stop()

result = st.session_state.get(key)

# ----- landing page (no run yet) ----------------------------------------------

if result is None:
    st.markdown(ABOUT_MD)
    st.stop()

# ----- clean dataset properties (paper Table 1) -------------------------------

st.subheader(f"Clean dataset — `{dataset}`")

props = h.characterize(result)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Rows", f"{props['n_rows']:,}")
c2.metric("Columns", props["n_cols"])
c3.metric("Avg. redundancy", f"{props['avg_redundancy']:.2f}")
c4.metric("Avg. value length", f"{props['avg_value_length']:.1f}")
c5.metric("Attribute overlap", f"{props['attribute_overlap']:.2f}")
st.caption(
    "Properties of the **clean** ground-truth table. *Avg. redundancy* and "
    "*avg. value length* are averaged across all columns; *attribute overlap* "
    "measures how much the attributes are shared across the FDs."
)

cols = list(result["clean"].columns)
with st.expander(f"Columns ({len(cols)})"):
    st.markdown(" ".join(f"`{c}`" for c in cols))

fd_left, fd_right = st.columns([2, 1])
with fd_left:
    st.markdown(f"**Functional dependencies** ({len(result['set_of_fds'])})")
    fd_md = []
    for text, composite in h.format_fds(result):
        note = " &nbsp;_(composite LHS — not yet repaired)_" if composite else ""
        fd_md.append(f"- `{text}`{note}")
    st.markdown("\n".join(fd_md))
with fd_right:
    st.markdown("**Bound attributes** (§4.2)")
    bound = sorted(result["bound_attributes"])
    st.markdown("\n".join(f"- `{b}`" for b in bound) if bound else "_none_")
    st.caption("Seed the chase: not determined by any FD, so taken as-is.")

# ----- repair quality dashboard (§6.1) ----------------------------------------

m = result["metrics"]
st.subheader("Repair quality")
etype_n = errortype[1:] if errortype.startswith("e") else errortype
st.markdown(f"**Error type:** {etype_n}  \n**Error rate:** {rate}%")
st.caption(f"Approximate execution time: **~{result['elapsed']:.1f}s**")
q1, q2, q3 = st.columns(3)
q1.metric("Precision", f"{m['precision']:.3f}")
q2.metric("Recall", f"{m['recall']:.3f}")
q3.metric("F1", f"{m['f1']:.3f}")
n1, n2, n3 = st.columns(3)
n1.metric("Dirty cells", f"{m['n_dirty']:,}")
n2.metric("Repaired cells", f"{m['n_repaired']:,}")
n3.metric("Correctly repaired", f"{m['n_correct']:,}")

# ----- graphs (built natively from the saved graph data) ----------------------

st.divider()
st.subheader("Graphs")

gd = result.get("graph_data")
if not gd:
    st.info("No graph data yet — press **▶ Run Horizon**.")
else:
    st.markdown("**FD graph** — attributes as nodes, each FD a directed edge")
    # not container-width: the DOT caps the size so the whole graph fits on screen
    st.graphviz_chart(h.fd_graph_dot(gd), use_container_width=False)
    st.caption(
        "A dashed box marks a strongly connected component (a cycle among the FDs, §4.2)."
    )

    st.markdown("**Traversal order** — strongly connected components, collapsed")
    # not container-width: the DOT caps the size so the whole graph fits on screen
    st.graphviz_chart(h.scc_order_dot(gd), use_container_width=False)
    st.caption(
        "Each component is one node, labelled with its position `[i]` in the order "
        "Horizon processes the FDs (§5.1)."
    )

# ----- repaired cells ---------------------------------------------------------

st.divider()
st.subheader("Repaired cells")
diff_df, total = h.build_diff_rows(result)
st.caption(f"{total:,} cells changed by the repair (showing up to {len(diff_df)}).")
if diff_df.empty:
    st.info("No cells were changed.")
else:
    st.dataframe(diff_df, use_container_width=True, hide_index=True)
