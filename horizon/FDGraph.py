"""
FDGraph: Build a NetworkX graph from CSV data with Functional Dependency edges.

Each unique (column, value) pair becomes a node. This means:
- Same values in the same column share the same node
- Same values in different columns have different nodes
- Edges represent functional dependencies between column-value pairs
"""

from collections import Counter
from pathlib import Path
from platform import node
from typing import Optional
import sys

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from utils.logging_config import get_logger

logger = get_logger(__name__)

output_dir: Path = Path("output")
enable_plotting: bool = True

lhs_column_name: str = "LHS"
rhs_column_name: str = "RHS"


class FDGraph:
    """
    A graph representation of CSV data with functional dependency edges.

    Nodes represent unique (column, value) pairs. Multiple cells with the
    same value in the same column will reference the same node.
    """

    def __init__(self, data_path: str, fd_path: str):
        """
        Initialize the FDGraph.

        Args:
            data_path: Path to the CSV file containing the data
            fd_path: Path to the CSV file containing functional dependencies
                     (must have 'from' and 'to' columns with column names)
        """
        logger.info(f"Initializing FDGraph with data: {data_path}, FDs: {fd_path}")
        self.data_path = data_path
        self.fd_path = fd_path

        # Load data
        logger.debug(f"Loading data from {data_path}")
        self.df = pd.read_csv(data_path)
        self.columns = list(self.df.columns)
        logger.info(f"Loaded data: {len(self.df)} rows, {len(self.columns)} columns")

        # Load functional dependencies
        logger.debug(f"Loading FDs from {fd_path}")
        self.fd_df = pd.read_csv(fd_path)
        logger.info(f"Loaded {len(self.fd_df)} functional dependencies")

        # Build the graph
        logger.info("Building FDGraph...")
        self.graph = self._build_graph()

        # Calculate edge qualities
        logger.info("Calculating edge qualities...")
        self.calculate_edge_qualities()
        logger.info(f"FDGraph initialization completed. Graph has {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges")

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

    def _build_graph(self) -> nx.DiGraph:
        """
        Build the graph with nodes for unique (column, value) pairs
        and edges based on functional dependencies.

        Returns:
            NetworkX DiGraph with column-value nodes and FD-based edges
        """
        logger.debug("Starting graph construction")
        G = nx.DiGraph()

        # Get columns that appear in the functional dependencies
        fd_columns = set()
        for _, fd in self.fd_df.iterrows():
            fd_columns.add(fd[lhs_column_name])
            fd_columns.add(fd[rhs_column_name])

        # Add nodes for unique (column, value) pairs
        # Using a set to avoid duplicate nodes
        seen_nodes = Counter()
        for row_idx in self.df.index:
            for col_name in self.columns:
                # Only add nodes for columns that appear in the FDs
                if col_name not in fd_columns:
                    continue
                value = self.df.loc[row_idx, col_name]
                node_id = self._cell_node_id(col_name, value)

                # Add node only once per unique (column, value) pair
                if node_id not in seen_nodes:
                    G.add_node(node_id, column=col_name, value=value)
                seen_nodes[node_id] += 1

        # Add edges based on functional dependencies
        # For each FD and each row, connect the corresponding nodes
        fd_counter = Counter()

        for _, fd in self.fd_df.iterrows():
            from_col = fd[lhs_column_name]
            to_col = fd[rhs_column_name]

            # Validate columns exist
            if from_col not in self.columns or to_col not in self.columns:
                continue

            # For each row, create an edge from the 'from' node to the 'to' node
            for row_idx in self.df.index:
                from_value = self.df.loc[row_idx, from_col]
                to_value = self.df.loc[row_idx, to_col]

                from_node = self._cell_node_id(from_col, from_value)
                to_node = self._cell_node_id(to_col, to_value)

                # Add edge if both nodes exist
                if from_node in G.nodes and to_node in G.nodes:
                    if G.has_edge(from_node, to_node):
                        G[from_node][to_node]["support"] += 1
                    else:
                        G.add_edge(
                            from_node,
                            to_node,
                            fd_from=from_col,
                            fd_to=to_col,
                            support=1,
                        )
                    fd_counter[(from_col, to_col)] += 1

        # adjusting support measure to match function in paper
        for from_node, to_node, edge_data in G.edges(data=True):
            initial_sup = edge_data["support"]
            G[from_node][to_node]["support"] = (
                initial_sup / fd_counter[(edge_data["fd_from"], edge_data["fd_to"])]
            )

        if enable_plotting:
            logger.debug("Saving FD pattern graph visualization")
            nx.draw(G, with_labels=True, pos=nx.circular_layout(G))
            plt.savefig(str(output_dir / "fd_pattern_graph.png"))
            plt.clf()

        logger.debug(f"Graph construction completed: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G

    def calculate_edge_qualities(self):
        """
        Calculate quality for each edge in the graph and store as edge attributes.

        Quality = (support of edge + sum of supports of reachable edges) / total edges visited in DFS

        The quality is stored as a 'quality' attribute on each edge.
        """
        for from_node, to_node, edge_data in self.graph.edges(data=True):
            # Start DFS from the target node of this edge
            visited_edges = set()
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
                quality = (first_edge_support + total_support_sum) / (edges_visited + 1)
            else:
                quality = (
                    first_edge_support  # If no other edges reachable, quality = support
                )

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
        return self.df.loc[row_idx, col_name]

    def get_node_id(self, row_idx: int, col_name: str) -> str:
        """Get the node ID for a (column, value) pair at the given row and column."""
        value = self.df.loc[row_idx, col_name]
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



# example usage
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python FDGraph.py <dataset_folder>")
        print("  dataset_folder: Path to folder containing clean.csv, dirty.csv, and fds.csv")
        sys.exit(1)
    
    dataset_folder = Path(sys.argv[1])
    
    if not dataset_folder.exists():
        print(f"Error: Dataset folder '{dataset_folder}' does not exist")
        sys.exit(1)
    
    # Construct paths to the datasets
    clean_path = dataset_folder / "clean.csv"
    dirty_path = dataset_folder / "dirty.csv"
    fds_path = dataset_folder / "fds.csv"
    
    # Check that all required files exist
    for file_path, name in [(clean_path, "clean.csv"), (dirty_path, "dirty.csv"), (fds_path, "fds.csv")]:
        if not file_path.exists():
            print(f"Error: Required file '{name}' not found in '{dataset_folder}'")
            sys.exit(1)
    
    print(f"Loading dataset from: {dataset_folder}")
    print(f"  Data: {clean_path}")
    print(f"  FDs: {fds_path}")
    print()
    
    # Create FDGraph for dirty data
    print("Creating FDGraph for dirty data...")
    fd_graph_dirty = FDGraph(str(dirty_path), str(fds_path))
    print(f"  Nodes: {fd_graph_dirty.graph.number_of_nodes()}")
    print(f"  Edges: {fd_graph_dirty.graph.number_of_edges()}")
    print()
    