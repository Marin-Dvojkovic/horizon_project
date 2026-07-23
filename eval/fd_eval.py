"""FD-side metrics over a set of functional dependencies.

Characterises the FDs themselves and their interaction with the data:
attribute overlap and the four §4.1 pattern interaction cases (FD-only), plus
LHS redundancy, G3 error, and violation clusters (data-dependent). Terminology
(LHS/RHS, ``attr(fd)``) follows §3.1; interaction cases follow §4.1.
"""

import math
from itertools import combinations

import polars as pl

from horizon.fds.fd import FunctionalDependency


def fd_lhs_redundancy(df: pl.DataFrame, fds: list[FunctionalDependency]) -> dict[tuple, float]:
    """Generalise ``column_redundancy`` to each FD's LHS as a composite key.

    For a singleton LHS this matches ``column_redundancy``; for a composite LHS
    (§3.1) the tuple of LHS values is the unit counted. Rows with a null in any
    LHS column are dropped. FDs sharing the same LHS collapse to one entry.

    Args:
        df: Table providing the LHS columns for each FD.
        fds: FDs whose LHS redundancy is measured.

    Returns:
        Mapping of each distinct LHS attribute tuple to its redundancy in
        [0, 1].
    """
    out: dict[tuple, float] = {}
    for fd in fds:
        if fd.lhs_attributes in out:
            continue
        sub = df.select(list(fd.lhs_attributes)).drop_nulls()
        n = sub.height
        out[fd.lhs_attributes] = 0.0 if n <= 1 else math.log(n / sub.n_unique()) / math.log(n)
    return out


def attribute_overlap(fds: list[FunctionalDependency]) -> float:
    """Fraction of attribute occurrences across the FDs that are repeats.

    Paper Table 1 "Attribute overlap": pools every LHS and RHS attribute
    occurrence (case-insensitive) across all FDs, then returns
    ``(total - distinct) / total`` — higher when FDs share attributes.

    Args:
        fds: FDs whose attribute occurrences are pooled.

    Returns:
        Overlap in [0, 1]; 0.0 for an empty FD list.
    """
    if not fds:
        return 0.0

    all_attributes = []
    for fd in fds:
        all_attributes.extend([str(attr).lower() for attr in fd.lhs_attributes])
        all_attributes.append(str(fd.rhs).lower())

    total_count = len(all_attributes)
    if total_count == 0:
        return 0.0

    unique_count = len(set(all_attributes))

    overlap = (total_count - unique_count) / total_count

    return float(overlap)


# TODO: This is not correct, can be checked manually tho
def fd_interaction_cases(fds: list[FunctionalDependency]) -> set[str]:
    """Report which of the four §4.1 pattern interaction cases fire on any pair.

    Scans every unordered pair of FDs. LHS is treated as a set of attributes
    (composite LHS supported per §3.1). Cases are not mutually exclusive: IC4
    (cycle) strictly implies IC3 (chain), and a composite LHS can trigger
    several cases on a single pair.

    Note:
        KNOWN LIMITATION — the case-detection logic is unverified and believed
        incorrect (see the ``TODO`` above); results can be checked by hand but
        should not be trusted as-is. Left unchanged intentionally.

    Args:
        fds: FDs whose pairwise interactions are classified.

    Returns:
        Subset of ``{"IC1", "IC2", "IC3", "IC4"}`` present across the FD pairs.
    """
    cases: set[str] = set()
    for fd_i, fd_j in combinations(fds, 2):
        x_i, y_i = frozenset(fd_i.lhs_attributes), fd_i.rhs
        x_j, y_j = frozenset(fd_j.lhs_attributes), fd_j.rhs
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
    """Standard G3 error of ``fd`` on ``df``: ``1 - (sum mode_count(rhs | lhs)) / N``.

    The minimum fraction of rows to delete so ``fd`` holds. Nulls in LHS/RHS
    are dropped first.

    Args:
        df: Table pre-projected to ``attr(fd)`` (the function does not
            re-project).
        fd: The functional dependency to measure.

    Returns:
        G3 error in [0, 1]; 0.0 for empty input.
    """
    sub = df.drop_nulls()
    n = sub.height
    if n == 0:
        return 0.0
    # sentinel names so the count columns can't collide with an attribute named "c"
    mode_counts = (
        sub.group_by(list(fd.lhs_attributes) + [fd.rhs])
        .agg(pl.len().alias("__g3_count"))
        .group_by(list(fd.lhs_attributes))
        .agg(pl.col("__g3_count").max().alias("__g3_max"))
    )
    return 1.0 - mode_counts["__g3_max"].sum() / n


def violation_clusters(df: pl.DataFrame, fd: FunctionalDependency) -> pl.DataFrame:
    """Return unique (LHS, RHS, count) rows inside any LHS group that violates ``fd``.

    A group violates ``fd`` if it has >=2 distinct RHS values; all of that
    group's (LHS, RHS) pairs are returned (not just the minority RHS). Nulls in
    LHS/RHS are dropped first.

    Args:
        df: Table pre-projected to ``attr(fd)`` (the function does not
            re-project).
        fd: The functional dependency to inspect.

    Returns:
        DataFrame of (LHS..., RHS, count) rows for violating groups, sorted by
        LHS then count descending so the dominant RHS in each group leads.
    """
    sub = df.drop_nulls()
    counts = sub.group_by(list(fd.lhs_attributes) + [fd.rhs]).agg(pl.len().alias("count"))
    violating_keys = (
        counts.group_by(list(fd.lhs_attributes))
        .agg(pl.col(fd.rhs).n_unique().alias("_n_rhs"))
        .filter(pl.col("_n_rhs") > 1)
        .select(list(fd.lhs_attributes))
    )
    out = counts.join(violating_keys, on=list(fd.lhs_attributes), how="inner")
    return out.sort(
        list(fd.lhs_attributes) + ["count"],
        descending=[False] * len(fd.lhs_attributes) + [True],
    )


def characterize_fds(fds: list[FunctionalDependency]) -> dict:
    """Compute the data-independent FD-side metrics in one dict.

    Args:
        fds: FDs to characterise.

    Returns:
        Dict with ``attribute_overlap`` and ``fd_interaction_cases`` (keyed by
        function name).
    """
    return {
        "attribute_overlap": attribute_overlap(fds),
        "fd_interaction_cases": fd_interaction_cases(fds),
    }
