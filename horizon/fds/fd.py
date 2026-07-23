"""FunctionalDependency: a single FD X -> Y (composite LHS, single RHS attribute).

Models the canonical FDs of Horizon §3.1: LHS is normalised to a tuple, and the
class is hashable and value-equal so instances work as dict/set keys.
"""


class FunctionalDependency:
    """A functional dependency X -> Y over relation attributes (paper §3.1).

    LHS (antecedent) is normalised to a tuple so composite and singleton LHSs
    share one representation; RHS (consequent) is a single attribute. Equality
    and hashing are value-based, so instances serve as dict/set keys.

    Attributes:
        index: Position of this FD within its SetOfFDs.
        order: Traversal order assigned by static analysis (§5.1), or None.
        cyclic: Whether the FD lies on a cycle, set by static analysis, or None.
    """

    _index: int
    _order: int | None
    _cyclic: bool | None

    def __init__(
        self,
        lhs: tuple | list | str,
        rhs: str,
        index: int = 0,
        order: int | None = None,
    ) -> None:
        """Initialise an FD, normalising the LHS to a tuple.

        Args:
            lhs: Antecedent attribute(s); a bare str becomes a 1-tuple.
            rhs: Consequent (RHS) attribute.
            index: Position within a SetOfFDs.
            order: Traversal order from static analysis (§5.1), or None.
        """
        if isinstance(lhs, str):
            self._lhs = (lhs,)
        else:
            self._lhs = tuple(lhs)
        self._rhs = rhs
        self._index = index
        self._order = order
        self._cyclic = None

    @property
    def lhs(self) -> str | tuple:
        """LHS as a bare str for a singleton, else the full tuple."""
        if len(self._lhs) == 1:
            return self._lhs[0]
        return self._lhs

    @property
    def lhs_attributes(self) -> tuple:
        """LHS as a tuple of attribute names regardless of arity.

        Unlike `lhs`, which returns a bare str for a singleton LHS — iterating
        that str yields characters, not attributes. Use this whenever the LHS is
        treated as a column set.
        """
        return self._lhs

    @property
    def rhs(self) -> str:
        """Consequent (RHS) attribute."""
        return self._rhs

    @property
    def index(self) -> int:
        """Position of this FD within its SetOfFDs."""
        return self._index

    @index.setter
    def index(self, index: int) -> None:
        self._index = index

    @property
    def order(self) -> int | None:
        """Traversal order assigned by static analysis (§5.1), or None."""
        return self._order

    @order.setter
    def order(self, order: int) -> None:
        self._order = order

    @property
    def cyclic(self) -> bool | None:
        """Whether this FD lies on a cycle (set by static analysis), or None."""
        return self._cyclic

    @cyclic.setter
    def cyclic(self, cyclic: bool) -> None:
        self._cyclic = cyclic

    def __repr__(self) -> str:
        lhs_str = ", ".join(self._lhs)
        return f"FD({lhs_str} -> {self._rhs})"

    def __eq__(self, other: object) -> bool:
        """Value equality; also compares equal to an (lhs, rhs) tuple."""
        if isinstance(other, tuple):
            return self.lhs == other[0] and self._rhs == other[1]
        elif not isinstance(other, FunctionalDependency):
            return NotImplemented
        return self.lhs == other.lhs and self._rhs == other._rhs

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash((self.lhs, self._rhs))

    def as_tuple(self) -> tuple:
        """Return the FD as an (lhs, rhs) tuple.

        Returns:
            Tuple of (lhs, rhs), where lhs follows the `lhs` property's shape.
        """
        return (self.lhs, self._rhs)

    def get_attributes(self) -> list[str]:
        """Return all attributes of the FD, LHS attributes followed by the RHS.

        Returns:
            List of LHS attribute names with the RHS appended.
        """
        return [*self._lhs, self.rhs]
