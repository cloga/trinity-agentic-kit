from __future__ import annotations

import asyncio
import secrets

from trinity_agentic_kit.social_publish import (
    FakePublisherAdapter,
    HmacApprovalAuthority,
    InMemoryAuditSink,
    InMemoryPublishStateStore,
    SocialPublishCoordinator,
    SocialPublishRequest,
)


async def main() -> None:
    adapter = FakePublisherAdapter()
    authority = HmacApprovalAuthority(secrets.token_bytes(32), issuer="example")
    coordinator = SocialPublishCoordinator(
        adapters={adapter.platform: adapter},
        store=InMemoryPublishStateStore(),
        approval_authority=authority,
        audit_sink=InMemoryAuditSink(),
    )
    request = SocialPublishRequest(
        request_id="request-1",
        platform="fake",
        media_type="video",
        asset_ref="asset://demo-video",
        title="A safe demo",
        description="No network or platform account is used.",
        idempotency_key="demo-1",
    )

    await coordinator.prepare(request)
    # In production, only a trusted operator/admin surface may issue this grant.
    approval = authority.issue(request, grant_id="operator-approval-1")
    await coordinator.execute(request.request_id, approval)
    record = await coordinator.verify(request.request_id)
    print(record.state.value, record.published_url)


if __name__ == "__main__":
    asyncio.run(main())
