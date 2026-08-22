from __future__ import annotations

from trinity_agentic_kit.social_publish import SocialPublishRequest

from .models import (
    DriverDiagnostics,
    DriverPublishResult,
    DriverVerificationResult,
    SelectorProfile,
)


class FakeBrowserDriver:
    """Deterministic no-network driver for contract tests."""

    def __init__(
        self,
        *,
        session: bytes = b'{"fake":"session"}',
        session_valid: bool = True,
        publish_result: DriverPublishResult | None = None,
        verification_result: DriverVerificationResult | None = None,
    ) -> None:
        self.session = session
        self.session_valid = session_valid
        self.publish_result = publish_result or DriverPublishResult(
            submitted=True,
            platform_reference="fake-reference-1",
            evidence=("fake_submit_observed",),
        )
        self.verification_result = verification_result or DriverVerificationResult(
            found=True,
            published_url="https://example.invalid/item/1",
            evidence=("fake_public_item_observed",),
        )
        self.calls: list[tuple[str, object]] = []

    async def login_interactively(
        self,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bytes:
        self.calls.append(("login_interactively", (profile, timeout_seconds)))
        return self.session

    async def restore_session(
        self,
        session: bytes,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bool:
        self.calls.append(("restore_session", (session, profile, timeout_seconds)))
        return self.session_valid

    async def prepare(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverDiagnostics:
        self.calls.append(("prepare", (request, profile, timeout_seconds)))
        return DriverDiagnostics(
            operation="prepare",
            profile_name=profile.name,
            profile_version=profile.version,
            checkpoint="ready",
            elapsed_seconds=0.0,
        )

    async def publish_video(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        self.calls.append(("publish_video", (request, profile, timeout_seconds)))
        return self.publish_result

    async def publish_images(
        self,
        request: SocialPublishRequest,
        image_refs: tuple[str, ...],
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        self.calls.append(
            (
                "publish_images",
                (request, image_refs, profile, timeout_seconds),
            )
        )
        return self.publish_result

    async def publish_text(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        self.calls.append(("publish_text", (request, profile, timeout_seconds)))
        return self.publish_result

    async def verify(
        self,
        platform_reference: str,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverVerificationResult:
        self.calls.append(("verify", (platform_reference, profile, timeout_seconds)))
        return self.verification_result
