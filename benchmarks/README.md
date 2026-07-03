# Horizon Benchmarks

This directory holds a benchmarking script [benchmark_horizon.py](benchmark_horizon.py), which runs our Horizon implementation for all datasets under a given directory, using different error types and rates, repairability, as well as different numbers of tuples.

The script summarizes its results under `path/to/output_dir/benchmark_results.csv` and generates plots for each dataset.

## Running the code

In the project directory, run:

```bash
uv run benchmarks/benchmark_horizon.py [--horizon_path horizon/horizon.py] [--all_datasets_dir datasets] [--output_dir output] [--plot_only]
```

Explanation of arguments:

- _--horizon_path_ or _-hp_: Path of `horizon.py`. (default: `horizon/horizon.py`)
- _--all_datasets_dir_ or _-ds_: Directory containing all datasets to be run. (default: `datasets`)
- _--output_dir_ or _-o_: Output directory. (default: `output`)
- _--plot_only_ or _-p_: Skip benchmarking and only plot results, based on `benchmark_results.csv`.

## Plots

The first type of plots (f1_plot) show the F1 score for increasing error rates, the second type of plots show the throughput for increasing number of tuples, and the third type of plots (repair_time_plot) show the repair time for increasing numbers of tuples.
Plots are generated for each dataset, for each error type and rate and repairability combination.
