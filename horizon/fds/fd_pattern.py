"""FDPattern: an FD instantiated on concrete data values (paper §3.2)."""

from .fd import FunctionalDependency


class FDPattern:
    """An FD pattern (X -> Y, [lval, rval]): an FD bound to concrete values.

    Encodes a directed hyperedge of the FD pattern graph (§3.2): the LHS values
    map to a single RHS value under a given FD. Value-equal and hashable so
    patterns work as dict/set keys.
    """

    def __init__(self, fd: FunctionalDependency, lval: tuple | list | str, rval: str) -> None:
        """Initialise a pattern, normalising the LHS value to a tuple.

        Args:
            fd: The FunctionalDependency this pattern instantiates.
            lval: LHS value(s); a bare str becomes a 1-tuple.
            rval: The RHS value the LHS maps to.
        """
        self._fd = fd
        if isinstance(lval, str):
            self._lval = (lval,)
        else:
            self._lval = tuple(lval)
        self._rval = rval

    @property
    def fd(self) -> FunctionalDependency:
        """The FunctionalDependency this pattern instantiates."""
        return self._fd

    @property
    def lval(self) -> tuple:
        """LHS value(s) as a tuple."""
        return self._lval

    @property
    def rval(self) -> str:
        """The RHS value the LHS maps to."""
        return self._rval

    def __repr__(self) -> str:
        lval_str = ", ".join(self._lval)
        return f"([{str(self._fd)}], '{lval_str}' -> '{self._rval}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FDPattern):
            return NotImplemented
        return self._fd == other._fd and self._lval == other._lval and self._rval == other._rval

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash(str(self))
