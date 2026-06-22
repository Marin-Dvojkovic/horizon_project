import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

import polars as pl

from eval.effectiveness_eval import evaluate_repair

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
    elapsed_time: float,
) -> dict:
    """Calls our evaluation module to evaluate the effectiveness of the data repairs. Also adds repair time and throughput.
    If a file cannot be read or the evaluation fails, some metrics will not be recorded."""
    dirty_data: pl.DataFrame = pl.read_csv(dirty_data_path, infer_schema=False)

    # TODO: Get repair time directly from repair time statistics txt file

    # Add repair time and throughput to evaluation
    fixed_metrics: dict = {
        "n_tuples": len(dirty_data),
        "repair_time": round(elapsed_time, 3),
        "tuples_per_s": round(len(dirty_data) / elapsed_time, 3),
    }

    try:
        clean_data: pl.DataFrame = pl.read_csv(clean_data_path, infer_schema=False)
        cleaned_data: pl.DataFrame = pl.read_csv(cleaned_data_path, infer_schema=False)

        # Call evaluation
        evaluation: dict = evaluate_repair(clean_data, dirty_data, cleaned_data)
        evaluation.update(fixed_metrics)
    except Exception as e:
        print(f"Evaluation failed with {e}. Continuing...")
        return fixed_metrics

    return evaluation


def run_horizon(
    horizon_path: Path, dataset_path: Path, output_path: Path
) -> list[dict]:
    """Runs Horizon for the given dataset, for each error type and rate. Returns a list of evaluated runs."""
    evaluated_runs: list[dict] = []
    dataset_name: str = dataset_path.name

    # Get all dirty data files
    dirty_data_files: list[str] = ["dirty.csv"]
    if not (dataset_path / "dirty.csv").exists():
        injected_path: Path = dataset_path / "injected"
        if not injected_path.exists():
            print(
                f"\nNo dirty data file found. Skipping benchmarks for dataset {dataset_path.name}."
            )
            return []
        dirty_data_files = [
            str(Path("injected") / injected_data.name)
            for injected_data in injected_path.glob("*_r*.csv")
        ]

    # Get number of FDs
    fd_files: list[Path] = sorted(
        list(dataset_path.glob("fds.*")),
        key=lambda path: path.suffix.lower() != ".csv",
    )
    n_fds: int = 0
    if len(fd_files) < 1:
        print(f"No FD file found under {str(dataset_path)}")
    else:
        line_count: int = sum(1 for line in open(fd_files[0], "r").readlines())
        n_fds = line_count - 1 if fd_files[0].suffix == ".csv" else line_count

    # TODO: Load n tuples to show linear repair time

    # Run Horizon for each error type and rate
    for dirty_data_file in dirty_data_files:
        dirty_data_path: Path = dataset_path / Path(dirty_data_file)

        # Create sub-directory for each dirty data file
        dirty_data_output_dir: Path = (
            output_path / dirty_data_path.stem
            if dirty_data_file != "dirty.csv"
            else output_path
        )
        dirty_data_output_dir.mkdir(exist_ok=True)

        # Get dataset properties
        error_type, _, error_rate = dirty_data_path.stem.partition("_r")

        # Run benchmark command
        benchmark_cmd: list[str] = [
            sys.executable,
            str(horizon_path),
            "--dataset_dir",
            str(dataset_path),
            "--dirty_data_file",
            str(dirty_data_file),
            "--output_dir",
            str(dirty_data_output_dir),
            "--log_level",
            "WARNING",
        ]

        print(
            f"\nNow running benchmarks for dataset {dataset_name} with dirty data {dirty_data_file}."
        )
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
                    "error_rate": int(error_rate) * 0.01 if error_rate != "" else None,
                    "n_fds": n_fds,
                }
            )
            continue

        elapsed_time: float = end_time - start_time

        print(f"{dataset_name} completed in {elapsed_time:.2f}s.")

        # Compute evaluation
        evaluation: dict = eval_run(
            dataset_path / "clean.csv",
            dirty_data_path,
            dirty_data_output_dir / f"{dataset_name}_cleaned_data.csv",
            elapsed_time,
        )

        # If no error rate given, calculate via n_dirty / n_tuples
        dirty_data_properties: dict = {
            "dataset": dataset_name,
            "error_type": error_type,
            "error_rate": int(error_rate) * 0.01
            if error_rate != ""
            else round(evaluation["n_dirty"] / evaluation["n_tuples"], 3)
            if "n_dirty" in evaluation
            else None,
            "n_fds": n_fds,
        }

        # Combine evaluation and dataset properties
        evaluation.update(dirty_data_properties)

        evaluated_runs.append(evaluation)

    return evaluated_runs


def main(horizon_path: Path, all_datasets_dir: Path, output_dir: Path) -> None:
    # Create output directory and results csv file
    output_dir.mkdir(parents=True, exist_ok=True)
    results_file: Path = output_dir / "benchmark_results.csv"
    with open(results_file, "a", newline="") as csv_file:
        fieldnames: list[str] = [
            "dataset",
            "error_type",
            "error_rate",
            "n_fds",
            "n_tuples",
            "n_dirty",
            "n_repaired",
            "n_correct",
            "precision",
            "recall",
            "f1",
            "repair_time",
            "tuples_per_s",
        ]
        writer: csv.DictWriter = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

    # Find all datasets
    datasets: list[Path] = find_datasets(all_datasets_dir)
    print(f"Found {len(datasets)} dataset.")

    for dataset_path in datasets:
        # Create output directory for each dataset
        dataset_output_dir: Path = output_dir / dataset_path.name
        dataset_output_dir.mkdir(exist_ok=True)

        # Run Horizon
        evaluation: list[dict] = run_horizon(
            horizon_path, dataset_path, dataset_output_dir
        )
        # Remove dataset output directory if benchmark failed
        if len(evaluation) == 0:
            dataset_output_dir.rmdir()
            continue
        # Write evaluation to results csv
        with open(results_file, "a", newline="") as csv_file:
            writer: csv.DictWriter = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writerows(evaluation)

        # TODO: Plots


if __name__ == "__main__":
    # Parse arguments
    args: argparse.Namespace = parser.parse_args()

    main(Path(args.horizon_path), Path(args.all_datasets_dir), Path(args.output_dir))
