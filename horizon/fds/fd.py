class FunctionalDependency:
    _order: int | None

    def __init__(
        self, lhs: tuple | list | str, rhs: str, order: int | None = None
    ) -> None:
        if isinstance(lhs, str):
            self._lhs = (lhs,)
        else:
            self._lhs = tuple(lhs)
        self._rhs = rhs
        self._order = order

    @property
    def lhs(self) -> str | tuple:
        if len(self._lhs) == 1:
            return self._lhs[0]
        return self._lhs

    @property
    def rhs(self) -> str:
        return self._rhs

    @property
    def order(self) -> int | None:
        return self._order

    @order.setter
    def order(self, order: int) -> None:
        self._order = order

    def __repr__(self) -> str:
        lhs_str = ", ".join(self._lhs)
        return f"FD({lhs_str} -> {self._rhs})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple):
            return self.lhs == other[0] and self._rhs == other[1]
        elif not isinstance(other, FunctionalDependency):
            return NotImplemented
        return self.lhs == other.lhs and self._rhs == other._rhs

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash((self.lhs, self._rhs))

    def as_tuple(self) -> tuple:
        return (self.lhs, self._rhs)

    def get_attributes(self) -> list[str]:
        return [*self._lhs, self.rhs]
