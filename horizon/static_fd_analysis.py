import sys
from pathlib import Path
from symtable import Function
from textwrap import indent

import igraph as ig
import utils.loaders
from igraph import Graph
from utils.fd import FunctionalDependency

# Variables for using different datasets
lhs_column_name: str = "LHS"
rhs_column_name: str = "RHS"

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
    g: ig.Graph = ig.Graph.TupleList(
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

    print(f"FD graph has {g.vcount()} vertices and {g.ecount()} edges.")

    return g


# Find strongly connected components and build SCC graph
def find_strongly_connected_components(g: ig.Graph) -> Graph:
    # Compute and visualize components
    components: ig.VertexClustering = ig.Graph.components(g)
    ig.plot(
        components,
        palette=ig.RainbowPalette(),
        vertex_label=g.vs["name"],
        target=output_dir / "fd_graph_components.png",
    )

    # Build and visualize cluster graph (SCCG)
    sccg: ig.Graph = components.cluster_graph(
        combine_vertices={
            "name": lambda names: names,
        },
        combine_edges={"fd_index": lambda fd_indices: fd_indices},
    )
    ig.plot(
        sccg,
        vertex_color="green",
        vertex_label=sccg.vs["name"],
        edge_label=sccg.es["fd_index"],
        target=output_dir / "scc_fd_graph.png",
    )

    print(f"SCC graph has {sccg.vcount()} components and {sccg.ecount()} edges.")

    return sccg


# Implements Hierholzer's linear time algorithm for constructing an Eulerian cycle/tour
def order_subg(subg: ig.Graph) -> list[FunctionalDependency]:
    sub_order: list[FunctionalDependency] = []

    # Graph attributes
    n: int = subg.vcount()
    in_degrees: list[int] = [subg.indegree(i) for i in range(n)]
    out_degrees: list[int] = [subg.outdegree(i) for i in range(n)]

    # Check requirements for Eulerian cycle/tour
    uneven_vertices: list[int] = [
        i for i in range(n) if out_degrees[i] != in_degrees[i]
    ]
    if len(uneven_vertices) not in [0, 2]:
        raise RuntimeError(
            "Not possible to find a Eulerian cycle/tour and therefore not possible to order FDs."
        )

    # Pick start vertex
    start_v: int | None = 0

    if len(uneven_vertices) == 2:
        # Check requirements for Eulerian tour
        start_v = next(
            (i for i in uneven_vertices if out_degrees[i] == in_degrees[i] + 1), None
        )
        end_v: int | None = next(
            (i for i in uneven_vertices if in_degrees[i] == out_degrees[i] + 1), None
        )
        if start_v is None or end_v is None:
            raise RuntimeError(
                "Not possible to find a Eulerian tour and therrefore not possible to order FDs."
            )
        # Add artificial edge from end to start, in order to compute Eulerian cycle
        subg.add_edge(end_v, start_v)
        out_degrees[end_v] += 1
        in_degrees[start_v] += 1

    traversed_edge_count: list[int] = [0 for i in range(n)]
    visited: list[bool] = [True if i == start_v else False for i in range(n)]
    skipped: list[bool] = [False for i in range(n)]
    predecessor: list[int] = [0 for i in range(n)]

    c = 0
    lhs_v: int = start_v

    while c < subg.ecount():
        traversed_edge_count[lhs_v] += 1
        i: int = traversed_edge_count[lhs_v]

        # Reverse traversal of vertices (follow incoming edges from lhs_v)
        if i <= in_degrees[lhs_v]:
            rhs_v: int = subg.neighbors(lhs_v, mode="in")[i - 1]
            if not visited[rhs_v]:
                if rhs_v != start_v:
                    # Mark predecessor when reached for the first time
                    predecessor[rhs_v] = lhs_v
                visited[rhs_v] = True
            lhs_v = rhs_v
            continue

        # Start backtracking (follow outgoing edges from lhs_v)
        i = traversed_edge_count[lhs_v] - in_degrees[lhs_v]
        rhs_v: int = predecessor[lhs_v]

        # Skip edge
        if (
            i <= out_degrees[lhs_v]
            and subg.neighbors(lhs_v, mode="out")[i - 1] == rhs_v
            and not skipped[lhs_v]
        ):
            skipped[lhs_v] = True
            traversed_edge_count[lhs_v] += 1
            i += 1

        if i <= out_degrees[lhs_v]:
            rhs_v = subg.neighbors(lhs_v, mode="out")[i - 1]

        # Write traversed edge to sub-order
        sub_order.append(subg.es.find(_source=lhs_v, _target=rhs_v)["fd_index"])
        c += 1
        lhs_v = rhs_v

    # Get FDs and eliminate artificial edge
    return [set_of_fds[fd_index] for fd_index in sub_order if fd_index is not None]


# Implements Kahn's Algorithm for computing a topological sorting using BFS
def get_topological_sorting(g: ig.Graph, sccg: ig.Graph) -> list[FunctionalDependency]:
    ordered_fds: list[FunctionalDependency] = []

    # Start with vertices of SCCG with in-degree 0
    vertices: list[ig.Vertex] = [v for v in sccg.vs.select(_indegree_eq=0)]

    while vertices:
        component = vertices.pop(0)

        # If component contains more than 1 vertex
        if len(component["name"]) > 1:
            # Compute order of this component via Eulerian tour of subgraph
            subg = g.induced_subgraph(
                g.vs.select(name_in=component["name"]),
                implementation="create_from_scratch",
            )
            ordered_fds += order_subg(subg)

        # Iterate over neighbors
        for next_vertex in sccg.neighbors(component, mode="out"):
            # Add edge information to ordering and delete it
            edge: ig.Edge = sccg.es.find(_source=component, _target=next_vertex)
            ordered_fds += [set_of_fds[fd_index] for fd_index in edge["fd_index"]]
            sccg.delete_edges(edge)
            # If neighboring vertex now has in-degree 0, add it to vertices queue
            if sccg.indegree(next_vertex) == 0:
                vertices.append(sccg.vs[next_vertex])

    if len(ordered_fds) != len(set_of_fds):
        raise RuntimeError(
            f"Ordered FDs have length {len(ordered_fds)} while therer are {len(set_of_fds)} FDs."
        )

    return ordered_fds


def order_fds(
    topological_sorting: list[FunctionalDependency],
) -> list[FunctionalDependency]:
    return topological_sorting


def get_ordered_fds(fds_csv_path: Path) -> list[FunctionalDependency]:
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
    g: ig.Graph = build_fd_graph()

    # Turn FD graph into SCCG
    sccg: ig.Graph = find_strongly_connected_components(g)

    # Perform topological sorting on SCCG and get order of functional dependencies
    topological_sorting: list[FunctionalDependency] = get_topological_sorting(g, sccg)

    print(f"Final traversal order: {topological_sorting}")

    return topological_sorting
