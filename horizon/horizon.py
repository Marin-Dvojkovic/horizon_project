import sys
from pathlib import Path

from static_fd_analysis import get_ordered_fds


def main(dataset_dir: Path) -> None:
    # Build FD pattern graph

    # Get traversal order
    ordered_fds: list[list[str]] = get_ordered_fds(dataset_dir / "fds.csv")

    # ...


if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) != 2:
        print("Usage: python horizon.py <dataset_dir>")
        sys.exit(1)

    dataset_dir: str = sys.argv[1]

    main(Path(dataset_dir))
