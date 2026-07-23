"""PatternExpression: the composed FD-pattern lineage of one repaired tuple (§5.2).

A repaired tuple is a composition (the ▷ operator) of the FD patterns chased for
it; this container holds that ordered chain and records the tuple it belongs to.
"""

from collections.abc import Iterator

from .fd_pattern import FDPattern


class PatternExpression:
    """Ordered chain of FD patterns forming one tuple's repair lineage (§5.2).

    Each output tuple is a composition of the FD patterns selected while chasing
    the FD pattern graph. Value-equal and hashable (via its string form), and
    also compares equal to that string; supports indexing, iteration and len.
    """

    _fd_patterns: list[FDPattern]

    def __init__(self, tuple_index: int) -> None:
        """Initialise an empty expression for a given tuple.

        Args:
            tuple_index: Index of the tuple this expression repairs.
        """
        self._fd_patterns = []
        self._tuple_index: int = tuple_index

    @property
    def tuple_index(self) -> int:
        """Index of the tuple this expression repairs."""
        return self._tuple_index

    def __repr__(self) -> str:
        joined_patterns: str = " ▷ ".join(str(fd_pattern) for fd_pattern in self._fd_patterns)
        return f"t{self._tuple_index}: {joined_patterns}"

    def __eq__(self, other: object) -> bool:
        """Value equality via string form; also compares equal to that string."""
        if isinstance(other, str):
            return str(self) == other
        elif not isinstance(other, PatternExpression):
            return NotImplemented
        return str(self) == str(other)

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash(str(self))

    # Allows instances of this class to be indexed using square brackets
    def __getitem__(self, index: int) -> FDPattern:
        return self._fd_patterns[index]

    def __iter__(self) -> Iterator[FDPattern]:
        return iter(self._fd_patterns)

    def __len__(self) -> int:
        return len(self._fd_patterns)

    def add_fd_pattern(self, fd_pattern: FDPattern) -> None:
        """Append an FD pattern to the end of the composition.

        Args:
            fd_pattern: The FDPattern to append.
        """
        self._fd_patterns.append(fd_pattern)

    def attribute_in_expression(self, attribute: str) -> FDPattern | None:
        """Find the pattern whose FD determines the given attribute (its RHS).

        Args:
            attribute: RHS attribute name to look up.

        Returns:
            The first FDPattern with that RHS attribute, or None if absent.
        """
        for fd_pattern in self._fd_patterns:
            if fd_pattern.fd.rhs == attribute:
                return fd_pattern
        return None
