"""
FDGraph: Build a NetworkX graph from CSV data with Functional Dependency edges.

Each unique (column, value) pair becomes a node. This means:
- Same values in the same column share the same node
- Same values in different columns have different nodes
- Edges represent functional dependencies between column-value pairs
"""

import pandas as pd
import networkx as nx
from typing import Optional
import matplotlib.pyplot as plt
from collections import Counter


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
        self.data_path = data_path
        self.fd_path = fd_path
        
        # Load data
        self.df = pd.read_csv(data_path)
        self.columns = list(self.df.columns)
        
        # Load functional dependencies
        self.fd_df = pd.read_csv(fd_path)
        
        # Build the graph
        self.graph = self._build_graph()
        
        # Calculate edge qualities
        self.calculate_edge_qualities()
    
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
        col_name, _, value = node_id.partition('__')
        return col_name, value
    
    def _build_graph(self) -> nx.DiGraph:
        """
        Build the graph with nodes for unique (column, value) pairs 
        and edges based on functional dependencies.
        
        Returns:
            NetworkX DiGraph with column-value nodes and FD-based edges
        """
        G = nx.DiGraph()
        
        # Add nodes for unique (column, value) pairs
        # Using a set to avoid duplicate nodes
        seen_nodes = Counter()
        for row_idx in self.df.index:
            for col_name in self.columns:
                value = self.df.loc[row_idx, col_name]
                node_id = self._cell_node_id(col_name, value)
                
                # Add node only once per unique (column, value) pair
                if node_id not in seen_nodes:
                    G.add_node(
                        node_id,
                        column=col_name,
                        value=value
                    )
                seen_nodes[node_id] += 1
                    
        
        # Add edges based on functional dependencies
        # For each FD and each row, connect the corresponding nodes
        fd_counter = Counter()
        
        for _, fd in self.fd_df.iterrows():
            from_col = fd['from']
            to_col = fd['to']
            
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
                        G[from_node][to_node]['support'] += 1
                    else:
                        G.add_edge(from_node, to_node, fd_from=from_col, fd_to=to_col, support=1)
                    fd_counter[(from_col, to_col)] +=1
        
        # adjusting support measure to match function in paper
        for from_node, to_node, edge_data in G.edges(data=True):
            initial_sup = edge_data['support']
            G[from_node][to_node]['support'] = initial_sup / fd_counter[(edge_data["fd_from"], edge_data["fd_to"])]
        
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
            stack = [(to_node, {(from_node, to_node)})]  # Start from target node, mark this edge as visited
            
            while stack:
                current_node, path = stack.pop()
                
                # Explore all outgoing edges from current node
                for neighbor in self.graph.successors(current_node):
                    edge = (current_node, neighbor)
                    
                    if edge not in path:  # Avoid cycles
                        edge_support = self.graph[current_node][neighbor]['support']
                        total_support_sum += edge_support
                        edges_visited += 1
                        visited_edges.add(edge)
                        
                        # Continue DFS
                        new_path = path | {edge}
                        stack.append((neighbor, new_path))
                    else:
                        edge_support = self.graph[current_node][neighbor]['support']
                        total_support_sum += edge_support
                        edges_visited += 1
            
            # Calculate quality for this edge
            edge_support = edge_data['support']
            if edges_visited > 0:
                quality = (edge_support + total_support_sum) / (edges_visited + 1)
            else:
                quality = edge_support  # If no other edges reachable, quality = support
            
            # Store quality as edge attribute
            self.graph[from_node][to_node]['quality'] = quality
    
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
            
        return self.graph[from_node][to_node]['quality']
    
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
    
    def get_dependent_cells(self, row_idx: int, col_name: str) -> list[tuple[int, str]]:
        """
        Get all cells in the same row that depend on the given cell via functional dependencies.
        
        Args:
            row_idx: Row index
            col_name: Column name
            
        Returns:
            List of (row_idx, col_name) tuples for dependent cells
        """
        value = self.df.loc[row_idx, col_name]
        source_node = self._cell_node_id(col_name, value)
        dependents = []
        
        for _, fd in self.fd_df.iterrows():
            if fd['from'] == col_name:
                target_col = fd['to']
                target_value = self.df.loc[row_idx, target_col]
                target_node = self._cell_node_id(target_col, target_value)
                if target_node in self.graph:
                    dependents.append((row_idx, target_col))
        
        return dependents
    
    def get_determinant_cells(self, row_idx: int, col_name: str) -> list[tuple[int, str]]:
        """
        Get all cells that determine the given cell via functional dependencies.
        
        Args:
            row_idx: Row index
            col_name: Column name
            
        Returns:
            List of (row_idx, col_name) tuples for determinant cells
        """
        value = self.df.loc[row_idx, col_name]
        target_node = self._cell_node_id(col_name, value)
        determinants = []
        
        for _, fd in self.fd_df.iterrows():
            if fd['to'] == col_name:
                source_col = fd['from']
                source_value = self.df.loc[row_idx, source_col]
                source_node = self._cell_node_id(source_col, source_value)
                if source_node in self.graph:
                    determinants.append((row_idx, source_col))
        
        return determinants
    
    def get_cells_with_value(self, col_name: str, value) -> list[int]:
        """
        Get all row indices where the given column has the specified value.
        
        Args:
            col_name: Column name
            value: Value to search for
            
        Returns:
            List of row indices
        """
        return self.df[self.df[col_name] == value].index.tolist()
    
    def summary(self) -> dict:
        """Get a summary of the graph."""
        # Calculate average quality
        qualities = [data['quality'] for _, _, data in self.graph.edges(data=True)]
        avg_quality = sum(qualities) / len(qualities) if qualities else 0
        
        return {
            "num_rows": len(self.df),
            "num_columns": len(self.columns),
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "columns": self.columns,
            "functional_dependencies": len(self.fd_df),
            "average_edge_quality": avg_quality
        }
    
    def traverse_best_quality_path(self, ordered_fds: list[tuple[str, str]]) -> dict:
        """
        Traverse the graph following ordered FDs, picking highest quality edges.
        
        For each starting node in the first FD, follows the chain of FDs,
        selecting the highest quality edge at each step.
        
        Args:
            ordered_fds: List of tuples (from_col, to_col) representing the FD chain to follow
            
        Returns:
            Dictionary with starting node as key and formatted path as value
        """
        if not ordered_fds:
            return {}
        
        results = {}
        
        # Get the first FD to identify starting nodes
        first_from_col, _ = ordered_fds[0]
        
        # Find all unique starting nodes (nodes from the first column)
        starting_nodes = set()
        for node_id in self.graph.nodes():
            col_name, _ = self._parse_node_id(node_id)
            if col_name == first_from_col:
                starting_nodes.add(node_id)
        #print(starting_nodes)
        
        # For each starting node, traverse the path
        for start_node in starting_nodes:
            path_steps = []
            current_node = start_node
            
            for fd_idx, (from_col, to_col) in enumerate(ordered_fds):
                # Get all outgoing edges from current node
                best_edge = None
                best_quality = -1
                
                for next_node in self.graph.successors(current_node):
                    
                    '''
                    # Check if this edge matches the current FD
                    edge_data = self.graph[current_node][next_node]
                    print(self.graph[current_node][next_node])
                    edge_from_col = edge_data.get('fd_from')
                    edge_to_col = edge_data.get('fd_to')
                    '''
                    
                    #if edge_from_col == from_col and edge_to_col == to_col:
                    quality = self.graph[current_node][next_node]['quality']
                    if quality > best_quality:
                        best_quality = quality
                        best_edge = next_node
                
                if best_edge is None:
                    # No valid edge found for this FD
                    print("no valid edge found\n")
                    break
                
                # Extract values from node IDs
                _, from_value = self._parse_node_id(current_node)
                _, to_value = self._parse_node_id(best_edge)
                
                # Format the step
                fd_name = f"fd{fd_idx + 1}"
                step = f'({fd_name}, {{"{from_value}", "{to_value}"}})'
                path_steps.append(step)
                
                current_node = best_edge
            
            # Format the complete path
            if path_steps:
                path_str = " -> ".join(path_steps)
                _, start_value = self._parse_node_id(start_node)
                results[start_node] = f"{start_value}: {path_str}"
        
        return results


# Example usage
if __name__ == "__main__":
    # Load the beers dataset
    data_path = "../datasets/beers/dirty.csv"
    fd_path = "../datasets/beers/fds.csv"
    
    fd_graph = FDGraph(data_path, fd_path)
    
    # Print summary
    print("=== FDGraph Summary ===")
    summary = fd_graph.summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    # Show some edge qualities
    print(f"\n=== Sample Edge Qualities ===")
    count = 0
    for from_node, to_node, edge_data in fd_graph.graph.edges(data=True):
        quality = edge_data.get('quality', 'Not calculated')
        support = edge_data.get('support', 'N/A')
        print(f"  {from_node} -> {to_node}: quality={quality:.3f}, support={support:.3f}")
        count += 1
        if count >= 15:  # Show only first 5
            break
    
    # Example: Traverse best quality paths for ordered FDs
    print(f"\n=== Best Quality Paths ===")
    '''ordered_fds = [("id","brewery_id"),("brewery_id","brewery-name")]'''
    ordered_fds = [
        ("provider_id", "provider_adress"),
        ("provider_adress", "provider_area_id"),
        ("provider_area_id", "service_area"),
        ("service_area", "provider_area_id")
    ]
    paths = fd_graph.traverse_best_quality_path(ordered_fds)
    for node_id, path_str in list(paths.items())[:20]:  # Show first 5 paths
        print(f"  {path_str}")
    
    '''  
    nodes = "DeptName"
    
    # Example: Get node info for the (column, value) pair at row 0, column 'DeptName'
    node_id = fd_graph.get_node_id(0, nodes)
    print(f"\n=== Node Info for {nodes} (row 0) ===")
    print(f"  Node ID: {node_id}")
    print(f"  Info: {fd_graph.get_node_info(node_id)}")
    
    cells = "ZipCode"
    
    # Example: Get cells that depend on 'index' in row 0
    print(f"\n=== Cells dependent on {cells} in row 0 ===")
    dependents = fd_graph.get_dependent_cells(0, cells)
    for row, col in dependents:
        print(f"  r{row}_{col}: {fd_graph.get_cell_value(row, col)}")
    
    determant = "ManagerID"
    
    # Example: Get cells that determine 'brewery-name' in row 0
    print(f"\n=== Cells determining {determant} in row 0 ===")
    determinants = fd_graph.get_determinant_cells(0, determant)
    for row, col in determinants:
        print(f"  r{row}_{col}: {fd_graph.get_cell_value(row, col)}")
    '''