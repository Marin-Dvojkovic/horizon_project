import sys
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import utils.loaders
from utils.fd import FunctionalDependency

# Variables for using different datasets
lhs_column_name: str = "from"
rhs_column_name: str = "to"

output_dir: Path = Path("output")

# Global variables for storing FDs
set_of_fds: list[FunctionalDependency] = []
bound_attributes: set[str] = set()


def determine_boundedness(fds: list[FunctionalDependency]) -> None:
    global bound_attributes

    attribute_fd_mapping: dict[str, list[tuple[str, str]]] = {}
    free_attributes: set[str] = set()
    fds_to_check: list[tuple[str, str]] = []

    # TODO: Deal with multiple attributes on LHS correctly
    # Iterate over all FDs
    for fd in fds:
        rhs: str = fd.rhs
        if rhs not in attribute_fd_mapping:
            attribute_fd_mapping[rhs] = []

        # Always add RHS attributes to free attributes
        free_attributes.add(rhs)
        if rhs in bound_attributes:
            bound_attributes.remove(rhs)

        # For all LHS attributes
        for lhs in fd.lhs:
            # Collect all FDs that point to the respective attribute
            if lhs not in attribute_fd_mapping:
                attribute_fd_mapping[lhs] = []
            attribute_fd_mapping[rhs].append((lhs, rhs))

            # If LHS not in free attributes: Add LHS attribute to bound attributes
            if lhs not in free_attributes:
                bound_attributes.add(lhs)
                continue

            # If LHS in free attributes:
            # If there is no cycle LHS <-> RHS, LHS stays free
            if (rhs, lhs) not in attribute_fd_mapping[lhs]:
                continue
            # If there is a cycle LHS <-> RHS, but another attribute A bounds one of the attributes (A -> LHS or A -> RHS), LHS stays free
            if len(attribute_fd_mapping[lhs]) > 1 or len(attribute_fd_mapping[rhs]) > 1:
                continue
            # Else we don't know yet and have to check at the end
            fds_to_check.append((lhs, rhs))

    # Check unprocessed cycles LHS <-> RHS, if A with A -> LHS or A -> RHS appeared, both LHS and RHS stay free
    for lhs, rhs in fds_to_check:
        # Add LHS to bound attributes, if there is no other attribute A
        if len(attribute_fd_mapping[lhs]) == 1 and len(attribute_fd_mapping[rhs]) == 1:
            free_attributes.remove(lhs)
            bound_attributes.add(lhs)

    print(f"Found {len(bound_attributes)} bound attribute(s): {bound_attributes}.")


# Build FD graph from pandas df
def build_fd_graph(fds: pd.DataFrame) -> nx.DiGraph:
    # NOTE: Ignores multiple LHS attributes for now
    fds_simple: pd.DataFrame = fds[
        ~fds[lhs_column_name].str.contains(",")
    ]  # TODO: Support hyperedges

    # Create graph from pandas df
    G: nx.DiGraph = nx.from_pandas_edgelist(
        df=fds_simple,
        source=lhs_column_name,
        target=rhs_column_name,
        create_using=nx.DiGraph(),
    )

    print(f"FD graph has {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # Save figure as .png
    nx.draw(G, with_labels=True, pos=nx.circular_layout(G))
    plt.savefig(output_dir / "fd_graph.png")
    plt.clf()

    return G


def find_strongly_connected_components(G) -> tuple[nx.DiGraph, dict]:
    # Build condensation graph (SCCG)
    SCCG: nx.DiGraph = nx.condensation(
        G
    )  # Builds SCCG with nx.strongly_connected_components(G)
    member_mapping: dict = {
        node_data[0]: node_data[1]["members"] for node_data in SCCG.nodes.data()
    }

    print(
        f"SCC graph has {SCCG.number_of_nodes()} components and {SCCG.number_of_edges()} edges."
    )

    # Save figure as .png
    nx.draw(
        SCCG,
        with_labels=True,
        labels=member_mapping,
        pos=nx.circular_layout(SCCG),
    )
    plt.savefig(output_dir / "scc_fd_graph.png")
    plt.clf()

    return SCCG, member_mapping


def get_topological_sorting(SCCG: nx.DiGraph, member_mapping: dict) -> list[str]:
    # Perform topological sorting of SCCG
    topological_sorting: list[str] = []
    for sccg_node in nx.topological_sort(SCCG):
        for attribute in member_mapping[sccg_node]:
            topological_sorting.append(attribute)

    return topological_sorting


def order_fds(topological_sorting: list[str]) -> list[str]:
    # TODO: Proper order representation, for each bound attribute
    # Pseudocode from the paper:
    ## for i <- 0 to |Ordered_FDs| do
    ### forall FD f in Ordered_FDs[i] do

    return topological_sorting


def get_ordered_fds(fds_csv_path: Path) -> list[str]:
    global set_of_fds

    # Check fds.csv path
    if not fds_csv_path.exists():
        raise ValueError(f"CSV file {str(fds_csv_path)} does not exist.")

    # Create output directory
    if not output_dir.exists():
        output_dir.mkdir()

    # Use CSV data loader to read input FDs from file
    set_of_fds = utils.loaders.get_fds(
        fds_csv_path, utils.loaders.CSVFDLoader(lhs_column_name, rhs_column_name)
    )

    # Determine attribute boundedness
    determine_boundedness(set_of_fds)

    # Build FD graph
    G: nx.DiGraph = build_fd_graph(pd.read_csv(fds_csv_path))

    # Turn FD graph into SCCG
    SCCG, member_mapping = find_strongly_connected_components(G)

    # Perform topological sorting on SCCG
    topological_sorting: list[str] = get_topological_sorting(SCCG, member_mapping)

    # Order functional dependencies
    order: list[str] = order_fds(topological_sorting)
    print(f"Final traversal order: {order}")

    return order
