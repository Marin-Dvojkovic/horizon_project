import polars as pl
import pytest

from eval.fd_eval import (
    attribute_overlap,
    characterize_fds,
    fd_interaction_cases,
    g3_error,
    violation_clusters,
)
from horizon.fds.fd import FunctionalDependency as FD


def test_attribute_overlap_empty():
    assert attribute_overlap([]) == 0.0


def test_attribute_overlap_single_fd_no_overlap():
    # A → B: 2 occurrences, 2 unique → 0.0
    assert attribute_overlap([FD("A", "B")]) == 0.0


def test_attribute_overlap_shared_lhs():
    # A → B, A → C: 4 occurrences {A,B,A,C}, 3 unique → 0.25
    fds = [FD("A", "B"), FD("A", "C")]
    assert attribute_overlap(fds) == pytest.approx(0.25)


def test_attribute_overlap_case_insensitive():
    # A → B, a → c: normalised to lowercase → 4 occurrences, 3 unique → 0.25
    fds = [FD("A", "B"), FD("a", "c")]
    assert attribute_overlap(fds) == pytest.approx(0.25)


def test_fd_interaction_cases_ic1_isolated():
    # A → B, A → C: shared LHS, different RHS
    assert fd_interaction_cases([FD("A", "B"), FD("A", "C")]) == {"IC1"}


def test_fd_interaction_cases_ic2_isolated():
    # A → C, B → C: shared RHS
    assert fd_interaction_cases([FD("A", "C"), FD("B", "C")]) == {"IC2"}


def test_fd_interaction_cases_ic3_isolated():
    # A → B, B → C: chain
    assert fd_interaction_cases([FD("A", "B"), FD("B", "C")]) == {"IC3"}


def test_fd_interaction_cases_ic4_implies_ic3():
    # A → B, B → A: cycle. Set-based IC4 condition (Y∈X' AND Y'∈X) strictly implies
    # the IC3 condition (Y∈X' OR Y'∈X), so cyclic pairs fire both.
    assert fd_interaction_cases([FD("A", "B"), FD("B", "A")]) == {"IC3", "IC4"}


def test_fd_interaction_cases_composite_lhs_multi():
    # {A} → B, {A, B} → C: composite LHS pair triggers IC1 (X∩X'={A}) and IC3 (B∈X').
    fds = [FD(("A",), "B"), FD(("A", "B"), "C")]
    assert fd_interaction_cases(fds) == {"IC1", "IC3"}


def test_fd_interaction_cases_empty():
    assert fd_interaction_cases([]) == set()


def test_fd_interaction_cases_single_fd():
    # No pairs → no cases
    assert fd_interaction_cases([FD("A", "B")]) == set()


def test_fd_interaction_cases_disjoint_fds():
    # A → B, C → D: no shared attributes
    assert fd_interaction_cases([FD("A", "B"), FD("C", "D")]) == set()


def test_characterize_fds_keys_and_values():
    fds = [FD("A", "B"), FD("A", "C")]
    out = characterize_fds(fds)
    assert out == {
        "attribute_overlap": pytest.approx(0.25),
        "fd_interaction_cases": {"IC1"},
    }


def test_characterize_fds_empty():
    assert characterize_fds([]) == {
        "attribute_overlap": 0.0,
        "fd_interaction_cases": set(),
    }


def test_g3_error_clean_fd():
    # A → B holds perfectly: every LHS group has one RHS → G3 = 0
    df = pl.DataFrame({"a": ["x", "x", "y", "y"], "b": [1, 1, 2, 2]})
    assert g3_error(df, FD("a", "b")) == 0.0


def test_g3_error_one_violation():
    # group a={x}: rhs counts {1: 2, 2: 1}, max=2 → keep 2 of 3 → delete 1/4 total
    df = pl.DataFrame({"a": ["x", "x", "x", "y"], "b": [1, 1, 2, 9]})
    assert g3_error(df, FD("a", "b")) == pytest.approx(0.25)


def test_g3_error_fully_violated():
    # group a={x}: rhs counts {1:1, 2:1, 3:1}, max=1 → keep 1 of 3 → G3 = 2/3
    df = pl.DataFrame({"a": ["x", "x", "x"], "b": [1, 2, 3]})
    assert g3_error(df, FD("a", "b")) == pytest.approx(2 / 3)


def test_g3_error_composite_lhs():
    # {a, b} → c. Group (x, 1): rhs {10:2, 20:1}; group (x, 2): rhs {30:1}
    # max sum = 2 + 1 = 3, N = 4 → G3 = 1/4
    df = pl.DataFrame(
        {
            "a": ["x", "x", "x", "x"],
            "b": [1, 1, 1, 2],
            "c": [10, 10, 20, 30],
        }
    )
    assert g3_error(df, FD(("a", "b"), "c")) == pytest.approx(0.25)


def test_g3_error_empty():
    df = pl.DataFrame({"a": [], "b": []})
    assert g3_error(df, FD("a", "b")) == 0.0


def test_g3_error_nulls_dropped():
    # Null row dropped first; remaining 3 rows are clean → G3 = 0
    df = pl.DataFrame({"a": ["x", "x", "y", None], "b": [1, 1, 2, 9]})
    assert g3_error(df, FD("a", "b")) == 0.0


def test_violation_clusters_one_group():
    # User's example: a→b, one (a,b) row + three (a,c) rows → both pairs returned
    df = pl.DataFrame({"a": ["x", "x", "x", "x"], "b": ["p", "q", "q", "q"]})
    out = violation_clusters(df, FD("a", "b"))
    assert out.to_dicts() == [
        {"a": "x", "b": "q", "count": 3},
        {"a": "x", "b": "p", "count": 1},
    ]


def test_violation_clusters_clean_fd_empty():
    df = pl.DataFrame({"a": ["x", "x", "y"], "b": [1, 1, 2]})
    out = violation_clusters(df, FD("a", "b"))
    assert out.height == 0
    assert out.columns == ["a", "b", "count"]


def test_violation_clusters_mixed_groups():
    # Group y is clean (only rhs=9) and must be excluded; group x has 2 rhs values.
    df = pl.DataFrame({"a": ["x", "x", "x", "y", "y"], "b": [1, 1, 2, 9, 9]})
    out = violation_clusters(df, FD("a", "b"))
    assert out.to_dicts() == [
        {"a": "x", "b": 1, "count": 2},
        {"a": "x", "b": 2, "count": 1},
    ]


def test_violation_clusters_composite_lhs():
    # {a, b} → c. Group (x, 1) has c in {10, 20}; group (x, 2) has only c=30.
    df = pl.DataFrame(
        {
            "a": ["x", "x", "x", "x"],
            "b": [1, 1, 1, 2],
            "c": [10, 10, 20, 30],
        }
    )
    out = violation_clusters(df, FD(("a", "b"), "c"))
    assert out.to_dicts() == [
        {"a": "x", "b": 1, "c": 10, "count": 2},
        {"a": "x", "b": 1, "c": 20, "count": 1},
    ]


def test_violation_clusters_empty():
    df = pl.DataFrame({"a": [], "b": []})
    out = violation_clusters(df, FD("a", "b"))
    assert out.height == 0
    assert out.columns == ["a", "b", "count"]
