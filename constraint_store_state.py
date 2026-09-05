"""Availability is part of the authoritative account-constraint contract."""
from dataclasses import dataclass
from enum import Enum


class ConstraintLoadState(str, Enum):
    AVAILABLE_WITH_CONSTRAINTS = "available_with_constraints"
    AVAILABLE_EMPTY = "available_empty"
    UNAVAILABLE = "unavailable"


class ConstraintStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ConstraintLoad:
    state: ConstraintLoadState
    patterns: tuple[str, ...] = ()

    def require_available(self):
        if self.state is ConstraintLoadState.UNAVAILABLE:
            raise ConstraintStoreUnavailable("account_constraints_unavailable")
        return self.patterns


def load_constraints(reader, known_patterns):
    try:
        values = reader()
        if not isinstance(values, (list, tuple)) or any(
                not isinstance(value, str) or value not in known_patterns for value in values):
            return ConstraintLoad(ConstraintLoadState.UNAVAILABLE)
        patterns = tuple(sorted(set(values)))
        return ConstraintLoad(ConstraintLoadState.AVAILABLE_WITH_CONSTRAINTS
                              if patterns else ConstraintLoadState.AVAILABLE_EMPTY, patterns)
    except Exception:
        return ConstraintLoad(ConstraintLoadState.UNAVAILABLE)
