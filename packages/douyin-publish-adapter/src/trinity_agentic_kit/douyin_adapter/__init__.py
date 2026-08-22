"""Unofficial, user-operated Douyin publishing adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .adapter import DouyinPublisherAdapter
from .errors import (
    AdapterConfigurationError,
    AdapterErrorDetails,
    AdapterTimeoutError,
    BrowserOperationError,
    DouyinAdapterError,
    SessionRequiredError,
)
from .fake import FakeBrowserDriver
from .models import (
    DOUYIN_ADAPTER_VERSION,
    SELECTOR_PROFILE_SCHEMA_VERSION,
    DriverDiagnostics,
    DriverPublishResult,
    DriverVerificationResult,
    OperationTimeouts,
    SelectorProfile,
)
from .protocols import BrowserDriver, SessionProtector, SessionStore
from .session import (
    AppDataSessionStore,
    KeyringSessionProtector,
    MemorySessionStore,
    user_app_data_dir,
)

if TYPE_CHECKING:
    from .playwright_driver import PlaywrightBrowserDriver

__all__ = [
    "DOUYIN_ADAPTER_VERSION",
    "SELECTOR_PROFILE_SCHEMA_VERSION",
    "AdapterConfigurationError",
    "AdapterErrorDetails",
    "AdapterTimeoutError",
    "AppDataSessionStore",
    "BrowserDriver",
    "BrowserOperationError",
    "DouyinAdapterError",
    "DouyinPublisherAdapter",
    "DriverDiagnostics",
    "DriverPublishResult",
    "DriverVerificationResult",
    "FakeBrowserDriver",
    "KeyringSessionProtector",
    "MemorySessionStore",
    "OperationTimeouts",
    "PlaywrightBrowserDriver",
    "SelectorProfile",
    "SessionProtector",
    "SessionRequiredError",
    "SessionStore",
    "user_app_data_dir",
]


def __getattr__(name: str) -> object:
    if name == "PlaywrightBrowserDriver":
        try:
            from .playwright_driver import PlaywrightBrowserDriver
        except ImportError as exc:
            raise RuntimeError(
                "Install trinity-agentic-kit-douyin-adapter[playwright]"
            ) from exc
        return PlaywrightBrowserDriver
    raise AttributeError(name)
