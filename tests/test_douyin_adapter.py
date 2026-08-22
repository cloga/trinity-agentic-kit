from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace

import pytest

from trinity_agentic_kit.douyin_adapter import (
    AdapterConfigurationError,
    AdapterTimeoutError,
    DouyinPublisherAdapter,
    DriverDiagnostics,
    DriverPublishResult,
    DriverVerificationResult,
    FakeBrowserDriver,
    MemorySessionStore,
    OperationTimeouts,
    SelectorProfile,
    SessionRequiredError,
)
from trinity_agentic_kit.social_publish import (
    PlatformPublishResult,
    PublisherAdapter,
    SocialPublishRequest,
)


def selector_values(**extra: str) -> Mapping[str, str]:
    return {
        "authenticated": "auth",
        "composer_ready": "composer",
        "description_input": "description",
        "submit_button": "submit",
        "submission_reference": "reference",
        **extra,
    }


def profile(**selectors: str) -> SelectorProfile:
    return SelectorProfile(
        name="test-profile",
        version="1",
        login_url="https://example.invalid/login",
        publish_url="https://example.invalid/publish",
        verification_url_template=(
            "https://example.invalid/items/{platform_reference}"
        ),
        selectors=selector_values(**selectors),
    )


def request(
    media_type: str = "video",
    *,
    metadata: dict[str, object] | None = None,
) -> SocialPublishRequest:
    return SocialPublishRequest(
        request_id=f"request-{media_type}",
        platform="douyin",
        media_type=media_type,
        asset_ref=f"asset://{media_type}",
        title="Title",
        description="Description",
        idempotency_key=f"key-{media_type}",
        metadata=metadata or {},
    )


def adapter_for(
    media_type: str = "video",
    *,
    driver: FakeBrowserDriver | None = None,
    store: MemorySessionStore | None = None,
) -> tuple[DouyinPublisherAdapter, FakeBrowserDriver, MemorySessionStore]:
    fake = driver or FakeBrowserDriver()
    session_store = store or MemorySessionStore(fake.session)
    adapter = DouyinPublisherAdapter(
        driver=fake,
        session_store=session_store,
        selector_profile=profile(**{f"{media_type}_input": "media"}),
    )
    contract: PublisherAdapter = adapter
    assert contract.platform == "douyin"
    return adapter, fake, session_store


def test_interactive_login_saves_returned_session() -> None:
    fake = FakeBrowserDriver(session=b"new-session")
    store = MemorySessionStore()
    adapter, _, _ = adapter_for(driver=fake, store=store)

    asyncio.run(adapter.login_interactively())

    assert store.load() == b"new-session"
    assert fake.calls[0][0] == "login_interactively"


def test_prepare_requires_and_restores_valid_session() -> None:
    adapter, fake, _ = adapter_for()

    asyncio.run(adapter.prepare(request()))

    assert [call[0] for call in fake.calls] == ["restore_session", "prepare"]


def test_prepare_rejects_missing_or_expired_session() -> None:
    missing_adapter, _, _ = adapter_for(store=MemorySessionStore())
    with pytest.raises(SessionRequiredError) as missing:
        asyncio.run(missing_adapter.prepare(request()))
    assert missing.value.details.code == "session_required"

    expired_driver = FakeBrowserDriver(session_valid=False)
    store = MemorySessionStore(b"expired")
    expired_adapter, _, _ = adapter_for(driver=expired_driver, store=store)
    with pytest.raises(SessionRequiredError) as expired:
        asyncio.run(expired_adapter.prepare(request()))
    assert expired.value.details.code == "session_expired"
    assert store.load() is None


@pytest.mark.parametrize(
    ("media_type", "metadata", "expected_call"),
    [
        ("video", {}, "publish_video"),
        ("image", {"image_refs": ["asset://one", "asset://two"]}, "publish_images"),
        ("text", {}, "publish_text"),
    ],
)
def test_execute_dispatches_by_media_type(
    media_type: str,
    metadata: dict[str, object],
    expected_call: str,
) -> None:
    adapter, fake, _ = adapter_for(media_type)

    result = asyncio.run(adapter.execute(request(media_type, metadata=metadata)))

    assert result.submitted
    assert result.platform_reference == "fake-reference-1"
    assert [call[0] for call in fake.calls] == [
        "restore_session",
        expected_call,
    ]
    if media_type == "image":
        image_call = fake.calls[1][1]
        assert isinstance(image_call, tuple)
        assert image_call[1] == ("asset://one", "asset://two")


def test_execute_maps_published_and_uncertain_results() -> None:
    published_driver = FakeBrowserDriver(
        publish_result=DriverPublishResult(
            submitted=True,
            platform_reference="ref",
            published_url="https://example.invalid/public",
        )
    )
    published_adapter, _, _ = adapter_for(driver=published_driver)
    published = asyncio.run(published_adapter.execute(request()))
    assert published.published_url == "https://example.invalid/public"

    uncertain_driver = FakeBrowserDriver(
        publish_result=DriverPublishResult(
            submitted=False,
            platform_reference="ref",
        )
    )
    uncertain_adapter, _, _ = adapter_for(driver=uncertain_driver)
    uncertain = asyncio.run(uncertain_adapter.execute(request()))
    assert uncertain.verification_pending
    assert uncertain.error_code == "submission_outcome_uncertain"


def test_verify_only_uses_lookup_and_never_publish() -> None:
    adapter, fake, _ = adapter_for()

    result = asyncio.run(adapter.verify(request(), platform_reference="reference-1"))

    assert result.published_url == "https://example.invalid/item/1"
    assert [call[0] for call in fake.calls] == ["restore_session", "verify"]


def test_verify_pending_preserves_reference() -> None:
    fake = FakeBrowserDriver(
        verification_result=DriverVerificationResult(
            found=False,
            evidence=("not_ready",),
        )
    )
    adapter, _, _ = adapter_for(driver=fake)

    result = asyncio.run(adapter.verify(request(), platform_reference="ref"))

    assert result == PlatformPublishResult(
        submitted=True,
        verification_pending=True,
        platform_reference="ref",
        evidence=("not_ready",),
        retryable=True,
    )


def test_request_and_profile_validation_are_structured() -> None:
    adapter, _, _ = adapter_for()
    with pytest.raises(AdapterConfigurationError) as wrong_platform:
        asyncio.run(adapter.prepare(replace(request(), platform="not-douyin")))
    assert wrong_platform.value.details.code == "platform_mismatch"

    with pytest.raises(AdapterConfigurationError) as wrong_media:
        asyncio.run(adapter.prepare(request("audio")))
    assert wrong_media.value.details.code == "unsupported_media_type"

    invalid_profile_adapter = DouyinPublisherAdapter(
        driver=FakeBrowserDriver(),
        session_store=MemorySessionStore(b"session"),
        selector_profile=profile(),
    )
    with pytest.raises(AdapterConfigurationError) as invalid_profile:
        asyncio.run(invalid_profile_adapter.prepare(request()))
    assert invalid_profile.value.details.code == "selector_profile_invalid"


@pytest.mark.parametrize(
    "metadata",
    [{}, {"image_refs": []}, {"image_refs": [""]}, {"image_refs": [1]}],
)
def test_image_requests_require_valid_image_refs(
    metadata: dict[str, object],
) -> None:
    adapter, _, _ = adapter_for("image")
    with pytest.raises(AdapterConfigurationError):
        asyncio.run(adapter.prepare(request("image", metadata=metadata)))


def test_verify_requires_reference() -> None:
    adapter, _, _ = adapter_for()
    with pytest.raises(AdapterConfigurationError) as error:
        asyncio.run(adapter.verify(request(), platform_reference=" "))
    assert error.value.details.code == "missing_platform_reference"


def test_selector_profile_is_versioned_immutable_and_validated() -> None:
    original = {"authenticated": "auth"}
    configured = SelectorProfile(
        name="test",
        version="1",
        login_url="https://example.invalid/login",
        publish_url="https://example.invalid/publish",
        verification_url_template="https://example.invalid/{platform_reference}",
        selectors=original,
    )
    original["authenticated"] = "changed"
    assert configured.selectors["authenticated"] == "auth"
    with pytest.raises(TypeError):
        configured.selectors["new"] = "value"  # type: ignore[index]
    with pytest.raises(ValueError, match="schema"):
        replace(configured, schema_version=2)
    with pytest.raises(ValueError, match="platform_reference"):
        replace(configured, verification_url_template="https://example.invalid")
    with pytest.raises(ValueError, match="blank"):
        replace(configured, selectors={"authenticated": ""})


def test_timeouts_are_bounded() -> None:
    assert OperationTimeouts().execute_seconds == 120
    with pytest.raises(ValueError, match="at most 600"):
        OperationTimeouts(login_seconds=601)


def test_slow_driver_is_cancelled_with_structured_timeout() -> None:
    class SlowDriver(FakeBrowserDriver):
        async def prepare(
            self,
            request: SocialPublishRequest,
            profile: SelectorProfile,
            *,
            timeout_seconds: float,
        ) -> DriverDiagnostics:
            del request, profile, timeout_seconds
            await asyncio.sleep(1)
            raise AssertionError("wait_for should cancel this coroutine")

    adapter = DouyinPublisherAdapter(
        driver=SlowDriver(),
        session_store=MemorySessionStore(b"session"),
        selector_profile=profile(video_input="video"),
        timeouts=OperationTimeouts(prepare_seconds=0.01),
    )

    with pytest.raises(AdapterTimeoutError) as error:
        asyncio.run(adapter.prepare(request()))
    assert error.value.details.code == "operation_timeout"
