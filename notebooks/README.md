# Notebooks

Exploratory and experiment notebooks that run against the `horizon/` library and the
datasets described in the root `README.md`. Each notebook opens with a markdown cell
stating its purpose, the relevant paper section, its inputs/outputs, and its config knobs;
edit the config cell near the top to point a notebook at a different dataset or size.

Datasets are gitignored and pulled separately (see the root `README.md` "Remote data").

## Data preparation

| Notebook | Purpose |
|---|---|
| `csv_to_parquet.ipynb` | Stream a dataset's `clean.csv` to `clean.parquet`; optionally down-sample a large parquet table. |
| `augment_service_tickets.ipynb` | Triplicate `service_tickets` to a larger row count with fresh ids (scalability inputs). |
| `build_injected.ipynb` | Rebuild `injected/*.csv` dirty tables by replaying BART `*_changes.csv` logs onto `clean.csv`. |
| `union_parking_v2.ipynb` | DuckDB union of the fiscal-year parking CSVs into one merged table. |

## Dataset & FD characterization

| Notebook | Purpose |
|---|---|
| `characterize_dataset.ipynb` | Characterize a dataset + its FDs (paper Table 1 / §3.1); `LAZY` toggle for streaming vs eager, `MIN_REDUNDANCY` FD filter, optional (off by default) filtered-`fds.csv` write-back. |
| `single_attr_fds_hospital_2k.ipynb` | Brute-force check which single-attribute FDs hold exactly (G3=0) and compare to the declared `fds.csv`. |

## Repair effectiveness (§6.1)

| Notebook | Purpose |
|---|---|
| `repair_eval.ipynb` | Run the Horizon pipeline on every injected table of a dataset and score precision/recall/F1. |
| `llm_repair_eval.ipynb` | LLM repair baseline via the `claude` CLI, scored with the same §6.1 metrics for a head-to-head. |
| `opendatauk_eval.ipynb` | Run Horizon on the `opendatauk` tables and compare against the reference Horizon output. |

## Runtime & scalability (§6.4)

| Notebook | Purpose |
|---|---|
| `runtime_service_tickets.ipynb` | Horizon runtime vs increasing row counts (Figure 5c–d). |
| `runtime_vs_fds/*.ipynb` | Runtime vs the number of FDs, one notebook per dataset (`hospital_2k`, `insurance_claims_2k`, `service_tickets`). |
