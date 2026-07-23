"""Reconstruct a BART-injected dirty table from `clean.csv` + a changes log.

BART records every error it injects as a headerless 3-column CSV row:

    {rowid}.{attribute} , dirty_value , clean_value

`rowid` is 1-based over data rows. The third column is the original clean
value; the second is the injected (dirty) value. So a dirty table is just
`clean.csv` with cell (rowid, attribute) overwritten by the dirty value.

A changes file can log several rows for the same cell (the clean value is the
same on each, the candidate dirty value differs) because one cell is implicated
by several FD constraints. A single dirty table holds one value per cell, so
the caller dedupes (last wins) before applying — `parse_changes` returns the
raw rows so the caller can measure how many were dropped.

These are building blocks; orchestration (which tables/rates, output paths, the
dedup report) lives in the caller — see `notebooks/build_injected.ipynb`.
"""

from pathlib import Path

import polars as pl


def read_str(source: str | Path, *, has_header: bool = True) -> pl.DataFrame:
    """Read a CSV with every cell as a string.

    Reading everything as text preserves leading zeros and avoids float
    reformatting.

    Args:
        source: Path to the CSV file.
        has_header: Whether the first row is a header.

    Returns:
        The CSV as an all-Utf8 DataFrame.
    """
    return pl.read_csv(source, has_header=has_header, infer_schema_length=0)


def parse_changes(changes_path: str | Path) -> pl.DataFrame:
    """Parse a headerless BART changes file into structured columns.

    Rows are returned as-is, including duplicate cells; dedupe with
    ``.unique(["__row", "attr"], keep="last")`` before applying.

    Args:
        changes_path: Path to the headerless BART changes CSV.

    Returns:
        DataFrame with columns ``__row`` (1-based row id), ``attr``, ``dirty``
        (injected value) and ``recorded`` (original clean value).
    """
    raw = read_str(changes_path, has_header=False)
    return raw.select(
        pl.col("column_1").str.extract(r"^(\d+)\.", 1).cast(pl.Int64).alias("__row"),
        pl.col("column_1").str.extract(r"^\d+\.(.+)$", 1).alias("attr"),
        pl.col("column_2").alias("dirty"),
        pl.col("column_3").alias("recorded"),
    )


def apply_changes(clean: pl.DataFrame, changes: pl.DataFrame) -> pl.DataFrame:
    """Return ``clean`` with each (row, attr) cell set to its dirty value.

    Each cell is updated by a keyed ``update`` (never a fan-out join), so
    duplicate keys could only ever overwrite, never multiply rows. Before
    overwriting, each recorded clean value is checked against ``clean.csv`` at
    that cell as a ground-truth guard.

    Args:
        clean: The clean table to inject errors into.
        changes: Parsed changes deduped to one row per cell (see
            ``parse_changes``).

    Returns:
        The dirty table (``clean`` with injected values applied).

    Raises:
        ValueError: If a change names an unknown attribute, or a recorded clean
            value disagrees with ``clean`` at that cell.
    """
    df = clean.with_row_index("__row", offset=1)
    for (attr,), grp in changes.group_by("attr"):
        if attr not in clean.columns:
            raise ValueError(f"unknown attribute {attr!r}")

        # guard: recorded clean value must match clean.csv at that cell (§ ground truth)
        check = grp.join(df.select("__row", attr), on="__row", how="left")
        bad = check.filter(pl.col("recorded") != pl.col(attr))
        if bad.height:
            raise ValueError(
                f"{bad.height} recorded values disagree with clean on {attr!r}, "
                f"e.g. {bad.head(3).to_dicts()}"
            )

        other = grp.select("__row", pl.col("dirty").alias(attr))
        df = df.update(other, on="__row", how="left", include_nulls=True)

    return df.drop("__row")
