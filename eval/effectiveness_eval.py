import polars as pl


def precision(n_correct: int, n_repaired: int) -> float:
    """Correctly repaired cells / total repaired (changed) cells (§6.1).

    No cells changed -> 0.0.
    """
    return 0.0 if n_repaired == 0 else n_correct / n_repaired


def recall(n_correct: int, n_dirty: int) -> float:
    """Correctly repaired cells / total dirty (error) cells (§6.1).

    No dirty cells -> 0.0.
    """
    return 0.0 if n_dirty == 0 else n_correct / n_dirty


def f1(precision: float, recall: float) -> float:
    """Harmonic mean 2PR / (P + R) (§6.1). P = R = 0 -> 0.0."""
    denom = precision + recall
    return 0.0 if denom == 0 else 2 * precision * recall / denom


def repair_counts(
    clean: pl.DataFrame, dirty: pl.DataFrame, cleaned: pl.DataFrame
) -> dict[str, int]:
    """Cell-level error / repair / correct counts across three aligned tables.

    Compares ground-truth `clean`, the injected `dirty`, and the repair
    `cleaned` output cell by cell over their shared columns (in clean's
    order). Tables are aligned positionally — row i is the same tuple in
    each — so they must have equal height; a mismatch raises ValueError.

    A cell is:
    - *dirty* (an error) if `dirty != clean`,
    - *repaired* (changed) if `cleaned != dirty`,
    - *correctly repaired* if it was changed and now matches truth
      (`cleaned != dirty` and `cleaned == clean`).

    null == null counts as equal (`eq_missing`/`ne_missing`), so a cell that
    is null in two frames is not counted as a difference. PRECONDITION: the
    three frames are read with a common dtype (e.g. all Utf8) so values are
    compared like-for-like — see the eval notebook.
    """
    if not (clean.height == dirty.height == cleaned.height):
        raise ValueError(
            f"row counts differ: clean={clean.height}, "
            f"dirty={dirty.height}, cleaned={cleaned.height}"
        )
    columns = [c for c in clean.columns if c in dirty.columns and c in cleaned.columns]
    n_dirty = n_repaired = n_correct = 0
    for c in columns:
        error = dirty[c].ne_missing(clean[c])
        changed = cleaned[c].ne_missing(dirty[c])
        correct = changed & cleaned[c].eq_missing(clean[c])
        n_dirty += int(error.sum())
        n_repaired += int(changed.sum())
        n_correct += int(correct.sum())
    return {"n_dirty": n_dirty, "n_repaired": n_repaired, "n_correct": n_correct}


def evaluate_repair(
    clean: pl.DataFrame, dirty: pl.DataFrame, cleaned: pl.DataFrame
) -> dict:
    """Repair effectiveness (§6.1) over three aligned tables, in one call.

    Single entry point for the notebook: counts dirty/repaired/correct cells
    once via `repair_counts`, then derives precision, recall and F1. Returns
    the counts alongside the three metrics.
    """
    counts = repair_counts(clean, dirty, cleaned)
    p = precision(counts["n_correct"], counts["n_repaired"])
    r = recall(counts["n_correct"], counts["n_dirty"])
    return {**counts, "precision": p, "recall": r, "f1": f1(p, r)}
