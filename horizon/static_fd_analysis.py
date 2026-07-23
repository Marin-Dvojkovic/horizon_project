"""Static analysis of the FD set: boundness and traversal order.

Builds the FD graph and its SCC graph, then derives an FD traversal order via
topological sorting over the SCC DAG (paper §5.1) and identifies bound/free (and
source) attributes (§4.2). Cyclic SCCs are ordered with an Eulerian tour.
"""

import json
import time
from collections import deque
from pathlib import Path

import igraph as ig
import matplotlib.pyplot as plt
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs
from igraph import Graph
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Use matplotlib as backend for igraph
ig.config["plotting.backend"] = "matplotlib"


class FDGraph:
    """Attribute-level FD graph and its strongly-connected-component graph (paper §5.1).

    Wraps the FD set as a directed graph over attributes, together with the SCC
    graph (a DAG) used to compute the FD traversal order and attribute boundness.
    """

    # Class variables
    _set_of_fds: SetOfFDs
    _fd_g: Graph
    _scc_g: Graph
    _components: ig.VertexClustering

    def __init__(
        self,
        set_of_fds: SetOfFDs,
    ) -> None:
        """Build the FD graph and its SCC graph from a set of FDs.

        Args:
            set_of_fds: Functional dependencies to analyse.

        Returns:
            None.
        """
        self._set_of_fds = set_of_fds

        # Build FD graph
        self._fd_g = self._build_fd_graph()

        # Turn FD graph into SCCG
        self._scc_g = self._find_strongly_connected_components()

    def _build_fd_graph(self) -> Graph:
        """Build the directed attribute graph with one edge per FD.

        Returns:
            An igraph Graph whose edges carry the originating ``fd_index``.
        """
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

        logger.info(f"FD graph built: {g.vcount()} vertices and {g.ecount()} edges")
        return g

    def _find_strongly_connected_components(self) -> Graph:
        """Find strongly connected components and build the SCC graph (paper §5.1).

        Returns:
            The SCC graph (a DAG), with component attribute names and per-edge
            ``fd_index`` lists preserved.
        """
        logger.info("Finding strongly connected components...")
        # Compute components
        components: ig.VertexClustering = Graph.components(self._fd_g)
        self._components = components
        logger.debug(f"Found {len(components)} components")

        # Build cluster graph (SCCG)
        logger.info("Building SCC graph...")
        scc_g: Graph = components.cluster_graph(
            combine_vertices={
                "name": lambda names: names,
            },
            combine_edges={"fd_index": lambda fd_indices: fd_indices},
        )

        logger.info(
            f"SCC graph built: {scc_g.vcount()} components and {scc_g.ecount()} edges"
        )
        return scc_g

    def _order_subg(
        self, sub_g: Graph, start_v: int, order_counter: int
    ) -> list[FunctionalDependency]:
        """Order the FDs within one cyclic SCC via an Eulerian tour (paper §5.1).

        Uses Hierholzer's linear-time algorithm to traverse the SCC subgraph, tagging
        each FD with an ascending ``order`` as its edge is traversed.

        Args:
            sub_g: Induced subgraph of one SCC.
            start_v: Vertex index to start the tour from.
            order_counter: First order value to assign in this SCC.

        Returns:
            The FDs of this SCC in traversal order.

        Raises:
            RuntimeError: If the subgraph admits no Eulerian cycle/tour.
        """
        sub_order: list[FunctionalDependency] = []

        # Graph attributes
        n: int = sub_g.vcount()
        in_degrees: list[int] = sub_g.indegree()
        out_degrees: list[int] = sub_g.outdegree()

        # Check requirements for Eulerian cycle/tour
        uneven_vertices: list[int] = [
            i for i in range(n) if out_degrees[i] != in_degrees[i]
        ]
        if len(uneven_vertices) not in [0, 2]:
            logger.error(
                "Not possible to find a Eulerian cycle/tour and therefore not possible to order FDs."
            )
            raise RuntimeError(
                "Not possible to find a Eulerian cycle/tour and therefore not possible to order FDs."
            )

        if len(uneven_vertices) == 2:
            # Check requirements for Eulerian tour
            tour_start_v: int | None = next(
                (i for i in uneven_vertices if out_degrees[i] == in_degrees[i] + 1),
                None,
            )
            tour_end_v: int | None = next(
                (i for i in uneven_vertices if in_degrees[i] == out_degrees[i] + 1),
                None,
            )
            if tour_start_v != start_v or tour_end_v is None:
                # NOTE: latent NameError on this error path: `ordered_fds` is undefined
                # here (the local is `sub_order`), and the message text is wrong (it
                # is an Eulerian-tour failure, not an FD-count mismatch). Not fixed.
                logger.error(
                    f"Ordered FDs have length {sum([len(order) for order in ordered_fds])} while there are {len(self._set_of_fds)} FDs."  # noqa: F821
                )
                raise RuntimeError(
                    "Not possible to find a Eulerian tour and therefore not possible to order FDs."
                )
            # Add artificial edge from end to start, in order to compute Eulerian cycle
            sub_g.add_edge(tour_end_v, tour_start_v)
            out_degrees[tour_end_v] += 1
            in_degrees[tour_start_v] += 1

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
            fd_index: int | None = sub_g.es.find(_source=lhs_v, _target=rhs_v)[
                "fd_index"
            ]
            # Skip artificial edge
            if fd_index is not None:
                # Add order to FD and append to sub-order
                self._set_of_fds[fd_index].order = order_counter
                sub_order.append(self._set_of_fds[fd_index])
                order_counter += 1
            c += 1
            lhs_v = rhs_v

        return sub_order

    def _get_topological_sorting(
        self, g: Graph, order_counter: int
    ) -> list[FunctionalDependency]:
        """Topologically order the FDs of one SCC-graph component (paper §4.2, §5.1).

        Runs Kahn's BFS-based topological sort; in-degree-0 vertices seed the bound
        (and source) attribute sets per §4.2, and multi-vertex SCCs are expanded via
        :meth:`_order_subg`.

        Args:
            g: One weakly-connected component of the SCC graph.
            order_counter: First order value to assign in this component.

        Returns:
            The component's FDs in traversal order.
        """
        ordered_fds: list[FunctionalDependency] = []

        # Start with vertices of graph with in-degree 0
        v_queue: list[ig.Vertex] = [v for v in g.vs.select(_indegree_eq=0)]

        # Bound attributes = vertices with in-degree 0
        # If vertex is a SCC, pick the first (arbitrary order)
        # Source attributes (never appear as an FD RHS) = vertices with in-degree 0
        # Ignore SCCs for source attributes (stricter)
        self._set_of_fds.bound_attributes.update([v["name"][0] for v in v_queue])
        self._set_of_fds.source_attributes.update(
            [v["name"][0] for v in v_queue if len(v["name"]) < 2]
        )
        logger.info(
            f"Identified {len(self._set_of_fds.bound_attributes)} bound attributes: {self._set_of_fds.bound_attributes}"
        )

        while v_queue:
            v: ig.Vertex = v_queue.pop(0)

            # If scc contains more than 1 vertex
            if len(v["name"]) > 1:
                # Compute order of this scc via Eulerian tour of subgraph
                sub_g = self._fd_g.induced_subgraph(
                    self._fd_g.vs.select(name_in=v["name"]),
                    implementation="create_from_scratch",
                )
                # Start with last seen vertex, if possible
                start_index: int = (
                    sub_g.vs.find(name=ordered_fds[-1].rhs).index
                    if len(ordered_fds) > 0
                    and len(sub_g.vs.select(name=ordered_fds[-1].rhs)) == 1
                    else 0
                )
                sub_order: list[FunctionalDependency] = self._order_subg(
                    sub_g, start_index, order_counter
                )
                ordered_fds += sub_order
                order_counter += len(sub_order)

            # Iterate over neighbors
            for w in g.neighbors(v, mode="out"):
                # Add edge information to ordering and delete it
                edge: ig.Edge = g.es.find(_source=v, _target=w)
                for fd_index in edge["fd_index"]:
                    # Skip edges which represent multiple LHS attributes
                    if fd_index is None:
                        continue
                    # Add order to FD and append to FD order
                    self._set_of_fds[fd_index].order = order_counter
                    ordered_fds.append(self._set_of_fds[fd_index])
                    order_counter += 1
                g.delete_edges(edge)
                # If neighboring vertex now has in-degree 0, add it to vertices queue
                if g.indegree(w) == 0:
                    v_queue.append(g.vs[w])

        return ordered_fds

    def order_fds(self) -> list[FunctionalDependency]:
        """Compute the full FD traversal order across all components (paper §5.1).

        Returns:
            All FDs in the order the repair should apply them.

        Raises:
            ValueError: If the produced order does not cover every FD.
        """
        # Perform topological sorting of each sub-component of SCCG
        ordered_fds: list[FunctionalDependency] = []

        order_counter: int = 0
        for sub_g in self._scc_g.decompose(mode="weak"):
            ordered_fds.extend(self._get_topological_sorting(sub_g, order_counter))
            order_counter += 1

        if len(ordered_fds) != len(self._set_of_fds):
            logger.error(
                f"Ordered FDs have length {len(ordered_fds)} while there are {len(self._set_of_fds)} FDs."
            )
            raise ValueError(
                f"Ordered FDs have length {len(ordered_fds)} while there are {len(self._set_of_fds)} FDs."
            )

        return ordered_fds

    def dfs_tree(self, start_attribute: str) -> list[int]:
        """Return the FD indices of the tree edges of a DFS from one attribute.

        Used to distinguish non-cyclic (tree) FDs from back-edges (§3.3 quality).

        Args:
            start_attribute: Attribute name to root the DFS at.

        Returns:
            The ``fd_index`` of each edge visited as a DFS tree edge.
        """
        start_v: int = self._fd_g.vs.find(name=start_attribute).index
        stack: deque[int] = deque([start_v])
        visited_v: set[int] = set([start_v])
        dfs_edges: list[int] = []
        while stack:
            v: int = stack.pop()
            for w in self._fd_g.neighbors(v, mode="out"):
                if w in visited_v:
                    continue
                visited_v.add(w)
                stack.append(w)
                dfs_edges.append(self._fd_g.es.find(_source=v, _target=w)["fd_index"])
        return dfs_edges

    def plot_graphs(self, dataset_name: str, output_dir: Path) -> None:
        """Save PNG visualizations of the FD graph, components and SCC graph.

        Args:
            dataset_name: Name used to prefix output filenames.
            output_dir: Directory the PNGs are written to.

        Returns:
            None.
        """
        # Visualize FD graph
        logger.debug("Saving FD graph visualization")
        g_v_count: int = self._fd_g.vcount()
        plt.figure(figsize=(max(7, g_v_count / 2), max(7, g_v_count / 2)))

        ig.plot(
            self._fd_g,
            layout="tree",
            vertex_color="green",
            vertex_label=self._fd_g.vs["name"],
            vertex_label_dist=1.5,
            edge_label=[
                self._set_of_fds[fd_index].order if fd_index is not None else None
                for fd_index in self._fd_g.es["fd_index"]
            ],
        )

        plt.gca().invert_yaxis()  # Plot tree with root at top
        plt.savefig(str(output_dir / f"{dataset_name}_fd_graph.png"))
        plt.clf()
        plt.close()

        # Visualize components
        logger.debug("Saving component visualization")
        plt.figure(figsize=(max(7, g_v_count / 2), max(7, g_v_count / 2)))

        ig.plot(
            self._components,
            layout="tree",
            palette=ig.RainbowPalette(),
            vertex_label=self._fd_g.vs["name"],
            vertex_label_dist=1.5,
        )

        plt.gca().invert_yaxis()  # Plot tree with root at top
        plt.savefig(str(output_dir / f"{dataset_name}_fd_graph_components.png"))
        plt.clf()
        plt.close()

        # Visualize SCCG
        logger.debug("Saving SCC graph visualization")
        plt.figure(
            figsize=(max(7, self._scc_g.vcount() / 2), max(7, self._scc_g.vcount() / 2))
        )

        ig.plot(
            self._scc_g,
            layout="tree",
            vertex_color="green",
            vertex_label=self._scc_g.vs["name"],
            vertex_label_dist=1.5,
            edge_label=[
                [
                    self._set_of_fds[fd_index].order if fd_index is not None else None
                    for fd_index in fd_indices
                ]
                for fd_indices in self._scc_g.es["fd_index"]
            ],
        )

        plt.gca().invert_yaxis()  # Plot tree with root at top
        plt.savefig(str(output_dir / f"{dataset_name}_scc_fd_graph.png"))
        plt.clf()
        plt.close()

    def graph_data(self) -> dict:
        """Return a JSON-serialisable description of the FD graph, SCCs and order.

        Bundles the FD graph nodes/edges, the SCC membership and the SCC-graph
        ordering so the UI can render the graphs independently of the PNG export.

        Returns:
            Dict with keys ``"nodes"``, ``"edges"``, ``"sccs"`` and ``"scc_order"``.
        """
        g: Graph = self._fd_g
        comps: ig.VertexClustering = self._components
        scc_g: Graph = self._scc_g

        nodes: list[dict] = [
            {
                "id": v.index,
                "label": ", ".join(v["name"])
                if isinstance(v["name"], tuple)
                else v["name"],
            }
            for v in g.vs
        ]
        edges: list[dict] = [
            {
                "source": e.source,
                "target": e.target,
                "order": self._set_of_fds[e["fd_index"]].order
                if e["fd_index"] is not None
                else None,
            }
            for e in g.es
        ]
        sccs: list[list] = [list(members) for members in comps]
        scc_nodes: list[dict] = [
            {
                "members": [g.vs.find(name=attribute).index for attribute in v["name"]],
                "label": ", ".join([str(name) for name in v["name"]]),
            }
            for v in scc_g.vs
        ]
        scc_edges: list[dict] = [
            {
                "source": e.source,
                "target": e.target,
                "order": ", ".join(
                    [
                        str(self._set_of_fds[fd_index].order)
                        for fd_index in e["fd_index"]
                        if fd_index is not None
                    ]
                ),
            }
            for e in scc_g.es
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "sccs": sccs,
            "scc_order": {"nodes": scc_nodes, "edges": scc_edges},
        }


def get_ordered_fds(
    set_of_fds: SetOfFDs,
    dataset_name: str = "",
    output_dir: Path = Path("output"),
    enable_plotting: bool = True,
) -> tuple[list[FunctionalDependency], float]:
    """Compute the FD traversal order and mark cyclic FDs (paper §4.2, §5.1).

    Builds the FD graph, orders the FDs via SCC topological sorting, and flags each
    FD as cyclic or not (used later to treat back-edges as support-only in §3.3).
    Optionally saves graph visualizations and structured graph JSON.

    Args:
        set_of_fds: Functional dependencies to order.
        dataset_name: Name used to prefix any saved output.
        output_dir: Directory plots and graph JSON are written to.
        enable_plotting: If True, save graph visualizations and JSON.

    Returns:
        Tuple of (FDs in traversal order, elapsed ordering time in seconds).
    """
    logger.info("Computing ordered FDs for pipeline execution")

    start: float = time.time()

    # Build FD graph and SCCG
    fd_graph: FDGraph = FDGraph(set_of_fds)

    # Perform topological sorting on SCCG and get order of functional dependencies
    logger.info("Performing topological sorting...")
    ordered_fds: list[FunctionalDependency] = fd_graph.order_fds()

    logger.info(f"Computed traversal order: {ordered_fds}")

    # Mark cyclic FDs (used later to skip back-edges in FD pattern graph quality computation)
    non_cyclic_fds: set = set(
        [
            fd_index
            for v in set_of_fds.bound_attributes
            for fd_index in fd_graph.dfs_tree(v)
        ]
    )
    for i in range(len(set_of_fds)):
        set_of_fds[i].cyclic = False if i in non_cyclic_fds else True

    logger.debug([f"{str(fd)}: {fd.cyclic}" for fd in set_of_fds])

    end: float = time.time()
    elapsed_time: float = end - start
    logger.info(f"Completed ordering FDs in {elapsed_time:.2f}s")

    # If plotting is enabled, save graph visualizations under output directory
    if enable_plotting:
        fd_graph.plot_graphs(dataset_name, output_dir)

        # save structured graph data for the UI to render itself (independent of the
        # PNG export and of FD ordering — best effort, never fatal)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            graph_json = output_dir / f"{dataset_name}_graph.json"
            graph_json.write_text(
                json.dumps(fd_graph.graph_data(), indent=2), encoding="utf-8"
            )
            logger.debug(f"Saved graph data to {graph_json}")
        except Exception as e:
            logger.warning(f"Could not export graph data: {e}")

    return ordered_fds, elapsed_time
