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

    def __init__(self, data_path: str, set_of_fds: SetOfFDs):
        """
        Initialize the FDPatternGraph.

        Args:
            data_path: Path to the CSV file containing the data
            set_of_fds: Parsed set of functional dependencies
        """
        self._set_of_fds = SetOfFDs(
            [fd for fd in set_of_fds if not isinstance(fd.lhs, tuple)],
            set_of_fds.bound_attributes,
        )  # TODO: Support multiple attributes on LHS
        self._fd_columns = self._set_of_fds.unique_attributes

        logger.info(
            f"Initializing FDPatternGraph with data: {data_path}, FDs: {str(self._set_of_fds)}"
        )

        # Load data
        logger.debug(f"Loading data from {data_path}")
        self._data = utils.loaders.load_table(data_path, list(self._fd_columns))
        self._number_of_tuples = len(self._data)
        logger.info(
            f"Loaded data: {self._number_of_tuples} rows, {len(self._fd_columns)} columns"
        )

        start: float = time.time()

        # Build the graph
        logger.info("Building FDPatternGraph...")
        self.graph = self._build_graph()

        # Calculate edge qualities
        logger.info("Calculating edge qualities...")
        self.calculate_edge_qualities()

        if enable_plotting:
            logger.debug("Saving FD pattern graph visualization")
            nx.draw(self.graph, with_labels=True, pos=nx.circular_layout(self.graph))
            nx.draw_networkx_edge_labels(
                self.graph,
                pos=nx.circular_layout(self.graph),
                edge_labels=nx.get_edge_attributes(self.graph, "quality"),
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

    def get_unique_values(self, col_name: str) -> list[str]:
        return (
            self._data.select(col_name)
            .unique(maintain_order=True)
            .to_dict(as_series=False)[col_name]
        )

    def _build_graph(self) -> nx.DiGraph:
        """
        Build the graph with nodes for unique (column, value) pairs
        and edges based on functional dependencies.

        Returns:
            NetworkX DiGraph with column-value nodes and FD-based edges
        """
        logger.debug("Starting graph construction")
        G = nx.DiGraph()

        # Add nodes for each unique value
        G.add_nodes_from(
            (self._cell_node_id(col_name, value), {"column": col_name, "value": value})
            for col_name in self._fd_columns
            for value in self.get_unique_values(col_name)
        )

        # Create edge list for each FD and each row (including duplicates)
        edges_list: list[tuple] = [
            (
                self._cell_node_id(from_col, self._data[row_idx, from_col]),
                self._cell_node_id(to_col, self._data[row_idx, to_col]),
            )
            for from_col, to_col in self._set_of_fds.as_tuple_list()
            for row_idx in range(self._number_of_tuples)
        ]

        # Add unique edges to graph and calculate support with counter
        # Nodes are added automatically
        G.add_edges_from(
            [
                (
                    *edge_tuple,
                    {
                        "support": support / self._number_of_tuples,
                        "quality": support / self._number_of_tuples,
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
        for source in self._set_of_fds.bound_attributes:
            source_nodes = [
                (u, v, d)
                for u, v, d in self.graph.edges(data=True)
                if self.graph.nodes[u]["column"] == source
            ]
            visited_edges: set = set()
            for from_node, to_node, edge_data in source_nodes:
                # Start DFS from the target node of this edge
                total_support_sum = 0
                edges_visited = 0

                # DFS stack: (current_node, path_to_here)
                stack = [
                    (to_node, {(from_node, to_node)})
                ]  # Start from target node, mark this edge as visited

                while stack:
                    current_node, path = stack.pop()

                    # Explore all outgoing edges from current node
                    for neighbor in self.graph.successors(current_node):
                        edge = (current_node, neighbor)

                        if edge in visited_edges:
                            continue

                        if edge not in path:  # Avoid cycles
                            edge_support = self.graph[current_node][neighbor]["support"]
                            total_support_sum += edge_support
                            edges_visited += 1
                            visited_edges.add(edge)

                            # Continue DFS
                            new_path = path | {edge}
                            stack.append((neighbor, new_path))
                        else:
                            edge_support = self.graph[current_node][neighbor]["support"]
                            total_support_sum += edge_support
                            edges_visited += 1

                # Calculate quality for this edge
                first_edge_support = edge_data["support"]
                if edges_visited > 0:
                    # quality = (edge_support + total_support_sum) / (edges_visited + 1)
                    quality = (first_edge_support + total_support_sum) / (
                        edges_visited + 1
                    )
                else:
                    quality = first_edge_support  # If no other edges reachable, quality = support

                # Store quality as edge attribute
                self.graph[from_node][to_node]["quality"] = quality

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

    def get_cell_value(self, row_idx: int, col_name: str):
        """Get the value of a cell at the given row and column."""
        return self._data[row_idx, col_name]

    def get_node_id(self, row_idx: int, col_name: str) -> str:
        """Get the node ID for a (column, value) pair at the given row and column."""
        value = self._data[row_idx, col_name]
        return self._cell_node_id(col_name, value)

    def get_node_info(self, node_id: str) -> dict:
        """Get all stored information about a node."""
        return self.graph.nodes[node_id]

    def get_graph(self) -> nx.DiGraph:
        """Get full graph data type."""
        return self.graph

    def choose_best_next_edge(self, lhs: str, lval: str, rhs: str) -> tuple[str, str]:
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
