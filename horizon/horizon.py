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


def load_fds(dataset_dir: Path, data_csv_path: Path) -> SetOfFDs:
    # Check for fds.csv or fds.txt (prefer .csv)
    fd_files: list[Path] = sorted(
        list(dataset_dir.glob("fds.*")),
        key=lambda path: path.suffix.lower() != ".csv",
    )
    if len(fd_files) < 1:
        logger.error(f"No FD file found under {str(dataset_dir)}")
        raise ValueError(f"No FD file found under {str(dataset_dir)}")

    fds_path: Path = fd_files[0]
    logger.debug(f"Loading FDs from: {fds_path}")

    # Use data loader to read input FDs from file
    fds: SetOfFDs = utils.loaders.get_fds(fds_path, data_csv_path)
    logger.info(f"Loaded {len(fds)} functional dependencies")
    return fds


def load_data(data_csv_path: Path) -> pl.DataFrame:
    # Check csv path
    if not data_csv_path.exists:
        logger.error(f"CSV file {str(data_csv_path)} does not exist")
        raise ValueError(f"CSV file {str(data_csv_path)} does not exist")

    # Load dirty data
    logger.info("Loading dirty data...")
    # dirty_data: pl.DataFrame = pl.read_csv(data_csv_path)
    data: pl.DataFrame = utils.loaders.load_table(data_csv_path)
    logger.info(
        f"Loaded dirty data with {len(data)} tuples and {len(data.columns)} columns"
    )
    return data


def repair_tuple(
    columns: dict[str, list[str]],
    t: int,
    fd: FunctionalDependency,
    repair_table: dict[FunctionalDependency, dict[str, str]],
    p_exp: PatternExpression,
    fd_pattern_graph: FDPatternGraph,
):
    lval: str = str(columns[fd.lhs][t])
    rval: str = str(columns[fd.rhs][t])
    existing_pattern: FDPattern | None = p_exp.attribute_in_expression(fd.rhs)
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
        rhs, rval = fd_pattern_graph.choose_best_next_edge(fd.lhs, lval, fd.rhs)
        pattern: FDPattern = FDPattern(fd, lval, rval)
        p_exp.add_fd_pattern(pattern)
        repair_table[fd][lval] = rval
        logger.debug(
            f"Tuple {t}: Applied graph-based repair for {fd} (LHS={lval} -> RHS={rval})"
        )

    # Apply repair in place
    columns[fd.rhs][t] = rval


def repair_dirty_data(
    dirty_data_path: Path,
    ordered_fds: list[list[FunctionalDependency]],
    fd_pattern_graph: FDPatternGraph,
) -> tuple[pl.DataFrame, list[PatternExpression]]:
    # Compute repairs for dirty data
    pattern_expressions: list[PatternExpression] = []
    repair_table: dict[FunctionalDependency, dict[str, str]] = {
        fd: {} for fds in ordered_fds for fd in fds
    }

    # Repair on Python lists, not the Polars frame: per-cell df[t, col] reads
    # and especially df[t, col] = val writes rebuild whole Arrow columns
    # (O(n) each), making the loop O(n^2). dict-of-lists makes them O(1);
    # rebuild the frame once at the end.
    dirty_data: pl.DataFrame = load_data(dirty_data_path)
    columns: dict[str, list[str]] = dirty_data.to_dict(as_series=False)
    n_tuples: int = len(dirty_data)
    # Clear df to save memory, columns is used to read the data
    dirty_data.clear()

    logger.info("Starting tuple repair process...")
    start: float = time.time()
    # Iterate over tuples and compute pattern expression for each
    for t in range(n_tuples):
        p_exp: PatternExpression = PatternExpression(t)
        for i in range(len(ordered_fds)):
            for fd in ordered_fds[i]:
                # TODO: Support multiple attributes on LHS
                if isinstance(fd.lhs, tuple):
                    continue
                repair_tuple(columns, t, fd, repair_table, p_exp, fd_pattern_graph)

        pattern_expressions.append(p_exp)
        if (t + 1) % max(1, n_tuples // 10) == 0:
            logger.info(f"Repaired {t + 1}/{n_tuples} tuples")

    end: float = time.time()
    elapsed_time: float = end - start

    logger.info(f"Tuple repair process completed in {elapsed_time:.2f}s")
    logger.debug(f"Repair table:\n{repair_table}")

    # Rebuild the data frame from the repaired columns
    cleaned_data: pl.DataFrame = pl.DataFrame(columns)

    return cleaned_data, pattern_expressions


def main(dataset_dir: Path, output_dir: Path, dirty_data_file: str) -> None:
    dataset_name: str = dataset_dir.name

    logger.info(
        f"Starting Horizon pipeline with dataset '{dataset_name}': {dataset_dir}"
    )

    # Verify data path
    fds_path: Path = dataset_dir / "fds.csv"
    dirty_data_path: Path = dataset_dir / dirty_data_file
    logger.debug(f"FD path: {fds_path}")
    logger.debug(f"Dirty data path: {dirty_data_path}")

    # Load FDs
    logger.info("Loading functional dependencies...")
    set_of_fds: SetOfFDs = load_fds(dataset_dir, dirty_data_path)

    # Get traversal order
    logger.info("Computing traversal order for FDs...")
    ordered_fds: list[list[FunctionalDependency]] = get_ordered_fds(
        set_of_fds, dataset_name, output_dir
    )

    # Build FD pattern graph
    logger.info("Building FD pattern graph...")
    fd_pattern_graph: FDPatternGraph = FDPatternGraph(str(dirty_data_path), set_of_fds)

    # Compute repairs for dirty data
    cleaned_data, pattern_expressions = repair_dirty_data(
        dirty_data_path, ordered_fds, fd_pattern_graph
    )

    # Create output directory
    if not output_dir.exists:
        logger.info(f"Creating output directory under {output_dir}")
    output_dir.mkdir(exist_ok=True)

    # Save cleaned data
    data_output_path: Path = output_dir / f"{dataset_name}_cleaned_data.csv"
    cleaned_data.write_csv(data_output_path)
    logger.info(f"Cleaned data saved to {data_output_path}")

    # Save pattern expressions as lineage
    exp_output_path: Path = output_dir / f"{dataset_name}_final_pattern_expressions.txt"
    exp_file = open(exp_output_path, "w", encoding="utf-8")
    exp_file.writelines("\n".join(f"{str(p_exp)}" for p_exp in pattern_expressions))
    exp_file.close()
    logger.info(f"Final pattern expressions saved to {exp_output_path}")


if __name__ == "__main__":
    # Parse arguments
    args: argparse.Namespace = parser.parse_args()

    # Setup logging
    setup_logging(log_level=getattr(logging, args.log_level.upper()))

    logger.info(f"Horizon pipeline started with arguments: {vars(args)}")

    try:
        main(Path(args.dataset_dir), Path(args.output_dir), args.dirty_data_file)
        logger.info("Pipeline execution completed successfully")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)
