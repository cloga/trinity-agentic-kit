from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from .contracts import (
    ConcurrentPublishUpdate,
    DuplicatePublishRequest,
    PublishEvent,
    PublishRecord,
    PublishState,
    SocialPublishRequest,
)


class SQLitePublishStateStore:
    """Durable platform-neutral publish state with optimistic concurrency."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser().resolve()

    def init_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS social_publish_records (
                    request_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_json TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    approval_grant_id TEXT NOT NULL DEFAULT '',
                    consumed_approval_grant_ids_json TEXT NOT NULL DEFAULT '[]',
                    platform_reference TEXT NOT NULL DEFAULT '',
                    published_url TEXT NOT NULL DEFAULT '',
                    last_error_code TEXT NOT NULL DEFAULT '',
                    last_error_message TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS social_publish_events (
                    request_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    PRIMARY KEY (request_id, sequence),
                    FOREIGN KEY (request_id)
                        REFERENCES social_publish_records(request_id)
                        ON DELETE CASCADE
                );
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(social_publish_records)"
                ).fetchall()
            }
            if "consumed_approval_grant_ids_json" not in columns:
                connection.execute(
                    """
                    ALTER TABLE social_publish_records
                    ADD COLUMN consumed_approval_grant_ids_json
                    TEXT NOT NULL DEFAULT '[]'
                    """
                )

    def get(self, request_id: str) -> PublishRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM social_publish_records WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            return (
                self._deserialize_record(connection, row) if row is not None else None
            )

    def get_by_idempotency_key(self, idempotency_key: str) -> PublishRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM social_publish_records WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return (
                self._deserialize_record(connection, row) if row is not None else None
            )

    def save(self, record: PublishRecord) -> None:
        request_json = json.dumps(
            asdict(record.request),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT revision FROM social_publish_records WHERE request_id = ?",
                (record.request.request_id,),
            ).fetchone()
            try:
                if existing is None:
                    if record.revision != 0:
                        raise ConcurrentPublishUpdate(
                            "New publish record must start at revision 0"
                        )
                    next_revision = 1
                    connection.execute(
                        """
                        INSERT INTO social_publish_records (
                            request_id, idempotency_key, request_json,
                            request_digest, state, approval_grant_id,
                            consumed_approval_grant_ids_json,
                            platform_reference, published_url,
                            last_error_code, last_error_message, revision
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        self._record_values(record, request_json, next_revision),
                    )
                else:
                    current_revision = int(existing["revision"])
                    if current_revision != record.revision:
                        raise ConcurrentPublishUpdate(
                            f"Stale publish revision {record.revision}; "
                            f"current revision is {current_revision}"
                        )
                    next_revision = current_revision + 1
                    cursor = connection.execute(
                        """
                        UPDATE social_publish_records
                        SET idempotency_key = ?,
                            request_json = ?,
                            request_digest = ?,
                            state = ?,
                            approval_grant_id = ?,
                            consumed_approval_grant_ids_json = ?,
                            platform_reference = ?,
                            published_url = ?,
                            last_error_code = ?,
                            last_error_message = ?,
                            revision = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE request_id = ? AND revision = ?
                        """,
                        (
                            record.request.idempotency_key,
                            request_json,
                            record.request_digest,
                            record.state.value,
                            record.approval_grant_id,
                            json.dumps(
                                record.consumed_approval_grant_ids,
                                separators=(",", ":"),
                            ),
                            record.platform_reference,
                            record.published_url,
                            record.last_error_code,
                            record.last_error_message,
                            next_revision,
                            record.request.request_id,
                            current_revision,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ConcurrentPublishUpdate(
                            "Publish record changed concurrently: "
                            f"{record.request.request_id}"
                        )
                self._save_events(connection, record)
            except sqlite3.IntegrityError as exc:
                raise DuplicatePublishRequest(
                    "Duplicate publish request or idempotency key: "
                    f"{record.request.idempotency_key}"
                ) from exc
            record.revision = next_revision

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _record_values(
        record: PublishRecord,
        request_json: str,
        revision: int,
    ) -> tuple[Any, ...]:
        return (
            record.request.request_id,
            record.request.idempotency_key,
            request_json,
            record.request_digest,
            record.state.value,
            record.approval_grant_id,
            json.dumps(
                record.consumed_approval_grant_ids,
                separators=(",", ":"),
            ),
            record.platform_reference,
            record.published_url,
            record.last_error_code,
            record.last_error_message,
            revision,
        )

    @staticmethod
    def _save_events(connection: sqlite3.Connection, record: PublishRecord) -> None:
        connection.executemany(
            """
            INSERT OR IGNORE INTO social_publish_events (
                request_id, sequence, state, occurred_at, actor, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.request.request_id,
                    event.sequence,
                    event.state.value,
                    event.occurred_at,
                    event.actor,
                    json.dumps(
                        event.details,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                for event in record.events
            ],
        )

    @staticmethod
    def _deserialize_record(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> PublishRecord:
        request_object: object = json.loads(str(row["request_json"]))
        if not isinstance(request_object, dict):
            raise ValueError("Stored publish request is not an object")
        request_payload = cast(dict[str, Any], request_object)
        metadata = request_payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("Stored publish request metadata is not an object")
        request = SocialPublishRequest(
            request_id=str(request_payload["request_id"]),
            platform=str(request_payload["platform"]),
            media_type=str(request_payload["media_type"]),
            asset_ref=str(request_payload["asset_ref"]),
            title=str(request_payload["title"]),
            description=str(request_payload["description"]),
            idempotency_key=str(request_payload["idempotency_key"]),
            metadata=cast(dict[str, Any], metadata),
            schema_version=int(request_payload["schema_version"]),
        )
        event_rows = connection.execute(
            """
            SELECT sequence, state, occurred_at, actor, details_json
            FROM social_publish_events
            WHERE request_id = ?
            ORDER BY sequence
            """,
            (request.request_id,),
        ).fetchall()
        events: list[PublishEvent] = []
        for event_row in event_rows:
            details_object: object = json.loads(str(event_row["details_json"]))
            if not isinstance(details_object, dict):
                raise ValueError("Stored publish event details are not an object")
            events.append(
                PublishEvent(
                    sequence=int(event_row["sequence"]),
                    state=PublishState(str(event_row["state"])),
                    occurred_at=str(event_row["occurred_at"]),
                    actor=str(event_row["actor"]),
                    details=cast(dict[str, Any], details_object),
                )
            )
        consumed_object: object = json.loads(
            str(row["consumed_approval_grant_ids_json"])
        )
        if not isinstance(consumed_object, list):
            raise ValueError("Stored consumed approval grants are not a list")
        consumed_objects = cast(list[object], consumed_object)
        if not all(isinstance(item, str) for item in consumed_objects):
            raise ValueError("Stored consumed approval grants are not a list")
        consumed_grant_ids = cast(list[str], consumed_objects)
        return PublishRecord(
            request=request,
            request_digest=str(row["request_digest"]),
            state=PublishState(str(row["state"])),
            events=events,
            approval_grant_id=str(row["approval_grant_id"]),
            consumed_approval_grant_ids=consumed_grant_ids,
            platform_reference=str(row["platform_reference"]),
            published_url=str(row["published_url"]),
            last_error_code=str(row["last_error_code"]),
            last_error_message=str(row["last_error_message"]),
            revision=int(row["revision"]),
        )
