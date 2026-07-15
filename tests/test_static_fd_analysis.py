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
    )
}

correct_ordered_fds: dict[str, list[FunctionalDependency]] = {
    "paper_example": [
        FunctionalDependency("provider_id", "provider_address"),
        FunctionalDependency("provider_address", "provider_area_id"),
        FunctionalDependency("provider_area_id", "service_area"),
        FunctionalDependency("service_area", "provider_area_id"),
    ]
}

correct_bound_attributes: dict[str, set[str]] = {"paper_example": {"provider_id"}}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example"]


def static_fd_analysis_test(dataset_name: str) -> None:
    fds: SetOfFDs = set_of_fds[dataset_name]

    # Get traversal order
    ordered_fds: list[FunctionalDependency] = get_ordered_fds(
        fds, dataset_name, OUTPUT_DIR
    )[0]

    assert fds.bound_attributes == correct_bound_attributes[dataset_name]
    assert ordered_fds == correct_ordered_fds[dataset_name]


def test_repair_datasets(all_test_datasets) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        static_fd_analysis_test(dataset)
