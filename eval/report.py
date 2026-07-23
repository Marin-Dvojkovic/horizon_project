"""Facades bundling the dataset- and FD-side metrics for one table + FD set.

``characterize`` runs the full metric suite over an in-memory table;
``characterize_lazy`` covers tables too large to materialise by loading only
``attr(fd)`` per FD. Both reuse the primitives in ``eval.dataset_eval`` and
``eval.fd_eval``.
"""

from pathlib import Path

import polars as pl

from eval.dataset_eval import avg_frequency, characterize_dataset
from eval.fd_eval import (
    characterize_fds,
    fd_lhs_redundancy,
    g3_error,
    violation_clusters,
)
from horizon.fds.fd import FunctionalDependency
from horizon.utils.loaders import load_table


def characterize(df: pl.DataFrame, fds: list[FunctionalDependency]) -> dict:
    """Merge the dataset-side and FD-side metrics for a table into one dict.

    Args:
        df: The table to characterise.
        fds: FDs defined over the table.

    Returns:
        Combined dict of ``characterize_dataset(df)`` and
        ``characterize_fds(fds)`` plus ``fd_lhs_redundancy``.
    """
    return {
        **characterize_dataset(df),
        **characterize_fds(fds),
        "fd_lhs_redundancy": fd_lhs_redundancy(df, fds),
    }


def characterize_lazy(source: str | Path, fds: list[FunctionalDependency]) -> dict:
    """Compute FD-side metrics for a table too large to materialise.

    Each FD loads only ``attr(fd)`` from disk (projection pushed into
    ``scan_csv`` by ``load_table``), then reuses the in-memory primitives.
    Progress is printed per FD.

    Args:
        source: Path to the table on disk.
        fds: FDs to characterise; columns are loaded per FD.

    Returns:
        Dict from ``characterize_fds`` plus ``fd_lhs_redundancy``,
        ``redundancy_per_column``, ``g3_error`` and ``violation_clusters``.
    """
    out = {**characterize_fds(fds)}
    lhs_red: dict[tuple, float] = {}
    red_per_col: dict[str, float] = {}
    g3: dict[FunctionalDependency, float] = {}
    clusters: dict[FunctionalDependency, pl.DataFrame] = {}
    for i, fd in enumerate(fds, 1):
        print(f"[{i}/{len(fds)}] {fd}", flush=True)
        df_fd = load_table(Path(source), columns=fd.get_attributes())
        mb = df_fd.estimated_size() / 1024 / 1024
        print(f"    loaded {df_fd.height:,} rows, {mb:.1f} MB", flush=True)
        if fd.lhs_attributes not in lhs_red:
            lhs_red.update(fd_lhs_redundancy(df_fd, [fd]))
        for c in df_fd.columns:
            if c not in red_per_col:
                red_per_col[c] = avg_frequency(df_fd[c])
        g3[fd] = g3_error(df_fd, fd)
        clusters[fd] = violation_clusters(df_fd, fd)
        print(
            f"    G3={g3[fd]:.4g}, {clusters[fd].height} violation rows",
            flush=True,
        )
    out["fd_lhs_redundancy"] = lhs_red
    out["redundancy_per_column"] = red_per_col
    out["g3_error"] = g3
    out["violation_clusters"] = clusters
    return out
