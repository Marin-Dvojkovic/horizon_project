import sys
import time
from pathlib import Path

import pandas as pd
import utils.loaders
from FDGraph import FDGraph
from static_fd_analysis import get_ordered_fds
from utils.fd import FunctionalDependency
from utils.fd_pattern import FDPattern
from utils.pattern_expression import PatternExpression

# Variables for using different datasets
lhs_column_name: str = "LHS"
rhs_column_name: str = "RHS"


def load_fds(fds_csv_path: Path):
    # Check fds.csv path
    if not fds_csv_path.exists:
        raise ValueError(f"CSV file {str(fds_csv_path)} does not exist.")

    # Use CSV data loader to read input FDs from file
    return utils.loaders.get_fds(
        fds_csv_path, utils.loaders.CSVFDLoader(lhs_column_name, rhs_column_name)
    )


def main(dataset_dir: Path) -> None:
    # Verify data path
    fds_path: Path = dataset_dir / "fds.csv"
    dirty_data_path = dataset_dir / "dirty.csv"
    clean_data_path = dataset_dir / "clean.csv"

    # Load data
    set_of_fds: list[FunctionalDependency] = load_fds(fds_path)

    # Build FD pattern graph
    fd_graph: FDGraph = FDGraph(str(dirty_data_path), str(fds_path))

    # Get traversal order
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(set_of_fds)

    # Compute repairs for dirty data
    dirty_data: pd.DataFrame = pd.read_csv(dirty_data_path)
    pattern_expressions: list[PatternExpression] = []
    repair_table: dict[FunctionalDependency, dict[str, str]] = {
        fd: {} for fd in set_of_fds
    }

    start = time.time()
    # Iterate over tuples and compute pattern expression for each
    for t in range(len(dirty_data)):
        p_exp: PatternExpression = PatternExpression(t)
        for i in range(len(ordered_fds)):
            for fd in ordered_fds[i]:
                lval: str = str(
                    dirty_data.at[t, fd.lhs[0]]
                )  # TODO: Support multiple attributes on LHS
                rval: str = str(dirty_data.at[t, fd.rhs])
                existing_pattern: FDPattern | None = p_exp.attribute_in_expression(
                    fd.rhs
                )
                if lval in repair_table[fd]:
                    # LHS value for this FD has been seen before (entry in table)
                    rval = repair_table[fd][lval]
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                elif existing_pattern is not None:
                    # RHS attribute is part of a previous FD, therefore use the same RHS value
                    rval = existing_pattern.rval
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval
                else:
                    # Choose best edge from FD pattern graph
                    rhs, rval = fd_graph.choose_best_next_edge(fd.lhs[0], lval, fd.rhs)
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval

                # Apply repair in place
                dirty_data.at[t, fd.rhs] = rval

        pattern_expressions.append(p_exp)

    end = time.time()

    print(f"Repair table:\n{repair_table}\n")
    print("Pattern expressions:\n")
    print("\n\n".join(f"{str(p_exp)}" for p_exp in pattern_expressions))

    print(f"\nFinished. Took {end - start}s to repair {len(dirty_data)} tuples.")

    dirty_data.to_csv("output/cleaned_data_result.csv", index=False)


if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) != 2:
        print("Usage: python horizon.py <dataset_dir>")
        sys.exit(1)

    dataset_dir: str = sys.argv[1]

    main(Path(dataset_dir))
