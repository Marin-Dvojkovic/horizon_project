from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from .fd import FunctionalDependency
from .logging_config import get_logger

logger = get_logger(__name__)


class FDLoader(ABC):
    @abstractmethod
    def load(self, source) -> list[FunctionalDependency]: ...


class CSVFDLoader(FDLoader):
    def __init__(
        self, lhs_column_name: str = "from", rhs_column_name: str = "to"
    ) -> None:
        self._lhs_column_name: str = lhs_column_name
        self._rhs_column_name: str = rhs_column_name
        logger.debug(f"Initialized CSVFDLoader with LHS column: {lhs_column_name}, RHS column: {rhs_column_name}")

    def load(self, source: str | Path) -> list[FunctionalDependency]:
        logger.debug(f"Loading FDs from CSV: {source}")
        df = pd.read_csv(source)
        logger.debug(f"Loaded CSV with {len(df)} rows")
        result = []
        for _, row in df.iterrows():
            lhs = tuple(
                attr.strip() for attr in str(row[self._lhs_column_name]).split(",")
            )
            rhs = str(row[self._rhs_column_name]).strip()
            result.append(FunctionalDependency(lhs, rhs))
        logger.info(f"Loaded {len(result)} functional dependencies from {source}")
        return result


_EXTENSION_LOADERS: dict[str, type[FDLoader]] = {
    ".csv": CSVFDLoader,
}


def get_fds(
    source: str | Path, loader: FDLoader | None = None
) -> list[FunctionalDependency]:
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
