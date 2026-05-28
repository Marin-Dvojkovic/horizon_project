from .fd_pattern import FDPattern


class PatternExpression:
    _fd_patterns: list[FDPattern]

    def __init__(self, tuple_index: int) -> None:
        self._fd_patterns = []
        self._tuple_index: int = tuple_index

    @property
    def tuple_index(self) -> int:
        return self._tuple_index

    def __repr__(self) -> str:
        joined_patterns: str = " ▷ ".join(
            str(fd_pattern) for fd_pattern in self._fd_patterns
        )
        return f"t{self._tuple_index}: {joined_patterns}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other
        elif not isinstance(other, PatternExpression):
            return NotImplemented
        return str(self) == str(other)

    # required by __eq__; allows use in sets and as dict keys (e.g. fd in seen_fds)
    def __hash__(self) -> int:
        return hash(str(self))

    def add_fd_pattern(self, fd_pattern: FDPattern) -> None:
        self._fd_patterns.append(fd_pattern)

    def attribute_in_expression(self, attribute: str) -> FDPattern | None:
        for fd_pattern in self._fd_patterns:
            if fd_pattern.fd.rhs == attribute:
                return fd_pattern
        return None
