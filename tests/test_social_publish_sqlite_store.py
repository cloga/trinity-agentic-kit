from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from trinity_agentic_kit.social_publish import (
    ConcurrentPublishUpdate,
    DuplicatePublishRequest,
    PublishEvent,
    PublishRecord,
    PublishState,
    SocialPublishRequest,
    SQLitePublishStateStore,
)


def make_record(
    *,
    request_id: str = "request-1",
    idempotency_key: str = "key-1",
) -> PublishRecord:
    request = SocialPublishRequest(
        request_id=request_id,
        platform="fake",
        media_type="video",
        asset_ref="asset://video",
        title="Title",
        description="Description",
        idempotency_key=idempotency_key,
        metadata={"source": "test"},
    )
    return PublishRecord(
        request=request,
        request_digest=f"digest-{request_id}",
        state=PublishState.AWAITING_APPROVAL,
        events=[
            PublishEvent(
                sequence=1,
                state=PublishState.AWAITING_APPROVAL,
                occurred_at="2026-01-01T00:00:00+00:00",
                actor="agent",
                details={"source": "test"},
            )
        ],
    )


def test_sqlite_store_round_trips_full_record(tmp_path: Path) -> None:
    store = SQLitePublishStateStore(tmp_path / "publish.db")
    store.init_schema()
    record = make_record()
    record.approval_grant_id = "grant-1"
    record.consumed_approval_grant_ids = ["grant-0"]
    record.platform_reference = "submission-1"

    store.save(record)
    loaded = store.get("request-1")

    assert record.revision == 1
    assert loaded is not None
    assert loaded.request.metadata == {"source": "test"}
    assert loaded.state is PublishState.AWAITING_APPROVAL
    assert loaded.events[0].details == {"source": "test"}
    assert loaded.approval_grant_id == "grant-1"
    assert loaded.consumed_approval_grant_ids == ["grant-0"]
    assert loaded.platform_reference == "submission-1"
    assert store.get_by_idempotency_key("key-1") == loaded


def test_sqlite_store_updates_and_preserves_ordered_events(
    tmp_path: Path,
) -> None:
    store = SQLitePublishStateStore(tmp_path / "publish.db")
    store.init_schema()
    record = make_record()
    store.save(record)
    record.state = PublishState.APPROVED
    record.events.append(
        PublishEvent(
            sequence=2,
            state=PublishState.APPROVED,
            occurred_at="2026-01-01T00:01:00+00:00",
            actor="operator",
        )
    )

    store.save(record)
    loaded = store.get("request-1")

    assert loaded is not None
    assert loaded.revision == 2
    assert [event.sequence for event in loaded.events] == [1, 2]
    assert loaded.state is PublishState.APPROVED


def test_sqlite_store_rejects_stale_revision(tmp_path: Path) -> None:
    store = SQLitePublishStateStore(tmp_path / "publish.db")
    store.init_schema()
    record = make_record()
    store.save(record)
    stale = store.get("request-1")
    fresh = store.get("request-1")
    assert stale is not None and fresh is not None
    fresh.state = PublishState.APPROVED
    store.save(fresh)
    stale.state = PublishState.CANCELLED

    with pytest.raises(ConcurrentPublishUpdate):
        store.save(stale)


def test_sqlite_store_rejects_duplicate_idempotency_key(
    tmp_path: Path,
) -> None:
    store = SQLitePublishStateStore(tmp_path / "publish.db")
    store.init_schema()
    store.save(make_record())

    with pytest.raises(DuplicatePublishRequest):
        store.save(make_record(request_id="request-2"))


def test_sqlite_store_migrates_legacy_grant_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "publish.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE social_publish_records (
                request_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                request_json TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                approval_grant_id TEXT NOT NULL DEFAULT '',
                platform_reference TEXT NOT NULL DEFAULT '',
                published_url TEXT NOT NULL DEFAULT '',
                last_error_code TEXT NOT NULL DEFAULT '',
                last_error_message TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    SQLitePublishStateStore(db_path).init_schema()

    with closing(sqlite3.connect(db_path)) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(social_publish_records)"
            ).fetchall()
        }
    assert "consumed_approval_grant_ids_json" in columns
