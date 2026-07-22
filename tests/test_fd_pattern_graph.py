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
            FunctionalDependency("provider_area_id", "service_area", 0),
            FunctionalDependency("provider_address", "provider_area_id", 1),
            FunctionalDependency("provider_id", "provider_address", 2),
            FunctionalDependency("service_area", "provider_area_id", 3),
        ]
    ),
    "adult_smoking_prevalence": SetOfFDs(
        [FunctionalDependency("yearvalue", "comparison", 0)]
    ),
    "shared_it_support_services": SetOfFDs(
        [
            FunctionalDependency("years", "historical_data"),
            FunctionalDependency("years", "target"),
        ]
    ),
}

# Correct qualities without pruning
correct_qualities: dict[str, list[tuple]] = {
    "paper_example": [
        ("provider_id__GF903", "provider_address__140 W Court", 0.3333),
        ("provider_id__GF903", "provider_address__1407 Wescam Court", 0.4444),
        # These edges are never inserted into the graph, as they are singleton source patterns
        # ("provider_id__YT43", "provider_address__1407 Wescam Court", 0.5),
        # ("provider_id__RG09", "provider_address__160 Asher St", 0.3333),
        ("provider_address__140 W Court", "provider_area_id__0", 0.3333),
        ("provider_address__1407 Wescam Court", "provider_area_id__T75", 0.5833),
        ("provider_address__160 Asher St", "provider_area_id__T75", 0.4167),
        ("provider_area_id__0", "service_area__212", 0.3333),
        ("provider_area_id__T75", "service_area__212", 0.6667),
        # TODO: Qualities should be 0.44 and 0.49, but currently quality of back-edges is support
        ("service_area__212", "provider_area_id__0", 0.3333),
        ("service_area__212", "provider_area_id__T75", 0.6667),
    ],
    "adult_smoking_prevalence": [
        ("yearvalue__1984.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1985.0", "comparison__Definition Expanded in 1996", 0.0185),
        ("yearvalue__2003.0", "comparison__Definition Expanded in 1996", 0.0093),
        ("yearvalue__1986.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1987.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1988.0", "comparison__Definition Expanded in 1996", 0.0185),
        ("yearvalue__2010.0", "comparison__Definition Expanded in 1996", 0.0463),
        ("yearvalue__1989.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1990.0", "comparison__Definition Expanded in 1996", 0.0185),
        ("yearvalue__1991.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1992.0", "comparison__Definition Expanded in 1996", 0.0185),
        ("yearvalue__1993.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1994.0", "comparison__Definition Expanded in 1996", 0.0093),
        ("yearvalue__1995.0", "comparison__Definition Expanded in 1996", 0.0278),
        ("yearvalue__1991.0", "comparison__Survey Methodology Changed in 2012", 0.0463),
        ("yearvalue__1984.0", "comparison__Survey Methodology Changed in 2012", 0.0556),
        ("yearvalue__1987.0", "comparison__Survey Methodology Changed in 2012", 0.0463),
        ("yearvalue__1997.0", "comparison__Survey Methodology Changed in 2012", 0.0093),
        ("yearvalue__1993.0", "comparison__Survey Methodology Changed in 2012", 0.0278),
        ("yearvalue__1985.0", "comparison__Survey Methodology Changed in 2012", 0.0370),
        ("yearvalue__1992.0", "comparison__Survey Methodology Changed in 2012", 0.0278),
        ("yearvalue__1986.0", "comparison__Survey Methodology Changed in 2012", 0.0833),
        ("yearvalue__1995.0", "comparison__Survey Methodology Changed in 2012", 0.0278),
        ("yearvalue__1988.0", "comparison__Survey Methodology Changed in 2012", 0.0185),
        ("yearvalue__2003.0", "comparison__Survey Methodology Changed in 2012", 0.0093),
        ("yearvalue__1990.0", "comparison__Survey Methodology Changed in 2012", 0.0093),
        ("yearvalue__1989.0", "comparison__Survey Methodology Changed in 2012", 0.0278),
        ("yearvalue__1994.0", "comparison__Survey Methodology Changed in 2012", 0.0093),
        ("yearvalue__2010.0", "comparison__Survey Methodology Changed in 2012", 0.0093),
        ("yearvalue__1984.0", "comparison__Present", 0.0463),
        ("yearvalue__1990.0", "comparison__Present", 0.0185),
        ("yearvalue__1992.0", "comparison__Present", 0.0093),
        ("yearvalue__1987.0", "comparison__Present", 0.0278),
        ("yearvalue__2010.0", "comparison__Present", 0.0093),
        ("yearvalue__1989.0", "comparison__Present", 0.0185),
        ("yearvalue__1986.0", "comparison__Present", 0.0370),
        ("yearvalue__1985.0", "comparison__Present", 0.0093),
        ("yearvalue__2003.0", "comparison__Present", 0.0093),
        ("yearvalue__1997.0", "comparison__Present", 0.0093),
        ("yearvalue__1995.0", "comparison__Present", 0.0185),
        ("yearvalue__1993.0", "comparison__Present", 0.0093),
    ],
    "shared_it_support_services": [
        ("years__2012.0", "historical_data__21.00%", 0.1429),
        ("years__2012.0", "historical_data__34.00%", 0.1429),
        ("years__2012.0", "historical_data__54.00%", 0.1429),
        # These edges are never inserted into the graph, as they are singleton source patterns
        # ("years__2014.0", "historical_data__63.00%", 0.1429),
        # ("years__2015.0", "historical_data__0.00%", 0.1429),
        # ("years__2016.0", "historical_data__0.00%", 0.1429),
        # ("years__2017.0", "historical_data__0.00%", 0.1429),
        # ("years__2012.0", "target__0.00%", 0.4286),
        # ("years__2014.0", "target__0.00%", 0.1429),
        # ("years__2015.0", "target__0.00%", 0.1429),
        # ("years__2016.0", "target__0.00%", 0.1429),
        # ("years__2017.0", "target__100.00%", 0.1429),
    ],
}

# Correct repair tables
correct_repair_table: dict[str, list[dict[str, str]]] = {
    "paper_example": [
        # FD with index 0
        {},
        # FD with index 1
        {},
        # FD with index 2
        {"YT43": "1407 Wescam Court", "RG09": "160 Asher St"},
        # FD with index 3
        {},
    ],
    "adult_smoking_prevalence": [{}],
    "shared_it_support_services": [
        {
            "2014.0": "63.00%",
            "2015.0": "0.00%",
            "2016.0": "0.00%",
            "2017.0": "0.00%",
        },
        {
            "2012.0": "0.00%",
            "2014.0": "0.00%",
            "2015.0": "0.00%",
            "2016.0": "0.00%",
            "2017.0": "100.00%",
        },
    ],
}

# Pruned edges
pruned_qualities: dict[str, list[tuple]] = {
    "paper_example": [
        # These edges are pruned in the graph after quality computation, as they are singleton patterns
        ("provider_address__140 W Court", "provider_area_id__0", 0.3333),
        ("provider_address__1407 Wescam Court", "provider_area_id__T75", 0.5833),
        ("provider_address__160 Asher St", "provider_area_id__T75", 0.4167),
        ("provider_area_id__0", "service_area__212", 0.3333),
        ("provider_area_id__T75", "service_area__212", 0.6667),
    ],
    "adult_smoking_prevalence": [],
    "shared_it_support_services": [],
}

# Correct repair tables after pruning
correct_pruned_repair_table: dict[str, list[dict[str, str]]] = {
    "paper_example": [
        # FD with index 0
        {"0": "212", "T75": "212"},
        # FD with index 1
        {"140 W Court": "0", "1407 Wescam Court": "T75", "160 Asher St": "T75"},
        # FD with index 2
        {"YT43": "1407 Wescam Court", "RG09": "160 Asher St"},
        # FD with index 3
        {},
    ],
    "adult_smoking_prevalence": [{}],
    "shared_it_support_services": [
        {
            "2014.0": "63.00%",
            "2015.0": "0.00%",
            "2016.0": "0.00%",
            "2017.0": "0.00%",
        },
        {
            "2012.0": "0.00%",
            "2014.0": "0.00%",
            "2015.0": "0.00%",
            "2016.0": "0.00%",
            "2017.0": "100.00%",
        },
    ],
}


@pytest.fixture
def all_test_datasets() -> list[str]:
    return ["paper_example", "adult_smoking_prevalence", "shared_it_support_services"]


def build_fd_pattern_graph_test(dataset_name: str) -> None:
    dirty_data_path: Path = TEST_DATA_DIR / dataset_name / "dirty.csv"

    fds: SetOfFDs = set_of_fds[dataset_name]

    # Get traversal order - sets order in set of FDs
    get_ordered_fds(fds, dataset_name, OUTPUT_DIR)

    # Build FD pattern graph without pruning edges
    fd_pattern_graph: FDPatternGraph = FDPatternGraph(
        dirty_data_path,
        fds,
        dataset_name,
        pruning=False,
        output_dir=OUTPUT_DIR,
        enable_plotting=True,
    )

    # Assert correct qualities
    for from_node, to_node, correct_quality in correct_qualities[dataset_name]:
        assert round(
            fd_pattern_graph.get_edge_quality(from_node, to_node), 4
        ) == pytest.approx(correct_quality)

    # Assert correct number of edges
    assert fd_pattern_graph.number_of_edges == len(correct_qualities[dataset_name])

    # Assert correct repair table
    assert fd_pattern_graph.repair_table == correct_repair_table[dataset_name]

    fd_pattern_graph.clear()

    # Build FD pattern graph with pruning edges
    fd_pattern_graph = FDPatternGraph(
        dirty_data_path,
        fds,
        dataset_name,
        pruning=True,
        output_dir=OUTPUT_DIR,
        enable_plotting=True,
    )

    # Assert correct qualities
    for from_node, to_node, correct_quality in correct_qualities[dataset_name]:
        if (from_node, to_node, correct_quality) not in pruned_qualities[dataset_name]:
            assert round(
                fd_pattern_graph.get_edge_quality(from_node, to_node), 4
            ) == pytest.approx(correct_quality)

    # Assert correct number of edges
    assert fd_pattern_graph.number_of_edges == len(
        correct_qualities[dataset_name]
    ) - len(pruned_qualities[dataset_name])

    # Assert correct pruned repair table
    assert fd_pattern_graph.repair_table == correct_pruned_repair_table[dataset_name]


def test_build_fd_pattern_graph(all_test_datasets) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for dataset in all_test_datasets:
        build_fd_pattern_graph_test(dataset)
