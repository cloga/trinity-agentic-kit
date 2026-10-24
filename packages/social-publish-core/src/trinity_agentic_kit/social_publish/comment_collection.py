from __future__ import annotations

import copy
import hashlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from .contracts import stable_json

COMMENT_COLLECTION_SCHEMA_VERSION = 1
COMMENT_FIELDS = frozenset({"text", "created_at", "author_reference"})
MAX_COMMENT_PAGE_SIZE = 100
MAX_COMMENT_PAGES_PER_CALL = 100
MAX_COMMENT_RETRIES = 5


class CommentCollectionError(RuntimeError):
    """Base error for platform-neutral comment collection."""


class DuplicateCommentCollectionRequest(CommentCollectionError):
    """Raised when an idempotency key is reused with different collection scope."""


class CommentCollectorAdapterError(CommentCollectionError):
    """An adapter failure with an explicit retry policy."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class CommentCollectionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


def _parse_time(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CommentCollectionConsent:
    consent_id: str
    granted_by: str
    purpose: str
    platform: str
    resource_ref: str
    allowed_fields: tuple[str, ...]
    granted_at: str
    expires_at: str
    retention_until: str
    schema_version: int = COMMENT_COLLECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "consent_id": self.consent_id,
            "granted_by": self.granted_by,
            "purpose": self.purpose,
            "platform": self.platform,
            "resource_ref": self.resource_ref,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing consent fields: {', '.join(missing)}")
        if self.schema_version != COMMENT_COLLECTION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported comment collection schema version: {self.schema_version}"
            )
        if len(set(self.allowed_fields)) != len(self.allowed_fields):
            raise ValueError("Consent allowed_fields cannot contain duplicates")
        unknown = set(self.allowed_fields) - COMMENT_FIELDS
        if unknown:
            raise ValueError(
                "Unsupported consent fields: " + ", ".join(sorted(unknown))
            )
        granted = _parse_time(self.granted_at, field_name="granted_at")
        expires = _parse_time(self.expires_at, field_name="expires_at")
        retention = _parse_time(self.retention_until, field_name="retention_until")
        if expires <= granted:
            raise ValueError("expires_at must be later than granted_at")
        if retention < granted:
            raise ValueError("retention_until cannot precede granted_at")


@dataclass(frozen=True, slots=True)
class CommentCollectionRequest:
    request_id: str
    platform: str
    resource_ref: str
    idempotency_key: str
    consent: CommentCollectionConsent
    requested_fields: tuple[str, ...] = ("text", "created_at")
    page_size: int = 50
    max_pages: int = 10
    max_retries: int = 2
    schema_version: int = COMMENT_COLLECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "request_id": self.request_id,
            "platform": self.platform,
            "resource_ref": self.resource_ref,
            "idempotency_key": self.idempotency_key,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing comment collection fields: {', '.join(missing)}")
        if self.schema_version != COMMENT_COLLECTION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported comment collection schema version: {self.schema_version}"
            )
        if self.platform != self.consent.platform:
            raise ValueError("Consent platform does not match request platform")
        if self.resource_ref != self.consent.resource_ref:
            raise ValueError("Consent resource does not match request resource")
        if not self.requested_fields:
            raise ValueError("requested_fields must explicitly name collected fields")
        if len(set(self.requested_fields)) != len(self.requested_fields):
            raise ValueError("requested_fields cannot contain duplicates")
        unknown = set(self.requested_fields) - COMMENT_FIELDS
        if unknown:
            raise ValueError(
                "Unsupported requested fields: " + ", ".join(sorted(unknown))
            )
        unauthorized = set(self.requested_fields) - set(self.consent.allowed_fields)
        if unauthorized:
            raise ValueError(
                "Consent does not allow requested fields: "
                + ", ".join(sorted(unauthorized))
            )
        if not 1 <= self.page_size <= MAX_COMMENT_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_COMMENT_PAGE_SIZE}")
        if not 1 <= self.max_pages <= MAX_COMMENT_PAGES_PER_CALL:
            raise ValueError(
                f"max_pages must be between 1 and {MAX_COMMENT_PAGES_PER_CALL}"
            )
        if not 0 <= self.max_retries <= MAX_COMMENT_RETRIES:
            raise ValueError(f"max_retries must be between 0 and {MAX_COMMENT_RETRIES}")


@dataclass(frozen=True, slots=True)
class CollectedComment:
    comment_id: str
    text: str | None = None
    created_at: str | None = None
    author_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.comment_id.strip():
            raise ValueError("comment_id cannot be blank")


@dataclass(frozen=True, slots=True)
class CommentPage:
    comments: tuple[CollectedComment, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if self.next_cursor is not None and not self.next_cursor.strip():
            raise ValueError("next_cursor must be non-empty when provided")


@dataclass(frozen=True, slots=True)
class CommentCollectionResult:
    request_id: str
    status: CommentCollectionStatus
    comments: tuple[CollectedComment, ...]
    next_cursor: str | None
    pages_fetched: int
    retention_until: str
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    schema_version: int = COMMENT_COLLECTION_SCHEMA_VERSION


def _empty_comments() -> list[CollectedComment]:
    return []


@dataclass(slots=True)
class CommentCollectionRecord:
    request: CommentCollectionRequest
    request_digest: str
    status: CommentCollectionStatus = CommentCollectionStatus.PARTIAL
    comments: list[CollectedComment] = field(default_factory=_empty_comments)
    next_cursor: str | None = None
    pages_fetched: int = 0
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False


class CommentCollectorAdapter(Protocol):
    platform: str

    async def fetch_page(
        self,
        request: CommentCollectionRequest,
        *,
        cursor: str | None,
        limit: int,
    ) -> CommentPage: ...


class CommentCollectionStore(Protocol):
    def get(self, request_id: str) -> CommentCollectionRecord | None: ...

    def get_by_idempotency_key(self, key: str) -> CommentCollectionRecord | None: ...

    def save(self, record: CommentCollectionRecord) -> None: ...


class InMemoryCommentCollectionStore:
    """Process-local store intended for tests and short-lived integrations."""

    def __init__(self) -> None:
        self._records: dict[str, CommentCollectionRecord] = {}
        self._idempotency_index: dict[str, str] = {}

    def get(self, request_id: str) -> CommentCollectionRecord | None:
        record = self._records.get(request_id)
        return copy.deepcopy(record) if record is not None else None

    def get_by_idempotency_key(self, key: str) -> CommentCollectionRecord | None:
        request_id = self._idempotency_index.get(key)
        return self.get(request_id) if request_id is not None else None

    def save(self, record: CommentCollectionRecord) -> None:
        indexed = self._idempotency_index.get(record.request.idempotency_key)
        if indexed is not None and indexed != record.request.request_id:
            raise DuplicateCommentCollectionRequest(
                f"Duplicate comment collection idempotency key: "
                f"{record.request.idempotency_key}"
            )
        existing = self._records.get(record.request.request_id)
        if existing is not None and existing.request_digest != record.request_digest:
            raise DuplicateCommentCollectionRequest(
                f"Request id {record.request.request_id!r} is bound to different scope"
            )
        self._records[record.request.request_id] = copy.deepcopy(record)
        self._idempotency_index[record.request.idempotency_key] = (
            record.request.request_id
        )


def _request_digest(request: CommentCollectionRequest) -> str:
    return hashlib.sha256(stable_json(asdict(request))).hexdigest()


class CommentCollectionCoordinator:
    """Collect consent-scoped comment pages with bounded retries and deduplication."""

    def __init__(
        self,
        *,
        adapters: dict[str, CommentCollectorAdapter],
        store: CommentCollectionStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def collect(
        self, request: CommentCollectionRequest
    ) -> CommentCollectionResult:
        self._validate_consent(request)
        adapter = self._adapters.get(request.platform)
        if adapter is None:
            raise CommentCollectionError(
                f"No comment collector registered for platform: {request.platform}"
            )
        if adapter.platform != request.platform:
            raise CommentCollectionError(
                "Registered comment collector platform does not match request"
            )

        digest = _request_digest(request)
        record = self._store.get_by_idempotency_key(request.idempotency_key)
        if record is not None and record.request_digest != digest:
            raise DuplicateCommentCollectionRequest(
                f"Idempotency key {request.idempotency_key!r} "
                "is bound to different collection scope"
            )
        if record is None:
            record = self._store.get(request.request_id)
            if record is not None and record.request_digest != digest:
                raise DuplicateCommentCollectionRequest(
                    f"Request id {request.request_id!r} is bound to different scope"
                )
        if record is None:
            record = CommentCollectionRecord(request=request, request_digest=digest)
            self._store.save(record)
        elif record.status is CommentCollectionStatus.COMPLETE:
            return self._result(record)

        record.error_code = ""
        record.error_message = ""
        record.retryable = False
        seen_comment_ids = {comment.comment_id for comment in record.comments}
        for _ in range(request.max_pages):
            self._validate_consent(request)
            cursor = record.next_cursor
            page = await self._fetch_page(adapter, request, cursor=cursor)
            if page is None:
                record = self._record_for_request(request)
                break
            if len(page.comments) > request.page_size:
                self._mark_failure(
                    record,
                    code="page_size_exceeded",
                    message="Collector returned more comments than requested",
                    retryable=False,
                )
                break
            record.pages_fetched += 1
            for comment in page.comments:
                if comment.comment_id not in seen_comment_ids:
                    record.comments.append(self._minimize(comment, request))
                    seen_comment_ids.add(comment.comment_id)
            if page.next_cursor == cursor and page.next_cursor is not None:
                self._mark_failure(
                    record,
                    code="cursor_stalled",
                    message="Collector returned the same pagination cursor",
                    retryable=False,
                )
                break
            record.next_cursor = page.next_cursor
            if page.next_cursor is None:
                record.status = CommentCollectionStatus.COMPLETE
                break
            record.status = CommentCollectionStatus.PARTIAL
            self._store.save(record)
        self._store.save(record)
        return self._result(record)

    async def _fetch_page(
        self,
        adapter: CommentCollectorAdapter,
        request: CommentCollectionRequest,
        *,
        cursor: str | None,
    ) -> CommentPage | None:
        for attempt in range(request.max_retries + 1):
            try:
                return await adapter.fetch_page(
                    request,
                    cursor=cursor,
                    limit=request.page_size,
                )
            except CommentCollectorAdapterError as exc:
                if not exc.retryable or attempt == request.max_retries:
                    record = self._record_for_request(request)
                    self._mark_failure(
                        record,
                        code=exc.code,
                        message=str(exc),
                        retryable=exc.retryable,
                    )
                    self._store.save(record)
                    return None
        return None

    def _record_for_request(
        self, request: CommentCollectionRequest
    ) -> CommentCollectionRecord:
        record = self._store.get(request.request_id)
        if record is None:
            raise CommentCollectionError("Collection record disappeared during fetch")
        return record

    @staticmethod
    def _minimize(
        comment: CollectedComment, request: CommentCollectionRequest
    ) -> CollectedComment:
        fields = set(request.requested_fields)
        return CollectedComment(
            comment_id=comment.comment_id,
            text=comment.text if "text" in fields else None,
            created_at=comment.created_at if "created_at" in fields else None,
            author_reference=(
                comment.author_reference if "author_reference" in fields else None
            ),
        )

    def _validate_consent(self, request: CommentCollectionRequest) -> None:
        now = self._clock().astimezone(timezone.utc)
        consent = request.consent
        if _parse_time(consent.granted_at, field_name="granted_at") > now:
            raise CommentCollectionError("Collection consent is not yet effective")
        if _parse_time(consent.expires_at, field_name="expires_at") <= now:
            raise CommentCollectionError("Collection consent has expired")
        if _parse_time(consent.retention_until, field_name="retention_until") <= now:
            raise CommentCollectionError("Consent retention deadline has passed")

    @staticmethod
    def _mark_failure(
        record: CommentCollectionRecord,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        record.status = (
            CommentCollectionStatus.PARTIAL
            if record.comments or record.next_cursor
            else CommentCollectionStatus.FAILED
        )
        record.error_code = code
        record.error_message = message
        record.retryable = retryable

    @staticmethod
    def _result(record: CommentCollectionRecord) -> CommentCollectionResult:
        return CommentCollectionResult(
            request_id=record.request.request_id,
            status=record.status,
            comments=tuple(record.comments),
            next_cursor=record.next_cursor,
            pages_fetched=record.pages_fetched,
            retention_until=record.request.consent.retention_until,
            error_code=record.error_code,
            error_message=record.error_message,
            retryable=record.retryable,
        )


class FakeCommentCollectorAdapter:
    """Deterministic no-network collector for contract tests and examples."""

    def __init__(
        self,
        platform: str = "fake",
        *,
        pages: tuple[CommentPage, ...] = (),
        failures: tuple[CommentCollectorAdapterError, ...] = (),
    ) -> None:
        self.platform = platform
        self.pages = pages
        self.failures = list(failures)
        self.calls: list[tuple[str | None, int]] = []
        self._cursor_indices: dict[str | None, int] = {}

    async def fetch_page(
        self,
        request: CommentCollectionRequest,
        *,
        cursor: str | None,
        limit: int,
    ) -> CommentPage:
        del request
        self.calls.append((cursor, limit))
        if self.failures:
            raise self.failures.pop(0)
        index = self._cursor_indices.get(cursor, 0)
        if index >= len(self.pages):
            return CommentPage(comments=())
        page = self.pages[index]
        self._cursor_indices[page.next_cursor] = index + 1
        return CommentPage(comments=page.comments, next_cursor=page.next_cursor)
