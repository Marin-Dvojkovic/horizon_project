"""LLM data-cleaning benchmark: repair a dirty table with Claude, score like Horizon.

Companion to `benchmark_horizon.py`. Instead of the Horizon pipeline, we ask an
LLM (Claude, via the Claude Code CLI in headless mode) to repair FD violations,
then score its repair with the same effectiveness metric (`eval.effectiveness_eval`,
paper §6.1) so LLM quality is directly comparable to Horizon's.

Flow per (table, run): serialize the dirty table + FDs into one prompt -> the
model returns a JSON *edit list* (only the cells it changes) -> apply those edits
into a copy of the dirty table to build the `cleaned` table -> caller scores
`cleaned` vs `clean.csv`. Asking for an edit list (not the whole corrected CSV)
keeps output small and guarantees `cleaned` has the same rows in the same order
as `dirty`, which `evaluate_repair` requires (it aligns rows positionally).

The CLI uses the logged-in Pro/Max subscription automatically (no API key), and
each `claude -p` call is a fresh, independent session. Tools are disabled, so it
is purely the model answering with text.

Orchestration (which tables/rates, how many runs, output paths) lives in the
caller — see `notebooks/llm_repair_eval.ipynb`.
"""

import json
import shutil
import subprocess
from pathlib import Path

import polars as pl

from horizon.fds.set_of_fds import SetOfFDs
from horizon.utils.loaders import load_table

_ROW = "__row__"  # 0-based row id column shown to the model and used to apply edits


def build_prompt(dirty: pl.DataFrame, fds: SetOfFDs) -> str:
    """Render one repair prompt: FD rules + the dirty table + the output contract.

    Only the FD-relevant columns (``fds.unique_attributes``) are shown — non-FD
    columns can't be FD-repaired anyway (Horizon leaves them too), and dropping
    them shrinks the prompt a lot (e.g. insurance 41 -> 12 columns).
    ``apply_edits`` still starts from the full dirty table, so scoring is over
    all columns as in ``repair_eval.ipynb``. The table is emitted as CSV with a
    leading ``__row__`` column (0-based, from ``with_row_index``) so the model
    references cells by an unambiguous integer; ``apply_edits`` numbers rows the
    same way, so row ids line up.

    Args:
        dirty: The dirty table to repair.
        fds: FD rules shown to the model and used to pick shown columns.

    Returns:
        The full prompt string (rules, CSV table and output contract).
    """
    fd_lines = "\n".join(
        f"{', '.join(fd.lhs_attributes)} -> {fd.rhs}" for fd in fds
    )
    attrs = [c for c in dirty.columns if c in fds.unique_attributes]  # keep table order
    csv_text = dirty.select(attrs).with_row_index(_ROW).write_csv()
    return (
        "You are repairing a table so that it satisfies a set of functional "
        "dependencies (FDs).\n\n"
        'An FD "A -> B" means every row with the same value in column A must '
        "have the same value in column B. The table below violates some FDs. "
        "Fix each violation by changing cell values to the value best supported "
        "by the data (the most frequent / consistent value for that group). "
        "Most cells are already correct: change as few cells as possible, and "
        "only to values that already occur in that column.\n\n"
        f"Functional dependencies:\n{fd_lines}\n\n"
        f"The table is CSV. The first column `{_ROW}` is a 0-based row id used "
        f"only to reference cells; never change `{_ROW}`.\n\n"
        f"{csv_text}\n"
        "Return ONLY a JSON array of the cells you change, and nothing else. "
        "Each element is a 3-item array [row, col, value]: `row` is the "
        "`__row__` integer, `col` is the column name, `value` is the new value. "
        'Example: [[12,"state","TX"],[87,"zip_code","75201"]]. Include only the '
        "cells you change. No prose, no markdown, no code fences."
    )


def run_claude(prompt: str, model: str = "sonnet", timeout: int = 600) -> dict:
    """Call ``claude -p`` headless with tools off; return result text + metadata.

    Uses subscription auth (no API key). The prompt goes via stdin because a
    full table is far larger than a command-line argument allows.

    Args:
        prompt: The full repair prompt to send on stdin.
        model: Claude model alias to invoke (e.g. ``"sonnet"``).
        timeout: Per-call timeout in seconds.

    Returns:
        On success, a dict with ``result``, ``session_id``, ``usage`` and
        ``cost``. On any failure (non-zero exit, timeout, unparseable output),
        a dict with an ``error`` key.
    """
    claude = shutil.which("claude") or "claude"
    cmd = [
        claude, "-p",
        "--model", model,
        "--output-format", "json",
        "--allowedTools", "",  # empty allow-list: no tools, pure text answer
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True,
            text=True, encoding="utf-8", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    if proc.returncode != 0:
        return {"error": f"cli exit {proc.returncode}: {(proc.stderr or '')[:500]}"}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"bad cli json: {e}", "raw": proc.stdout[:500]}
    return {
        "result": payload.get("result", ""),
        "session_id": payload.get("session_id"),
        "usage": payload.get("usage"),
        "cost": payload.get("total_cost_usd"),
    }


def parse_edits(result_text: str) -> tuple[list[dict], int]:
    """Extract the JSON edit list from the model's reply.

    Tolerates code fences / surrounding prose by slicing to the outermost
    brackets. Accepts both compact ``[row, col, value]`` triples and
    ``{"row", "col", "value"}`` objects.

    Args:
        result_text: The model's raw reply text.

    Returns:
        A tuple of (structurally valid edits, count of malformed elements).

    Raises:
        ValueError: If no JSON array can be parsed from the reply at all.
    """
    text = result_text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array found in model output")
    try:
        raw = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"edit list is not valid JSON: {e}") from e
    if not isinstance(raw, list):
        raise ValueError("model output is not a JSON array")

    edits: list[dict] = []
    n_malformed = 0
    for el in raw:
        row = col = None
        value = _MISSING
        if isinstance(el, (list, tuple)) and len(el) == 3:  # compact [row, col, value]
            row, col, value = _as_row(el[0]), el[1], el[2]
        elif isinstance(el, dict):  # object {"row":..,"col":..,"value":..}
            row, col, value = _as_row(el.get("row")), el.get("col"), el.get("value", _MISSING)
        if row is not None and isinstance(col, str) and value is not _MISSING:
            edits.append({"row": row, "col": col, "value": value})
        else:
            n_malformed += 1
    return edits, n_malformed


_MISSING = object()  # sentinel: distinguishes an absent value from a null/"" value


def _as_row(v) -> int | None:
    """Coerce a row id to int; accept ints and digit-strings (bools rejected).

    Args:
        v: Candidate row id from the parsed edit element.

    Returns:
        The row id as an int, or None if it is not a valid integer row id.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v.strip())
    return None


def apply_edits(dirty: pl.DataFrame, edits: list[dict]) -> tuple[pl.DataFrame, int]:
    """Apply the model's edits into a copy of ``dirty``.

    Values are coerced to str so the frame stays all-Utf8 (the
    ``evaluate_repair`` precondition). Rows are keyed by a 0-based ``__row__``
    index matching ``build_prompt`` and updated with a keyed join per column
    (mirroring ``inject.apply_changes``), so duplicate keys overwrite rather
    than fan out rows.

    Args:
        dirty: The dirty table to apply edits onto (not mutated).
        edits: Parsed edits, each ``{"row", "col", "value"}``.

    Returns:
        A tuple of (cleaned table, count of edits skipped). Edits with an
        out-of-range ``row`` or unknown ``col`` are skipped and counted, never
        fatal.
    """
    height = dirty.height
    cols = set(dirty.columns)
    by_col: dict[str, dict[int, str]] = {}
    n_skipped = 0
    for e in edits:
        row, col = e["row"], e["col"]
        if col not in cols or not (0 <= row < height):
            n_skipped += 1
            continue
        by_col.setdefault(col, {})[row] = str(e["value"])  # last write wins per cell

    cleaned = dirty.with_row_index(_ROW)
    for col, row_val in by_col.items():
        other = pl.DataFrame(
            {
                _ROW: pl.Series(list(row_val.keys()), dtype=pl.UInt32),
                col: pl.Series(list(row_val.values()), dtype=pl.Utf8),
            }
        )
        cleaned = cleaned.update(other, on=_ROW, how="left", include_nulls=True)
    return cleaned.drop(_ROW), n_skipped


def repair_one(
    dirty_path: Path,
    fds: SetOfFDs,
    model: str,
    out_dir: Path,
    run_idx: int,
    timeout: int = 600,
) -> dict:
    """Repair one dirty table once with the LLM and write the cleaned CSV.

    The caller loads the cleaned CSV and scores it with ``evaluate_repair``.

    Args:
        dirty_path: Path to the dirty table to repair.
        fds: FD rules to include in the prompt.
        model: Claude model alias to invoke.
        out_dir: Directory the cleaned CSV is written to.
        run_idx: Run index, used in the output filename.
        timeout: Per-call CLI timeout in seconds.

    Returns:
        Run metadata: ``status`` in ``{"ok", "cli_error", "parse_error"}``, edit
        counts, timing, token usage/cost, and ``cleaned_path`` on success.
    """
    import time

    t0 = time.perf_counter()
    dirty = load_table(dirty_path)
    prompt = build_prompt(dirty, fds)
    res = run_claude(prompt, model=model, timeout=timeout)
    secs = time.perf_counter() - t0

    if "error" in res:
        return {"status": "cli_error", "error": res["error"], "secs": secs}
    try:
        edits, n_malformed = parse_edits(res["result"])
    except ValueError as e:
        return {
            "status": "parse_error", "error": str(e), "secs": secs,
            "usage": res.get("usage"), "cost": res.get("cost"),
        }

    cleaned, n_skipped = apply_edits(dirty, edits)
    out_dir.mkdir(parents=True, exist_ok=True)
    cleaned_path = out_dir / f"{dirty_path.stem}__run{run_idx}.csv"
    cleaned.write_csv(cleaned_path)
    return {
        "status": "ok",
        "n_edits": len(edits),
        "n_invalid": n_malformed + n_skipped,
        "secs": secs,
        "usage": res.get("usage"),
        "cost": res.get("cost"),
        "cleaned_path": str(cleaned_path),
    }
