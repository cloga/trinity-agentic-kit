from __future__ import annotations

from typing import Protocol

from trinity_agentic_kit.social_publish import SocialPublishRequest

from .models import (
    DriverDiagnostics,
    DriverPublishResult,
    DriverVerificationResult,
    SelectorProfile,
)


class SessionStore(Protocol):
    """Persist opaque browser state outside the working directory."""

    def load(self) -> bytes | None: ...

    def save(self, session: bytes) -> None: ...

    def clear(self) -> None: ...


class SessionProtector(Protocol):
    """Optional protection boundary for session bytes."""

    def protect(self, session: bytes) -> bytes: ...

    def unprotect(self, protected_session: bytes) -> bytes: ...


class BrowserDriver(Protocol):
    """Browser operations used by the adapter."""

    async def close(self) -> None: ...

    async def login_interactively(
        self,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bytes: ...

    async def restore_session(
        self,
        session: bytes,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bool: ...

    async def prepare(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverDiagnostics: ...

    async def publish_video(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult: ...

    async def publish_images(
        self,
        request: SocialPublishRequest,
        image_refs: tuple[str, ...],
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult: ...

    async def publish_text(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult: ...

    async def verify(
        self,
        platform_reference: str,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverVerificationResult: ...
