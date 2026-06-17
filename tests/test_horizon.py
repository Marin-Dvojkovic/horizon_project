from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from horizon.fd_pattern_graph import FDPatternGraph
from horizon.fds.fd import FunctionalDependency
from horizon.fds.set_of_fds import SetOfFDs
from horizon.horizon import load_data, repair_dirty_data
from horizon.static_fd_analysis import get_ordered_fds

test_data_dir: Path = Path(__file__).parent.resolve() / "test_data"
output_dir: Path = Path(__file__).parent.resolve() / Path("output")


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example"]


def repair_dirty_data_test(dataset_name: str) -> None:
    dirty_data_path: Path = test_data_dir / f"{dataset_name}_dirty.csv"
    clean_data_path: Path = test_data_dir / f"{dataset_name}_clean.csv"

    set_of_fds: SetOfFDs = SetOfFDs(
        [
            FunctionalDependency("provider_id", "provider_address"),
            FunctionalDependency("provider_address", "provider_area_id"),
            FunctionalDependency("provider_area_id", "service_area"),
            FunctionalDependency("service_area", "provider_area_id"),
        ]
    )

    # Get traversal order
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(
        set_of_fds, dataset_name, output_dir
    )

    # Build FD pattern graph
    fd_pattern_graph: FDPatternGraph = FDPatternGraph(str(dirty_data_path), set_of_fds)

    # Compute repairs for dirty data
    dirty_data: pl.DataFrame = load_data(dirty_data_path)
    cleaned_data, _ = repair_dirty_data(dirty_data, ordered_fds, fd_pattern_graph)

    # Assert correctness of repairs
    clean_data: pl.DataFrame = load_data(clean_data_path)

    assert_frame_equal(cleaned_data, clean_data)


def test_repair_datasets(all_test_datasets) -> None:
    output_dir.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        repair_dirty_data_test(dataset)
