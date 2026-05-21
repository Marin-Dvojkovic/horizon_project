import sys
from pathlib import Path

from static_fd_analysis import get_ordered_fds
from FDGraph import FDGraph


def main(dataset_dir: Path) -> None:
    dirty_path = dataset_dir / "dirty.csv"
    fds_path = dataset_dir / "fds.csv"

    # Build FD pattern graph from dirty data and the FD definitions
    fd_graph = FDGraph(str(dirty_path), str(fds_path))

    # Get traversal order from the static FD analysis
    ordered_fds: list[str] = get_ordered_fds(fds_path)

    # Traverse the best-quality path through the FD graph
    best_paths = fd_graph.traverse_best_quality_path(ordered_fds)

    print("Best quality paths:")
    if not best_paths:
        print("  No paths were generated. Check ordered FDs or graph connectivity.")
    else:
        for start_node, path_str in best_paths.items():
            print(f"  {path_str}")


if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) != 2:
        print("Usage: python horizon.py <dataset_dir>")
        sys.exit(1)

    dataset_dir: str = sys.argv[1]

    main(Path(dataset_dir))
