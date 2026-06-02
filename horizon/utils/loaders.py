from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
import polars as pl
from fds.fd import FunctionalDependency
from fds.set_of_fds import SetOfFDs

from .logging_config import get_logger

logger = get_logger(__name__)


class FDLoader(ABC):
    @abstractmethod
    def load(self, source) -> SetOfFDs: ...


class CSVFDLoader(FDLoader):
    def __init__(
        self, lhs_column_name: str = "from", rhs_column_name: str = "to"
    ) -> None:
        self._lhs_column_name: str = lhs_column_name
        self._rhs_column_name: str = rhs_column_name
        logger.debug(
            f"Initialized CSVFDLoader with LHS column: {lhs_column_name}, RHS column: {rhs_column_name}"
        )

    def load(self, source: str | Path) -> SetOfFDs:
        logger.debug(f"Loading FDs from CSV: {source}")
        df = pd.read_csv(source)
        logger.debug(f"Loaded CSV with {len(df)} rows")
        set_of_fds = SetOfFDs()
        for _, row in df.iterrows():
            # composite LHS is ";"-separated; lowercase to match load_table's columns
            lhs = tuple(
                attr.strip().lower()
                for attr in str(row[self._lhs_column_name]).split(";")
            )
            rhs = str(row[self._rhs_column_name]).strip().lower()
            set_of_fds.add_fd(FunctionalDependency(lhs, rhs))
        logger.info(f"Loaded {len(set_of_fds)} functional dependencies from {source}")
        return set_of_fds


_EXTENSION_LOADERS: dict[str, type[FDLoader]] = {
    ".csv": CSVFDLoader,
}


def get_fds(source: str | Path, loader: FDLoader | None = None) -> SetOfFDs:
    logger.debug(f"Getting FDs from source: {source}")
    if loader is None:
        ext = Path(source).suffix.lower()
        logger.debug(f"File extension: {ext}")
        loader_cls = _EXTENSION_LOADERS.get(ext)
        if loader_cls is None:
            logger.error(f"No loader registered for extension '{ext}'")
            raise ValueError(f"No loader registered for extension '{ext}'")
        loader = loader_cls()
    return loader.load(source)


def _scan_csv(source: str | Path) -> pl.LazyFrame:
    return pl.scan_csv(source, infer_schema_length=10_000)


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
    ext = Path(source).suffix.lower()
    scanner = _SCANNERS.get(ext)
    if scanner is None:
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
