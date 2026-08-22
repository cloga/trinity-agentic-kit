from __future__ import annotations

from collections.abc import Callable

from .contracts import PlatformPublishResult, SocialPublishRequest

PrepareHook = Callable[[SocialPublishRequest], None]


class FakePublisherAdapter:
    """Deterministic no-network adapter for contract tests and examples."""

    platform = "fake"

    def __init__(
        self,
        *,
        execute_result: PlatformPublishResult | None = None,
        verify_result: PlatformPublishResult | None = None,
        prepare_hook: PrepareHook | None = None,
    ) -> None:
        self.execute_result = execute_result or PlatformPublishResult(
            submitted=True,
            platform_reference="fake-submission-1",
            evidence=("fake_submit_recorded",),
        )
        self.verify_result = verify_result or PlatformPublishResult(
            submitted=True,
            published_url="https://example.invalid/published/1",
            platform_reference="fake-submission-1",
            evidence=("fake_public_url_recorded",),
        )
        self.prepare_hook = prepare_hook
        self.prepare_calls = 0
        self.execute_calls = 0
        self.verify_calls = 0

    async def prepare(self, request: SocialPublishRequest) -> None:
        self.prepare_calls += 1
        if self.prepare_hook is not None:
            self.prepare_hook(request)

    async def execute(self, request: SocialPublishRequest) -> PlatformPublishResult:
        del request
        self.execute_calls += 1
        return self.execute_result

    async def verify(
        self,
        request: SocialPublishRequest,
        *,
        platform_reference: str,
    ) -> PlatformPublishResult:
        del request, platform_reference
        self.verify_calls += 1
        return self.verify_result
