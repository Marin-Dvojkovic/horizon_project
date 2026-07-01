import math

import polars as pl
import pytest

from eval.dataset_eval import (
    avg_frequency,
    avg_redundancy,
    avg_value_length,
    characterize_dataset,
    column_redundancy,
    low_redundancy_col_count,
    n_cols,
    n_rows,
)


def test_column_redundancy_handcomputed():
    # 5 vals, 3 unique → log(5/3) / log(5)
    s = pl.Series(["a", "a", "b", "c", "c"])
    assert column_redundancy(s) == pytest.approx(math.log(5 / 3) / math.log(5))


def test_column_redundancy_all_unique():
    s = pl.Series(["a", "b", "c"])
    assert column_redundancy(s) == 0.0


def test_column_redundancy_empty():
    s = pl.Series([], dtype=pl.Utf8)
    assert column_redundancy(s) == 0.0


def test_column_redundancy_null_mixed():
    # after drop: 3 non-null, 2 unique → log(3/2) / log(3)
    s = pl.Series(["a", None, "a", "b"])
    assert column_redundancy(s) == pytest.approx(math.log(3 / 2) / math.log(3))


def test_avg_redundancy_handcomputed():
    # col1: 4 vals, 2 unique → log(2)/log(4) = 0.5
    # col2: 4 vals, 4 unique → 0.0
    # mean = 0.25
    df = pl.DataFrame({"col1": ["a", "a", "b", "b"], "col2": ["w", "x", "y", "z"]})
    assert avg_redundancy(df) == 0.25


def test_avg_redundancy_empty_df():
    df = pl.DataFrame()
    assert avg_redundancy(df) == 0.0


def test_avg_redundancy_single_column():
    df = pl.DataFrame({"only": ["a", "a", "b"]})
    assert avg_redundancy(df) == pytest.approx(math.log(3 / 2) / math.log(3))


def test_avg_value_length_handcomputed():
    # col1 lens: 3, 2 → mean 2.5; col2 lens: 4 → mean 4; mean-of-means = 3.25
    df = pl.DataFrame({"col1": ["abc", "de"], "col2": ["wxyz", None]})
    assert avg_value_length(df) == pytest.approx(3.25)


def test_avg_value_length_non_string_dtype():
    # ints stringified: "1","22","333" → lens 1,2,3 → mean 2.0
    df = pl.DataFrame({"nums": [1, 22, 333]})
    assert avg_value_length(df) == pytest.approx(2.0)


def test_avg_value_length_empty_df():
    df = pl.DataFrame()
    assert avg_value_length(df) == 0.0


def test_avg_value_length_all_null_column_skipped():
    # only col has all-null entries → no col contributes → 0.0
    df = pl.DataFrame({"a": [None, None]}, schema={"a": pl.Utf8})
    assert avg_value_length(df) == 0.0


def test_avg_frequency_handcomputed():
    # 5 non-null, 2 unique → 2.5
    s = pl.Series(["a", "a", "b", "b", "b"])
    assert avg_frequency(s) == 2.5


def test_avg_frequency_all_unique():
    s = pl.Series(["a", "b", "c"])
    assert avg_frequency(s) == 1.0


def test_avg_frequency_empty():
    s = pl.Series([], dtype=pl.Utf8)
    assert avg_frequency(s) == 0.0


def test_avg_frequency_null_mixed():
    # after drop: 2 non-null, 1 unique → 2.0
    s = pl.Series(["a", "a", None])
    assert avg_frequency(s) == 2.0


def test_low_redundancy_col_count_handcomputed():
    # N=6 in every col. freq: low=1.0 (6 unique), mid=3.0 (2 unique), high=6.0 (1 unique)
    # At default thr=5, low and mid qualify → 2
    df = pl.DataFrame(
        {
            "low": ["a", "b", "c", "d", "e", "f"],
            "mid": ["x", "x", "x", "y", "y", "y"],
            "high": ["z"] * 6,
        }
    )
    assert low_redundancy_col_count(df) == 2


def test_low_redundancy_col_count_custom_threshold():
    # N=6 in both. freq: a=2.0 (3 unique), b=3.0 (2 unique). thr=2 picks only "a".
    df = pl.DataFrame(
        {
            "a": ["x", "x", "y", "y", "z", "z"],
            "b": ["p", "p", "p", "q", "q", "q"],
        }
    )
    assert low_redundancy_col_count(df, threshold=2) == 1


def test_low_redundancy_col_count_empty():
    assert low_redundancy_col_count(pl.DataFrame()) == 0


def test_n_rows_and_n_cols():
    df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    assert n_rows(df) == 3
    assert n_cols(df) == 2


def test_n_rows_and_n_cols_empty():
    df = pl.DataFrame()
    assert n_rows(df) == 0
    assert n_cols(df) == 0


def test_characterize_dataset_keys_and_values():
    df = pl.DataFrame(
        {
            "a": ["x", "x", "y", "y"],  # freq 2.0, redundancy 0.5, str len 1
            "b": ["pp", "qq", "rr", "ss"],  # freq 1.0, redundancy 0.0, str len 2
        }
    )
    out = characterize_dataset(df)
    assert out == {
        "n_rows": 4,
        "n_cols": 2,
        "avg_redundancy": pytest.approx(0.25),
        "redundancy_per_column": {"a": 2.0, "b": 1.0},
        "avg_value_length": pytest.approx(1.5),
        "low_redundancy_col_count": 2,
    }


def test_characterize_dataset_empty():
    out = characterize_dataset(pl.DataFrame())
    assert out == {
        "n_rows": 0,
        "n_cols": 0,
        "avg_redundancy": 0.0,
        "redundancy_per_column": {},
        "avg_value_length": 0.0,
        "low_redundancy_col_count": 0,
    }
