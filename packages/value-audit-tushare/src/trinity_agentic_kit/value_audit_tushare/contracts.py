from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

PACKAGE_VERSION = "0.1.0"


class TushareClient(Protocol):
    def query(
        self,
        api_name: str,
        *,
        fields: str = "",
        **params: str,
    ) -> object: ...


class TushareAdapterError(RuntimeError):
    """Base error for the public adapter."""


class TushareTokenError(TushareAdapterError):
    """Raised when the default network client has no token."""


class TushareMappingError(TushareAdapterError, ValueError):
    """Raised when provider rows cannot form the public core payload."""


class TushareRequestError(TushareAdapterError):
    def __init__(self, api_name: str, attempts: int, *, retryable: bool) -> None:
        self.api_name = api_name
        self.attempts = attempts
        self.retryable = retryable
        kind = "transient" if retryable else "permanent"
        super().__init__(
            f"Tushare endpoint {api_name!r} failed after {attempts} "
            f"attempt(s); classified as {kind}."
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    maximum_delay_seconds: float = 4.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if (
            not math.isfinite(self.initial_delay_seconds)
            or self.initial_delay_seconds < 0
        ):
            raise ValueError("initial_delay_seconds must be finite and non-negative")
        if not math.isfinite(self.backoff_multiplier) or self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be finite and at least 1")
        if (
            not math.isfinite(self.maximum_delay_seconds)
            or self.maximum_delay_seconds < 0
        ):
            raise ValueError("maximum_delay_seconds must be finite and non-negative")
