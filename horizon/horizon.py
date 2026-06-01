import argparse
import logging
import sys
import time
from pathlib import Path

import polars as pl
import utils.loaders
from fd_pattern_graph import FDPatternGraph
from fds.fd import FunctionalDependency
from fds.fd_pattern import FDPattern
from fds.pattern_expression import PatternExpression
from fds.set_of_fds import SetOfFDs
from static_fd_analysis import get_ordered_fds
from utils.logging_config import get_logger, setup_logging

# Setup logging
logger: logging.Logger = get_logger(__name__)

# Parse arguments
parser: argparse.ArgumentParser = argparse.ArgumentParser(
    description="Horizon: Scalable Dependency-driven Data Cleaning."
)
parser.add_argument(
    "--dataset_dir",
    "-ds",
    type=str,
    required=True,
    help="Dataset directory. Required argument.",
)
parser.add_argument(
    "--dirty_data_file",
    "-dd",
    type=str,
    default="dirty.csv",
    help="Dirty data file, relative to the given dataset_dir. (default: dirty.csv)",
)
parser.add_argument(
    "--output_dir",
    "-o",
    type=str,
    default="output",
    help="Output directory, relative to the cwd. (default: output)",
)
parser.add_argument(
    "--log_level",
    "-l",
    type=str,
    default="INFO",
    help="Log level. Options: DEBUG, INFO, ERROR. (default: INFO)",
)
args: argparse.Namespace = parser.parse_args()

# Dataset directory and output directory
dataset_dir: Path = Path(args.dataset_dir)
output_dir: Path = Path(args.output_dir)

# Variables for using different datasets
lhs_column_name: str = "from"
rhs_column_name: str = "to"


def load_fds(fds_csv_path: Path) -> SetOfFDs:
    logger.debug(f"Loading FDs from: {fds_csv_path}")
    # Check fds.csv path
    if not fds_csv_path.exists:
        logger.error(f"CSV file {str(fds_csv_path)} does not exist.")
        raise ValueError(f"CSV file {str(fds_csv_path)} does not exist.")

    # Use CSV data loader to read input FDs from file
    fds: SetOfFDs = utils.loaders.get_fds(
        fds_csv_path, utils.loaders.CSVFDLoader(lhs_column_name, rhs_column_name)
    )
    logger.info(f"Loaded {len(fds)} functional dependencies")
    return fds


def main() -> None:
    dataset_name: str = dataset_dir.name

    logger.info(
        f"Starting Horizon pipeline with dataset '{dataset_name}': {dataset_dir}"
    )

    # Verify data path
    fds_path: Path = dataset_dir / "fds.csv"
    dirty_data_path: Path = dataset_dir / args.dirty_data_file
    logger.debug(f"FD path: {fds_path}")
    logger.debug(f"Dirty data path: {dirty_data_path}")

    # Load FDs
    logger.info("Loading functional dependencies...")
    set_of_fds: SetOfFDs = load_fds(fds_path)

    # Load dirty data
    logger.info("Loading dirty data...")
    # dirty_data: pl.DataFrame = pl.read_csv(dirty_data_path)
    dirty_data: pl.DataFrame = utils.loaders.load_table(dirty_data_path)
    logger.info(
        f"Loaded dirty data with {len(dirty_data)} tuples and {len(dirty_data.columns)} columns"
    )

    # Get traversal order
    logger.info("Computing traversal order for FDs...")
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(
        set_of_fds, dataset_name, output_dir
    )

    # Build FD pattern graph
    logger.info("Building FD pattern graph...")
    fd_graph: FDPatternGraph = FDPatternGraph(str(dirty_data_path), set_of_fds)

    # Compute repairs for dirty data
    pattern_expressions: list[PatternExpression] = []
    repair_table: dict[FunctionalDependency, dict[str, str]] = {
        fd: {} for fd in set_of_fds
    }

    logger.info("Starting tuple repair process...")
    start: float = time.time()
    # Iterate over tuples and compute pattern expression for each
    for t in range(len(dirty_data)):
        p_exp: PatternExpression = PatternExpression(t)
        for i in range(len(ordered_fds)):
            for fd in ordered_fds[i]:
                # TODO: Support multiple attributes on LHS
                if isinstance(fd.lhs, tuple):
                    continue
                lval: str = str(dirty_data[t, fd.lhs])
                rval: str = str(dirty_data[t, fd.rhs])
                existing_pattern: FDPattern | None = p_exp.attribute_in_expression(
                    fd.rhs
                )
                if lval in repair_table[fd]:
                    # LHS value for this FD has been seen before (entry in table)
                    rval = repair_table[fd][lval]
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    logger.debug(
                        f"Tuple {t}: Applied cached repair for {fd} (LHS={lval} -> RHS={rval})"
                    )
                elif existing_pattern is not None:
                    # RHS attribute is part of a previous FD, therefore use the same RHS value
                    rval = existing_pattern.rval
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval
                    logger.debug(
                        f"Tuple {t}: Applied existing pattern repair for {fd} (LHS={lval} -> RHS={rval})"
                    )
                else:
                    # Choose best edge from FD pattern graph
                    rhs, rval = fd_graph.choose_best_next_edge(fd.lhs, lval, fd.rhs)
                    pattern: FDPattern = FDPattern(fd, lval, rval)
                    p_exp.add_fd_pattern(pattern)
                    repair_table[fd][lval] = rval
                    logger.debug(
                        f"Tuple {t}: Applied graph-based repair for {fd} (LHS={lval} -> RHS={rval})"
                    )

                # Apply repair in place
                dirty_data[t, fd.rhs] = rval

        pattern_expressions.append(p_exp)
        if (t + 1) % max(1, len(dirty_data) // 10) == 0:
            logger.info(f"Repaired {t + 1}/{len(dirty_data)} tuples")

    end: float = time.time()
    elapsed_time: float = end - start

    logger.info(f"Tuple repair process completed in {elapsed_time:.2f}s")
    logger.debug(f"Repair table:\n{repair_table}")

    # Create output directory
    if not output_dir.exists:
        logger.info(f"Creating output directory under {output_dir}")
    output_dir.mkdir(exist_ok=True)

    # Save cleaned data
    data_output_path: Path = output_dir / f"{dataset_name}_cleaned_data.csv"
    dirty_data.write_csv(data_output_path)
    logger.info(f"Cleaned data saved to {data_output_path}")
    logger.info(f"Pipeline completed successfully. Total time: {elapsed_time:.2f}s")

    # Save pattern expressions as lineage
    exp_output_path: Path = output_dir / f"{dataset_name}_final_pattern_expressions.txt"
    exp_file = open(exp_output_path, "w")
    exp_file.writelines("\n".join(f"{str(p_exp)}" for p_exp in pattern_expressions))
    exp_file.close()
    logger.info(f"Final pattern expressions saved to {exp_output_path}")


if __name__ == "__main__":
    # Setup logging
    setup_logging(log_level=getattr(logging, args.log_level))

    logger.info(f"Horizon pipeline started with arguments: {vars(args)}")

    try:
        main()
        logger.info("Pipeline execution completed successfully")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)
