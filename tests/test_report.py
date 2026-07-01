import polars as pl

from eval.report import characterize
from horizon.fds.fd import FunctionalDependency as FD


def test_characterize_merges_both_sides():
    df = pl.DataFrame({"a": ["x", "x"], "b": ["y", "z"]})
    fds = [FD("a", "b")]
    out = characterize(df, fds)
    assert set(out.keys()) == {
        "n_rows",
        "n_cols",
        "avg_redundancy",
        "redundancy_per_column",
        "avg_value_length",
        "low_redundancy_col_count",
        "attribute_overlap",
        "fd_interaction_cases",
        "fd_lhs_redundancy",
    }
    assert out["n_rows"] == 2
    assert out["n_cols"] == 2
    assert out["fd_interaction_cases"] == set()


def test_characterize_empty_inputs():
    out = characterize(pl.DataFrame(), [])
    assert out["n_rows"] == 0
    assert out["attribute_overlap"] == 0.0
    assert out["fd_interaction_cases"] == set()
