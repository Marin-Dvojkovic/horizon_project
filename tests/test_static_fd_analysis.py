from pathlib import Path

import pytest

from horizon.fds.fd import FunctionalDependency
from horizon.fds.set_of_fds import SetOfFDs
from horizon.static_fd_analysis import get_ordered_fds

TEST_DATA_DIR: Path = Path(__file__).parent.resolve() / "test_data"
OUTPUT_DIR: Path = Path(__file__).parent.resolve() / Path("output")


set_of_fds: dict[str, SetOfFDs] = {
    "paper_example": SetOfFDs(
        [
            FunctionalDependency("provider_area_id", "service_area"),
            FunctionalDependency("provider_address", "provider_area_id"),
            FunctionalDependency("provider_id", "provider_address"),
            FunctionalDependency("service_area", "provider_area_id"),
        ]
    ),
    "interaction_case_1": SetOfFDs(
        [
            FunctionalDependency("A", "B"),
            FunctionalDependency("A", "C"),
            FunctionalDependency("A", "D"),
        ]
    ),
    "interaction_case_2": SetOfFDs(
        [
            FunctionalDependency("A", "C"),
            FunctionalDependency("B", "C"),
            FunctionalDependency("D", "C"),
        ]
    ),
    "interaction_case_3": SetOfFDs(
        [
            FunctionalDependency("A", "B"),
            FunctionalDependency("B", "C"),
            FunctionalDependency("C", "D"),
        ]
    ),
    "interaction_case_4": SetOfFDs(
        [
            FunctionalDependency("A", "B"),
            FunctionalDependency("B", "A"),
        ]
    ),
    "interaction_case_4a": SetOfFDs(
        [
            FunctionalDependency("A", "B"),
            FunctionalDependency("B", "C"),
            FunctionalDependency("C", "B"),
        ]
    ),
    "interaction_case_4b": SetOfFDs(
        [
            FunctionalDependency("A", "B"),
            FunctionalDependency("B", "A"),
            FunctionalDependency("B", "C"),
        ]
    ),
    "hyperedges": SetOfFDs(
        [
            FunctionalDependency("A", "C"),
            FunctionalDependency("B", "D"),
            FunctionalDependency(("A", "B"), "E"),
        ]
    ),
}

correct_ordered_fds: dict[str, list[FunctionalDependency]] = {
    "paper_example": [
        FunctionalDependency("provider_id", "provider_address"),
        FunctionalDependency("provider_address", "provider_area_id"),
        FunctionalDependency("provider_area_id", "service_area"),
        FunctionalDependency("service_area", "provider_area_id"),
    ],
    "interaction_case_1": [
        FunctionalDependency("A", "D"),
        FunctionalDependency("A", "C"),
        FunctionalDependency("A", "B"),
    ],
    "interaction_case_2": [
        FunctionalDependency("D", "C"),
        FunctionalDependency("B", "C"),
        FunctionalDependency("A", "C"),
    ],
    "interaction_case_3": [
        FunctionalDependency("A", "B"),
        FunctionalDependency("B", "C"),
        FunctionalDependency("C", "D"),
    ],
    "interaction_case_4": [
        FunctionalDependency("A", "B"),
        FunctionalDependency("B", "A"),
    ],
    "interaction_case_4a": [
        FunctionalDependency("A", "B"),
        FunctionalDependency("B", "C"),
        FunctionalDependency("C", "B"),
    ],
    "interaction_case_4b": [
        FunctionalDependency("A", "B"),
        FunctionalDependency("B", "A"),
        FunctionalDependency("B", "C"),
    ],
    "hyperedges": [
        FunctionalDependency("B", "D"),
        FunctionalDependency("A", "C"),
        FunctionalDependency(("A", "B"), "E"),
    ],
}

correct_bound_attributes: dict[str, set[str]] = {
    "paper_example": {"provider_id"},
    "interaction_case_1": {"A"},
    "interaction_case_2": {"A", "B", "D"},
    "interaction_case_3": {"A"},
    "interaction_case_4": {"A"},
    "interaction_case_4a": {"A"},
    "interaction_case_4b": {"A"},
    "hyperedges": {"A", "B"},
}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return [
        "paper_example",
        "interaction_case_1",
        "interaction_case_2",
        "interaction_case_3",
        "interaction_case_4",
        "interaction_case_4a",
        "interaction_case_4b",
        "hyperedges",
    ]


def static_fd_analysis_test(dataset_name: str) -> None:
    fds: SetOfFDs = set_of_fds[dataset_name]

    # Get traversal order
    ordered_fds: list[FunctionalDependency] = get_ordered_fds(fds, dataset_name, OUTPUT_DIR)[0]

    assert fds.bound_attributes == correct_bound_attributes[dataset_name]
    assert ordered_fds == correct_ordered_fds[dataset_name]


def test_repair_datasets(all_test_datasets) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        static_fd_analysis_test(dataset)
