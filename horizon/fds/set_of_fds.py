from typing import Iterator

from .fd import FunctionalDependency


class SetOfFDs:
    _set_of_fds: list[FunctionalDependency]
    _unique_attributes: set[str]
    _bound_attributes: set[str]

    def __init__(
        self,
        set_of_fds: list[FunctionalDependency] | None = None,
        bound_attributes: set[str] | None = None,
    ) -> None:
        # default to fresh containers; shared mutable defaults would leak FDs
        # across instances (e.g. load_fds() builds several in one process)
        self._set_of_fds = set_of_fds if set_of_fds is not None else []
        self._bound_attributes = (
            bound_attributes if bound_attributes is not None else set()
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

    def get_ordered_set_of_fds(self) -> list[FunctionalDependency]:
        return sorted(
            self._set_of_fds,
            key=lambda fd: fd.order if fd.order is not None else len(self._set_of_fds),
        )

    def add_fd(self, fd: FunctionalDependency) -> None:
        self._set_of_fds.append(fd)
        self._unique_attributes.update(
            set(attribute for attribute in fd.get_attributes())
        )

    def as_tuple_list(self) -> list[tuple]:
        return [fd.as_tuple() for fd in self._set_of_fds]
