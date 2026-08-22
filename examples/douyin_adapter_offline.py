from __future__ import annotations

import asyncio

from trinity_agentic_kit.douyin_adapter import (
    DouyinPublisherAdapter,
    FakeBrowserDriver,
    MemorySessionStore,
    SelectorProfile,
)
from trinity_agentic_kit.social_publish import SocialPublishRequest


async def main() -> None:
    profile = SelectorProfile(
        name="offline-example",
        version="1",
        login_url="https://example.invalid/login",
        publish_url="https://example.invalid/publish",
        verification_url_template=(
            "https://example.invalid/items/{platform_reference}"
        ),
        selectors={
            "authenticated": "[data-example='authenticated']",
            "composer_ready": "[data-example='composer']",
            "description_input": "[data-example='description']",
            "submit_button": "[data-example='submit']",
            "submission_reference": "[data-example='reference']",
            "video_input": "[data-example='video']",
        },
    )
    driver = FakeBrowserDriver()
    adapter = DouyinPublisherAdapter(
        driver=driver,
        session_store=MemorySessionStore(driver.session),
        selector_profile=profile,
    )
    request = SocialPublishRequest(
        request_id="offline-1",
        platform="douyin",
        media_type="video",
        asset_ref="asset://offline-video",
        title="Offline example",
        description="No browser or network is used.",
        idempotency_key="offline-1",
    )

    await adapter.prepare(request)
    result = await adapter.execute(request)
    print(result.platform_reference)


if __name__ == "__main__":
    asyncio.run(main())
