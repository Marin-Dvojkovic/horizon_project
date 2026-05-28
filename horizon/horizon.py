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
from utils.logging_config import setup_logging, get_logger
import logging

# Setup logging
logger = get_logger(__name__)

# Variables for using different datasets
lhs_column_name: str = "LHS"
rhs_column_name: str = "RHS"


def load_fds(fds_csv_path: Path):
    logger.debug(f"Loading FDs from: {fds_csv_path}")
    # Check fds.csv path
    if not fds_csv_path.exists:
        logger.error(f"CSV file {str(fds_csv_path)} does not exist.")
        raise ValueError(f"CSV file {str(fds_csv_path)} does not exist.")

    # Use CSV data loader to read input FDs from file
    fds = utils.loaders.get_fds(
        fds_csv_path, utils.loaders.CSVFDLoader(lhs_column_name, rhs_column_name)
    )
    logger.info(f"Loaded {len(fds)} functional dependencies")
    return fds


def main(dataset_dir: Path) -> None:
    logger.info(f"Starting Horizon pipeline with dataset: {dataset_dir}")
    # Verify data path
    fds_path: Path = dataset_dir / "fds.csv"
    dirty_data_path = dataset_dir / "dirty.csv"
    clean_data_path = dataset_dir / "clean.csv"

    logger.debug(f"FD path: {fds_path}")
    logger.debug(f"Dirty data path: {dirty_data_path}")
    logger.debug(f"Clean data path: {clean_data_path}")

    # Load data
    logger.info("Loading functional dependencies...")
    set_of_fds: list[FunctionalDependency] = load_fds(fds_path)

    # Build FD pattern graph
    logger.info("Building FD pattern graph...")
    fd_graph: FDGraph = FDGraph(str(dirty_data_path), str(fds_path))

    # Get traversal order
    logger.info("Computing traversal order for FDs...")
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(set_of_fds)

    # Compute repairs for dirty data
    logger.info("Loading dirty data...")
    dirty_data: pd.DataFrame = pd.read_csv(dirty_data_path)
    logger.info(f"Loaded dirty data with {len(dirty_data)} tuples and {len(dirty_data.columns)} columns")
    
    pattern_expressions: list[PatternExpression] = []
    repair_table: dict[FunctionalDependency, dict[str, str]] = {
        fd: {} for fd in set_of_fds
    }

    logger.info("Starting tuple repair process...")
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
                    logger.debug(f"Tuple {t}: Applied cached repair for {fd} (LHS={lval} -> RHS={rval})")
                elif existing_pattern is not None:
                    # RHS attribute is part of a previous FD, therefore use the same RHS value
                    rval = existing_pattern.rval
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval
                    logger.debug(f"Tuple {t}: Applied existing pattern repair for {fd} (LHS={lval} -> RHS={rval})")
                else:
                    # Choose best edge from FD pattern graph
                    rhs, rval = fd_graph.choose_best_next_edge(fd.lhs[0], lval, fd.rhs)
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval
                    logger.debug(f"Tuple {t}: Applied graph-based repair for {fd} (LHS={lval} -> RHS={rval})")

                # Apply repair in place
                dirty_data.at[t, fd.rhs] = rval

        pattern_expressions.append(p_exp)
        if (t + 1) % max(1, len(dirty_data) // 10) == 0:
            logger.info(f"Repaired {t + 1}/{len(dirty_data)} tuples")

    end = time.time()
    elapsed_time = end - start

    logger.info(f"Tuple repair process completed in {elapsed_time:.2f}s")
    logger.debug(f"Repair table:\n{repair_table}")
    logger.info(f"Generated pattern expressions for {len(pattern_expressions)} tuples")

    # Save cleaned data
    output_path = Path("output/cleaned_data_result.csv")
    output_path.parent.mkdir(exist_ok=True)
    dirty_data.to_csv(output_path, index=False)
    logger.info(f"Cleaned data saved to {output_path}")
    logger.info(f"Pipeline completed successfully. Total time: {elapsed_time:.2f}s")


if __name__ == "__main__":
    # Setup logging
    setup_logging(log_level=logging.DEBUG)
    
    # Parse arguments
    if len(sys.argv) != 2:
        print("Usage: python horizon.py <dataset_dir>")
        sys.exit(1)

    dataset_dir: str = sys.argv[1]
    logger.info(f"Horizon pipeline started with arguments: {sys.argv[1:]}")

    try:
        main(Path(dataset_dir))
        logger.info("Pipeline execution completed successfully")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)
