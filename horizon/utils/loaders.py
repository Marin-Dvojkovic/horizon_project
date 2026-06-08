from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs

from .logging_config import get_logger

logger = get_logger(__name__)


class FDLoader(ABC):
    @abstractmethod
    def load(self, source) -> SetOfFDs: ...


class CSVFDLoader(FDLoader):
    def __init__(self) -> None:
        logger.debug("Initialized CSVFDLoader")

    def load(self, source: str | Path) -> SetOfFDs:
        logger.debug(f"Loading FDs from CSV: {source}")
        df: pl.DataFrame = pl.read_csv(source)
        if len(df.columns) < 2:
            logger.error(f"CSV has less than two columns: {df.columns}")
            raise ValueError(f"CSV has less than two columns: {df.columns}")
        logger.debug(f"Loaded CSV with {len(df)} rows")

        set_of_fds: SetOfFDs = SetOfFDs()

        for row in df.iter_rows():
            # composite LHS is ";"-separated; lowercase to match load_table's columns
            lhs: tuple[str] = tuple(
                attr.strip().lower() for attr in str(row[0]).split(";")
            )
            rhs: str = str(row[1]).strip().lower()
            set_of_fds.add_fd(FunctionalDependency(lhs, rhs))

        logger.info(f"Loaded {len(set_of_fds)} functional dependencies from {source}")
        return set_of_fds


class TXTFDLoader(FDLoader):
    def __init__(self, columns_csv_path: Path, separator: str = "->") -> None:
        if not columns_csv_path.exists:
            logger.error(f"CSV file {str(columns_csv_path)} does not exist")
            raise ValueError(f"CSV file {str(columns_csv_path)} does not exist")
        self._column_names = self.load_column_names(columns_csv_path)
        self._separator: str = separator
        logger.debug(
            f"Initialized TXTFDLoader with columns: {self._column_names}, separator: {separator}"
        )

    def load_column_names(self, columns_csv_path: Path) -> list[str]:
        # Read only the header (no rows needed) using Polars
        try:
            df: pl.DataFrame = pl.read_csv(str(columns_csv_path), n_rows=0)
            return list(df.columns)
        except Exception:
            # Fallback: try reading full file then columns
            try:
                df: pl.DataFrame = pl.read_csv(str(columns_csv_path))
                return list(df.columns)
            except Exception:
                return []

    def parse_line(self, line) -> tuple[list[str], str] | None:
        parts = line.split(self._separator)
        if len(parts) != 2:
            return None
        lhs_indices: list[str] = [
            s.strip() for s in parts[0].strip().split(",") if s.strip()
        ]
        rhs_index: str = parts[1].strip()
        return lhs_indices, rhs_index

    def load(self, source: str | Path) -> SetOfFDs:
        logger.debug(f"Loading FDs from TXT: {source}")

        set_of_fds: SetOfFDs = SetOfFDs()
        colnames: list[str] = self._column_names

        with open(source, "r", encoding="utf-8") as f:
            lines = f.readlines()
        logger.debug(f"Loaded TXT with {len(lines)} rows")

        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parsed: tuple[list[str], str] | None = self.parse_line(line)
            if parsed is None:
                continue
            lhs: tuple[str] = tuple(colnames[int(x)] for x in parsed[0])
            rhs: str = colnames[int(parsed[1])]
            set_of_fds.add_fd(FunctionalDependency(lhs, rhs))

        logger.info(f"Loaded {len(set_of_fds)} functional dependencies from {source}")
        return set_of_fds


_EXTENSION_LOADERS: dict[str, type[FDLoader]] = {
    ".csv": CSVFDLoader,
    ".txt": TXTFDLoader,
}


def get_fds(source: str | Path, columns_csv_path: Path) -> SetOfFDs:
    logger.debug(f"Getting FDs from source: {source}")
    ext: str = Path(source).suffix.lower()
    loader: type[FDLoader] | None = _EXTENSION_LOADERS.get(ext)
    if loader is None:
        logger.error(f"No loader registered for extension '{ext}'")
        raise ValueError(f"No loader registered for extension '{ext}'")
    if loader == TXTFDLoader:
        return TXTFDLoader(columns_csv_path).load(source)
    return loader().load(source)


def _scan_csv(source: str | Path) -> pl.LazyFrame:
    # read every column as Utf8: Horizon treats all cells as strings, and
    # dtype inference would rewrite e.g. "5" -> "5.0" on output
    return pl.scan_csv(source, infer_schema_length=0)


def _scan_parquet(source: str | Path) -> pl.LazyFrame:
    return pl.scan_parquet(source)


_SCANNERS = {
    ".csv": _scan_csv,
    ".parquet": _scan_parquet,
}


def load_table(source: str | Path, columns: list[str] | None = None) -> pl.DataFrame:
    """Read a CSV or Parquet table with column names lowercased.

    Dispatches to a per-extension scanner. Matches the lowercasing in
    `CSVFDLoader` so FDs and DataFrame columns share one casing convention.
    Pass `columns` (any casing) to read only a subset — projection is pushed
    down into the scan so unselected columns are never read. Missing names
    raise ValueError.
    """
    ext: str = Path(source).suffix.lower()
    scanner = _SCANNERS.get(ext)
    if scanner is None:
        logger.error(f"No loader registered for extension '{ext}'")
        raise ValueError(f"No loader registered for extension '{ext}'")
    lf = scanner(source)
    lf = lf.rename({c: c.strip().lower() for c in lf.collect_schema().names()})
    if columns is not None:
        wanted = [c.strip().lower() for c in columns]
        missing = [c for c in wanted if c not in lf.collect_schema().names()]
        if missing:
            raise ValueError(f"columns not found: {missing}")
        lf = lf.select(wanted)
    return lf.collect()
