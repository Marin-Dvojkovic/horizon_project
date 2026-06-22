"""
FDPatternGraph: Build a NetworkX graph from CSV data with Functional Dependency edges.

Each unique (column, value) pair becomes a node. This means:
- Same values in the same column share the same node
- Same values in different columns have different nodes
- Edges represent functional dependencies between column-value pairs
"""

import time
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import polars as pl
import utils.loaders
from fds.set_of_fds import SetOfFDs
from utils.logging_config import get_logger

logger = get_logger(__name__)

output_dir: Path = Path("output")
enable_plotting: bool = False


class FDPatternGraph:
    """
    A graph representation of CSV data with functional dependency edges.

    Nodes represent unique (column, value) pairs. Multiple cells with the
    same value in the same column will reference the same node.
    """

    # Class variable
    graph: nx.DiGraph

    def __init__(self, data_path: str, set_of_fds: SetOfFDs):
        """
        Initialize the FDPatternGraph.

        Args:
            data_path: Path to the CSV file containing the data
            set_of_fds: Parsed set of functional dependencies
        """
        logger.info(
            f"Initializing FDPatternGraph with data: {data_path}, FDs: {str(set_of_fds)}"
        )

        # Load data
        logger.debug(f"Loading data from {data_path}")

        fd_columns: set[str] = set_of_fds.unique_attributes
        data: pl.DataFrame = utils.loaders.load_table(data_path, list(fd_columns))
        logger.info(f"Loaded data: {len(data)} rows, {len(fd_columns)} columns")

        start: float = time.time()

        # Build the graph
        logger.info("Building FDPatternGraph...")
        self.graph = self._build_graph(data, set_of_fds)

        # Calculate edge qualities
        logger.info("Calculating edge qualities...")
        self.calculate_edge_qualities()

        if enable_plotting:
            logger.debug("Saving FD pattern graph visualization")
            # Only plot subgraph with 3 values for each attribute
            sub_g_nodes: list[int] = [
                node
                for col_name in fd_columns
                for node in [
                    n
                    for n, data in self.graph.nodes(data=True)
                    if data["column"] == col_name
                ][:3]
            ]
            sub_g: nx.Graph = self.graph.subgraph(sub_g_nodes)
            nx.draw(sub_g, with_labels=True, pos=nx.circular_layout(sub_g))
            nx.draw_networkx_edge_labels(
                sub_g,
                pos=nx.circular_layout(sub_g),
                edge_labels=nx.get_edge_attributes(sub_g, "quality"),
            )
            plt.savefig(str(output_dir / "fd_pattern_graph.png"))
            plt.clf()

        end: float = time.time()
        logger.info(
            f"FDPatternGraph initialization completed in {(end - start):.2f}s. Graph has {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges"
        )

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

    def _get_unique_values(self, df: pl.DataFrame, col_name: str) -> list[str]:
        """Returns all unique values in the given column of the data frame as a list."""
        return (
            df.select(col_name)
            .unique(maintain_order=True)
            .to_dict(as_series=False)[col_name]
        )

    def _build_graph(self, data: pl.DataFrame, set_of_fds: SetOfFDs) -> nx.DiGraph:
        """
        Build the graph with nodes for unique (column, value) pairs
        and edges based on functional dependencies.

        Returns:
            NetworkX DiGraph with column-value nodes and FD-based edges
        """
        logger.debug("Starting graph construction")
        G: nx.DiGraph = nx.DiGraph()

        # Add nodes for each unique value
        G.add_nodes_from(
            (self._cell_node_id(col_name, value), {"column": col_name, "value": value})
            for col_name in data.columns
            for value in self._get_unique_values(data, col_name)
        )

        # Create edge list for each FD and each row (including duplicates)
        number_of_tuples: int = len(data)
        edges_list: list[tuple] = [
            (
                self._cell_node_id(str(fd.lhs), data[row_idx, fd.lhs]),
                self._cell_node_id(fd.rhs, data[row_idx, fd.rhs]),
                fd.cyclic,
                fd.order,
            )
            for fd in set_of_fds
            if not isinstance(fd.lhs, tuple)  # TODO: Support multiple attributes on LHS
            for row_idx in range(number_of_tuples)
        ]

        # Add unique edges to graph and calculate support with counter
        # Add back-edge and order properties
        G.add_edges_from(
            [
                (
                    edge_tuple[0],
                    edge_tuple[1],
                    {
                        "support": support / number_of_tuples,
                        "quality": support / number_of_tuples,
                        "back_edge": edge_tuple[2],
                        "order": edge_tuple[3],
                        "sum_support": 0,
                        "n_reachable": 0,
                    },
                )
                for edge_tuple, support in Counter(edges_list).items()
            ],
        )

        logger.debug(
            f"Graph construction completed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
        )
        return G

    def calculate_edge_qualities(self):
        """
        Calculate quality for each edge in the graph and store as edge attributes.

        Quality = (support of edge + sum of supports of reachable edges) / total edges visited in DFS

        The quality is stored as a 'quality' attribute on each edge.
        """
        # Sort edges in reverse order: From bottom to top
        sorted_edges: list = sorted(
            self.graph.edges(data=True), key=lambda edge: edge[2]["order"]
        )
        sorted_edges.reverse()

        # Iterate over all edges and compute quality
        skipped_edges: list = []
        for from_node, to_node, edge_data in sorted_edges:
            # Skip back-edges
            if edge_data["back_edge"]:
                skipped_edges.append((from_node, to_node, edge_data))
                continue
            # Sum over direct neighbors summed support to get reachable support
            reachable_support: int = sum(
                [
                    self.graph[to_node][direct_neighbor]["sum_support"]
                    for direct_neighbor in self.graph.successors(to_node)
                    if not self.graph[to_node][direct_neighbor]["back_edge"]
                ]
            )
            self.graph[from_node][to_node]["sum_support"] = (
                edge_data["support"] + reachable_support
            )
            self.graph[from_node][to_node]["n_reachable"] = sum(
                [
                    self.graph[to_node][direct_neighbor]["n_reachable"] + 1
                    for direct_neighbor in self.graph.successors(to_node)
                    if not self.graph[to_node][direct_neighbor]["back_edge"]
                ]
            )
            self.graph[from_node][to_node]["quality"] = edge_data["sum_support"] / (
                edge_data["n_reachable"] + 1
            )

        for from_node, to_node, edge_data in skipped_edges:
            # TODO: Compute quality for back-edges
            return

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
        return self.graph.nodes[node_id]

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
