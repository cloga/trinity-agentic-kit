from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FailureKind(str, Enum):
    TRANSIENT = "transient"
    AUTHENTICATION = "authentication"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    PERMISSION = "permission"
    REF_CONFLICT = "ref_conflict"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    jitter_ratio: float = 0.2
    command_timeout_seconds: float = 180.0
    stale_lock_seconds: float = 1800.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")
        if self.command_timeout_seconds <= 0 or self.stale_lock_seconds <= 0:
            raise ValueError("timeouts must be positive")

    def delay_for(self, attempt: int, *, random_unit: float) -> float:
        base = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** max(attempt - 1, 0)),
        )
        jitter = base * self.jitter_ratio * ((random_unit * 2) - 1)
        return max(0.0, base + jitter)


@dataclass(frozen=True, slots=True)
class RepositoryAccess:
    login: str
    repository: str
    can_push: bool


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt: int
    failure_kind: FailureKind | None
    returncode: int
    message: str
    delay_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class TransportResult:
    succeeded: bool
    attempts: tuple[AttemptRecord, ...] = field(default_factory=tuple)
    stdout: str = ""
    failure_kind: FailureKind | None = None
    exit_code: int = 0
