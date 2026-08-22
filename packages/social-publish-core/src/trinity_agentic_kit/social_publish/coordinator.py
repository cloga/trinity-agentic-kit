from __future__ import annotations

from typing import Any

from .approval import HmacApprovalAuthority, iso_utc, utc_now
from .contracts import (
    ALLOWED_TRANSITIONS,
    ApprovalGrantError,
    AuditSink,
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


class SocialPublishCoordinator:
    """Coordinate a publication while keeping platform side effects isolated."""

    def __init__(
        self,
        *,
        adapters: dict[str, PublisherAdapter],
        store: PublishStateStore,
        approval_authority: HmacApprovalAuthority,
        audit_sink: AuditSink,
    ) -> None:
        self._adapters = dict(adapters)
        self._store = store
        self._approval_authority = approval_authority
        self._audit_sink = audit_sink

    async def prepare(
        self, request: SocialPublishRequest, *, actor: str = "agent"
    ) -> PublishRecord:
        existing = self._store.get_by_idempotency_key(request.idempotency_key)
        digest = request_digest(request)
        if existing is not None:
            if existing.request_digest != digest:
                raise DuplicatePublishRequest(
                    f"Idempotency key {request.idempotency_key!r} "
                    "is bound to different content"
                )
            return existing

        adapter = self._adapter(request.platform)
        initial = PublishEvent(
            sequence=1,
            state=PublishState.PREPARING,
            occurred_at=iso_utc(utc_now()),
            actor=actor,
        )
        record = PublishRecord(
            request=request,
            request_digest=digest,
            state=PublishState.PREPARING,
            events=[initial],
        )
        self._store.save(record)
        self._audit_sink.append(request.request_id, initial)
        await self._run_prepare(record, adapter=adapter, actor=actor)
        self._transition(record, PublishState.AWAITING_APPROVAL, actor=actor)
        return record

    def approve(
        self,
        request_id: str,
        token: str,
        *,
        actor: str = "approver",
    ) -> PublishRecord:
        record = self._record(request_id)
        if record.state is not PublishState.AWAITING_APPROVAL:
            raise InvalidPublishTransition(
                f"Publish request is not awaiting approval: {record.state.value}"
            )
        grant = self._approval_authority.verify(token, record.request)
        if grant.grant_id in record.consumed_approval_grant_ids:
            raise ApprovalGrantError("Approval grant has already been consumed")
        record.approval_grant_id = grant.grant_id
        self._transition(
            record,
            PublishState.APPROVED,
            actor=actor,
            details={
                "grant_id": grant.grant_id,
                "expires_at": grant.expires_at,
            },
        )
        return record

    async def execute(
        self, request_id: str, token: str, *, actor: str = "agent"
    ) -> PublishRecord:
        record = self._record(request_id)
        grant = self._approval_authority.verify(token, record.request)
        if record.approval_grant_id and record.approval_grant_id != grant.grant_id:
            raise ApprovalGrantError("Approval grant does not match the approved grant")
        if record.state is PublishState.AWAITING_APPROVAL:
            self.approve(
                request_id,
                token,
                actor=f"grant:{grant.issuer}",
            )
        record = self._record(request_id)
        if record.state is not PublishState.APPROVED:
            raise InvalidPublishTransition(
                f"Publish request is not approved: {record.state.value}"
            )
        if grant.grant_id in record.consumed_approval_grant_ids:
            raise ApprovalGrantError("Approval grant has already been consumed")

        # Consume before the side effect so an uncertain result cannot be replayed.
        record.consumed_approval_grant_ids.append(grant.grant_id)
        self._store.save(record)
        self._transition(record, PublishState.EXECUTING, actor=actor)
        try:
            result = await self._adapter(record.request.platform).execute(
                record.request
            )
        except (OSError, ValueError, PublisherAdapterError) as exc:
            record.last_error_code = "adapter_exception"
            record.last_error_message = str(exc)
            self._transition(
                record,
                PublishState.VERIFICATION_PENDING,
                actor=actor,
                details=self._error_details(record),
            )
            raise
        return self._apply_result(record, result, actor=actor)

    async def verify(self, request_id: str, *, actor: str = "agent") -> PublishRecord:
        record = self._record(request_id)
        self._transition(record, PublishState.VERIFYING, actor=actor)
        try:
            result = await self._adapter(record.request.platform).verify(
                record.request,
                platform_reference=record.platform_reference,
            )
        except (OSError, ValueError, PublisherAdapterError) as exc:
            record.last_error_code = "verification_exception"
            record.last_error_message = str(exc)
            self._transition(
                record,
                PublishState.VERIFICATION_PENDING,
                actor=actor,
                details=self._error_details(record),
            )
            raise
        return self._apply_result(record, result, actor=actor)

    def cancel(self, request_id: str, *, actor: str = "operator") -> PublishRecord:
        record = self._record(request_id)
        self._transition(record, PublishState.CANCELLED, actor=actor)
        return record

    def retry(self, request_id: str, *, actor: str = "operator") -> PublishRecord:
        record = self._record(request_id)
        if record.last_error_code == "prepare_failed":
            raise InvalidPublishTransition(
                "Preparation failures must use reprepare before approval"
            )
        record.approval_grant_id = ""
        self._transition(record, PublishState.AWAITING_APPROVAL, actor=actor)
        return record

    async def reprepare(
        self, request_id: str, *, actor: str = "operator"
    ) -> PublishRecord:
        record = self._record(request_id)
        if (
            record.state is not PublishState.FAILED
            or record.last_error_code != "prepare_failed"
        ):
            raise InvalidPublishTransition(
                f"Publish request {request_id} does not require re-preparation"
            )
        self._transition(record, PublishState.PREPARING, actor=actor)
        await self._run_prepare(
            record,
            adapter=self._adapter(record.request.platform),
            actor=actor,
        )
        record.last_error_code = ""
        record.last_error_message = ""
        self._transition(record, PublishState.AWAITING_APPROVAL, actor=actor)
        return record

    def _adapter(self, platform: str) -> PublisherAdapter:
        adapter = self._adapters.get(platform)
        if adapter is None:
            raise SocialPublishError(
                f"No publisher adapter registered for platform: {platform}"
            )
        return adapter

    def _record(self, request_id: str) -> PublishRecord:
        record = self._store.get(request_id)
        if record is None:
            raise SocialPublishError(f"Publish request not found: {request_id}")
        return record

    def _transition(
        self,
        record: PublishRecord,
        target: PublishState,
        *,
        actor: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if target not in ALLOWED_TRANSITIONS[record.state]:
            raise InvalidPublishTransition(
                f"Illegal publish transition: {record.state.value} -> {target.value}"
            )
        event = PublishEvent(
            sequence=len(record.events) + 1,
            state=target,
            occurred_at=iso_utc(utc_now()),
            actor=str(actor or "system"),
            details=dict(details or {}),
        )
        record.state = target
        record.events.append(event)
        self._store.save(record)
        self._audit_sink.append(record.request.request_id, event)

    def _apply_result(
        self,
        record: PublishRecord,
        result: PlatformPublishResult,
        *,
        actor: str,
    ) -> PublishRecord:
        record.platform_reference = (
            result.platform_reference or record.platform_reference
        )
        record.published_url = result.published_url
        record.last_error_code = result.error_code
        record.last_error_message = result.error_message
        details: dict[str, Any] = {
            "platform_reference": record.platform_reference,
            "published_url": result.published_url,
            "verification_pending": result.verification_pending,
            "evidence": list(result.evidence),
            "error_code": result.error_code,
            "error_message": result.error_message,
            "retryable": result.retryable,
            "requires_manual_intervention": (result.requires_manual_intervention),
        }
        if result.published_url:
            target = PublishState.PUBLISHED
        elif record.state is PublishState.VERIFYING or result.verification_pending:
            target = PublishState.VERIFICATION_PENDING
        elif result.submitted:
            target = PublishState.SUBMITTED
        else:
            target = PublishState.FAILED
        self._transition(record, target, actor=actor, details=details)
        return record

    async def _run_prepare(
        self,
        record: PublishRecord,
        *,
        adapter: PublisherAdapter,
        actor: str,
    ) -> None:
        try:
            await adapter.prepare(record.request)
        except (OSError, ValueError, PublisherAdapterError) as exc:
            record.last_error_code = "prepare_failed"
            record.last_error_message = str(exc)
            self._transition(
                record,
                PublishState.FAILED,
                actor=actor,
                details=self._error_details(record),
            )
            raise

    @staticmethod
    def _error_details(record: PublishRecord) -> dict[str, Any]:
        return {
            "error_code": record.last_error_code,
            "error_message": record.last_error_message,
        }
