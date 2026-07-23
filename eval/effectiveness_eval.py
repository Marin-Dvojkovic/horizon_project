"""Repair effectiveness metrics: precision, recall, F1 (paper §6.1).

Scores a repair by comparing three positionally-aligned tables — ground-truth
``clean``, the injected ``dirty``, and the repair output ``cleaned`` — cell by
cell, then reducing the counts to the §6.1 precision/recall/F1 triple. Provides
eager (DataFrame) and lazy/streaming (LazyFrame) variants of the same logic.
"""

import polars as pl


def precision(n_correct: int, n_repaired: int) -> float:
    """Correctly repaired cells over total repaired (changed) cells (§6.1).

    Args:
        n_correct: Cells changed that now match ground truth.
        n_repaired: Cells changed at all.

    Returns:
        Precision in [0, 1]; 0.0 when no cells were changed.
    """
    return 0.0 if n_repaired == 0 else n_correct / n_repaired


def recall(n_correct: int, n_dirty: int) -> float:
    """Correctly repaired cells over total dirty (error) cells (§6.1).

    Args:
        n_correct: Cells changed that now match ground truth.
        n_dirty: Cells that were errors in the dirty table.

    Returns:
        Recall in [0, 1]; 0.0 when there were no dirty cells.
    """
    return 0.0 if n_dirty == 0 else n_correct / n_dirty


def f1(precision: float, recall: float) -> float:
    """Harmonic mean ``2PR / (P + R)`` of precision and recall (§6.1).

    Args:
        precision: Precision value.
        recall: Recall value.

    Returns:
        F1 in [0, 1]; 0.0 when both precision and recall are 0.
    """
    denom = precision + recall
    return 0.0 if denom == 0 else 2 * precision * recall / denom


def repair_counts(
    clean: pl.DataFrame, dirty: pl.DataFrame, cleaned: pl.DataFrame
) -> dict[str, int]:
    """Count cell-level errors / repairs / correct repairs across three tables.

    Compares the three tables cell by cell over their shared columns (in
    ``clean``'s order). A cell is *dirty* (an error) if ``dirty != clean``,
    *repaired* (changed) if ``cleaned != dirty``, and *correctly repaired* if it
    was changed and now matches truth (``cleaned != dirty`` and
    ``cleaned == clean``). ``null == null`` counts as equal
    (``eq_missing``/``ne_missing``), so a cell null in two frames is not a
    difference.

    Args:
        clean: Ground-truth table.
        dirty: Injected (dirty) table.
        cleaned: Repair output. Aligned positionally with the others — row i is
            the same tuple in each — and read with a common dtype (e.g. all
            Utf8) so values compare like-for-like (see the eval notebook).

    Returns:
        Dict with ``n_dirty``, ``n_repaired`` and ``n_correct``.

    Raises:
        ValueError: If the three tables do not all have equal height.
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
    """Score repair effectiveness (§6.1) over three aligned tables in one call.

    Single entry point for the notebook: counts dirty/repaired/correct cells
    once via ``repair_counts``, then derives precision, recall and F1.

    Args:
        clean: Ground-truth table.
        dirty: Injected (dirty) table.
        cleaned: Repair output, aligned positionally with the others.

    Returns:
        Dict with the ``repair_counts`` keys plus ``precision``, ``recall`` and
        ``f1``.

    Raises:
        ValueError: If the three tables do not all have equal height.
    """
    counts = repair_counts(clean, dirty, cleaned)
    p = precision(counts["n_correct"], counts["n_repaired"])
    r = recall(counts["n_correct"], counts["n_dirty"])
    return {**counts, "precision": p, "recall": r, "f1": f1(p, r)}


def lazy_repair_counts(
    clean: pl.LazyFrame, dirty: pl.LazyFrame, cleaned: pl.LazyFrame
) -> dict[str, int]:
    """Compute the same counts as ``repair_counts`` but over LazyFrames.

    Streams the three frames in aligned batches so tables too large to
    materialise can be scored; results match ``repair_counts`` exactly.

    Args:
        clean: Ground-truth table.
        dirty: Injected (dirty) table.
        cleaned: Repair output, aligned positionally with the others.

    Returns:
        Dict with ``n_dirty``, ``n_repaired`` and ``n_correct``.

    Raises:
        ValueError: If the three frames do not all have equal length.
    """
    # Check lazy frame lengths
    if not (
        clean.select(pl.len()).collect().item()
        == dirty.select(pl.len()).collect().item()
        == cleaned.select(pl.len()).collect().item()
    ):
        raise ValueError(
            f"row counts differ: clean={clean.select(pl.len()).collect().item()}, "
            f"dirty={dirty.select(pl.len()).collect().item()}, cleaned={cleaned.select(pl.len()).collect().item()}"
        )

    columns: list[str] = [
        c
        for c in clean.collect_schema().names()
        if c in dirty.collect_schema().names() and c in cleaned.collect_schema().names()
    ]
    n_dirty = n_repaired = n_correct = 0

    # Iterate in batches over clean, dirty, and cleaned lazy frames
    batch_size: int = 1000
    for clean_df, dirty_df, cleaned_df in zip(
        clean.collect_batches(
            maintain_order=True, engine="streaming", chunk_size=batch_size
        ),
        dirty.collect_batches(
            maintain_order=True, engine="streaming", chunk_size=batch_size
        ),
        cleaned.collect_batches(
            maintain_order=True, engine="streaming", chunk_size=batch_size
        ),
    ):
        for c in columns:
            error = dirty_df[c].ne_missing(clean_df[c])
            changed = cleaned_df[c].ne_missing(dirty_df[c])
            correct = changed & cleaned_df[c].eq_missing(clean_df[c])
            n_dirty += int(error.sum())
            n_repaired += int(changed.sum())
            n_correct += int(correct.sum())

    return {"n_dirty": n_dirty, "n_repaired": n_repaired, "n_correct": n_correct}


def lazy_evaluate_repair(
    clean: pl.LazyFrame, dirty: pl.LazyFrame, cleaned: pl.LazyFrame
) -> dict:
    """Score effectiveness like ``evaluate_repair`` but over LazyFrames.

    Args:
        clean: Ground-truth table.
        dirty: Injected (dirty) table.
        cleaned: Repair output, aligned positionally with the others.

    Returns:
        Dict with the ``lazy_repair_counts`` keys plus ``precision``,
        ``recall`` and ``f1``.

    Raises:
        ValueError: If the three frames do not all have equal length.
    """
    counts = lazy_repair_counts(clean, dirty, cleaned)
    p = precision(counts["n_correct"], counts["n_repaired"])
    r = recall(counts["n_correct"], counts["n_dirty"])
    return {**counts, "precision": p, "recall": r, "f1": f1(p, r)}
