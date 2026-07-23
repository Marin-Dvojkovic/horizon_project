"""SetOfFDs: the collection of FDs (Sigma) defined over a relation (paper §3.1).

Owns the FD list plus the derived attribute sets — all attributes, bound
attributes (§4.2), and source attributes (bound and never an RHS) — and keeps FD
indices unique. Assumed minimal and in canonical form per §3.1.
"""

from collections.abc import Iterator

from .fd import FunctionalDependency


class SetOfFDs:
    """Collection of FDs (Sigma) with derived attribute sets (paper §3.1, §4.2).

    Holds the ordered FD list and caches the union of all attributes, the bound
    attributes (never an RHS; §4.2), and the source attributes (bound and never
    an RHS). Value-equal and hashable; supports indexing, iteration and len.
    """

    _set_of_fds: list[FunctionalDependency]
    _unique_attributes: set[str]
    _bound_attributes: set[str]
    _source_attributes: set[str]

    def __init__(
        self,
        set_of_fds: list[FunctionalDependency] | None,
        bound_attributes: set[str] | None = None,
    ) -> None:
        """Initialise the set, reindexing FDs and caching derived attributes.

        FDs are sorted by index and reassigned contiguous unique indices, so any
        missing, duplicate or skipped indices are normalised.

        Args:
            set_of_fds: The FDs to hold, or None for an empty set.
            bound_attributes: Bound attributes (§4.2); defaults to empty.
        """
        # SetOfFDs manages FDs and their indices, which should always be unique
        if set_of_fds is not None:
            # Sort set by index and reassign unique indices
            # in case of missing indices, duplicates or skipped indices
            self._set_of_fds = sorted(set_of_fds, key=lambda fd: fd.index)
            for i, fd in enumerate(self._set_of_fds):
                fd.index = i
        else:
            self._set_of_fds = []
        self._bound_attributes = bound_attributes if bound_attributes is not None else set()
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
        """The FDs held, ordered by index."""
        return self._set_of_fds

    @property
    def unique_attributes(self) -> set[str]:
        """Union of all attributes appearing in any FD."""
        return self._unique_attributes

    @property
    def bound_attributes(self) -> set[str]:
        """Bound attributes: those never appearing as an FD RHS (§4.2)."""
        return self._bound_attributes

    @bound_attributes.setter
    def bound_attributes(self, bound_attributes: set[str]) -> None:
        self._bound_attributes = bound_attributes

    @property
    def source_attributes(self) -> set[str]:
        """Source attributes: bound attributes that are never an FD RHS."""
        return self._source_attributes

    @source_attributes.setter
    def source_attributes(self, source_attributes: set[str]) -> None:
        self._source_attributes = source_attributes

    def get_ordered_set_of_fds(self) -> list[FunctionalDependency]:
        """Return the FDs in traversal order (set by static_fd_analysis.py, §5.1).

        Returns:
            FDs sorted by their `order`; FDs with no order sort last.
        """
        return sorted(
            self._set_of_fds,
            key=lambda fd: fd.order if fd.order is not None else len(self._set_of_fds),
        )

    def add_fd(self, fd: FunctionalDependency) -> None:
        """Append an FD, giving it a unique index and refreshing unique attributes.

        Args:
            fd: The FunctionalDependency to append; its index is overwritten.
        """
        # NOTE: only _unique_attributes is refreshed here — _bound_attributes and
        # _source_attributes (computed once at construction) go stale on this
        # incremental-add path. Defect: not fixed.
        new_index: int = len(self._set_of_fds)
        fd.index = new_index
        self._set_of_fds.append(fd)
        self._unique_attributes.update(set(attribute for attribute in fd.get_attributes()))

    def as_tuple_list(self) -> list[tuple]:
        """Return the FDs as a list of (lhs, rhs) tuples.

        Returns:
            One (lhs, rhs) tuple per FD, in index order.
        """
        return [fd.as_tuple() for fd in self._set_of_fds]

    def is_bound(self, attribute: str) -> bool:
        """Return whether the attribute is bound (§4.2).

        Args:
            attribute: Attribute name to test.

        Returns:
            True if the attribute is in the bound set.
        """
        return attribute in self._bound_attributes

    def is_source(self, attribute: str) -> bool:
        """Return whether the attribute is a source column (never an FD RHS).

        Args:
            attribute: Attribute name to test.

        Returns:
            True if the attribute is in the source set.
        """
        return attribute in self._source_attributes

    def __repr__(self) -> str:
        return str(self._set_of_fds)

    def __eq__(self, other: object) -> bool:
        """Value equality on the contained FD list."""
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
