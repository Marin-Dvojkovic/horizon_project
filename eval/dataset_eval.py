"""Dataset-side metrics characterising a table (paper Table 1).

Implements the data properties reported in the paper's Table 1 — average
redundancy (frequency of each attribute value), the count of low-redundancy
attributes, and average value length — plus a log-scaled redundancy variant.
`characterize_dataset` bundles them all into one dict for a table.
"""

import math

import polars as pl


def column_redundancy(series: pl.Series) -> float:
    """Log-scaled redundancy of a column in [0, 1].

    Computes ``log(N / n_unique) / log(N)``. Log-scale so low- and
    high-cardinality columns both spread across the range instead of
    saturating near 0 or 1. Nulls are dropped before counting.

    Args:
        series: The column to measure.

    Returns:
        Redundancy in [0, 1]; 0.0 for empty or single-row input.
    """
    non_null = series.drop_nulls()
    n = len(non_null)
    if n <= 1:
        return 0.0
    return math.log(n / non_null.n_unique()) / math.log(n)


def avg_redundancy(df: pl.DataFrame) -> float:
    """Mean of ``column_redundancy`` across all columns.

    Args:
        df: The table to measure.

    Returns:
        Mean column redundancy; 0.0 for an empty (no-column) df.
    """
    if df.width == 0:
        return 0.0
    return sum(column_redundancy(df[c]) for c in df.columns) / df.width


def avg_frequency(series: pl.Series) -> float:
    """Average appearances of a value: ``non_null_count / unique_count``.

    Denormalised counterpart to ``column_redundancy``; this is the paper's
    Table 1 "average redundancy" at the column level.

    Args:
        series: The column to measure.

    Returns:
        Mean appearances per distinct value; 0.0 for empty input.
    """
    non_null = series.drop_nulls()
    unique = non_null.n_unique()
    if unique == 0:
        return 0.0
    return len(non_null) / unique


def redundancy_per_column(df: pl.DataFrame) -> dict[str, float]:
    """Paper's avg. redundancy (``avg_frequency``) for every column, keyed by name.

    Per-column view of the paper's "average frequency of each attribute value"
    (Table 1). Each value is ``non_null_count / unique_count`` for that column.

    Args:
        df: The table to measure.

    Returns:
        Mapping of column name to its ``avg_frequency``.
    """
    return {c: avg_frequency(df[c]) for c in df.columns}


def avg_value_length(df: pl.DataFrame) -> float:
    """Mean string length per column (non-null only), averaged across columns.

    Two-step mean: per-column mean of ``len(str(v))``, then mean across
    columns. This is the paper's Table 1 "average value length".

    Args:
        df: The table to measure.

    Returns:
        Mean value length; 0.0 if every column is empty/all-null.
    """
    col_means: list[float] = []
    for c in df.columns:
        non_null = df[c].drop_nulls()
        if len(non_null) == 0:
            continue
        lengths = non_null.cast(pl.Utf8).str.len_chars()
        col_means.append(float(lengths.mean()))
    if not col_means:
        return 0.0
    return sum(col_means) / len(col_means)


def low_redundancy_col_count(df: pl.DataFrame, threshold: float = 5) -> int:
    """Count of columns whose ``avg_frequency`` is at or below ``threshold``.

    This is the paper's Table 1 "Atts w. AvgRed. <= 5" (default threshold 5).

    Args:
        df: The table to measure.
        threshold: Redundancy cutoff; columns at or below it are counted.

    Returns:
        Number of low-redundancy columns.
    """
    return sum(1 for c in df.columns if avg_frequency(df[c]) <= threshold)


def n_rows(df: pl.DataFrame) -> int:
    """Number of rows in ``df``.

    Args:
        df: The table to measure.

    Returns:
        Row count.
    """
    return df.height


def n_cols(df: pl.DataFrame) -> int:
    """Number of columns in ``df``.

    Args:
        df: The table to measure.

    Returns:
        Column count.
    """
    return df.width


def characterize_dataset(df: pl.DataFrame) -> dict:
    """Compute all dataset-side metrics in one dict, keyed by function name.

    Args:
        df: The table to characterise.

    Returns:
        Dict with ``n_rows``, ``n_cols``, ``avg_redundancy``,
        ``redundancy_per_column``, ``avg_value_length`` and
        ``low_redundancy_col_count``.
    """
    return {
        "n_rows": n_rows(df),
        "n_cols": n_cols(df),
        "avg_redundancy": avg_redundancy(df),
        "redundancy_per_column": redundancy_per_column(df),
        "avg_value_length": avg_value_length(df),
        "low_redundancy_col_count": low_redundancy_col_count(df),
    }
