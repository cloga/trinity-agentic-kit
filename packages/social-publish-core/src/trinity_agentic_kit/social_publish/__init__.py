"""Safe platform-neutral social publication contracts and orchestration."""

from .adapters import FakePublisherAdapter
from .approval import HmacApprovalAuthority
from .contracts import (
    APPROVAL_GRANT_SCHEMA,
    EXECUTE_PUBLISH_CAPABILITY,
    PLATFORM_PUBLISH_RESULT_SCHEMA,
    SOCIAL_PUBLISH_REQUEST_SCHEMA,
    SOCIAL_PUBLISH_SCHEMA_VERSION,
    ApprovalGrant,
    ApprovalGrantError,
    AuditSink,
    ConcurrentPublishUpdate,
    DuplicatePublishRequest,
    InvalidPublishTransition,
    PlatformPublishResult,
    PublisherAdapter,
    PublisherAdapterError,
    PublishEvent,
    PublishRecord,
    PublishState,
    PublishStateStore,
    SocialPublishError,
    SocialPublishRequest,
    request_digest,
)
from .coordinator import SocialPublishCoordinator
from .sqlite_store import SQLitePublishStateStore
from .stores import InMemoryAuditSink, InMemoryPublishStateStore

__all__ = [
    "APPROVAL_GRANT_SCHEMA",
    "EXECUTE_PUBLISH_CAPABILITY",
    "PLATFORM_PUBLISH_RESULT_SCHEMA",
    "SOCIAL_PUBLISH_REQUEST_SCHEMA",
    "SOCIAL_PUBLISH_SCHEMA_VERSION",
    "ApprovalGrant",
    "ApprovalGrantError",
    "AuditSink",
    "ConcurrentPublishUpdate",
    "DuplicatePublishRequest",
    "FakePublisherAdapter",
    "HmacApprovalAuthority",
    "InMemoryAuditSink",
    "InMemoryPublishStateStore",
    "InvalidPublishTransition",
    "PlatformPublishResult",
    "PublishEvent",
    "PublishRecord",
    "PublishState",
    "PublishStateStore",
    "PublisherAdapter",
    "PublisherAdapterError",
    "SQLitePublishStateStore",
    "SocialPublishCoordinator",
    "SocialPublishError",
    "SocialPublishRequest",
    "request_digest",
]
