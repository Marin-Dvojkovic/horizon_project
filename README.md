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

```bash
uv run path/to/code.py <args>
```

Explanation of arguments:

-
