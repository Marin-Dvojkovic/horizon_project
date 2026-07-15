from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from horizon.fds.fd import FunctionalDependency
from horizon.fds.set_of_fds import SetOfFDs
from horizon.horizon import run_horizon
from horizon.utils.loaders import load_table

TEST_DATA_DIR: Path = Path(__file__).parent.resolve() / "test_data"
OUTPUT_DIR: Path = Path(__file__).parent.resolve() / Path("output")

set_of_fds: dict[str, SetOfFDs] = {
    "paper_example": SetOfFDs(
        [
            FunctionalDependency("provider_area_id", "service_area", 0),
            FunctionalDependency("provider_address", "provider_area_id", 1),
            FunctionalDependency("provider_id", "provider_address", 2),
            FunctionalDependency("service_area", "provider_area_id", 3),
        ]
    )
}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example"]


def repair_dirty_data_test(dataset_name: str) -> None:
    dirty_data_path: Path = TEST_DATA_DIR / f"{dataset_name}_dirty.csv"
    fds: SetOfFDs = set_of_fds[dataset_name]

    # Compute repairs for dirty data
    cleaned_data_path: Path = OUTPUT_DIR / f"{dataset_name}_cleaned_data.csv"
    run_horizon(dataset_name, dirty_data_path, fds, OUTPUT_DIR)
    cleaned_data: pl.DataFrame = load_table(cleaned_data_path)

    # Assert correctness of repairs
    clean_data_path: Path = TEST_DATA_DIR / f"{dataset_name}_clean.csv"
    clean_data: pl.DataFrame = load_table(clean_data_path)

    assert_frame_equal(cleaned_data, clean_data)


def test_repair_datasets(all_test_datasets) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        repair_dirty_data_test(dataset)
