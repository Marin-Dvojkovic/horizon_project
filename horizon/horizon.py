import argparse
import json
import logging
import sys
import time
from pathlib import Path

import polars as pl
from fd_pattern_graph import FDPatternGraph
from fds.fd import FunctionalDependency
from fds.fd_pattern import FDPattern
from fds.pattern_expression import PatternExpression
from fds.set_of_fds import SetOfFDs
from static_fd_analysis import get_ordered_fds
from utils.loaders import iter_table_batches, load_fds
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
    "--n_rows",
    "-n",
    type=int,
    help="Number of rows to repair (still uses full dataset to build graphs). (default: all rows)",
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
    help="Log level. Options: DEBUG, INFO, WARNING, ERROR. (default: INFO)",
)
parser.add_argument(
    "--enable_plotting",
    "-p",
    action="store_true",
    help="Enable plotting of the graphs.",
)
parser.add_argument(
    "--collect_pattern_expressions",
    "-ex",
    action="store_true",
    help="Enable collecting pattern expressions for lineage.",
)


def repair_tuple(
    columns: dict[str, list[str]],
    t: int,
    fd: FunctionalDependency,
    repair_table: list[dict[str, str]],
    p_exp: PatternExpression,
    fd_pattern_graph: FDPatternGraph,
) -> None:
    """Given a data frame as a dict, applies in-place repairs for tuple with index t and functional dependency fd."""
    lval: str = str(columns[fd.lhs][t])
    rval: str = str(columns[fd.rhs][t])
    existing_pattern: FDPattern | None = p_exp.attribute_in_expression(fd.rhs)
    if lval in repair_table[fd.index]:
        # LHS value for this FD has been seen before (entry in table)
        rval = repair_table[fd.index][lval]
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
        repair_table[fd.index][lval] = rval
        logger.debug(
            f"Tuple {t}: Applied existing pattern repair for {fd} (LHS={lval} -> RHS={rval})"
        )
    else:
        # Choose best edge from FD pattern graph
        rhs, rval = fd_pattern_graph.choose_best_next_edge(fd.lhs, lval, fd.rhs)
        pattern: FDPattern = FDPattern(fd, lval, rval)
        p_exp.add_fd_pattern(pattern)
        repair_table[fd.index][lval] = rval
        logger.debug(
            f"Tuple {t}: Applied graph-based repair for {fd} (LHS={lval} -> RHS={rval})"
        )

    # Apply repair in place
    columns[fd.rhs][t] = rval


def repair_dirty_data(
    dirty_data_path: Path,
    cleaned_data_output_path: Path,
    ordered_fds: list[FunctionalDependency],
    repair_table: list[dict[str, str]],
    fd_pattern_graph: FDPatternGraph,
    n_rows: int | None = None,
    collect_pattern_expressions: bool = False,
) -> tuple[list[PatternExpression], float]:
    """Repairs data under the given dirty data path, based on the given order and FD Pattern graph.
    If n_rows is given, only repairs the first n_rows tuples.
    Set collect_pattern_expressions=False to free each tuple's PatternExpression immediately when the lineage is not needed (e.g. runtime benchmarks).
    Saves cleaned data under given cleaned data output path."""

    # Compute repairs for dirty data
    pattern_expressions: list[PatternExpression] = []

    # Only FD-touched columns are read/mutated by the repair; convert just those
    # to Python lists per batch. Untouched columns ride along as compact Arrow
    # (~3-4x smaller than Python str lists) and are stitched back in at write time.
    fd_columns: list[str] = list(
        {
            col
            for fd in ordered_fds
            if not isinstance(fd.lhs, tuple)
            for col in (fd.lhs, fd.rhs)
        }
    )

    logger.info("Loading dirty data...")
    logger.info("Starting tuple repair process...")
    start: float = time.time()

    # Total tuple index i
    i: int = 0
    # Stream each repaired batch straight to disk. Holding only the current batch
    # caps output memory at O(batch); the previous pl.concat into a growing
    # LazyFrame kept the entire cleaned dataset resident until the final sink.
    # iter_table_batches reads the input with memory bounded by block size (not
    # file size), so the input is never materialised; the row total is therefore
    # not known up front, and progress is logged by absolute count.
    with open(cleaned_data_output_path, "wb") as cleaned_file:
        first_batch: bool = True
        # Iterate over batches
        for df in iter_table_batches(dirty_data_path, n_rows=n_rows):
            batch_size: int = len(df)
            # Convert the FD columns of the batch into a columns dict.
            # Per-cell df[t, col] reads on a Polars data frame and especially
            # df[t, col] = val writes rebuild whole Arrow columns (O(n) each),
            # making the loop O(n^2). dict-of-lists makes them O(1).
            columns: dict[str, list[str]] = df.select(fd_columns).to_dict(
                as_series=False
            )

            # Iterate over tuples in batch and compute pattern expression for each
            for t in range(batch_size):
                p_exp: PatternExpression = PatternExpression(i)
                for fd in ordered_fds:
                    # NOTE: Currently does not support multiple attributes on LHS
                    if isinstance(fd.lhs, tuple):
                        continue
                    repair_tuple(columns, t, fd, repair_table, p_exp, fd_pattern_graph)
                i += 1

                # Each tuple's PatternExpression is needed only while repairing that tuple
                # Retaining all of them (for the lineage output) costs O(n_tuples) objects
                if collect_pattern_expressions:
                    pattern_expressions.append(p_exp)

                if i % 1_000_000 == 0:
                    logger.info(f"Repaired {i} tuples")

            # Stitch repaired FD columns back into the batch (original column
            # order preserved) and write; header only on the first batch.
            repaired: pl.DataFrame = df.with_columns(
                [pl.Series(name, values) for name, values in columns.items()]
            )
            repaired.write_csv(cleaned_file, include_header=first_batch)
            first_batch = False

    end: float = time.time()
    elapsed_time: float = end - start

    logger.info(f"Tuple repair process completed in {elapsed_time:.2f}s")
    logger.debug(f"Repair table:\n{repair_table}")

    # Clear the FD pattern graph to save memory
    fd_pattern_graph.clear()

    logger.info(f"Cleaned data saved to {cleaned_data_output_path}")

    return pattern_expressions, elapsed_time


def run_horizon(
    dataset_name: str,
    dirty_data_path: Path,
    set_of_fds: SetOfFDs,
    output_dir: Path,
    n_rows: int | None = None,
    enable_plotting: bool = False,
    collect_pattern_expressions: bool = False,
) -> None:
    # Create output directory
    if not output_dir.exists:
        logger.info(f"Creating output directory under {output_dir}")
    output_dir.mkdir(exist_ok=True)

    # Get traversal order
    logger.info("Computing traversal order for FDs...")
    ordered_fds, fd_ordering_time = get_ordered_fds(
        set_of_fds, dataset_name, output_dir, enable_plotting
    )

    # Build FD pattern graph
    logger.info("Building FD pattern graph...")
    fd_pattern_graph: FDPatternGraph = FDPatternGraph(
        dirty_data_path, set_of_fds, dataset_name, output_dir, enable_plotting
    )

    # Compute repairs for dirty data
    pattern_expressions, repair_time = repair_dirty_data(
        dirty_data_path,
        output_dir / f"{dataset_name}_cleaned_data.csv",
        ordered_fds,
        fd_pattern_graph.repair_table,
        fd_pattern_graph,
        n_rows,
        collect_pattern_expressions,
    )

    # Save repair time statistics
    stat_output_path: Path = output_dir / f"{dataset_name}_statistics.json"
    repair_statistics = {
        "order_fds_time": fd_ordering_time,
        "build_fd_pattern_graph_time": fd_pattern_graph._build_time,
        "repair_time": repair_time,
        "total_time": fd_ordering_time + fd_pattern_graph._build_time + repair_time,
    }
    stat_file = open(stat_output_path, "w", encoding="utf-8")
    json.dump(repair_statistics, stat_file)
    stat_file.close()
    logger.info(f"Repair time statistics saved to {stat_output_path}")

    # Save pattern expressions as lineage
    if collect_pattern_expressions:
        exp_output_path: Path = (
            output_dir / f"{dataset_name}_final_pattern_expressions.txt"
        )
        exp_file = open(exp_output_path, "w", encoding="utf-8")
        exp_file.writelines("\n".join(f"{str(p_exp)}" for p_exp in pattern_expressions))
        exp_file.close()
        logger.info(f"Final pattern expressions saved to {exp_output_path}")


def main(
    dataset_dir: Path,
    dirty_data_file: str,
    output_dir: Path,
    n_rows: int | None,
    enable_plotting: bool,
    collect_pattern_expressions: bool,
) -> None:
    # Verify data path
    dirty_data_path: Path = dataset_dir / dirty_data_file
    if not dirty_data_path.exists():
        logger.error(f"File {dirty_data_path} does not exist")
        raise ValueError(f"File {dirty_data_path} does not exist")
    logger.debug(f"Dirty data path: {dirty_data_path}")

    # Load FDs
    logger.info("Loading functional dependencies...")
    set_of_fds: SetOfFDs = load_fds(dataset_dir, dirty_data_path)

    dataset_name: str = dataset_dir.name

    logger.info(
        f"Starting Horizon pipeline with dataset '{dataset_name}': {dataset_dir}"
    )

    run_horizon(
        dataset_name,
        dirty_data_path,
        set_of_fds,
        output_dir,
        n_rows,
        enable_plotting,
        collect_pattern_expressions,
    )


if __name__ == "__main__":
    # Parse arguments
    args: argparse.Namespace = parser.parse_args()

    # Setup logging
    setup_logging(log_level=getattr(logging, args.log_level.upper()))

    logger.info(f"Horizon pipeline started with arguments: {vars(args)}")

    try:
        main(
            Path(args.dataset_dir),
            args.dirty_data_file,
            Path(args.output_dir),
            args.n_rows,
            args.enable_plotting,
            args.collect_pattern_expressions,
        )
        logger.info("Pipeline execution completed successfully")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {str(e)}", exc_info=True)
        sys.exit(1)
