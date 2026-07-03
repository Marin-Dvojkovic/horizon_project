from pathlib import Path

import pytest

from horizon.fd_pattern_graph import FDPatternGraph
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

correct_qualities: dict[str, list[tuple]] = {
    "paper_example": [
        ("provider_id__GF903", "provider_address__140 W Court", 0.3333),
        ("provider_id__GF903", "provider_address__1407 Wescam Court", 0.4444),
        ("provider_id__YT43", "provider_address__1407 Wescam Court", 0.5),
        ("provider_id__RG09", "provider_address__160 Asher St", 0.3333),
        ("provider_address__140 W Court", "provider_area_id__0", 0.3333),
        ("provider_address__1407 Wescam Court", "provider_area_id__T75", 0.5833),
        ("provider_address__160 Asher St", "provider_area_id__T75", 0.4167),
        ("provider_area_id__0", "service_area__212", 0.3333),
        ("provider_area_id__T75", "service_area__212", 0.6667),
        # TODO: Uncomment once quality computation of back-edges is correct
        # ("service_area__212", "provider_area_id__0", 0.44),
        # ("service_area__212", "provider_area_id__T75", 0.49),
    ]
}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example"]


def build_fd_pattern_graph_test(dataset_name: str) -> None:
    dirty_data_path: Path = TEST_DATA_DIR / f"{dataset_name}_dirty.csv"

    fds: SetOfFDs = set_of_fds[dataset_name]

    # Get traversal order - sets order in set of FDs
    get_ordered_fds(fds, dataset_name, OUTPUT_DIR)

    # Build FD pattern graph
    fd_pattern_graph: FDPatternGraph = FDPatternGraph(
        dirty_data_path, fds, dataset_name, OUTPUT_DIR, True
    )

    # Assert correct qualities
    for from_node, to_node, correct_quality in correct_qualities[dataset_name]:
        assert round(
            fd_pattern_graph.get_edge_quality(from_node, to_node), 4
        ) == pytest.approx(correct_quality)


def test_build_fd_pattern_graph(all_test_datasets) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        build_fd_pattern_graph_test(dataset)
