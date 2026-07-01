from pathlib import Path

import pytest

from horizon.fds.fd import FunctionalDependency
from horizon.fds.set_of_fds import SetOfFDs
from horizon.static_fd_analysis import get_ordered_fds

test_data_dir: Path = Path(__file__).parent.resolve() / "test_data"
output_dir: Path = Path(__file__).parent.resolve() / Path("output")


correct_ordered_fds: dict[str, list[list[FunctionalDependency]]] = {
    "paper_example": [
        [
            FunctionalDependency("provider_id", "provider_address"),
            FunctionalDependency("provider_address", "provider_area_id"),
            FunctionalDependency("provider_area_id", "service_area"),
            FunctionalDependency("service_area", "provider_area_id"),
        ]
    ]
}

correct_bound_attributes: dict[str, set[str]] = {"paper_example": {"provider_id"}}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example"]


def static_fd_analysis_test(dataset_name: str) -> None:
    set_of_fds: SetOfFDs = SetOfFDs(
        [
            FunctionalDependency("provider_area_id", "service_area"),
            FunctionalDependency("provider_address", "provider_area_id"),
            FunctionalDependency("provider_id", "provider_address"),
            FunctionalDependency("service_area", "provider_area_id"),
        ]
    )

    # Get traversal order
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(
        set_of_fds, dataset_name, output_dir
    )[0]

    assert set_of_fds.bound_attributes == correct_bound_attributes[dataset_name]
    assert ordered_fds == correct_ordered_fds[dataset_name]


def test_repair_datasets(all_test_datasets) -> None:
    output_dir.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        static_fd_analysis_test(dataset)
