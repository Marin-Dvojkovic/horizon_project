class FunctionalDependency:
    def __init__(self, lhs: tuple | list | str, rhs: str) -> None:
        if isinstance(lhs, str):
            self._lhs = (lhs,)
        else:
            self._lhs = tuple(lhs)
        self._rhs = rhs

    @property
    def lhs(self) -> tuple:
        return self._lhs

    @property
    def rhs(self) -> str:
        return self._rhs

    def __repr__(self) -> str:
        lhs_str = ", ".join(self._lhs)
        return f"FD({lhs_str} -> {self._rhs})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FunctionalDependency):
            return NotImplemented
        return self._lhs == other._lhs and self._rhs == other._rhs

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash((self._lhs, self._rhs))

    def as_tuple(self) -> tuple:
        return (", ".join(self._lhs), self.rhs)
