"""
FDPatternGraph: Build a NetworkX graph from CSV data with Functional Dependency edges.

Each unique (column, value) pair becomes a node. This means:
- Same values in the same column share the same node
- Same values in different columns have different nodes
- Edges represent functional dependencies between column-value pairs
"""

import time
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs
from utils.loaders import iter_table_batches
from utils.logging_config import get_logger

logger = get_logger(__name__)


class FDPatternGraph:
    """
    A graph representation of CSV data with functional dependency edges.

    Nodes represent unique (column, value) pairs. Multiple cells with the
    same value in the same column will reference the same node.
    """

    # Class variable
    graph: nx.DiGraph
    _repair_table: list[dict[str, str]]

    def __init__(
        self,
        data_path: Path,
        set_of_fds: SetOfFDs,
        dataset_name: str = "",
        pruning: bool = True,
        output_dir: Path = Path("output"),
        enable_plotting: bool = False,
    ) -> None:
        """
        Initialize the FDPatternGraph.

        Args:
            data_path: Path to the CSV file containing the data
            set_of_fds: Parsed set of functional dependencies
        """
        logger.info(
            f"Initializing FDPatternGraph with data: {str(data_path)}, FDs: {str(set_of_fds)}"
        )

        # Load data
        logger.debug(f"Loading data from {str(data_path)}")

        # Initialize repair table
        self._repair_table = [dict() for fd in set_of_fds]

        start: float = time.time()

        # Build the graph and compute qualities on the fly
        logger.info("Building FDPatternGraph...")
        self.graph = self._build_graph(data_path, set_of_fds)

        # Pruning is always true, deactivate only for debugging
        if pruning:
            logger.info("Pruning edges of FDPatternGraph...")
            # Prune unused edges
            self._prune_edges()

        end: float = time.time()
        self._build_time: float = end - start
        logger.info(
            f"FDPatternGraph initialization completed in {self._build_time:.2f}s. Graph has {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges"
        )

        if enable_plotting:
            logger.debug("Saving FD pattern graph visualization")
            # Only plot subgraph with 3 values for each attribute
            sub_g_nodes: list[int] = [
                node
                for col_name in set_of_fds.unique_attributes
                for node in [
                    n
                    for n in self.graph.nodes()
                    if self._parse_node_id(n)[0] == col_name
                ][:3]
            ]
            sub_g: nx.Graph = self.graph.subgraph(sub_g_nodes)
            nx.draw(sub_g, with_labels=True, pos=nx.circular_layout(sub_g))
            nx.draw_networkx_edge_labels(
                sub_g,
                pos=nx.circular_layout(sub_g),
                edge_labels=nx.get_edge_attributes(sub_g, "quality"),
            )
            plt.savefig(str(output_dir / f"{dataset_name}_fd_pattern_graph.png"))
            plt.clf()

    @property
    def repair_table(self) -> list[dict[str, str]]:
        return self._repair_table

    @property
    def number_of_nodes(self) -> int:
        return self.graph.number_of_nodes()

    @property
    def number_of_edges(self) -> int:
        return self.graph.number_of_edges()

    def _cell_node_id(self, col_name: str, value) -> str:
        """
        Generate a unique node ID for a (column, value) pair.

        Format: "{col_name}__{value}" - e.g., "brewery-name__Guinness"
        Same value in the same column always produces the same node ID.
        Different columns get different nodes even for the same value.
        """
        return f"{col_name}__{value}"

    def _parse_node_id(self, node_id: str) -> tuple[str, str]:
        """
        Parse a node ID back to (col_name, value).

        Args:
            node_id: Node identifier like "brewery-name_Guinness"

        Returns:
            Tuple of (column_name, value)
        """
        col_name, _, value = node_id.partition("__")
        return col_name, value

    def _build_graph(self, data_path: Path, set_of_fds: SetOfFDs) -> nx.DiGraph:
        """
        Build the graph with nodes for unique (column, value) pairs
        and edges based on functional dependencies.
        Calculate quality for each edge in the graph and store as edge attributes.

        Returns:
            NetworkX DiGraph with column-value nodes and FD-based edges
        """
        logger.debug("Starting graph construction")
        G: nx.DiGraph = nx.DiGraph()

        # Get reverse ordered set of FDs for bottom-up addition of edges
        # TODO: Support multiple attributes on LHS
        ordered_set_of_fds: list[tuple[int, FunctionalDependency]] = [
            (fd.index, fd)
            for fd in set_of_fds.get_ordered_set_of_fds()
            if not isinstance(fd.lhs, tuple)
        ]
        ordered_set_of_fds.reverse()

        # Phase 1: one bounded streaming pass over the input to accumulate, per FD,
        # the count of each distinct (LHS, RHS) pair (the pattern support). Blocks
        # are read with memory bounded by block size (iter_table_batches); each
        # block's per-FD group-by counts are folded into a running dict. This
        # replaces a per-FD group_by over the whole frame, which materialised ~the
        # input file. maintain_order=True on the per-block group-by plus insertion
        # into an order-preserving dict keeps global first-occurrence (row) order:
        # blocks arrive in file order, so a pair's dict position is fixed at its
        # first appearance anywhere. That order is load-bearing --- choose_best_next
        # _edge breaks quality ties by first-inserted edge (see
        # project_fd_graph_tiebreak_order).
        pair_counts: dict[FunctionalDependency, dict[tuple, int]] = {
            fd: {} for _, fd in ordered_set_of_fds
        }
        n_tuples: int = 0
        # Read only the FD columns (projection pushed into the reader).
        for block in iter_table_batches(
            data_path, columns=list(set_of_fds.unique_attributes)
        ):
            n_tuples += block.height
            for fd, counts in pair_counts.items():
                for lval, rval, count in (
                    block.group_by(fd.lhs, fd.rhs, maintain_order=True)
                    .len()
                    .iter_rows()
                ):
                    key: tuple = (lval, rval)
                    counts[key] = counts.get(key, 0) + count

        # Phase 2: add nodes and edges for each FD (in reverse order) from the
        # accumulated counts, computing edge quality on the fly.
        for fd_index, fd in ordered_set_of_fds:
            counts: dict[tuple, int] = pair_counts[fd]
            fd_repairs: dict[str, str] = self._repair_table[fd_index]

            # Get total LHS count: a real violation (same LHS -> two RHS) is two pairs of
            # count 1 whose LHS total is 2, and must be kept
            lhs_totals: dict = {}
            for (lval, _rval), count in counts.items():
                lhs_totals[lval] = lhs_totals.get(lval, 0) + count

            # Check singleton FD patterns (count == 1 and LHS total < 2) during loop,
            # then directly insert into the repair table and mark for deletion

            # Compute quality for each FD edge (non back-edges)
            for (lval, rval), count in counts.items():
                # If pattern appears only once, insert directly into repair table
                singleton_pattern: bool = count == 1 and lhs_totals[lval] < 2
                if singleton_pattern:
                    fd_repairs[lval] = rval
                    # Skip edge creation for source attributes (never appears as a RHS)
                    # Dropping this edge changes no other edge's quality
                    if fd.lhs in set_of_fds.source_attributes:
                        continue

                # If FD is cyclic, all its edges are back-edges, therefore skip quality computation
                if fd.cyclic:
                    # Back-edges currently have support-only quality
                    G.add_edge(
                        self._cell_node_id(fd.lhs, lval),
                        self._cell_node_id(fd.rhs, rval),
                        support=count / n_tuples,
                        quality=count / n_tuples,
                        back_edge=fd.cyclic,
                        sum_support=0,
                        n_reachable=0,
                        mark_delete=singleton_pattern,
                    )
                    # Nodes are added automatically
                    continue

                # Add nodes to the graph, to compute quality
                from_node = self._cell_node_id(fd.lhs, lval)
                to_node = self._cell_node_id(fd.rhs, rval)
                G.add_nodes_from([from_node, to_node])

                support: float = count / n_tuples

                # Sum over direct neighbor's summed support to get reachable support
                reachable_support: int = sum(
                    [
                        G[to_node][direct_neighbor]["sum_support"]
                        for direct_neighbor in G.successors(to_node)
                        if not G[to_node][direct_neighbor]["back_edge"]
                    ]
                )
                # Store support sum and number of reachable FDs for each edge
                sum_support: float = support + reachable_support
                n_reachable: int = sum(
                    [
                        G[to_node][direct_neighbor]["n_reachable"] + 1
                        for direct_neighbor in G.successors(to_node)
                        if not G[to_node][direct_neighbor]["back_edge"]
                    ]
                )

                # Add edge and calculate quality via sum_support / (n_reachable + 1)
                G.add_edge(
                    from_node,
                    to_node,
                    support=support,
                    quality=sum_support / (n_reachable + 1),
                    back_edge=fd.cyclic,
                    sum_support=sum_support,
                    n_reachable=n_reachable,
                    mark_delete=singleton_pattern,
                )

        # TODO: Compute quality for back-edges (currently added with support-only quality)

        logger.debug(
            f"Initial graph construction completed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
        )

        return G

    def _prune_edges(self) -> None:
        # quality is now final; the repair only ever reads `quality` (see
        # choose_best_next_edge / get_edge_quality). Drop the per-edge scratch
        # attributes (support, back_edge, order, sum_support, n_reachable), keeping
        # only quality, so they aren't held on every edge for the whole repair.
        edges_to_remove: list[tuple] = []
        for u, v, edge_data in self.graph.edges(data=True):
            # Delete all marked edges
            if edge_data["mark_delete"]:
                edges_to_remove.append((u, v))
                continue
            quality: float = edge_data["quality"]
            # clear() + reassign actually shrinks the dict; pop() alone would not.
            edge_data.clear()
            edge_data["quality"] = quality

        # Prune all marked edges (already have an entry in the repair table)
        self.graph.remove_edges_from(edges_to_remove)

        logger.debug(
            f"Pruned {len(edges_to_remove)} edges. Graph now has {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges"
        )

    def get_edge_quality(self, from_node: str, to_node: str) -> float:
        """
        Get the quality of a specific edge.

        Args:
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            Quality score for the edge
        """
        if not self.graph.has_edge(from_node, to_node):
            raise ValueError(f"Edge from {from_node} to {to_node} does not exist")

        return self.graph[from_node][to_node]["quality"]

    def get_node_info(self, node_id: str) -> dict:
        """Get all stored information about a node."""
        col_name, value = self._parse_node_id(node_id)
        return {"column": col_name, "value": value}

    def has_node(self, col_name: str, value: str) -> bool:
        """True if a (column, value) node exists in the graph."""
        return self.graph.has_node(self._cell_node_id(col_name, value))

    def choose_best_next_edge(self, lhs: str, lval: str, rhs: str) -> tuple[str, str]:
        """Choose best next edge given a LHS attribute and value, returns RHS attribute and value with the highest quality."""
        logger.debug(f"Choosing best edge: {lhs}({lval}) -> {rhs}")
        current_node: str = self._cell_node_id(lhs, lval)

        successors: list[str] = [
            successor
            for successor in self.graph.successors(current_node)
            if self._parse_node_id(successor)[0] == rhs
        ]

        best_edge: str | None = None
        best_quality = -1

        for next_node in successors:
            quality = self.graph[current_node][next_node]["quality"]
            if quality > best_quality:
                best_quality = quality
                best_edge = next_node

        if best_edge is None:
            # No valid edge found for this FD
            logger.error(f"No valid edge found from {current_node} to {rhs}")
            raise RuntimeError(f"No valid edge found from {current_node} to {rhs}.\n")

        result = self._parse_node_id(best_edge)
        logger.debug(f"Selected edge with quality {best_quality:.4f}: {result}")
        return result

    def clear(self) -> None:
        """Clears the FD Pattern graph."""
        self.graph.clear()
