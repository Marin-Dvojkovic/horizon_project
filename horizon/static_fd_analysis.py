import time
from pathlib import Path

import igraph as ig
import matplotlib.pyplot as plt
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs
from igraph import Graph
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Use matplotlib as backend for igraph
plotting_enabled: bool
ig.config["plotting.backend"] = "matplotlib"


class FDGraph:
    def __init__(
        self,
        set_of_fds: SetOfFDs,
        dataset_name: str,
        output_dir: Path = Path("output"),
    ) -> None:
        self._set_of_fds = set_of_fds
        self._output_dir = output_dir
        self._dataset_name = dataset_name

        # Build FD graph
        self._g: Graph = self.build_fd_graph()

        # Turn FD graph into SCCG
        self._scc_g: Graph = self.find_strongly_connected_components()

    # Build FD graph
    def build_fd_graph(self) -> Graph:
        logger.info(
            f"Building FD graph from {len(self._set_of_fds)} functional dependencies"
        )
        # Create iGraph from tuple list and visualize
        g: Graph = Graph.TupleList(
            [(*fd, i) for i, fd in enumerate(self._set_of_fds.as_tuple_list())],
            directed=True,
            edge_attrs="fd_index",
        )

        g.add_edges(
            [
                (single, multiple)
                for multiple in g.vs
                for single in multiple["name"]
                if isinstance(multiple["name"], tuple)
                and len(g.vs.select(name_eq=single)) != 0
            ]
        )

        if plotting_enabled:
            logger.debug("Saving FD graph visualization")
            plt.figure(figsize=(max(7, g.vcount() / 2), max(7, g.vcount() / 2)))

            ig.plot(
                g,
                layout="tree",
                vertex_color="green",
                vertex_label=g.vs["name"],
                vertex_label_dist=1.5,
                edge_label=g.es["fd_index"],
            )

            plt.gca().invert_yaxis()  # Plot tree with root at top
            plt.savefig(str(self._output_dir / f"{self._dataset_name}_fd_graph.png"))
            plt.clf()

        logger.info(f"FD graph built: {g.vcount()} vertices and {g.ecount()} edges")
        return g

    # Find strongly connected components and build SCC graph
    def find_strongly_connected_components(self) -> Graph:
        logger.info("Finding strongly connected components...")
        # Compute and visualize components
        components: ig.VertexClustering = Graph.components(self._g)
        logger.debug(f"Found {len(components)} components")

        if plotting_enabled:
            logger.debug("Saving component visualization")
            plt.figure(
                figsize=(max(7, self._g.vcount() / 2), max(7, self._g.vcount() / 2))
            )

            ig.plot(
                components,
                layout="tree",
                palette=ig.RainbowPalette(),
                vertex_label=self._g.vs["name"],
                vertex_label_dist=1.5,
            )

            plt.gca().invert_yaxis()  # Plot tree with root at top
            plt.savefig(
                str(self._output_dir / f"{self._dataset_name}_fd_graph_components.png")
            )
            plt.clf()

        # Build and visualize cluster graph (SCCG)
        logger.info("Building SCC graph...")
        scc_g: Graph = components.cluster_graph(
            combine_vertices={
                "name": lambda names: names,
            },
            combine_edges={"fd_index": lambda fd_indices: fd_indices},
        )

        if plotting_enabled:
            logger.debug("Saving SCC graph visualization")
            plt.figure(figsize=(max(7, scc_g.vcount() / 2), max(7, scc_g.vcount() / 2)))

            ig.plot(
                scc_g,
                layout="tree",
                vertex_color="green",
                vertex_label=scc_g.vs["name"],
                vertex_label_dist=1.5,
                edge_label=scc_g.es["fd_index"],
            )

            plt.gca().invert_yaxis()  # Plot tree with root at top
            plt.savefig(
                str(self._output_dir / f"{self._dataset_name}_scc_fd_graph.png")
            )
            plt.clf()

        logger.info(
            f"SCC graph built: {scc_g.vcount()} components and {scc_g.ecount()} edges"
        )
        return scc_g

    # Implements Hierholzer's linear time algorithm for constructing an Eulerian cycle/tour
    def order_subg(self, sub_g: Graph) -> list[FunctionalDependency]:
        sub_order: list[FunctionalDependency] = []

        # Graph attributes
        n: int = sub_g.vcount()
        in_degrees: list[int] = [sub_g.indegree(i) for i in range(n)]
        out_degrees: list[int] = [sub_g.outdegree(i) for i in range(n)]

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
                (i for i in uneven_vertices if out_degrees[i] == in_degrees[i] + 1),
                None,
            )
            end_v: int | None = next(
                (i for i in uneven_vertices if in_degrees[i] == out_degrees[i] + 1),
                None,
            )
            if start_v is None or end_v is None:
                raise RuntimeError(
                    "Not possible to find a Eulerian tour and therefore not possible to order FDs."
                )
            # Add artificial edge from end to start, in order to compute Eulerian cycle
            sub_g.add_edge(end_v, start_v)
            out_degrees[end_v] += 1
            in_degrees[start_v] += 1

        traversed_edge_count: list[int] = [0 for i in range(n)]
        visited: list[bool] = [True if i == start_v else False for i in range(n)]
        skipped: list[bool] = [False for i in range(n)]
        predecessor: list[int] = [0 for i in range(n)]

        c = 0
        lhs_v: int = start_v

        while c < sub_g.ecount():
            traversed_edge_count[lhs_v] += 1
            i: int = traversed_edge_count[lhs_v]

            # Reverse traversal of vertices (follow incoming edges from lhs_v)
            if i <= in_degrees[lhs_v]:
                rhs_v: int = sub_g.neighbors(lhs_v, mode="in")[i - 1]
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
                and sub_g.neighbors(lhs_v, mode="out")[i - 1] == rhs_v
                and not skipped[lhs_v]
            ):
                skipped[lhs_v] = True
                traversed_edge_count[lhs_v] += 1
                i += 1

            if i <= out_degrees[lhs_v]:
                rhs_v = sub_g.neighbors(lhs_v, mode="out")[i - 1]

            # Write traversed edge to sub-order
            sub_order.append(sub_g.es.find(_source=lhs_v, _target=rhs_v)["fd_index"])
            c += 1
            lhs_v = rhs_v

        # Get FDs and eliminate artificial edge
        return [
            self._set_of_fds[fd_index] for fd_index in sub_order if fd_index is not None
        ]

    # Implements Kahn's Algorithm for computing a topological sorting using BFS
    def get_topological_sorting(
        self, component_g: Graph, original_g: Graph
    ) -> list[FunctionalDependency]:
        ordered_fds: list[FunctionalDependency] = []

        # Start with vertices of graph with in-degree 0
        vertices: list[ig.Vertex] = [v for v in component_g.vs.select(_indegree_eq=0)]

        while vertices:
            component_v = vertices.pop(0)

            # If component contains more than 1 vertex
            if len(component_v["name"]) > 1:
                # Compute order of this component via Eulerian tour of subgraph
                sub_g = original_g.induced_subgraph(
                    original_g.vs.select(name_in=component_v["name"]),
                    implementation="create_from_scratch",
                )
                ordered_fds += self.order_subg(sub_g)

            # Iterate over neighbors
            for next_vertex in component_g.neighbors(component_v, mode="out"):
                # Add edge information to ordering and delete it
                edge: ig.Edge = component_g.es.find(
                    _source=component_v, _target=next_vertex
                )
                ordered_fds += [
                    self._set_of_fds[fd_index]
                    for fd_index in edge["fd_index"]
                    if fd_index is not None
                ]
                component_g.delete_edges(edge)
                # If neighboring vertex now has in-degree 0, add it to vertices queue
                if component_g.indegree(next_vertex) == 0:
                    vertices.append(component_g.vs[next_vertex])

        return ordered_fds

    def order_fds(self) -> list[list[FunctionalDependency]]:
        # Perform topological sorting of each sub-component of SCCG
        ordered_fds: list[list[FunctionalDependency]] = [
            self.get_topological_sorting(sub_g, self._g)
            for sub_g in self._scc_g.decompose(mode="weak")
        ]

        if sum([len(order) for order in ordered_fds]) != len(self._set_of_fds):
            raise RuntimeError(
                f"Ordered FDs have length {sum([len(order) for order in ordered_fds])} while therer are {len(self._set_of_fds)} FDs."
            )

        return ordered_fds


def get_ordered_fds(
    set_of_fds: SetOfFDs,
    dataset_name: str,
    output_dir: Path,
    enable_plotting: bool = True,
) -> list[list[FunctionalDependency]]:
    global plotting_enabled
    plotting_enabled = enable_plotting

    logger.info("Computing ordered FDs for pipeline execution")

    start: float = time.time()

    # Build FD graph and SCCG
    fd_graph: FDGraph = FDGraph(set_of_fds, dataset_name, output_dir)

    # Perform topological sorting on SCCG and get order of functional dependencies
    logger.info("Performing topological sorting...")
    ordered_fds: list[list[FunctionalDependency]] = fd_graph.order_fds()

    set_of_fds.set_bound_attributes(
        {fds[0].lhs for fds in ordered_fds if not isinstance(fds[0].lhs, tuple)}
    )  # TODO: Support multiple attributes on LHS
    logger.info(
        f"Identified {len(set_of_fds.bound_attributes)} bound attributes: {set_of_fds.bound_attributes}"
    )

    logger.info(f"Computed traversal order with {len(ordered_fds)} groups")
    for i, fd_group in enumerate(ordered_fds):
        logger.debug(f"Group {i}: {len(fd_group)} FDs")

    end: float = time.time()
    logger.info(f"Completed ordering FDs in {(end - start):.2f}s")

    return ordered_fds
