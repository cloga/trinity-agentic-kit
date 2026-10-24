from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Protocol, cast

import pytest
from jsonschema import Draft202012Validator

from trinity_agentic_kit.social_publish import (
    COMMENT_COLLECTION_REQUEST_SCHEMA,
    COMMENT_COLLECTION_RESULT_SCHEMA,
    CollectedComment,
    CommentCollectionConsent,
    CommentCollectionCoordinator,
    CommentCollectionError,
    CommentCollectionRequest,
    CommentCollectionStatus,
    CommentCollectorAdapterError,
    CommentPage,
    DuplicateCommentCollectionRequest,
    FakeCommentCollectorAdapter,
    InMemoryCommentCollectionStore,
)


class SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def make_request(
    *,
    now: datetime | None = None,
    request_id: str = "collection-1",
    idempotency_key: str = "idem-1",
    requested_fields: tuple[str, ...] = ("text", "created_at"),
    max_pages: int = 1,
    max_retries: int = 1,
) -> CommentCollectionRequest:
    instant = now or datetime(2026, 1, 1, tzinfo=timezone.utc)
    granted = instant.isoformat()
    expires = (instant.replace(year=instant.year + 1)).isoformat()
    retention = (instant.replace(year=instant.year + 2)).isoformat()
    return CommentCollectionRequest(
        request_id=request_id,
        platform="fake",
        resource_ref="post:123",
        idempotency_key=idempotency_key,
        consent=CommentCollectionConsent(
            consent_id="consent-1",
            granted_by="operator-1",
            purpose="moderation review",
            platform="fake",
            resource_ref="post:123",
            allowed_fields=("text", "created_at", "author_reference"),
            granted_at=granted,
            expires_at=expires,
            retention_until=retention,
        ),
        requested_fields=requested_fields,
        page_size=2,
        max_pages=max_pages,
        max_retries=max_retries,
    )


def make_coordinator(
    adapter: FakeCommentCollectorAdapter, *, now: datetime | None = None
) -> tuple[CommentCollectionCoordinator, InMemoryCommentCollectionStore]:
    store = InMemoryCommentCollectionStore()
    clock = now or datetime(2026, 1, 1, tzinfo=timezone.utc)
    coordinator = CommentCollectionCoordinator(
        adapters={"fake": adapter},
        store=store,
        clock=lambda: clock,
    )
    return coordinator, store


def test_collection_resumes_cursor_deduplicates_and_minimizes_fields() -> None:
    adapter = FakeCommentCollectorAdapter(
        pages=(
            CommentPage(
                comments=(
                    CollectedComment(
                        "comment-1", "first", "2026-01-01T00:00:00Z", "user-1"
                    ),
                    CollectedComment(
                        "comment-2", "second", "2026-01-01T00:01:00Z", "user-2"
                    ),
                ),
                next_cursor="cursor-2",
            ),
            CommentPage(
                comments=(
                    CollectedComment(
                        "comment-2", "duplicate", "2026-01-01T00:01:00Z", "user-2"
                    ),
                    CollectedComment(
                        "comment-3", "third", "2026-01-01T00:02:00Z", "user-3"
                    ),
                )
            ),
        )
    )
    coordinator, _ = make_coordinator(adapter)
    request = make_request(max_pages=1)

    first = asyncio.run(coordinator.collect(request))
    second = asyncio.run(coordinator.collect(request))
    replay = asyncio.run(coordinator.collect(request))

    assert first.status is CommentCollectionStatus.PARTIAL
    assert first.next_cursor == "cursor-2"
    assert second.status is CommentCollectionStatus.COMPLETE
    assert [comment.comment_id for comment in second.comments] == [
        "comment-1",
        "comment-2",
        "comment-3",
    ]
    assert all(comment.author_reference is None for comment in second.comments)
    assert replay == second
    assert adapter.calls == [(None, 2), ("cursor-2", 2)]


def test_collection_retries_only_within_bound_and_reports_failure() -> None:
    adapter = FakeCommentCollectorAdapter(
        failures=(
            CommentCollectorAdapterError(
                "temporarily unavailable", code="temporary", retryable=True
            ),
            CommentCollectorAdapterError(
                "temporarily unavailable", code="temporary", retryable=True
            ),
        )
    )
    coordinator, _ = make_coordinator(adapter)

    result = asyncio.run(coordinator.collect(make_request(max_retries=1)))

    assert result.status is CommentCollectionStatus.FAILED
    assert result.error_code == "temporary"
    assert result.retryable
    assert len(adapter.calls) == 2


def test_expired_consent_is_rejected_before_adapter_call() -> None:
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    adapter = FakeCommentCollectorAdapter(pages=(CommentPage(comments=()),))
    coordinator, _ = make_coordinator(adapter, now=now)

    with pytest.raises(CommentCollectionError, match="expired"):
        request = make_request()
        expired_consent = replace(
            request.consent,
            expires_at="2026-01-02T12:00:00+00:00",
        )
        expired_request = replace(request, consent=expired_consent)
        asyncio.run(coordinator.collect(expired_request))
    assert adapter.calls == []


def test_request_rejects_fields_outside_explicit_consent() -> None:
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    consent = CommentCollectionConsent(
        consent_id="consent-1",
        granted_by="operator-1",
        purpose="review",
        platform="fake",
        resource_ref="post:123",
        allowed_fields=("text",),
        granted_at=instant.isoformat(),
        expires_at="2027-01-01T00:00:00+00:00",
        retention_until="2028-01-01T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="does not allow"):
        CommentCollectionRequest(
            request_id="collection-1",
            platform="fake",
            resource_ref="post:123",
            idempotency_key="idem-1",
            consent=consent,
            requested_fields=("text", "author_reference"),
        )


def test_idempotency_key_cannot_be_reused_for_different_scope() -> None:
    adapter = FakeCommentCollectorAdapter(pages=(CommentPage(comments=()),))
    coordinator, _ = make_coordinator(adapter)
    first = make_request()
    changed = make_request(request_id="collection-2")

    asyncio.run(coordinator.collect(first))
    with pytest.raises(DuplicateCommentCollectionRequest):
        asyncio.run(coordinator.collect(changed))


def test_public_comment_schemas_validate_request_and_result() -> None:
    adapter = FakeCommentCollectorAdapter(
        pages=(CommentPage(comments=(CollectedComment("comment-1", text="hello"),)),)
    )
    coordinator, _ = make_coordinator(adapter)
    request = make_request()
    result = asyncio.run(coordinator.collect(request))

    request_validator = cast(
        SchemaValidator, Draft202012Validator(COMMENT_COLLECTION_REQUEST_SCHEMA)
    )
    result_validator = cast(
        SchemaValidator, Draft202012Validator(COMMENT_COLLECTION_RESULT_SCHEMA)
    )
    request_payload = asdict(request)
    request_payload["consent"]["allowed_fields"] = list(
        request_payload["consent"]["allowed_fields"]
    )
    request_payload["requested_fields"] = list(request_payload["requested_fields"])
    result_payload = asdict(result)
    result_payload["status"] = result.status.value
    result_payload["comments"] = [
        {
            **asdict(comment),
        }
        for comment in result.comments
    ]
    request_validator.validate(request_payload)
    result_validator.validate(result_payload)
