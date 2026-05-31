import math

import polars as pl


def column_redundancy(series: pl.Series) -> float:
    """log(N / n_unique) / log(N) ∈ [0, 1]. Empty/single-row input returns 0.0.

    Log-scale so low- and high-cardinality columns both spread across the range
    instead of saturating near 0 or 1. Nulls are dropped before counting.
    """
    non_null = series.drop_nulls()
    n = len(non_null)
    if n <= 1:
        return 0.0
    return math.log(n / non_null.n_unique()) / math.log(n)


def avg_redundancy(df: pl.DataFrame) -> float:
    """Mean of column_redundancy across all columns. Empty df returns 0.0."""
    if df.width == 0:
        return 0.0
    return sum(column_redundancy(df[c]) for c in df.columns) / df.width


def avg_frequency(series: pl.Series) -> float:
    """Average appearances of a value: non_null_count / unique_count.

    Denormalised counterpart to column_redundancy. Empty input returns 0.0.
    """
    non_null = series.drop_nulls()
    unique = non_null.n_unique()
    if unique == 0:
        return 0.0
    return len(non_null) / unique


def avg_value_length(df: pl.DataFrame) -> float:
    """Mean string length per column (non-null only), averaged across columns.

    Two-step mean: per-column mean of `len(str(v))`, then mean across columns.
    All-null columns are skipped. Empty df returns 0.0.
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
    """# columns whose avg_frequency ≤ threshold. Paper Table 1: threshold=5."""
    return sum(1 for c in df.columns if avg_frequency(df[c]) <= threshold)


def n_rows(df: pl.DataFrame) -> int:
    return df.height


def n_cols(df: pl.DataFrame) -> int:
    return df.width


def characterize_dataset(df: pl.DataFrame) -> dict:
    """All dataset-side metrics in one dict, keyed by function name."""
    return {
        "n_rows": n_rows(df),
        "n_cols": n_cols(df),
        "avg_redundancy": avg_redundancy(df),
        "avg_value_length": avg_value_length(df),
        "low_redundancy_col_count": low_redundancy_col_count(df),
    }
