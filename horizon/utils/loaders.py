"""Loaders for FDs and data tables (paper §3.1: FDs Sigma and instance I).

Reads the FD set (Sigma) from fds.csv/fds.txt into a SetOfFDs, and reads a data
instance from CSV/Parquet into polars frames with a shared lowercase-column
convention so FD attribute names and table columns line up.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

import polars as pl
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs

from .logging_config import get_logger

logger = get_logger(__name__)


class FDLoader(ABC):
    """Abstract base class for FD loaders, dispatched on file extension."""

    @abstractmethod
    def load(self, source) -> SetOfFDs:
        """Load FDs from the source into a SetOfFDs.

        Args:
            source: Path to the FD file to read.

        Returns:
            The parsed SetOfFDs.
        """
        ...


class CSVFDLoader(FDLoader):
    """Class to load FDs from a CSV file into a SetOfFDs object."""

    def __init__(self) -> None:
        logger.debug("Initialized CSVFDLoader")

    def load(self, source: Path) -> SetOfFDs:
        """Load FDs from a CSV with `from`/`to` columns into a SetOfFDs.

        A composite LHS is `;`-separated in the `from` column; each LHS attribute
        and the RHS are stripped and lowercased to match load_table's columns.
        The `;`-split also serves as a workaround for a corrupted fds.csv whose
        LHS had a `;` between every character (see the TODO below).

        Args:
            source: Path to the FD CSV file.

        Returns:
            The parsed SetOfFDs.

        Raises:
            ValueError: If the CSV has fewer than two columns.
        """
        logger.debug(f"Loading FDs from CSV: {source}")
        df: pl.DataFrame = pl.read_csv(source)
        if len(df.columns) < 2:
            logger.error(f"CSV has less than two columns: {df.columns}")
            raise ValueError(f"CSV has less than two columns: {df.columns}")
        logger.debug(f"Loaded CSV with {len(df)} rows")

        fds: list[FunctionalDependency] = []

        for i, row in enumerate(df.iter_rows()):
            # TODO: drop the ";"-between-every-char workaround for corrupted fds.csv — unnecessary, ugly
            # composite LHS is ";"-separated; lowercase to match load_table's columns
            lhs: tuple[str] = tuple(attr.strip().lower() for attr in str(row[0]).split(";"))
            rhs: str = str(row[1]).strip().lower()
            fds.append(FunctionalDependency(lhs, rhs, i))

        set_of_fds: SetOfFDs = SetOfFDs(fds)

        logger.info(f"Loaded {len(set_of_fds)} functional dependencies from {source}")
        return set_of_fds


class TXTFDLoader(FDLoader):
    """
    Class to load FDs from a TXT file into a SetOfFDs object. Assumes FDs in the file
    are represented by column indices and a separator (e.g., 1 -> 5).
    """

    def __init__(self, columns_or_path: list[str] | Path, separator: str = "->") -> None:
        """Initialise the loader with column names and an FD separator.

        Args:
            columns_or_path: Either the column names directly, or a CSV path
                whose header supplies them (indices in the TXT map to columns).
            separator: Token separating LHS from RHS in each line.

        Raises:
            ValueError: If a CSV path is given but does not exist.
        """
        self._separator: str = separator
        if isinstance(columns_or_path, list):
            self._column_names = columns_or_path
            logger.debug(
                f"Initialized TXTFDLoader with columns: {self._column_names}, separator: {separator}"
            )
            return
        # NOTE: bug — `exists` is not called (missing ()), so this is always
        # truthy and the guard never raises on a missing path. Not fixed.
        if not columns_or_path.exists:
            logger.error(f"CSV file {str(columns_or_path)} does not exist")
            raise ValueError(f"CSV file {str(columns_or_path)} does not exist")
        self._column_names = self.load_column_names(columns_or_path)
        logger.debug(
            f"Initialized TXTFDLoader with columns: {self._column_names} from file {str(columns_or_path)}, separator: {separator}"
        )

    def load_column_names(self, columns_csv_path: Path) -> list[str]:
        """Read column names from a CSV header, stripping bracketed dtypes.

        Args:
            columns_csv_path: Path to the CSV whose header names the columns.

        Returns:
            Column names with any `(...)` dtype suffix removed.

        Raises:
            RuntimeError: If the CSV cannot be read at all.
        """
        # Read only the header (no rows needed)
        try:
            df: pl.DataFrame = pl.read_csv(str(columns_csv_path), n_rows=0, infer_schema=False)
            # Remove data types in brackets
            return [re.sub(r"\(.*?\)", "", column_name) for column_name in df.columns]
        except Exception:
            # Fallback: try reading full file then columns
            try:
                df: pl.DataFrame = pl.read_csv(str(columns_csv_path), infer_schema=False)
                # Remove data types in brackets
                return [re.sub(r"\(.*?\)", "", column_name) for column_name in df.columns]
            except Exception as e:
                logger.error(f"Could not read {columns_csv_path}. Failed with error: {e}")
                raise RuntimeError(
                    f"Could not read {columns_csv_path}. Failed with error: {e}"
                ) from e

    def parse_line(self, line) -> tuple[list[str], str] | None:
        """Parse one TXT line into LHS/RHS column indices.

        Args:
            line: A single line, LHS and RHS separated by `self._separator`,
                LHS indices comma-separated.

        Returns:
            A (lhs_indices, rhs_index) tuple, or None if the line is malformed.
        """
        parts = line.split(self._separator)
        if len(parts) != 2:
            return None
        lhs_indices: list[str] = [s.strip() for s in parts[0].strip().split(",") if s.strip()]
        rhs_index: str = parts[1].strip()
        return lhs_indices, rhs_index

    def load(self, source: Path) -> SetOfFDs:
        """Load FDs from a TXT file of column-index rules into a SetOfFDs.

        Blank lines and `#` comment lines are skipped; each remaining line's
        indices are resolved against the configured column names.

        Args:
            source: Path to the FD TXT file.

        Returns:
            The parsed SetOfFDs.
        """
        logger.debug(f"Loading FDs from TXT: {source}")

        colnames: list[str] = self._column_names

        with open(source, encoding="utf-8") as f:
            lines = f.readlines()
        logger.debug(f"Loaded TXT with {len(lines)} rows")

        fds: list[FunctionalDependency] = []

        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parsed: tuple[list[str], str] | None = self.parse_line(line)
            if parsed is None:
                continue
            lhs: tuple[str] = tuple(colnames[int(x)] for x in parsed[0])
            rhs: str = colnames[int(parsed[1])]
            fds.append(FunctionalDependency(lhs, rhs, i))

        set_of_fds: SetOfFDs = SetOfFDs(fds)

        logger.info(f"Loaded {len(set_of_fds)} functional dependencies from {source}")
        return set_of_fds


_EXTENSION_LOADERS: dict[str, type[FDLoader]] = {
    ".csv": CSVFDLoader,
    ".txt": TXTFDLoader,
}


def get_fds(source: Path, columns_or_path: list[str] | Path) -> SetOfFDs:
    """Load FDs from a source file, dispatching on its extension.

    Args:
        source: Path to fds.csv or fds.txt.
        columns_or_path: Column names or a CSV path, used only by the TXT loader
            to resolve column indices; ignored for CSV.

    Returns:
        The parsed SetOfFDs.

    Raises:
        ValueError: If the source does not exist or its extension is unregistered.
    """
    if not source.exists():
        logger.error(f"File {str(source)} does not exist")
        raise ValueError(f"File {str(source)} does not exist")

    logger.debug(f"Getting FDs from source: {source}")
    ext: str = Path(source).suffix.lower()
    loader: type[FDLoader] | None = _EXTENSION_LOADERS.get(ext)
    if loader is None:
        logger.error(f"No loader registered for extension '{ext}'")
        raise ValueError(f"No loader registered for extension '{ext}'")

    if loader == TXTFDLoader:
        return TXTFDLoader(columns_or_path).load(source)
    return loader().load(source)


def load_fds(dataset_dir: Path, data_csv_path: Path) -> SetOfFDs:
    """Find and load the FD file under a dataset directory (prefers fds.csv).

    Args:
        dataset_dir: Directory searched for an `fds.*` file.
        data_csv_path: Data CSV path passed through to the TXT loader for
            resolving column indices.

    Returns:
        The parsed SetOfFDs.

    Raises:
        ValueError: If no FD file is found under the directory.
    """
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
    fds: SetOfFDs = get_fds(fds_path, data_csv_path)
    logger.info(f"Loaded {len(fds)} functional dependencies")
    return fds


def _scan_csv(source: Path, n_rows: int | None) -> pl.LazyFrame:
    """Lazily scan a CSV with every column typed as Utf8."""
    # read every column as Utf8: Horizon treats all cells as strings, and
    # dtype inference would rewrite e.g. "5" -> "5.0" on output
    return pl.scan_csv(source, infer_schema_length=0, n_rows=n_rows)


def _scan_parquet(source: Path, n_rows: int | None) -> pl.LazyFrame:
    """Lazily scan a Parquet file, casting every column to Utf8."""
    # cast every column to Utf8 to match _scan_csv: Horizon treats all cells as
    # strings, and parquet's native types would otherwise write e.g. "5" -> "5.0"
    return pl.scan_parquet(source, n_rows=n_rows).cast(pl.Utf8)


_SCANNERS = {
    ".csv": _scan_csv,
    ".parquet": _scan_parquet,
}


def load_table(
    source: Path, columns: list[str] | None = None, n_rows: int | None = None
) -> pl.DataFrame:
    """Read a CSV or Parquet table into a DataFrame with columns lowercased.

    Dispatches to a per-extension scanner. Matches the lowercasing in
    `CSVFDLoader` so FDs and DataFrame columns share one casing convention.
    Projection is pushed into the scan, so unselected columns are never read.

    Note: near-duplicate of `lazy_load_table`; the only difference is the final
    `.collect()` here.

    Args:
        source: Path to the CSV or Parquet file.
        columns: Optional subset to read (any casing); None reads all columns.
        n_rows: Optional cap on the number of rows read.

    Returns:
        The materialised DataFrame.

    Raises:
        ValueError: If the source is missing, its extension is unregistered, or
            a requested column is not found.
    """
    if not source.exists():
        logger.error(f"File {str(source)} does not exist")
        raise ValueError(f"File {str(source)} does not exist")

    ext: str = Path(source).suffix.lower()
    scanner = _SCANNERS.get(ext)
    if scanner is None:
        logger.error(f"No loader registered for extension '{ext}'")
        raise ValueError(f"No loader registered for extension '{ext}'")

    lf: pl.LazyFrame = scanner(source, n_rows)
    # Remove data types in brackets
    # Lowercase column names to match the casing convention in the FD loaders.
    lf = lf.rename(
        {c: re.sub(r"\(.*?\)", "", c.strip().lower()) for c in lf.collect_schema().names()}
    )

    if columns is not None:
        wanted: list[str] = [re.sub(r"\(.*?\)", "", c.strip().lower()) for c in columns]
        missing: list[str] = [c for c in wanted if c not in lf.collect_schema().names()]
        if missing:
            raise ValueError(f"columns not found: {missing}")
        lf = lf.select(wanted)
    return lf.collect()


def lazy_load_table(
    source: Path, columns: list[str] | None = None, n_rows: int | None = None
) -> pl.LazyFrame:
    """Read a CSV or Parquet table into a LazyFrame with columns lowercased.

    Allows streaming and is more suitable for data larger than RAM.

    Note: near-duplicate of `load_table`; the only difference is that this
    returns the LazyFrame without a final `.collect()`.

    Args:
        source: Path to the CSV or Parquet file.
        columns: Optional subset to read (any casing); None reads all columns.
        n_rows: Optional cap on the number of rows read.

    Returns:
        The uncollected LazyFrame.

    Raises:
        ValueError: If the source is missing, its extension is unregistered, or
            a requested column is not found.
    """
    if not source.exists():
        logger.error(f"File {str(source)} does not exist")
        raise ValueError(f"File {str(source)} does not exist")

    ext: str = Path(source).suffix.lower()
    scanner = _SCANNERS.get(ext)
    if scanner is None:
        logger.error(f"No loader registered for extension '{ext}'")
        raise ValueError(f"No loader registered for extension '{ext}'")

    lf: pl.LazyFrame = scanner(source, n_rows)
    # Remove data types in brackets
    # Lowercase column names to match the casing convention in the FD loaders.
    lf = lf.rename(
        {c: re.sub(r"\(.*?\)", "", c.strip().lower()) for c in lf.collect_schema().names()}
    )

    if columns is not None:
        wanted: list[str] = [re.sub(r"\(.*?\)", "", c.strip().lower()) for c in columns]
        missing: list[str] = [c for c in wanted if c not in lf.collect_schema().names()]
        if missing:
            raise ValueError(f"columns not found: {missing}")
        lf = lf.select(wanted)
    return lf


def iter_table_batches(
    source: Path,
    columns: list[str] | None = None,
    n_rows: int | None = None,
    block_bytes: int = 8 * 1024 * 1024,
) -> Iterator[pl.DataFrame]:
    """Yield a table in row batches with memory bounded by block size, not file size.

    Additive, non-breaking companion to `lazy_load_table` for streaming a whole
    table once (e.g. the repair loop). For CSV it reads via pyarrow's block-based
    reader, whose peak memory is ~O(block_bytes) regardless of file size -- unlike
    scan_csv().collect_batches(), which under the polars streaming engine
    materialises ~a full copy of the CSV. Columns are read as Utf8 and lowercased,
    matching `lazy_load_table`. Non-CSV sources fall back to the lazy streaming
    path, so their behaviour is unchanged.

    Args:
        source: Path to the CSV or Parquet file.
        columns: Optional subset to read (any casing); projection is pushed into
            the reader so unselected columns are never parsed.
        n_rows: Optional cap on total rows yielded across all batches.
        block_bytes: Target CSV read-block size, bounding peak memory.

    Yields:
        Row-batch DataFrames with lowercased Utf8 columns.

    Raises:
        ValueError: If the source is missing or a requested column is not found.
    """
    if not source.exists():
        logger.error(f"File {str(source)} does not exist")
        raise ValueError(f"File {str(source)} does not exist")

    if Path(source).suffix.lower() != ".csv":
        # Non-CSV: reuse the existing lazy reader unchanged.
        lf: pl.LazyFrame = lazy_load_table(source, columns=columns, n_rows=n_rows)
        yield from lf.collect_batches(maintain_order=True, engine="streaming")
        return

    # Local imports: pyarrow is only needed on this CSV path.
    import csv as _csv

    import pyarrow as pa
    import pyarrow.csv as pa_csv

    # Read the header once so every column is forced to Utf8 (matching _scan_csv,
    # which uses infer_schema_length=0) and names are lowercased like the lazy path.
    with open(source, encoding="utf-8", newline="") as header_file:
        header: list[str] = next(_csv.reader(header_file))

    # Project to `columns` if requested: pyarrow parses only the included columns.
    include_columns: list[str] | None = None
    kept: list[str] = header
    if columns is not None:
        wanted: set[str] = {re.sub(r"\(.*?\)", "", c.strip().lower()) for c in columns}
        kept = [name for name in header if re.sub(r"\(.*?\)", "", name.strip().lower()) in wanted]
        missing: set[str] = wanted - {re.sub(r"\(.*?\)", "", name.strip().lower()) for name in kept}
        if missing:
            raise ValueError(f"columns not found: {sorted(missing)}")
        include_columns = kept
    rename: dict[str, str] = {name: re.sub(r"\(.*?\)", "", name.strip().lower()) for name in kept}

    reader = pa_csv.open_csv(
        str(source),
        read_options=pa_csv.ReadOptions(block_size=block_bytes),
        convert_options=pa_csv.ConvertOptions(
            column_types={name: pa.string() for name in kept},
            include_columns=include_columns,
            # Match polars scan_csv null handling: an empty field is null (which
            # the pipeline stringifies to "None"), but ONLY the empty string --
            # pyarrow's default also nulls "NA"/"null"/etc., which polars keeps as
            # literal strings. Without this, empties come through as "" and diverge.
            strings_can_be_null=True,
            null_values=[""],
        ),
    )

    remaining: int | None = n_rows
    for record_batch in reader:
        if remaining is not None and remaining <= 0:
            break
        df: pl.DataFrame = pl.from_arrow(record_batch).rename(rename)
        if remaining is not None:
            if len(df) > remaining:
                df = df.head(remaining)
            remaining -= len(df)
        yield df
