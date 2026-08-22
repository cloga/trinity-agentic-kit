from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable
from typing import TypeVar, cast
from urllib.parse import quote

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    StorageState,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from trinity_agentic_kit.social_publish import SocialPublishRequest

from .errors import AdapterTimeoutError, BrowserOperationError
from .models import (
    DriverDiagnostics,
    DriverPublishResult,
    DriverVerificationResult,
    SelectorProfile,
)

_T = TypeVar("_T")


class PlaywrightBrowserDriver:
    """Visible-browser Playwright driver with no stealth behavior."""

    def __init__(self, *, browser_name: str = "chromium") -> None:
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise ValueError("browser_name must be chromium, firefox, or webkit")
        self._browser_name = browser_name
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._checkpoint = "not_started"
        self._selector_name = ""

    async def login_interactively(
        self,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bytes:
        started = time.monotonic()

        async def operation() -> bytes:
            page = await self._new_context()
            await page.goto(profile.login_url)
            await self._wait_for(
                page,
                profile,
                "authenticated",
                timeout_seconds,
            )
            context = self._require_context()
            state = await context.storage_state()
            return json.dumps(
                state,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

        return await self._run(
            operation(),
            operation="login",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def restore_session(
        self,
        session: bytes,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> bool:
        started = time.monotonic()

        async def operation() -> bool:
            state_object: object = json.loads(session.decode("utf-8"))
            if not isinstance(state_object, dict):
                raise ValueError("Session state must be a JSON object")
            page = await self._new_context(
                storage_state=cast(StorageState, state_object)
            )
            await page.goto(profile.publish_url)
            try:
                await self._wait_for(
                    page,
                    profile,
                    "authenticated",
                    timeout_seconds,
                )
            except AdapterTimeoutError:
                return False
            return True

        return await self._run(
            operation(),
            operation="restore_session",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def prepare(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverDiagnostics:
        started = time.monotonic()

        async def operation() -> DriverDiagnostics:
            page = self._require_page()
            await page.goto(profile.publish_url)
            await self._wait_for(page, profile, "composer_ready", timeout_seconds)
            selector_name = {
                "video": "video_input",
                "image": "image_input",
                "text": "text_input",
            }[request.media_type.strip().lower()]
            await self._wait_for(page, profile, selector_name, timeout_seconds)
            return self._diagnostics("prepare", profile, started, checkpoint="ready")

        return await self._run(
            operation(),
            operation="prepare",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def publish_video(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        return await self._publish(
            request,
            profile,
            input_name="video_input",
            input_files=request.asset_ref,
            timeout_seconds=timeout_seconds,
        )

    async def publish_images(
        self,
        request: SocialPublishRequest,
        image_refs: tuple[str, ...],
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        return await self._publish(
            request,
            profile,
            input_name="image_input",
            input_files=list(image_refs),
            timeout_seconds=timeout_seconds,
        )

    async def publish_text(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverPublishResult:
        started = time.monotonic()

        async def operation() -> DriverPublishResult:
            page = self._require_page()
            await page.fill(
                profile.selectors["text_input"],
                self._caption(request),
            )
            return await self._submit(page, profile, started)

        return await self._run(
            operation(),
            operation="execute_text",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def verify(
        self,
        platform_reference: str,
        profile: SelectorProfile,
        *,
        timeout_seconds: float,
    ) -> DriverVerificationResult:
        started = time.monotonic()

        async def operation() -> DriverVerificationResult:
            page = self._require_page()
            url = profile.verification_url_template.format(
                platform_reference=quote(platform_reference, safe="")
            )
            await page.goto(url)
            published_link = profile.selectors.get("published_link")
            if published_link is None:
                return DriverVerificationResult(
                    found=False,
                    evidence=("verification_page_loaded",),
                    diagnostics=self._diagnostics(
                        "verify",
                        profile,
                        started,
                        checkpoint="reference_loaded",
                    ),
                )
            try:
                await self._wait_for(
                    page,
                    profile,
                    "published_link",
                    timeout_seconds,
                )
            except AdapterTimeoutError:
                return DriverVerificationResult(
                    found=False,
                    evidence=("public_item_not_observed",),
                    diagnostics=self._diagnostics(
                        "verify",
                        profile,
                        started,
                        checkpoint="not_found",
                    ),
                )
            href = await page.locator(published_link).first.get_attribute("href")
            return DriverVerificationResult(
                found=bool(href),
                published_url=href or "",
                evidence=("public_item_observed",) if href else (),
                diagnostics=self._diagnostics(
                    "verify",
                    profile,
                    started,
                    checkpoint="found" if href else "not_found",
                ),
            )

        return await self._run(
            operation(),
            operation="verify",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None

    async def _publish(
        self,
        request: SocialPublishRequest,
        profile: SelectorProfile,
        *,
        input_name: str,
        input_files: str | list[str],
        timeout_seconds: float,
    ) -> DriverPublishResult:
        started = time.monotonic()

        async def operation() -> DriverPublishResult:
            page = self._require_page()
            await page.set_input_files(profile.selectors[input_name], input_files)
            title_input = profile.selectors.get("title_input")
            if title_input is not None:
                await page.fill(title_input, request.title)
            await page.fill(
                profile.selectors["description_input"],
                request.description,
            )
            return await self._submit(page, profile, started)

        return await self._run(
            operation(),
            operation=f"execute_{request.media_type}",
            profile=profile,
            timeout_seconds=timeout_seconds,
            started=started,
        )

    async def _submit(
        self,
        page: Page,
        profile: SelectorProfile,
        started: float,
    ) -> DriverPublishResult:
        await page.click(profile.selectors["submit_button"])
        await self._wait_for(
            page,
            profile,
            "submission_reference",
            timeout_seconds=30.0,
        )
        reference = (
            await page.locator(
                profile.selectors["submission_reference"]
            ).first.text_content()
            or ""
        ).strip()
        return DriverPublishResult(
            submitted=bool(reference),
            platform_reference=reference,
            evidence=("submission_reference_observed",) if reference else (),
            diagnostics=self._diagnostics(
                "execute",
                profile,
                started,
                checkpoint="submitted" if reference else "uncertain",
            ),
        )

    async def _new_context(
        self,
        *,
        storage_state: StorageState | None = None,
    ) -> Page:
        await self.close()
        self._playwright = await async_playwright().start()
        browser_type = getattr(self._playwright, self._browser_name)
        browser = await browser_type.launch(headless=False)
        self._browser = browser
        if storage_state is None:
            context = await browser.new_context()
        else:
            context = await browser.new_context(storage_state=storage_state)
        self._context = context
        page = await context.new_page()
        self._page = page
        return page

    async def _wait_for(
        self,
        page: Page,
        profile: SelectorProfile,
        selector_name: str,
        timeout_seconds: float,
    ) -> None:
        self._checkpoint = "waiting_for_selector"
        self._selector_name = selector_name
        try:
            await page.wait_for_selector(
                profile.selectors[selector_name],
                timeout=timeout_seconds * 1000,
            )
        except PlaywrightTimeoutError as exc:
            raise AdapterTimeoutError(
                f"Timed out waiting for {selector_name}",
                code="selector_timeout",
                operation="browser_wait",
                retryable=True,
                diagnostics=DriverDiagnostics(
                    operation="browser_wait",
                    profile_name=profile.name,
                    profile_version=profile.version,
                    checkpoint=self._checkpoint,
                    elapsed_seconds=timeout_seconds,
                    current_url=page.url,
                    selector_name=selector_name,
                ),
            ) from exc

    async def _run(
        self,
        awaitable: Awaitable[_T],
        *,
        operation: str,
        profile: SelectorProfile,
        timeout_seconds: float,
        started: float,
    ) -> _T:
        try:
            return await asyncio.wait_for(awaitable, timeout_seconds)
        except (asyncio.TimeoutError, PlaywrightTimeoutError) as exc:
            raise AdapterTimeoutError(
                f"{operation} timed out",
                code="browser_timeout",
                operation=operation,
                retryable=operation == "verify",
                requires_manual_intervention=operation == "login",
                diagnostics=self._diagnostics(
                    operation,
                    profile,
                    started,
                    checkpoint=self._checkpoint,
                ),
            ) from exc
        except AdapterTimeoutError:
            raise
        except (OSError, RuntimeError, ValueError, PlaywrightError) as exc:
            raise BrowserOperationError(
                f"{operation} failed: {exc}",
                code="playwright_operation_failed",
                operation=operation,
                retryable=operation == "verify",
                diagnostics=self._diagnostics(
                    operation,
                    profile,
                    started,
                    checkpoint=self._checkpoint,
                ),
            ) from exc

    def _diagnostics(
        self,
        operation: str,
        profile: SelectorProfile,
        started: float,
        *,
        checkpoint: str,
    ) -> DriverDiagnostics:
        return DriverDiagnostics(
            operation=operation,
            profile_name=profile.name,
            profile_version=profile.version,
            checkpoint=checkpoint,
            elapsed_seconds=max(0.0, time.monotonic() - started),
            current_url=self._page.url if self._page is not None else "",
            selector_name=self._selector_name,
        )

    def _require_context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser context has not been initialized")
        return self._context

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session has not been restored")
        return self._page

    @staticmethod
    def _caption(request: SocialPublishRequest) -> str:
        return "\n".join(
            value for value in (request.title, request.description) if value
        )
