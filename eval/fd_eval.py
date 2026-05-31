import math
from itertools import combinations

import polars as pl

from horizon.utils.fd import FunctionalDependency


def fd_lhs_redundancy(
    df: pl.DataFrame, fds: list[FunctionalDependency]
) -> dict[tuple, float]:
    """`column_redundancy` generalised to each FD's LHS as a composite key.

    For singleton LHS this matches `column_redundancy`; for composite LHS (§3.1)
    the tuple of LHS values is the unit counted. Rows with a null in any LHS
    column are dropped. FDs sharing the same LHS collapse to one entry.
    """
    out: dict[tuple, float] = {}
    for fd in fds:
        if fd.lhs in out:
            continue
        sub = df.select(list(fd.lhs)).drop_nulls()
        n = sub.height
        out[fd.lhs] = 0.0 if n <= 1 else math.log(n / sub.n_unique()) / math.log(n)
    return out


def attribute_overlap(fds: list[FunctionalDependency]) -> float:
    if not fds:
        return 0.0

    all_attributes = []
    for fd in fds:
        all_attributes.extend([str(attr).lower() for attr in fd.lhs])
        all_attributes.append(str(fd.rhs).lower())

    total_count = len(all_attributes)
    if total_count == 0:
        return 0.0

    unique_count = len(set(all_attributes))

    overlap = (total_count - unique_count) / total_count

    return float(overlap)


# TODO: This is not correct, can be checked manually tho
def fd_interaction_cases(fds: list[FunctionalDependency]) -> set[str]:
    """Which of the four §4.1 FD pattern interaction cases fire on any unordered pair.

    LHS is treated as a set of attributes (composite LHS supported per §3.1). Cases
    are not mutually exclusive: IC4 (cycle) strictly implies IC3 (chain), and composite
    LHS can trigger several cases on a single pair.
    """
    cases: set[str] = set()
    for fd_i, fd_j in combinations(fds, 2):
        x_i, y_i = frozenset(fd_i.lhs), fd_i.rhs
        x_j, y_j = frozenset(fd_j.lhs), fd_j.rhs
        if x_i & x_j and y_i != y_j:
            cases.add("IC1")
        if y_i == y_j:
            cases.add("IC2")
        y_i_in_x_j = y_i in x_j
        y_j_in_x_i = y_j in x_i
        if y_i_in_x_j or y_j_in_x_i:
            cases.add("IC3")
        if y_i_in_x_j and y_j_in_x_i:
            cases.add("IC4")
    return cases


def g3_error(df: pl.DataFrame, fd: FunctionalDependency) -> float:
    """Standard G3: 1 − (Σ mode_count(rhs | lhs)) / N.

    Min fraction of rows to delete so `fd` holds. Nulls in LHS/RHS dropped
    first; empty input returns 0.0. PRECONDITION: `df` is pre-projected to
    `attr(fd)` — function does not re-project.
    """
    sub = df.drop_nulls()
    n = sub.height
    if n == 0:
        return 0.0
    # sentinel names so the count columns can't collide with an attribute named "c"
    mode_counts = (
        sub.group_by(list(fd.lhs) + [fd.rhs])
        .agg(pl.len().alias("__g3_count"))
        .group_by(list(fd.lhs))
        .agg(pl.col("__g3_count").max().alias("__g3_max"))
    )
    return 1.0 - mode_counts["__g3_max"].sum() / n


def violation_clusters(df: pl.DataFrame, fd: FunctionalDependency) -> pl.DataFrame:
    """Unique (LHS, RHS, count) rows inside any LHS group that violates `fd`.

    A group violates `fd` if it has ≥2 distinct RHS values; all of that group's
    (LHS, RHS) pairs are returned (not just the minority RHS). Sorted by LHS,
    then count desc so the dominant RHS in each group leads.

    Nulls in LHS/RHS dropped first. PRECONDITION: `df` is pre-projected to
    `attr(fd)` — function does not re-project.
    """
    sub = df.drop_nulls()
    counts = sub.group_by(list(fd.lhs) + [fd.rhs]).agg(pl.len().alias("count"))
    violating_keys = (
        counts.group_by(list(fd.lhs))
        .agg(pl.col(fd.rhs).n_unique().alias("_n_rhs"))
        .filter(pl.col("_n_rhs") > 1)
        .select(list(fd.lhs))
    )
    out = counts.join(violating_keys, on=list(fd.lhs), how="inner")
    return out.sort(
        list(fd.lhs) + ["count"],
        descending=[False] * len(fd.lhs) + [True],
    )


def characterize_fds(fds: list[FunctionalDependency]) -> dict:
    """All FD-side metrics in one dict, keyed by function name."""
    return {
        "attribute_overlap": attribute_overlap(fds),
        "fd_interaction_cases": fd_interaction_cases(fds),
    }
