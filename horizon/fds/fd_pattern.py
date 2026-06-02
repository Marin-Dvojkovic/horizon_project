from .fd import FunctionalDependency


class FDPattern:
    def __init__(
        self, fd: FunctionalDependency, lval: tuple | list | str, rval: str
    ) -> None:
        self._fd = fd
        if isinstance(lval, str):
            self._lval = (lval,)
        else:
            self._lval = tuple(lval)
        self._rval = rval

    @property
    def fd(self) -> FunctionalDependency:
        return self._fd

    @property
    def lval(self) -> tuple:
        return self._lval

    @property
    def rval(self) -> str:
        return self._rval

    def __repr__(self) -> str:
        lval_str = ", ".join(self._lval)
        return f"([{str(self._fd)}], '{lval_str}' -> '{self._rval}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FDPattern):
            return NotImplemented
        return (
            self._fd == other._fd
            and self._lval == other._lval
            and self._rval == other._rval
        )

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash(str(self))
