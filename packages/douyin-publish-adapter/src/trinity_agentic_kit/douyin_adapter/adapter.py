from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar, cast

from trinity_agentic_kit.social_publish import (
    PlatformPublishResult,
    SocialPublishRequest,
)

from .errors import (
    AdapterConfigurationError,
    AdapterTimeoutError,
    BrowserOperationError,
    DouyinAdapterError,
    SessionRequiredError,
)
from .models import (
    SUPPORTED_MEDIA_TYPES,
    DriverPublishResult,
    DriverVerificationResult,
    OperationTimeouts,
    SelectorProfile,
)
from .protocols import BrowserDriver, SessionStore

_T = TypeVar("_T")


class DouyinPublisherAdapter:
    """User-operated adapter implementing the social-publish core contract."""

    platform = "douyin"

    def __init__(
        self,
        *,
        driver: BrowserDriver,
        session_store: SessionStore,
        selector_profile: SelectorProfile,
        timeouts: OperationTimeouts | None = None,
    ) -> None:
        self._driver = driver
        self._session_store = session_store
        self._profile = selector_profile
        self._timeouts = timeouts or OperationTimeouts()

    async def login_interactively(self) -> None:
        session = await self._bounded(
            self._driver.login_interactively(
                self._profile,
                timeout_seconds=self._timeouts.login_seconds,
            ),
            operation="login",
            timeout_seconds=self._timeouts.login_seconds,
        )
        if not session:
            raise BrowserOperationError(
                "Interactive login returned no session state",
                code="empty_session",
                operation="login",
                requires_manual_intervention=True,
            )
        self._session_store.save(session)

    async def prepare(self, request: SocialPublishRequest) -> None:
        media_type = self._validate_request(request)
        self._validate_profile(media_type)
        await self._restore_session(operation="prepare")
        await self._bounded(
            self._driver.prepare(
                request,
                self._profile,
                timeout_seconds=self._timeouts.prepare_seconds,
            ),
            operation="prepare",
            timeout_seconds=self._timeouts.prepare_seconds,
        )

    async def execute(self, request: SocialPublishRequest) -> PlatformPublishResult:
        media_type = self._validate_request(request)
        self._validate_profile(media_type)
        await self._restore_session(operation="execute")
        if media_type == "video":
            operation = self._driver.publish_video(
                request,
                self._profile,
                timeout_seconds=self._timeouts.execute_seconds,
            )
        elif media_type == "image":
            operation = self._driver.publish_images(
                request,
                self._image_refs(request),
                self._profile,
                timeout_seconds=self._timeouts.execute_seconds,
            )
        else:
            operation = self._driver.publish_text(
                request,
                self._profile,
                timeout_seconds=self._timeouts.execute_seconds,
            )
        result = await self._bounded(
            operation,
            operation="execute",
            timeout_seconds=self._timeouts.execute_seconds,
        )
        return self._publish_result(result)

    async def verify(
        self,
        request: SocialPublishRequest,
        *,
        platform_reference: str,
    ) -> PlatformPublishResult:
        media_type = self._validate_request(request)
        self._validate_profile(media_type)
        reference = platform_reference.strip()
        if not reference:
            raise AdapterConfigurationError(
                "Verification requires a platform reference",
                code="missing_platform_reference",
                operation="verify",
            )
        await self._restore_session(operation="verify")
        result = await self._bounded(
            self._driver.verify(
                reference,
                self._profile,
                timeout_seconds=self._timeouts.verify_seconds,
            ),
            operation="verify",
            timeout_seconds=self._timeouts.verify_seconds,
        )
        return self._verification_result(reference, result)

    async def _restore_session(self, *, operation: str) -> None:
        session = self._session_store.load()
        if session is None:
            raise SessionRequiredError(
                "Run interactive login before publishing",
                code="session_required",
                operation=operation,
                requires_manual_intervention=True,
            )
        restored = await self._bounded(
            self._driver.restore_session(
                session,
                self._profile,
                timeout_seconds=self._timeouts.prepare_seconds,
            ),
            operation=operation,
            timeout_seconds=self._timeouts.prepare_seconds,
        )
        if not restored:
            self._session_store.clear()
            raise SessionRequiredError(
                "The saved session is no longer valid; log in again",
                code="session_expired",
                operation=operation,
                requires_manual_intervention=True,
            )

    async def _bounded(
        self,
        awaitable: Awaitable[_T],
        *,
        operation: str,
        timeout_seconds: float,
    ) -> _T:
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise AdapterTimeoutError(
                f"{operation} exceeded {timeout_seconds:g} seconds",
                code="operation_timeout",
                operation=operation,
                retryable=operation == "verify",
                requires_manual_intervention=operation == "login",
            ) from exc
        except DouyinAdapterError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise BrowserOperationError(
                f"{operation} failed: {exc}",
                code="browser_operation_failed",
                operation=operation,
                retryable=operation == "verify",
            ) from exc

    def _validate_request(self, request: SocialPublishRequest) -> str:
        if request.platform.strip().lower() != self.platform:
            raise AdapterConfigurationError(
                f"Expected platform {self.platform!r}",
                code="platform_mismatch",
                operation="prepare",
            )
        media_type = request.media_type.strip().lower()
        if media_type not in SUPPORTED_MEDIA_TYPES:
            raise AdapterConfigurationError(
                f"Unsupported media type: {request.media_type}",
                code="unsupported_media_type",
                operation="prepare",
            )
        if media_type == "image":
            self._image_refs(request)
        return media_type

    def _validate_profile(self, media_type: str) -> None:
        try:
            self._profile.validate_for(media_type)
        except ValueError as exc:
            raise AdapterConfigurationError(
                str(exc),
                code="selector_profile_invalid",
                operation="prepare",
            ) from exc

    @staticmethod
    def _image_refs(request: SocialPublishRequest) -> tuple[str, ...]:
        raw_refs = request.metadata.get("image_refs")
        if not isinstance(raw_refs, list):
            raise AdapterConfigurationError(
                "Image requests require metadata.image_refs",
                code="image_refs_required",
                operation="prepare",
            )
        raw_objects = cast(list[object], raw_refs)
        if not raw_objects or not all(
            isinstance(item, str) and item.strip() for item in raw_objects
        ):
            raise AdapterConfigurationError(
                "metadata.image_refs must contain non-empty strings",
                code="image_refs_invalid",
                operation="prepare",
            )
        return tuple(cast(list[str], raw_objects))

    @staticmethod
    def _publish_result(result: DriverPublishResult) -> PlatformPublishResult:
        if result.published_url:
            return PlatformPublishResult(
                submitted=True,
                published_url=result.published_url,
                platform_reference=result.platform_reference,
                evidence=result.evidence,
            )
        if result.submitted:
            return PlatformPublishResult(
                submitted=True,
                platform_reference=result.platform_reference,
                evidence=result.evidence,
            )
        return PlatformPublishResult(
            submitted=False,
            verification_pending=True,
            platform_reference=result.platform_reference,
            evidence=result.evidence,
            error_code="submission_outcome_uncertain",
            error_message="The driver did not confirm submission",
            retryable=False,
            requires_manual_intervention=True,
        )

    @staticmethod
    def _verification_result(
        reference: str,
        result: DriverVerificationResult,
    ) -> PlatformPublishResult:
        if result.found and result.published_url:
            return PlatformPublishResult(
                submitted=True,
                published_url=result.published_url,
                platform_reference=reference,
                evidence=result.evidence,
            )
        return PlatformPublishResult(
            submitted=True,
            verification_pending=True,
            platform_reference=reference,
            evidence=result.evidence,
            retryable=True,
        )
