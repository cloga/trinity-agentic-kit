from __future__ import annotations

from dataclasses import dataclass

from trinity_agentic_kit.social_publish import PublisherAdapterError

from .models import DriverDiagnostics


@dataclass(frozen=True, slots=True)
class AdapterErrorDetails:
    code: str
    operation: str
    retryable: bool
    requires_manual_intervention: bool
    diagnostics: DriverDiagnostics | None = None


class DouyinAdapterError(PublisherAdapterError):
    """Structured adapter failure safe to expose to orchestration code."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        operation: str,
        retryable: bool = False,
        requires_manual_intervention: bool = False,
        diagnostics: DriverDiagnostics | None = None,
    ) -> None:
        super().__init__(message)
        self.details = AdapterErrorDetails(
            code=code,
            operation=operation,
            retryable=retryable,
            requires_manual_intervention=requires_manual_intervention,
            diagnostics=diagnostics,
        )


class AdapterConfigurationError(DouyinAdapterError):
    pass


class SessionRequiredError(DouyinAdapterError):
    pass


class AdapterTimeoutError(DouyinAdapterError):
    pass


class BrowserOperationError(DouyinAdapterError):
    pass
