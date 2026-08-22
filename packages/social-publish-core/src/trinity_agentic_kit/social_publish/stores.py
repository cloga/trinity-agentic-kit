from __future__ import annotations

import copy

from .contracts import (
    ConcurrentPublishUpdate,
    DuplicatePublishRequest,
    PublishEvent,
    PublishRecord,
)


class InMemoryPublishStateStore:
    """Process-local state store with optimistic concurrency semantics."""

    def __init__(self) -> None:
        self._records: dict[str, PublishRecord] = {}
        self._idempotency_index: dict[str, str] = {}

    def get(self, request_id: str) -> PublishRecord | None:
        record = self._records.get(request_id)
        return copy.deepcopy(record) if record is not None else None

    def get_by_idempotency_key(self, idempotency_key: str) -> PublishRecord | None:
        request_id = self._idempotency_index.get(idempotency_key)
        return self.get(request_id) if request_id is not None else None

    def save(self, record: PublishRecord) -> None:
        existing = self._records.get(record.request.request_id)
        indexed_request_id = self._idempotency_index.get(record.request.idempotency_key)
        if (
            indexed_request_id is not None
            and indexed_request_id != record.request.request_id
        ):
            raise DuplicatePublishRequest(
                f"Duplicate publish idempotency key: {record.request.idempotency_key}"
            )
        if existing is None:
            if record.revision != 0:
                raise ConcurrentPublishUpdate(
                    "New publish record must start at revision 0"
                )
        elif record.revision != existing.revision:
            raise ConcurrentPublishUpdate(
                f"Stale publish revision {record.revision}; "
                f"current revision is {existing.revision}"
            )
        record.revision += 1
        self._records[record.request.request_id] = copy.deepcopy(record)
        self._idempotency_index[record.request.idempotency_key] = (
            record.request.request_id
        )


class InMemoryAuditSink:
    """Collect audit events for tests and process-local integrations."""

    def __init__(self) -> None:
        self.events: list[tuple[str, PublishEvent]] = []

    def append(self, request_id: str, event: PublishEvent) -> None:
        self.events.append((request_id, event))
