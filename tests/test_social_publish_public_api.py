from __future__ import annotations

from typing import Protocol

from trinity_agentic_kit import social_publish
from trinity_agentic_kit.social_publish import (
    FakePublisherAdapter,
    InMemoryPublishStateStore,
    PublisherAdapter,
    PublishStateStore,
)


class AdapterFactory(Protocol):
    def __call__(self) -> PublisherAdapter: ...


def test_fake_adapter_satisfies_public_adapter_contract() -> None:
    factory: AdapterFactory = FakePublisherAdapter
    adapter = factory()
    assert adapter.platform == "fake"


def test_in_memory_store_satisfies_public_store_contract() -> None:
    store: PublishStateStore = InMemoryPublishStateStore()
    assert store.get("missing") is None


def test_public_api_exports_expected_contracts() -> None:
    expected = {
        "ApprovalGrant",
        "FakePublisherAdapter",
        "HmacApprovalAuthority",
        "InMemoryPublishStateStore",
        "PlatformPublishResult",
        "PublisherAdapter",
        "PublishState",
        "SQLitePublishStateStore",
        "SocialPublishCoordinator",
        "SocialPublishRequest",
    }
    assert expected.issubset(set(social_publish.__all__))
