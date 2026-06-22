# Horizon Project

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency and environment management.

**1. Install uv** (if you don't have it): https://docs.astral.sh/uv/getting-started/installation/

**2. Create the virtual environment and install dependencies:**

```bash
uv sync
```

This installs all dependencies (defined in [`pyproject.toml`](pyproject.toml).) into `.venv` and pins them via `uv.lock`.

**3.** Make sure to use the Python interpreter from `.venv` — in VS Code, select it via **Select Interpreter** and point it to `.venv/bin/python` (or `.venv/Scripts/python.exe` on Windows).

## Running the code

In the project directory, run:

```bash
uv run horizon/horizon.py --dataset_dir path/to/dataset/ --dirty_data_file dirty.csv --output_dir output --log_level INFO
```

Explanation of arguments:

- _--dataset_dir_ or _-ds_: Directory containing clean (`clean.csv`) and dirty data (`dirty.csv`, can be configured via _-dd_), as well as the functional dependencies (`fds.csv`). Required argument.
- _--dirty_data_file_ or _-dd_: Dirty data file, relative to the given dataset_dir. (default: dirty.csv)
- _output_dir_ or _-o_: Output directory. (default: output)
- _log_level_ or _-l_: Log level. Options: DEBUG, INFO, ERROR. (default: INFO)

Run the tests with `uv run pytest`.

## Layout

- `horizon/` — core model + repair pipeline. `utils/` holds `FunctionalDependency`,
  `get_fds()` and `load_table()`; `FDGraph.py`, `horizon.py`, `static_fd_analysis.py` the repair.
- `eval/` — dataset/FD characterization metrics; `characterize()` / `characterize_lazy()`.
- `inject.py` + `notebooks/build_injected.ipynb` — rebuild BART-injected dirty tables from `bart/`.
- `remote_data/` — fetch/upload dataset tables to Hugging Face.
- `datasets/` — local data (gitignored), one folder per table; pulled from HF.
- `docs/` — code documentation with Doxygen.
- `tests/` — simple test cases confirming the correctness of the implementation.

## Remote data

Large data is kept off GitHub in a Hugging Face repo mirroring `datasets/`
(set via `HORIZON_HF_REPO` / `HF_TOKEN` in `.env` — see `.env.example`):

```bash
make list-datasets                    # available tables + sizes
make download TABLES="hospital_170k"  # -> datasets_temp/ (move into datasets/ by hand)
make upload   TABLES="hospital_170k"  # push local tables up
```
