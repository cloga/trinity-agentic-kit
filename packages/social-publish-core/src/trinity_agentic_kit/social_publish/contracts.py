from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from importlib.resources import files
from typing import Any, Protocol, cast

SOCIAL_PUBLISH_SCHEMA_VERSION = 1
EXECUTE_PUBLISH_CAPABILITY = "publish.execute"
JsonObject = dict[str, Any]


def _empty_json_object() -> JsonObject:
    return {}


def _empty_string_list() -> list[str]:
    return []


def _load_schema(filename: str) -> JsonObject:
    payload: object = json.loads(
        files("trinity_agentic_kit.social_publish.schemas")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid bundled JSON Schema: {filename}")
    return cast(JsonObject, payload)


SOCIAL_PUBLISH_REQUEST_SCHEMA = _load_schema("social-publish-request-v1.json")
PLATFORM_PUBLISH_RESULT_SCHEMA = _load_schema("platform-publish-result-v1.json")
APPROVAL_GRANT_SCHEMA = _load_schema("approval-grant-v1.json")


class SocialPublishError(RuntimeError):
    """Base error for platform-neutral publication workflows."""


class InvalidPublishTransition(SocialPublishError):
    """Raised when a publication state transition is not allowed."""


class ApprovalGrantError(SocialPublishError):
    """Raised when an approval grant is missing, invalid, or expired."""


class DuplicatePublishRequest(SocialPublishError):
    """Raised when an idempotency key is reused with different content."""


class ConcurrentPublishUpdate(SocialPublishError):
    """Raised when a stale process attempts to overwrite a newer record."""


class PublisherAdapterError(SocialPublishError):
    """Raised when an adapter cannot complete an operation."""


class PublishState(str, Enum):
    PREPARING = "preparing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUBMITTED = "submitted"
    VERIFYING = "verifying"
    PUBLISHED = "published"
    VERIFICATION_PENDING = "verification_pending"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[PublishState, frozenset[PublishState]] = {
    PublishState.PREPARING: frozenset(
        {PublishState.AWAITING_APPROVAL, PublishState.FAILED}
    ),
    PublishState.AWAITING_APPROVAL: frozenset(
        {PublishState.APPROVED, PublishState.CANCELLED}
    ),
    PublishState.APPROVED: frozenset({PublishState.EXECUTING, PublishState.CANCELLED}),
    PublishState.EXECUTING: frozenset(
        {
            PublishState.SUBMITTED,
            PublishState.PUBLISHED,
            PublishState.VERIFICATION_PENDING,
            PublishState.FAILED,
        }
    ),
    PublishState.SUBMITTED: frozenset(
        {
            PublishState.VERIFYING,
            PublishState.PUBLISHED,
            PublishState.VERIFICATION_PENDING,
        }
    ),
    PublishState.VERIFYING: frozenset(
        {
            PublishState.PUBLISHED,
            PublishState.VERIFICATION_PENDING,
            PublishState.FAILED,
        }
    ),
    PublishState.VERIFICATION_PENDING: frozenset(
        {PublishState.VERIFYING, PublishState.CANCELLED}
    ),
    PublishState.PUBLISHED: frozenset(),
    PublishState.FAILED: frozenset(
        {
            PublishState.PREPARING,
            PublishState.AWAITING_APPROVAL,
            PublishState.CANCELLED,
        }
    ),
    PublishState.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class SocialPublishRequest:
    request_id: str
    platform: str
    media_type: str
    asset_ref: str
    title: str
    description: str
    idempotency_key: str
    metadata: JsonObject = field(default_factory=_empty_json_object)
    schema_version: int = SOCIAL_PUBLISH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "request_id": self.request_id,
            "platform": self.platform,
            "media_type": self.media_type,
            "asset_ref": self.asset_ref,
            "idempotency_key": self.idempotency_key,
        }
        missing = [
            name for name, value in required.items() if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(
                f"Missing required publish request fields: {', '.join(missing)}"
            )
        if self.schema_version != SOCIAL_PUBLISH_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported social publish schema version: {self.schema_version}"
            )


@dataclass(frozen=True, slots=True)
class PlatformPublishResult:
    submitted: bool
    verification_pending: bool = False
    published_url: str = ""
    platform_reference: str = ""
    evidence: tuple[str, ...] = ()
    error_code: str = ""
    error_message: str = ""
    retryable: bool = False
    requires_manual_intervention: bool = False


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    grant_id: str
    request_id: str
    platform: str
    idempotency_key: str
    request_digest: str
    capabilities: tuple[str, ...]
    issued_at: str
    expires_at: str
    issuer: str
    schema_version: int = SOCIAL_PUBLISH_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PublishEvent:
    sequence: int
    state: PublishState
    occurred_at: str
    actor: str
    details: JsonObject = field(default_factory=_empty_json_object)


@dataclass(slots=True)
class PublishRecord:
    request: SocialPublishRequest
    request_digest: str
    state: PublishState
    events: list[PublishEvent]
    approval_grant_id: str = ""
    consumed_approval_grant_ids: list[str] = field(default_factory=_empty_string_list)
    platform_reference: str = ""
    published_url: str = ""
    last_error_code: str = ""
    last_error_message: str = ""
    revision: int = 0


class PublisherAdapter(Protocol):
    platform: str

    async def prepare(self, request: SocialPublishRequest) -> None: ...

    async def execute(self, request: SocialPublishRequest) -> PlatformPublishResult: ...

    async def verify(
        self,
        request: SocialPublishRequest,
        *,
        platform_reference: str,
    ) -> PlatformPublishResult: ...


class PublishStateStore(Protocol):
    def get(self, request_id: str) -> PublishRecord | None: ...

    def get_by_idempotency_key(self, idempotency_key: str) -> PublishRecord | None: ...

    def save(self, record: PublishRecord) -> None: ...


class AuditSink(Protocol):
    def append(self, request_id: str, event: PublishEvent) -> None: ...


def stable_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def request_digest(request: SocialPublishRequest) -> str:
    return hashlib.sha256(stable_json(asdict(request))).hexdigest()
