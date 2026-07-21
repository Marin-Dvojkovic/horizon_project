import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import polars as pl
import pyarrow.parquet as pq

from eval.effectiveness_eval import lazy_evaluate_repair
from horizon.utils.loaders import lazy_load_table

# Parse arguments
parser: argparse.ArgumentParser = argparse.ArgumentParser(
    description="Horizon Benchmarks for all datasets under a given directory."
)
parser.add_argument(
    "--horizon_path",
    "-hp",
    type=Path,
    default=Path("horizon/horizon.py"),
    help="Path of horizon.py. (default: horizon/horizon.py)",
)
parser.add_argument(
    "--all_datasets_dir",
    "-ds",
    type=Path,
    default=Path("datasets"),
    help="Datasets directory. (default: datasets)",
)
parser.add_argument(
    "--output_dir",
    "-o",
    type=Path,
    default=Path("output"),
    help="Output directory, relative to the cwd. (default: output)",
)
parser.add_argument(
    "--build_graph_on_subset",
    "-g",
    action="store_true",
    help="Build FD pattern graph on a subset of the data.",
)
parser.add_argument(
    "--plot_only",
    "-p",
    action="store_true",
    help="Skip benchmarking and only plot results.",
)

FIELD_NAMES: list[str] = [
    "dataset",
    "error_type",
    "error_rate",
    "repairability",
    "n_fds",
    "n_tuples",
    "n_dirty",
    "n_repaired",
    "n_correct",
    "precision",
    "recall",
    "f1",
    "order_fds_time",
    "build_fd_pattern_graph_time",
    "repair_time",
    "total_time",
    "tuples_per_s",
]


def find_datasets(all_datasets_dir: Path) -> list[Path]:
    """Returns a list of all datasets under the given datasets directory."""
    if not all_datasets_dir.exists():
        raise ValueError(f"Directory {all_datasets_dir} does not exist!")
    return sorted(
        [
            dataset_path
            for dataset_path in all_datasets_dir.iterdir()
            if dataset_path.is_dir()
        ]
    )


def eval_run(
    clean_data_path: Path,
    dirty_data_path: Path,
    cleaned_data_path: Path,
    statistics_path: Path,
    n_rows: int,
    elapsed_time: float,
) -> dict:
    """Calls our evaluation module to evaluate the effectiveness of the data repairs. Also adds repair time and throughput.
    If a file cannot be read or the evaluation fails, some metrics will not be recorded."""
    dirty_data: pl.LazyFrame = lazy_load_table(dirty_data_path, n_rows=n_rows)

    # Get repair time directly from statistics file
    total_time: float = elapsed_time
    order_fds_time: float | None = None
    build_fd_pattern_graph_time: float | None = None
    repair_time: float | None = None
    try:
        with open(statistics_path, "r") as json_file:
            data = json.load(json_file)
            total_time = data["total_time"]
            order_fds_time = data["order_fds_time"]
            build_fd_pattern_graph_time = data["build_fd_pattern_graph_time"]
            repair_time = data["repair_time"]
    except Exception:
        print(
            f"Could not read statistics file {statistics_path}. Continuing with measured time..."
        )

    # Add repair time and throughput to evaluation
    fixed_metrics: dict = {
        "order_fds_time": order_fds_time,
        "build_fd_pattern_graph_time": build_fd_pattern_graph_time,
        "repair_time": repair_time,
        "total_time": total_time,
        "tuples_per_s": round(n_rows / total_time, 5),
    }

    try:
        clean_data: pl.LazyFrame = lazy_load_table(clean_data_path, n_rows=n_rows)
        cleaned_data: pl.LazyFrame = lazy_load_table(cleaned_data_path)

        # Call evaluation
        evaluation: dict = lazy_evaluate_repair(clean_data, dirty_data, cleaned_data)
        evaluation.update(fixed_metrics)
        # Delete cleaned file to save space
        cleaned_data_path.unlink()
    except Exception as e:
        print(f"Evaluation failed with {e}. Continuing...")
        return fixed_metrics

    return evaluation


def run_horizon_benchmark(
    horizon_path: Path,
    dataset_path: Path,
    output_path: Path,
    output_csv_path: Path,
    build_graph_on_subset: bool,
) -> list[dict]:
    """Runs Horizon for the given dataset, for each error type and rate, as well as different numbers of tuples. Returns a list of evaluated runs."""
    evaluated_runs: list[dict] = []
    dataset_name: str = dataset_path.name

    # Get all dirty data files (default: dirty.csv or dirty.parquet)
    dirty_data_files: list[str] = [
        "dirty.csv" if (dataset_path / "dirty.csv").exists() else "dirty.parquet"
    ]
    # Check for injected/ over dirty.csv
    injected_path: Path = dataset_path / "injected"
    if injected_path.exists():
        dirty_data_files = [
            str(Path("injected") / injected_data.name)
            for injected_data in injected_path.glob("*_r*.csv")
        ]
    elif len(list(dataset_path.glob("clean.*"))) > 0:
        # If injected/ does not exist, take clean.csv or clean.parquet
        dirty_data_files = [
            "clean.csv" if (dataset_path / "clean.csv").exists() else "clean.parquet"
        ]
    else:
        print(
            f"\nNo dirty data file found under {str(dataset_path)}. Skipping benchmarks for dataset {dataset_path.name}."
        )
        return []

    # Get number of FDs
    fd_files: list[Path] = sorted(
        list(dataset_path.glob("fds.*")),
        key=lambda path: path.suffix.lower() != ".csv",
    )
    n_fds: int = 0
    if len(fd_files) < 1:
        print(
            f"\nNo FD file found under {str(dataset_path)}. Skipping benchmarks for dataset {dataset_path.name}."
        )
        return []
    else:
        line_count: int = sum(1 for line in open(fd_files[0], "r").readlines())
        n_fds = line_count - 1 if fd_files[0].suffix == ".csv" else line_count

    # Run Horizon for each error type and rate
    for dirty_data_file in dirty_data_files:
        dirty_data_path: Path = dataset_path / Path(dirty_data_file)
        # Count number of rows to perform experiment for different numbers of tuples
        total_rows: int = 0
        if Path(dirty_data_file).suffix.lower() == ".parquet":
            pf = pq.ParquetFile(dataset_path / dirty_data_file)
            total_rows = pf.metadata.num_rows
        else:
            total_rows = sum(1 for line in open(dirty_data_path, "r").readlines()) - 1

        # Get dataset properties
        error_type: str | None = None
        error_rate: str | None = None
        repairability: str | None = None
        p: re.Pattern = re.compile(r"^(e[123])_r(\d{2})(?:_(low|med|high))?$")
        m: re.Match | None = p.match(dirty_data_path.stem)
        if m is not None:
            error_type, error_rate, repairability = m.groups()

        # Run experiment for different numbers of tuples
        for n_tuples in range(
            round(total_rows / 10), total_rows + 1, round(total_rows / 10)
        ):
            n_tuples_file: str = dirty_data_file
            # To build FD pattern graph on a subset of the data, create temporary csv
            if build_graph_on_subset:
                base = pl.read_csv(
                    dirty_data_path, n_rows=n_tuples, infer_schema_length=0
                )
                n_tuples_file = (
                    f"{dirty_data_path.stem}_{n_tuples}{dirty_data_path.suffix}"
                )
                base.write_csv(dataset_path / Path(n_tuples_file))

            # Create sub-directory for each dirty data file and number of tuples
            output_sub_dir: Path = (
                output_path / dirty_data_path.stem / str(n_tuples)
                if "injected" in dirty_data_file
                else output_path / str(n_tuples)
            )
            output_sub_dir.mkdir(parents=True, exist_ok=True)

            # Run benchmark command
            benchmark_cmd: list[str] = [
                sys.executable,
                str(horizon_path),
                "--dataset_dir",
                str(dataset_path),
                "--dirty_data_file",
                str(n_tuples_file),
                "--output_dir",
                str(output_sub_dir),
                "--log_level",
                "WARNING",
                "--n_rows",
                str(n_tuples),
            ]

            print(
                f"\nNow running benchmarks for dataset {dataset_name} with dirty data {dirty_data_file} and {n_tuples} tuples."
            )
            # Record time as a fallback
            start_time: float = time.time()
            result = subprocess.run(benchmark_cmd, text=True)
            end_time: float = time.time()

            # Deal with failed runs
            if result.returncode != 0:
                print(f"Command {' '.join(benchmark_cmd)} failed with {result.stderr}.")
                evaluated_runs.append(
                    {
                        "dataset": dataset_name,
                        "error_type": error_type,
                        "error_rate": int(error_rate) * 0.01
                        if error_rate is not None
                        else None,
                        "repairability": repairability,
                        "n_fds": n_fds,
                        "n_tuples": n_tuples,
                    }
                )
                continue

            elapsed_time: float = end_time - start_time
            print(f"{dataset_name} completed in {elapsed_time:.2f}s.")

            # Compute evaluation
            print(f"Evaluating {dataset_name} with dirty data {dirty_data_file}...")
            evaluation: dict = eval_run(
                dataset_path / "clean.csv"
                if (dataset_path / "clean.csv").exists()
                else dataset_path / "clean.parquet",
                dataset_path / n_tuples_file,
                output_sub_dir / f"{dataset_name}_cleaned_data.csv",
                output_sub_dir / f"{dataset_name}_statistics.json",
                n_tuples,
                elapsed_time,
            )

            # If no error rate given, calculate via n_dirty / n_tuples
            dirty_data_properties: dict = {
                "dataset": dataset_name,
                "error_type": error_type,
                "error_rate": int(error_rate) * 0.01
                if error_rate is not None
                else round(evaluation["n_dirty"] / n_tuples, 3)
                if "n_dirty" in evaluation
                else None,
                "repairability": repairability,
                "n_fds": n_fds,
                "n_tuples": n_tuples,
            }

            # Combine evaluation and dataset properties
            evaluation.update(dirty_data_properties)

            evaluated_runs.append(evaluation)

            # Write evaluation directly to results csv
            with open(output_csv_path, "a", newline="") as csv_file:
                writer: csv.DictWriter = csv.DictWriter(
                    csv_file, fieldnames=FIELD_NAMES
                )
                writer.writerow(evaluation)

            # Cleanup: Delete temporary file
            if build_graph_on_subset:
                Path(dataset_path / n_tuples_file).unlink()

    return evaluated_runs


def millions_formatter(x: int, pos) -> str:
    return "%1.1fM" % (x * 1e-6)


def plot_dataset(evals: pl.DataFrame, output_dir: Path) -> None:
    """Creates plots for one dataset with different error types and rates, as well as different numbers of tuples.
    The first type of plots (f1_plot) show the F1 score for increasing error rates, the second type of plots show the throughput for increasing number of tuples, and the third type of plots (repair_time_plot) show the repair time for increasing numbers of tuples."""
    # Plot F1 score for increasing error rates
    try:
        # Create plot for each error type and repairability, for the full amount of tuples
        eval_f1: pl.DataFrame = (
            evals.sort("error_rate")
            .group_by(["error_type", "repairability", "n_tuples"], maintain_order=True)
            .agg(pl.col("error_rate") * 100, pl.col("f1"))
        ).filter(pl.col("n_tuples") == pl.col("n_tuples").max())

        for row in eval_f1.iter_rows(named=True):
            # Skip if only one point
            if len(row["error_rate"]) < 2:
                continue
            plt.plot(row["error_rate"], row["f1"], ".-")
            plt.ylim(0, 1)
            plt.xticks(row["error_rate"])
            plt.xlabel("Error %")
            plt.ylabel("F1 score")
            plt.grid()
            plt.tight_layout()
            f1_plot_path: Path = (
                output_dir / f"{row['error_type']}_{row['repairability']}_f1_plot.png"
                if row["repairability"] is not None
                else output_dir / f"{row['error_type']}_f1_plot.png"
            )
            plt.savefig(f1_plot_path)
            plt.clf()
            plt.close()
    except Exception as e:
        print(f"Plotting F1 score failed with: {e}. Continuing...")

    # Plot throughput for increasing numbers of tuples
    try:
        # Create plot for each error type, rate, and repairability
        eval_throughput: pl.DataFrame = (
            evals.sort("n_tuples")
            .group_by(
                ["error_type", "error_rate", "repairability"], maintain_order=True
            )
            .agg(pl.col("n_tuples"), pl.col("tuples_per_s"))
        )

        for row in eval_throughput.iter_rows(named=True):
            # Skip if only one point
            if len(row["n_tuples"]) < 2:
                continue
            plt.plot(row["n_tuples"], row["tuples_per_s"], ".-")
            plt.xticks(row["n_tuples"])
            if row["n_tuples"][0] > 1000000:
                plt.gca().xaxis.set_major_formatter(
                    ticker.FuncFormatter(millions_formatter)
                )
            plt.xlabel("Number of tuples")
            plt.ylabel("Throughput (tuples/s)")
            plt.grid()
            plt.tight_layout()
            throughput_plot_path: Path = (
                output_dir
                / f"{row['error_type']}_{row['error_rate']}_{row['repairability']}_throughput_plot.png"
                if row["repairability"] is not None
                else output_dir
                / f"{row['error_type']}_{row['error_rate']}_throughput_plot.png"
            )
            plt.savefig(throughput_plot_path)
            plt.clf()
            plt.close()
    except Exception as e:
        print(f"Plotting throughput failed with: {e}. Continuing...")

    # Plot repair time for increasing numbers of tuples
    try:
        # Create plot for each error type, rate, and repairability
        eval_repair_time: pl.DataFrame = (
            evals.sort("n_tuples")
            .group_by(
                ["error_type", "error_rate", "repairability"], maintain_order=True
            )
            .agg(
                pl.col("n_tuples"),
                pl.col("order_fds_time") * 1000,
                pl.col("build_fd_pattern_graph_time") * 1000,
                pl.col("repair_time") * 1000,
                pl.col("total_time") * 1000,
            )
        )
        for row in eval_repair_time.iter_rows(named=True):
            ms_s_min: str = "ms"
            if row["total_time"][0] > 60000:
                # Switch to minutes if total time of the first entry is larger than 1min
                ms_s_min = "min"
                row["order_fds_time"] = [time / 60000 for time in row["order_fds_time"]]
                row["build_fd_pattern_graph_time"] = [
                    time / 1000 for time in row["build_fd_pattern_graph_time"]
                ]
                row["repair_time"] = [time / 60000 for time in row["repair_time"]]
                row["total_time"] = [time / 60000 for time in row["total_time"]]
            if row["total_time"][0] > 1000:
                # Switch to seconds if total time of the first entry is larger than 1s
                ms_s_min = "s"
                row["order_fds_time"] = [time / 1000 for time in row["order_fds_time"]]
                row["build_fd_pattern_graph_time"] = [
                    time / 1000 for time in row["build_fd_pattern_graph_time"]
                ]
                row["repair_time"] = [time / 1000 for time in row["repair_time"]]
                row["total_time"] = [time / 1000 for time in row["total_time"]]

            # Skip if only one point
            if len(row["n_tuples"]) < 2:
                continue
            bottom: list[int] = [0 for t in row["n_tuples"]]
            width: float = (row["n_tuples"][1] - row["n_tuples"][0]) * 0.9
            sub_times: dict[str, str] = {
                "order_fds_time": "Ordering FDs",
                "build_fd_pattern_graph_time": "Building FD Pattern graph",
                "repair_time": "Applying repairs",
            }
            for key, label in sub_times.items():
                bar = plt.bar(
                    row["n_tuples"], row[key], width=width, label=label, bottom=bottom
                )
                plt.bar_label(
                    bar,
                    labels=[round(value, 2) for value in row[key]],
                    label_type="center",
                )
                bottom = [sum(values) for values in zip(bottom, row[key], strict=True)]
            plt.xticks(row["n_tuples"])
            if row["n_tuples"][0] > 1000000:
                plt.gca().xaxis.set_major_formatter(
                    ticker.FuncFormatter(millions_formatter)
                )
            plt.xlabel("Number of tuples")
            plt.ylabel(f"Repair time ({ms_s_min})")
            plt.grid(axis="y")
            plt.legend()
            plt.tight_layout()
            repair_time_plot_path: Path = (
                output_dir
                / f"{row['error_type']}_{row['error_rate']}_{row['repairability']}_repair_time_plot.png"
                if row["repairability"] is not None
                else output_dir
                / f"{row['error_type']}_{row['error_rate']}_repair_time_plot.png"
            )
            plt.savefig(repair_time_plot_path)
            plt.clf()
            plt.close()

            # Total time plots
            plt.bar(
                row["n_tuples"], row["total_time"], width=width * 0.8, edgecolor="black"
            )
            plt.xticks(row["n_tuples"])
            if row["n_tuples"][0] > 1000000:
                plt.gca().xaxis.set_major_formatter(
                    ticker.FuncFormatter(millions_formatter)
                )
            plt.xlabel("Number of tuples")
            plt.ylabel(f"Total repair time ({ms_s_min})")
            plt.grid(axis="y")
            plt.tight_layout()
            total_time_plot_path: Path = (
                output_dir
                / f"{row['error_type']}_{row['error_rate']}_{row['repairability']}_total_time_plot.png"
                if row["repairability"] is not None
                else output_dir
                / f"{row['error_type']}_{row['error_rate']}_total_time_plot.png"
            )
            plt.savefig(total_time_plot_path)
            plt.clf()
            plt.close()
    except Exception as e:
        print(f"Plotting repair time failed with: {e}. Continuing...")


def plot_all(results: pl.DataFrame, output_dir: Path) -> None:
    """Creates plots for all datasets from the results .csv file."""
    # Group by datasets
    results = results.group_by("dataset").agg(
        pl.col("error_type"),
        pl.col("error_rate"),
        pl.col("repairability"),
        pl.col("n_tuples"),
        pl.col("f1"),
        pl.col("order_fds_time"),
        pl.col("build_fd_pattern_graph_time"),
        pl.col("repair_time"),
        pl.col("total_time"),
        pl.col("tuples_per_s"),
    )
    # Create plots for each dataset under the respective output directory
    for row in results.iter_rows(named=True):
        evals: pl.DataFrame = pl.DataFrame(row)
        plot_dataset(evals, output_dir / row["dataset"])


def main(
    horizon_path: Path,
    all_datasets_dir: Path,
    output_dir: Path,
    build_graph_on_subset: bool,
    plot_only: bool,
) -> None:
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file: Path = output_dir / "benchmark_results.csv"

    # If plot_only flag is given, plot results from csv file and exit
    if plot_only:
        plot_all(pl.read_csv(results_file), output_dir)
        return

    # Create results csv file and write header
    with open(results_file, "a", newline="") as csv_file:
        writer: csv.DictWriter = csv.DictWriter(csv_file, fieldnames=FIELD_NAMES)
        writer.writeheader()

    # Find all datasets
    datasets: list[Path] = find_datasets(all_datasets_dir)
    print(f"Found {len(datasets)} dataset.")

    # Run and plot each dataset
    for i, dataset_path in enumerate(datasets):
        # Create output directory for each dataset
        dataset_output_dir: Path = output_dir / dataset_path.name
        dataset_output_dir.mkdir(exist_ok=True)

        print(f"\nStarting runs for dataset {i + 1}/{len(datasets)}.\n")

        # Run Horizon
        evaluation: list[dict] = run_horizon_benchmark(
            horizon_path,
            dataset_path,
            dataset_output_dir,
            results_file,
            build_graph_on_subset,
        )
        # Remove dataset output directory if benchmark failed
        if len(evaluation) == 0:
            dataset_output_dir.rmdir()
            continue

        print(f"\nPlotting runs for dataset {i + 1}/{len(datasets)}.\n")
        plot_dataset(pl.DataFrame(evaluation), dataset_output_dir)


if __name__ == "__main__":
    # Parse arguments
    args: argparse.Namespace = parser.parse_args()

    main(
        Path(args.horizon_path),
        Path(args.all_datasets_dir),
        Path(args.output_dir),
        args.build_graph_on_subset,
        args.plot_only,
    )
