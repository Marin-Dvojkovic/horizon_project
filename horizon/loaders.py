from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from .fd import FunctionalDependency


class FDLoader(ABC):
    @abstractmethod
    def load(self, source) -> list[FunctionalDependency]:
        ...


class CSVFDLoader(FDLoader):
    def load(self, source: str | Path) -> list[FunctionalDependency]:
        df = pd.read_csv(source)
        result = []
        for _, row in df.iterrows():
            lhs = tuple(attr.strip() for attr in str(row["from"]).split(","))
            rhs = str(row["to"]).strip()
            result.append(FunctionalDependency(lhs, rhs))
        return result


_EXTENSION_LOADERS: dict[str, type[FDLoader]] = {
    ".csv": CSVFDLoader,
}


def get_fds(source: str | Path, loader: FDLoader | None = None) -> list[FunctionalDependency]:
    if loader is None:
        ext = Path(source).suffix.lower()
        loader_cls = _EXTENSION_LOADERS.get(ext)
        if loader_cls is None:
            raise ValueError(f"No loader registered for extension '{ext}'")
        loader = loader_cls()
    return loader.load(source)
