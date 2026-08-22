from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

import pytest
from jsonschema import Draft202012Validator

from trinity_agentic_kit.social_publish import (
    APPROVAL_GRANT_SCHEMA,
    PLATFORM_PUBLISH_RESULT_SCHEMA,
    SOCIAL_PUBLISH_REQUEST_SCHEMA,
    ApprovalGrantError,
    DuplicatePublishRequest,
    FakePublisherAdapter,
    HmacApprovalAuthority,
    InMemoryAuditSink,
    InMemoryPublishStateStore,
    InvalidPublishTransition,
    PlatformPublishResult,
    PublisherAdapterError,
    PublishState,
    SocialPublishCoordinator,
    SocialPublishError,
    SocialPublishRequest,
)


class SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def validate_schema(schema: Mapping[str, object], instance: object) -> None:
    validator = cast(SchemaValidator, Draft202012Validator(schema))
    validator.validate(instance)


def make_request(
    *,
    request_id: str = "request-1",
    idempotency_key: str = "idempotency-1",
    title: str = "Title",
) -> SocialPublishRequest:
    return SocialPublishRequest(
        request_id=request_id,
        platform="fake",
        media_type="video",
        asset_ref="asset://video-1",
        title=title,
        description="Description",
        idempotency_key=idempotency_key,
        metadata={"campaign": "example"},
    )


def make_coordinator() -> tuple[
    SocialPublishCoordinator,
    FakePublisherAdapter,
    InMemoryPublishStateStore,
    InMemoryAuditSink,
    HmacApprovalAuthority,
]:
    adapter = FakePublisherAdapter()
    store = InMemoryPublishStateStore()
    audit = InMemoryAuditSink()
    authority = HmacApprovalAuthority(b"a" * 32, issuer="test")
    coordinator = SocialPublishCoordinator(
        adapters={"fake": adapter},
        store=store,
        approval_authority=authority,
        audit_sink=audit,
    )
    return coordinator, adapter, store, audit, authority


def test_publish_requires_approval_then_verifies_public_url() -> None:
    coordinator, adapter, _, audit, authority = make_coordinator()
    request = make_request()

    prepared = asyncio.run(coordinator.prepare(request))
    token = authority.issue(request, grant_id="grant-1")
    submitted = asyncio.run(coordinator.execute(request.request_id, token))
    published = asyncio.run(coordinator.verify(request.request_id))

    assert prepared.state is PublishState.AWAITING_APPROVAL
    assert submitted.state is PublishState.SUBMITTED
    assert published.state is PublishState.PUBLISHED
    assert published.published_url == "https://example.invalid/published/1"
    assert adapter.execute_calls == 1
    assert [event.state for _, event in audit.events] == [
        PublishState.PREPARING,
        PublishState.AWAITING_APPROVAL,
        PublishState.APPROVED,
        PublishState.EXECUTING,
        PublishState.SUBMITTED,
        PublishState.VERIFYING,
        PublishState.PUBLISHED,
    ]
    assert audit.events[2][1].actor == "grant:test"


def test_public_json_schemas_validate_contract_payloads() -> None:
    request = make_request()
    result = PlatformPublishResult(submitted=True, evidence=("submitted",))
    authority = HmacApprovalAuthority(b"a" * 32, issuer="test")
    token = authority.issue(
        request,
        grant_id="grant-1",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    payload_part = token.split(".", 1)[0]
    payload_part += "=" * (-len(payload_part) % 4)
    approval_payload: object = json.loads(
        base64.urlsafe_b64decode(payload_part).decode("utf-8")
    )

    validate_schema(SOCIAL_PUBLISH_REQUEST_SCHEMA, asdict(request))
    validate_schema(
        PLATFORM_PUBLISH_RESULT_SCHEMA,
        {**asdict(result), "evidence": list(result.evidence)},
    )
    validate_schema(APPROVAL_GRANT_SCHEMA, approval_payload)


def test_prepare_is_idempotent_and_rejects_changed_content() -> None:
    coordinator, adapter, _, _, _ = make_coordinator()
    request = make_request()

    first = asyncio.run(coordinator.prepare(request))
    second = asyncio.run(coordinator.prepare(request))

    assert first.request == second.request
    assert first.request_digest == second.request_digest
    assert first.events == second.events
    assert adapter.prepare_calls == 1
    with pytest.raises(DuplicatePublishRequest):
        asyncio.run(coordinator.prepare(replace(request, title="Changed")))


def test_approval_is_short_lived_request_bound_and_capability_scoped() -> None:
    authority = HmacApprovalAuthority(
        b"a" * 32,
        issuer="test",
        max_ttl_seconds=60,
    )
    request = make_request()
    issued_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    token = authority.issue(
        request,
        grant_id="grant-1",
        ttl_seconds=30,
        now=issued_at,
    )

    assert (
        authority.verify(
            token,
            request,
            now=issued_at + timedelta(seconds=29),
        ).grant_id
        == "grant-1"
    )
    with pytest.raises(ApprovalGrantError, match="expired"):
        authority.verify(
            token,
            request,
            now=issued_at + timedelta(seconds=30),
        )
    with pytest.raises(ApprovalGrantError, match="does not match"):
        authority.verify(
            token,
            make_request(request_id="request-2"),
            now=issued_at,
        )
    with pytest.raises(ApprovalGrantError, match="does not match"):
        authority.verify(
            token,
            make_request(title="Changed after approval"),
            now=issued_at,
        )
    wrong_capability = authority.issue(
        request,
        grant_id="grant-2",
        ttl_seconds=30,
        capabilities=("publish.preview",),
        now=issued_at,
    )
    with pytest.raises(ApprovalGrantError, match="lacks capability"):
        authority.verify(wrong_capability, request, now=issued_at)
    with pytest.raises(ValueError, match="between 1 and 60"):
        authority.issue(request, grant_id="too-long", ttl_seconds=61)


def test_approval_rejects_tampering_and_replay() -> None:
    coordinator, adapter, _, _, authority = make_coordinator()
    request = make_request()
    asyncio.run(coordinator.prepare(request))
    token = authority.issue(request, grant_id="grant-1")
    payload, signature = token.split(".", 1)
    tampered = f"{payload[:-1]}A.{signature}"

    with pytest.raises(ApprovalGrantError):
        asyncio.run(coordinator.execute(request.request_id, tampered))

    asyncio.run(coordinator.execute(request.request_id, token))
    assert adapter.execute_calls == 1
    with pytest.raises((ApprovalGrantError, InvalidPublishTransition)):
        asyncio.run(coordinator.execute(request.request_id, token))
    assert adapter.execute_calls == 1


def test_execute_without_prepared_request_is_blocked() -> None:
    coordinator, adapter, _, _, authority = make_coordinator()
    request = make_request()
    token = authority.issue(request, grant_id="grant-1")

    with pytest.raises(SocialPublishError, match="not found"):
        asyncio.run(coordinator.execute(request.request_id, token))
    assert adapter.execute_calls == 0


def test_definitive_failure_requires_fresh_approval() -> None:
    coordinator, adapter, _, _, authority = make_coordinator()
    request = make_request()
    asyncio.run(coordinator.prepare(request))
    first_token = authority.issue(request, grant_id="grant-1")
    adapter.execute_result = PlatformPublishResult(
        submitted=False,
        error_code="validation_rejected",
        error_message="Platform rejected the request",
        requires_manual_intervention=True,
    )

    failed = asyncio.run(coordinator.execute(request.request_id, first_token))
    assert failed.state is PublishState.FAILED
    assert coordinator.retry(request.request_id).state is PublishState.AWAITING_APPROVAL
    with pytest.raises(ApprovalGrantError, match="consumed"):
        asyncio.run(coordinator.execute(request.request_id, first_token))

    second_token = authority.issue(request, grant_id="grant-2")
    adapter.execute_result = PlatformPublishResult(submitted=True)
    assert (
        asyncio.run(coordinator.execute(request.request_id, second_token)).state
        is PublishState.SUBMITTED
    )


def test_verification_pending_never_reexecutes() -> None:
    coordinator, adapter, _, _, authority = make_coordinator()
    request = make_request()
    asyncio.run(coordinator.prepare(request))
    token = authority.issue(request, grant_id="grant-1")
    asyncio.run(coordinator.execute(request.request_id, token))
    adapter.verify_result = PlatformPublishResult(
        submitted=True,
        verification_pending=True,
        platform_reference="fake-submission-1",
        evidence=("public_url_not_ready",),
        retryable=True,
    )

    first_check = asyncio.run(coordinator.verify(request.request_id))
    second_check = asyncio.run(coordinator.verify(request.request_id))

    assert first_check.state is PublishState.VERIFICATION_PENDING
    assert second_check.state is PublishState.VERIFICATION_PENDING
    assert adapter.execute_calls == 1
    assert adapter.verify_calls == 2


def test_prepare_failure_requires_reprepare() -> None:
    attempts = 0

    def prepare_hook(request: SocialPublishRequest) -> None:
        nonlocal attempts
        del request
        attempts += 1
        if attempts == 1:
            raise ValueError("asset is not ready")

    adapter = FakePublisherAdapter(prepare_hook=prepare_hook)
    store = InMemoryPublishStateStore()
    coordinator = SocialPublishCoordinator(
        adapters={"fake": adapter},
        store=store,
        approval_authority=HmacApprovalAuthority(b"a" * 32, issuer="test"),
        audit_sink=InMemoryAuditSink(),
    )
    request = make_request()

    with pytest.raises(ValueError, match="not ready"):
        asyncio.run(coordinator.prepare(request))
    with pytest.raises(InvalidPublishTransition, match="reprepare"):
        coordinator.retry(request.request_id)

    assert (
        asyncio.run(coordinator.reprepare(request.request_id)).state
        is PublishState.AWAITING_APPROVAL
    )
    assert attempts == 2


def test_uncertain_execute_failure_moves_to_verification_pending() -> None:
    class UncertainAdapter(FakePublisherAdapter):
        async def execute(self, request: SocialPublishRequest) -> PlatformPublishResult:
            del request
            self.execute_calls += 1
            raise PublisherAdapterError("connection lost after submit")

    adapter = UncertainAdapter()
    store = InMemoryPublishStateStore()
    authority = HmacApprovalAuthority(b"a" * 32, issuer="test")
    coordinator = SocialPublishCoordinator(
        adapters={"fake": adapter},
        store=store,
        approval_authority=authority,
        audit_sink=InMemoryAuditSink(),
    )
    request = make_request()
    asyncio.run(coordinator.prepare(request))
    token = authority.issue(request, grant_id="grant-1")

    with pytest.raises(PublisherAdapterError, match="connection lost"):
        asyncio.run(coordinator.execute(request.request_id, token))

    record = store.get(request.request_id)
    assert record is not None
    assert record.state is PublishState.VERIFICATION_PENDING
    with pytest.raises((ApprovalGrantError, InvalidPublishTransition)):
        asyncio.run(coordinator.execute(request.request_id, token))
    assert adapter.execute_calls == 1
