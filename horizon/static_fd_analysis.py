import sys
from pathlib import Path

import igraph as ig
import utils.loaders
from igraph import Graph
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


# Build FD graph
def build_fd_graph() -> Graph:
    # Create iGraph from tuple list and visualize
    g: Graph = ig.Graph.TupleList(
        [(*fd.as_tuple(), i) for i, fd in enumerate(set_of_fds)],
        directed=True,
        edge_attrs="fd_index",
    )  # TODO: Support hyperedges

    ig.plot(
        g,
        vertex_color="green",
        vertex_label=g.vs["name"],
        edge_label=g.es["fd_index"],
        target=output_dir / "fd_graph.png",
    )

    print(f"FD graph has {g.vcount()} nodes and {g.ecount()} edges.")

    return g


def find_strongly_connected_components(g: Graph) -> tuple[Graph, ig.VertexClustering]:
    # Compute and visualize components
    components: ig.VertexClustering = ig.Graph.components(g)
    ig.plot(
        components,
        palette=ig.RainbowPalette(),
        vertex_label=g.vs["name"],
        target=output_dir / "fd_graph_components.png",
    )

    # Build and visualize cluster graph (SCCG)
    sccg: Graph = components.cluster_graph(
        combine_vertices={
            "name": lambda names: ",".join(names),
        },
        combine_edges={"fd_index": lambda indices: indices},
    )
    ig.plot(
        sccg,
        vertex_color="green",
        vertex_label=sccg.vs["name"],
        edge_label=sccg.es["fd_index"],
        target=output_dir / "scc_fd_graph.png",
    )

    print(f"SCC graph has {sccg.vcount()} components and {sccg.ecount()} edges.")

    return sccg, components


def get_topological_sorting(
    sccg: Graph, components: ig.VertexClustering
) -> list[list[str]]:
    # Perform topological sorting of each subgraph of SCCG
    topological_sorting: list[list[str]] = [
        [
            name
            for i in subg.topological_sorting(mode="out")
            for name in sccg.vs.find(name=subg.vs[i]["name"])["name"].split(",")
        ]
        for subg in sccg.decompose(mode="weak")
    ]

    return topological_sorting


def order_fds(topological_sorting: list[list[str]]) -> list[list[str]]:
    # TODO: Proper order representation, for each bound attribute
    # Pseudocode from the paper:
    ## for i <- 0 to |Ordered_FDs| do
    ### forall FD f in Ordered_FDs[i] do

    return topological_sorting


def get_ordered_fds(fds_csv_path: Path) -> list[list[str]]:
    global set_of_fds

    # Check fds.csv path
    if not fds_csv_path.exists:
        raise ValueError(f"CSV file {str(fds_csv_path)} does not exist.")

    # Create output directory
    if not output_dir.exists:
        output_dir.mkdir()

    # Use CSV data loader to read input FDs from file
    set_of_fds = utils.loaders.get_fds(
        fds_csv_path, utils.loaders.CSVFDLoader(lhs_column_name, rhs_column_name)
    )

    # Determine attribute boundedness
    determine_boundedness(set_of_fds)

    # Build FD graph
    g: Graph = build_fd_graph()

    # Turn FD graph into SCCG
    sccg, components = find_strongly_connected_components(g)

    # Perform topological sorting on SCCG
    topological_sorting: list[list[str]] = get_topological_sorting(sccg, components)

    # Order functional dependencies
    order: list[list[str]] = order_fds(topological_sorting)
    print(f"Final traversal order: {order}")

    return order
