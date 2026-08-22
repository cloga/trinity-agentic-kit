from __future__ import annotations

import asyncio
from typing import Any

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from trinity_agentic_kit.douyin_adapter import (
    AdapterTimeoutError,
    BrowserOperationError,
    PlaywrightBrowserDriver,
    SelectorProfile,
)
from trinity_agentic_kit.social_publish import SocialPublishRequest


def profile(*, published_link: bool = True) -> SelectorProfile:
    selectors = {
        "authenticated": "auth",
        "composer_ready": "composer",
        "video_input": "video",
        "image_input": "image",
        "text_input": "text",
        "title_input": "title",
        "description_input": "description",
        "submit_button": "submit",
        "submission_reference": "reference",
    }
    if published_link:
        selectors["published_link"] = "published"
    return SelectorProfile(
        name="offline",
        version="1",
        login_url="https://example.invalid/login",
        publish_url="https://example.invalid/publish",
        verification_url_template="https://example.invalid/items/{platform_reference}",
        selectors=selectors,
    )


def request(media_type: str = "video") -> SocialPublishRequest:
    return SocialPublishRequest(
        request_id=f"request-{media_type}",
        platform="douyin",
        media_type=media_type,
        asset_ref=f"asset://{media_type}",
        title="Title",
        description="Description",
        idempotency_key=f"key-{media_type}",
    )


class FakeLocator:
    def __init__(self, *, text: str = "reference-1", href: str = "") -> None:
        self._text = text
        self._href = href
        self.first = self

    async def text_content(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._href if name == "href" else None


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.invalid/current"
        self.events: list[tuple[str, Any]] = []
        self.reference_text = "reference-1"
        self.published_href = "https://example.invalid/public/1"
        self.timeout_selector = ""

    async def goto(self, url: str) -> None:
        self.url = url
        self.events.append(("goto", url))

    async def wait_for_selector(self, selector: str, *, timeout: float) -> None:
        self.events.append(("wait", (selector, timeout)))
        if selector == self.timeout_selector:
            raise PlaywrightTimeoutError("not found")

    async def fill(self, selector: str, value: str) -> None:
        self.events.append(("fill", (selector, value)))

    async def set_input_files(
        self,
        selector: str,
        files: str | list[str],
    ) -> None:
        self.events.append(("files", (selector, files)))

    async def click(self, selector: str) -> None:
        self.events.append(("click", selector))

    def locator(self, selector: str) -> FakeLocator:
        if selector == "published":
            return FakeLocator(href=self.published_href)
        return FakeLocator(text=self.reference_text)


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    async def storage_state(self) -> dict[str, object]:
        return {"cookies": [], "origins": []}

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class Closable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class Stoppable:
    def __init__(self) -> None:
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


def driver_with_page() -> tuple[PlaywrightBrowserDriver, FakePage]:
    driver = PlaywrightBrowserDriver()
    page = FakePage()
    driver._page = page  # type: ignore[reportPrivateUsage]
    return driver, page


def test_constructor_and_required_state_fail_closed() -> None:
    with pytest.raises(ValueError, match="browser_name"):
        PlaywrightBrowserDriver(browser_name="unknown")
    driver = PlaywrightBrowserDriver()
    with pytest.raises(RuntimeError, match="context"):
        driver._require_context()  # type: ignore[reportPrivateUsage]
    with pytest.raises(RuntimeError, match="restored"):
        driver._require_page()  # type: ignore[reportPrivateUsage]


def test_prepare_and_all_publish_modes_use_configured_selectors() -> None:
    driver, page = driver_with_page()
    prepared = asyncio.run(driver.prepare(request(), profile(), timeout_seconds=1))
    video = asyncio.run(driver.publish_video(request(), profile(), timeout_seconds=1))
    images = asyncio.run(
        driver.publish_images(
            request("image"),
            ("one.png", "two.png"),
            profile(),
            timeout_seconds=1,
        )
    )
    text = asyncio.run(
        driver.publish_text(request("text"), profile(), timeout_seconds=1)
    )

    assert prepared.checkpoint == "ready"
    assert video.submitted and images.submitted and text.submitted
    assert ("files", ("video", "asset://video")) in page.events
    assert ("files", ("image", ["one.png", "two.png"])) in page.events
    assert ("fill", ("text", "Title\nDescription")) in page.events


def test_verify_handles_missing_pending_and_published_links() -> None:
    driver, page = driver_with_page()
    no_selector = asyncio.run(
        driver.verify("ref / 1", profile(published_link=False), timeout_seconds=1)
    )
    assert not no_selector.found
    assert "ref%20%2F%201" in page.url

    page.timeout_selector = "published"
    pending = asyncio.run(driver.verify("ref", profile(), timeout_seconds=0.01))
    assert not pending.found
    assert pending.evidence == ("public_item_not_observed",)

    page.timeout_selector = ""
    published = asyncio.run(driver.verify("ref", profile(), timeout_seconds=1))
    assert published.found
    assert published.published_url == "https://example.invalid/public/1"

    page.published_href = ""
    missing_href = asyncio.run(driver.verify("ref", profile(), timeout_seconds=1))
    assert not missing_href.found


def test_login_restore_and_close_with_offline_context() -> None:
    driver = PlaywrightBrowserDriver()
    page = FakePage()
    context = FakeContext(page)

    async def new_context(**kwargs: object) -> FakePage:
        del kwargs
        driver._context = context  # type: ignore[reportPrivateUsage]
        driver._page = page  # type: ignore[reportPrivateUsage]
        return page

    driver._new_context = new_context  # type: ignore[method-assign]
    session = asyncio.run(driver.login_interactively(profile(), timeout_seconds=1))
    assert b'"cookies":[]' in session
    assert asyncio.run(driver.restore_session(session, profile(), timeout_seconds=1))

    page.timeout_selector = "auth"
    assert not asyncio.run(
        driver.restore_session(session, profile(), timeout_seconds=0.01)
    )

    with pytest.raises(BrowserOperationError):
        asyncio.run(driver.restore_session(b"[]", profile(), timeout_seconds=1))

    browser = Closable()
    playwright = Stoppable()
    driver._context = context  # type: ignore[reportPrivateUsage]
    driver._browser = browser  # type: ignore[reportPrivateUsage, assignment]
    driver._playwright = playwright  # type: ignore[reportPrivateUsage, assignment]
    asyncio.run(driver.close())
    assert context.closed and browser.closed and playwright.stopped


def test_driver_timeout_and_browser_errors_are_structured() -> None:
    driver, _ = driver_with_page()

    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(AdapterTimeoutError) as timeout:
        asyncio.run(
            driver._run(  # type: ignore[reportPrivateUsage]
                slow(),
                operation="verify",
                profile=profile(),
                timeout_seconds=0.01,
                started=0,
            )
        )
    assert timeout.value.details.code == "browser_timeout"
    assert timeout.value.details.retryable

    async def invalid() -> None:
        raise ValueError("invalid")

    with pytest.raises(BrowserOperationError) as invalid_error:
        asyncio.run(
            driver._run(  # type: ignore[reportPrivateUsage]
                invalid(),
                operation="prepare",
                profile=profile(),
                timeout_seconds=1,
                started=0,
            )
        )
    assert invalid_error.value.details.code == "playwright_operation_failed"
