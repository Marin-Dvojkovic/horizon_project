from typing import Iterator

from .fd import FunctionalDependency


class SetOfFDs:
    _set_of_fds: list[FunctionalDependency]
    _unique_attributes: set[str]
    _bound_attributes: set[str]
    _source_attributes: set[str]

    def __init__(
        self,
        set_of_fds: list[FunctionalDependency] | None,
        bound_attributes: set[str] | None = None,
    ) -> None:
        # SetOfFDs manages FDs and their indices, which should always be unique
        if set_of_fds is not None:
            # Sort set by index and reassign unique indices
            # in case of missing indices, duplicates or skipped indices
            self._set_of_fds = sorted(set_of_fds, key=lambda fd: fd.index)
            for i, fd in enumerate(self._set_of_fds):
                fd.index = i
        else:
            self._set_of_fds = []
        self._bound_attributes = (
            bound_attributes if bound_attributes is not None else set()
        )
        self._source_attributes = (
            set(
                attribute
                for attribute in bound_attributes
                if attribute not in set(fd.rhs for fd in set_of_fds)
            )
            if set_of_fds is not None and bound_attributes is not None
            else set()
        )
        self._unique_attributes = {
            attribute for fd in self._set_of_fds for attribute in fd.get_attributes()
        }

    @property
    def set_of_fds(self) -> list[FunctionalDependency]:
        return self._set_of_fds

    @property
    def unique_attributes(self) -> set[str]:
        return self._unique_attributes

    @property
    def bound_attributes(self) -> set[str]:
        return self._bound_attributes

    @bound_attributes.setter
    def bound_attributes(self, bound_attributes: set[str]) -> None:
        self._bound_attributes = bound_attributes

    @property
    def source_attributes(self) -> set[str]:
        return self._source_attributes

    @source_attributes.setter
    def source_attributes(self, source_attributes: set[str]) -> None:
        self._source_attributes = source_attributes

    def get_ordered_set_of_fds(self) -> list[FunctionalDependency]:
        """Returns ordered set of FDs, set by static_fd_analyis.py."""
        return sorted(
            self._set_of_fds,
            key=lambda fd: fd.order if fd.order is not None else len(self._set_of_fds),
        )

    def add_fd(self, fd: FunctionalDependency) -> None:
        """Adds a new FD, adjusting its index (to preserve uniqueness),
        and updating unique attributes."""
        new_index: int = len(self._set_of_fds)
        fd.index = new_index
        self._set_of_fds.append(fd)
        self._unique_attributes.update(
            set(attribute for attribute in fd.get_attributes())
        )

    def as_tuple_list(self) -> list[tuple]:
        """Returns the set of FDs as tuples"""
        return [fd.as_tuple() for fd in self._set_of_fds]

    def is_bound(self, attribute: str) -> bool:
        """True if attribute is bound."""
        return attribute in self._bound_attributes

    def is_source(self, attribute: str) -> bool:
        """True if attribute never appears as an FD RHS (a source column)."""
        return attribute in self._source_attributes

    def __repr__(self) -> str:
        return str(self._set_of_fds)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SetOfFDs):
            return NotImplemented
        return self._set_of_fds == other.set_of_fds

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash(str(self))

    # Allows instances of this class to be indexed using square brackets
    def __getitem__(self, index: int) -> FunctionalDependency:
        return self._set_of_fds[index]

    def __iter__(self) -> Iterator[FunctionalDependency]:
        return iter(self._set_of_fds)

    def __len__(self) -> int:
        return len(self._set_of_fds)
