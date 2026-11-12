from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Protocol, TypeAlias
from zoneinfo import ZoneInfo

_BEIJING = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class WakeTimeWindow:
    """An explicit, half-open time interval supplied by a trusted caller."""

    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class ConfiguredSlot:
    """A canonical slot and its configured binding interval for one business day."""

    slot_id: str
    binding_window: WakeTimeWindow


def _canonical_identity_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _canonical_source_instant(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("occurred_at must be a timezone-aware original instant")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class SourceOccurrenceIdentity:
    """Host-authenticated unique source occurrence, not a time-window identity.

    The trusted entrypoint must authenticate the stable source namespace/ID and
    exact original trigger instant and guarantee this combination is unique.
    Construction checks structure only, not authenticity or uniqueness.
    Never derive this from receipt/processing time, window bounds, or lastRunAt.
    """

    source_namespace: str
    source_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _canonical_identity_text(self.source_namespace, "source_namespace")
        _canonical_identity_text(self.source_id, "source_id")
        object.__setattr__(
            self, "occurred_at", _canonical_source_instant(self.occurred_at)
        )


def _validate_optional_source_occurrence(value: object) -> None:
    if value is not None and not isinstance(value, SourceOccurrenceIdentity):
        raise ValueError("source_occurrence must be SourceOccurrenceIdentity or None")


@dataclass(frozen=True, slots=True)
class HostValidatedWakeEvidence:
    """Optional source facts validated by the consumer's actual entrypoint.

    `host_validation_reference` is for traceability, not a credential or proof.
    Supply identities only after a trusted adapter has validated their origin.
    This provider-neutral package cannot authenticate the claim or recognize a
    particular desktop wake mechanism.

    Message/occurrence IDs must identify the original wake or be host-verified
    aliases of it. A receiving message ID alone does not establish that link.
    The bindable window must describe the original source event, not receipt
    or processing time; delayed forwarding must not change its business date.
    `source_occurrence` is an independent optional identity, only for hosts
    actually guaranteeing its authenticated source/time combination is unique.
    """

    source_kind: str = ""
    host_validation_reference: str = ""
    bindable_window: WakeTimeWindow | None = None
    message_id: str = ""
    occurrence_id: str = ""
    source_occurrence: SourceOccurrenceIdentity | None = None

    def __post_init__(self) -> None:
        _validate_optional_source_occurrence(self.source_occurrence)


class WakeIdentityKind(str, Enum):
    MESSAGE = "message"
    OCCURRENCE = "occurrence"


@dataclass(frozen=True, slots=True)
class WakeIdentity:
    kind: WakeIdentityKind
    value: str


WakeBindingIdentity: TypeAlias = WakeIdentity | SourceOccurrenceIdentity


def _validate_binding_identity(value: object) -> WakeBindingIdentity:
    if isinstance(value, WakeIdentity):
        if type(value.kind) is not WakeIdentityKind:
            raise ValueError("wake identity kind must be a supported WakeIdentityKind")
        _canonical_identity_text(value.value, "wake identity")
        return value
    if isinstance(value, SourceOccurrenceIdentity):
        return value
    raise ValueError("Unsupported persisted wake identity type")


@dataclass(frozen=True, slots=True)
class WakeSlotBinding:
    """A stored binding or proposal containing only the current request's IDs."""

    business_date: date
    slot_id: str
    identities: tuple[WakeBindingIdentity, ...]


@dataclass(frozen=True, slots=True)
class SlotBindingIndex:
    """Persisted identity-to-slot bindings supplied by the consumer."""

    bindings: tuple[WakeSlotBinding, ...] = ()

    def __post_init__(self) -> None:
        seen_slots: set[tuple[date, str]] = set()
        seen_identities: set[WakeBindingIdentity] = set()
        for binding in self.bindings:
            if type(binding.business_date) is not date:
                raise ValueError("A persisted slot binding requires a business date")
            if (
                not binding.slot_id.strip()
                or binding.slot_id != binding.slot_id.strip()
            ):
                raise ValueError(
                    "A persisted slot binding requires a canonical slot ID"
                )
            address = (binding.business_date, binding.slot_id)
            if address in seen_slots:
                raise ValueError("A persisted slot may have only one binding")
            seen_slots.add(address)
            for raw_identity in binding.identities:
                identity = _validate_binding_identity(raw_identity)
                if identity in seen_identities:
                    raise ValueError("A wake identity may have only one slot binding")
                seen_identities.add(identity)


class SlotBindingStatus(str, Enum):
    READY = "ready"
    IDEMPOTENT = "idempotent"
    BLOCKED = "blocked"


class SlotBindingScope(str, Enum):
    SLOT_ONLY = "slot_only"
    WAKE_IDENTITY = "wake_identity"


@dataclass(frozen=True, slots=True)
class SlotBindingDecision:
    status: SlotBindingStatus
    reason: str
    binding: WakeSlotBinding | None = None
    scope: SlotBindingScope | None = None


class SlotPersistenceStatus(str, Enum):
    CLAIMED = "claimed"
    IDEMPOTENT = "idempotent"
    IDENTITY_BOUND_ELSEWHERE = "identity_bound_elsewhere"
    SLOT_OCCUPIED = "slot_occupied"


@dataclass(frozen=True, slots=True)
class SlotPersistenceResult:
    """Only CLAIMED represents a newly acquired slot, not IDEMPOTENT review."""

    status: SlotPersistenceStatus
    reason: str


class SlotBindingPersistencePort(Protocol):
    """Consumer-owned persistence for slot occupancy and wake identities."""

    def read_binding_index(
        self,
        *,
        identities: tuple[WakeBindingIdentity, ...],
        business_date: date,
    ) -> SlotBindingIndex:
        """Return identity history for these IDs and occupancy for this date.

        This read is a snapshot only; it does not reserve anything.
        """
        ...

    def bind_and_claim(self, binding: WakeSlotBinding) -> SlotPersistenceResult:
        """Atomically recheck and persist identity bindings plus slot occupancy.

        Implementations must recheck identity and occupancy conflicts and write
        both in the same transaction or equivalent atomic critical section.
        An empty identity tuple reserves only (business_date, slot_id), never
        proves which wake occupied it, and must not erase existing aliases.
        For an occupied slot with no incoming identities, return SLOT_OCCUPIED,
        not IDEMPOTENT: the latter requires a shared trusted identity.
        Incoming bindings contain only identities supplied with this request,
        never aliases borrowed from the caller's stored snapshot.
        SourceOccurrenceIdentity uses the separate namespace/source ID fields
        and canonical UTC instant as its key, not concatenated text, local wall
        time, or a message/occurrence ID. Recheck all identity types equally.
        For same-slot retries sharing an existing identity, merge every incoming
        alias with all currently stored aliases, never replace or remove them.
        Recheck conflicts for the entire merged set against current state,
        including aliases added since the caller's snapshot was read.
        Consumers should submit every non-blocked proposal, including
        IDEMPOTENT reviews, so the adapter can atomically recheck current state.
        This contract does not provide an implementation or cross-process lock.
        """
        ...


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _window_is_on_business_date(
    window: WakeTimeWindow | None, business_date: date
) -> bool:
    if (
        window is None
        or not _is_aware(window.starts_at)
        or not _is_aware(window.ends_at)
    ):
        return False
    starts_at = window.starts_at.astimezone(timezone.utc)
    ends_at = window.ends_at.astimezone(timezone.utc)
    return (
        starts_at < ends_at
        and starts_at.astimezone(_BEIJING).date() == business_date
        and (ends_at - timedelta(microseconds=1)).astimezone(_BEIJING).date()
        == business_date
    )


def _blocked(reason: str) -> SlotBindingDecision:
    return SlotBindingDecision(
        status=SlotBindingStatus.BLOCKED,
        reason=reason,
    )


def evaluate_wakeup_slot_binding(
    *,
    configured_slots: Sequence[ConfiguredSlot] | None,
    business_date: date | None,
    requested_slot_id: str,
    evidence: HostValidatedWakeEvidence | None,
    existing: SlotBindingIndex | None,
) -> SlotBindingDecision:
    """Purely check a caller-supplied wake against configured slot intervals.

    The caller must pass canonical slots from already-authorized configuration,
    an independently established Beijing business date, and a persisted binding
    snapshot. Optional trusted identities support cross-slot wake deduplication;
    without them only the supplied date/slot can be deduplicated. This function
    cannot authenticate inputs or infer the original date from delivery time.
    """
    if business_date is None:
        return _blocked("business_date_unknown")
    if type(business_date) is not date:
        return _blocked("business_date_invalid")
    if existing is None:
        return _blocked("binding_index_missing")
    identities: list[WakeBindingIdentity] = []
    if evidence is not None:
        if evidence.message_id != evidence.message_id.strip():
            return _blocked("wake_message_id_not_canonical")
        if evidence.occurrence_id != evidence.occurrence_id.strip():
            return _blocked("wake_occurrence_id_not_canonical")
        if evidence.message_id.strip():
            identities.append(
                WakeIdentity(WakeIdentityKind.MESSAGE, evidence.message_id)
            )
        if evidence.occurrence_id.strip():
            identities.append(
                WakeIdentity(WakeIdentityKind.OCCURRENCE, evidence.occurrence_id)
            )
        if evidence.source_occurrence is not None:
            identities.append(evidence.source_occurrence)
        if evidence.bindable_window is not None and not _window_is_on_business_date(
            evidence.bindable_window, business_date
        ):
            return _blocked("source_window_invalid_for_business_date")

    if not configured_slots:
        return _blocked("configured_slots_required")
    slots_by_id: dict[str, ConfiguredSlot] = {}
    for configured_slot in configured_slots:
        if not configured_slot.slot_id.strip():
            return _blocked("configured_slot_id_missing")
        if configured_slot.slot_id != configured_slot.slot_id.strip():
            return _blocked("configured_slot_id_not_canonical")
        if configured_slot.slot_id in slots_by_id:
            return _blocked("configured_slot_id_duplicated")
        if not _window_is_on_business_date(
            configured_slot.binding_window, business_date
        ):
            return _blocked("configured_slot_window_invalid_for_business_date")
        slots_by_id[configured_slot.slot_id] = configured_slot

    if not requested_slot_id.strip() or requested_slot_id != requested_slot_id.strip():
        return _blocked("requested_slot_id_invalid")
    requested = slots_by_id.get(requested_slot_id)
    if requested is None:
        return _blocked("requested_slot_not_configured")
    source_window = evidence.bindable_window if evidence is not None else None
    source_occurrence = evidence.source_occurrence if evidence is not None else None
    if source_occurrence is not None:
        instant = source_occurrence.occurred_at
        if instant.astimezone(_BEIJING).date() != business_date:
            return _blocked("source_occurrence_business_date_mismatch")
        if not (
            requested.binding_window.starts_at.astimezone(timezone.utc)
            <= instant
            < requested.binding_window.ends_at.astimezone(timezone.utc)
        ):
            return _blocked("source_occurrence_outside_requested_slot")
        if source_window is not None and not (
            source_window.starts_at.astimezone(timezone.utc)
            <= instant
            < source_window.ends_at.astimezone(timezone.utc)
        ):
            return _blocked("source_occurrence_outside_source_window")
    if source_window is not None:
        matching_slots = tuple(
            configured_slot
            for configured_slot in slots_by_id.values()
            if configured_slot.binding_window.starts_at.astimezone(timezone.utc)
            <= source_window.starts_at.astimezone(timezone.utc)
            and source_window.ends_at.astimezone(timezone.utc)
            <= configured_slot.binding_window.ends_at.astimezone(timezone.utc)
        )
        if len(matching_slots) != 1:
            return _blocked(
                "source_window_not_bindable"
                if not matching_slots
                else "source_window_matches_multiple_slots"
            )
        if matching_slots[0].slot_id != requested_slot_id:
            return _blocked("source_window_does_not_match_requested_slot")

    proposed = WakeSlotBinding(
        business_date=business_date,
        slot_id=requested_slot_id,
        identities=tuple(identities),
    )
    target_address = (business_date, requested_slot_id)
    target_binding = next(
        (
            binding
            for binding in existing.bindings
            if (binding.business_date, binding.slot_id) == target_address
        ),
        None,
    )
    proposed_identities = set(proposed.identities)
    for binding in existing.bindings:
        shared_identities = proposed_identities.intersection(binding.identities)
        if not shared_identities:
            continue
        if (binding.business_date, binding.slot_id) != target_address:
            return _blocked("wake_identity_already_bound_to_different_slot")

    if target_binding is not None:
        if not identities:
            return SlotBindingDecision(
                status=SlotBindingStatus.IDEMPOTENT,
                reason="slot_already_occupied_wake_identity_unknown",
                binding=proposed,
                scope=SlotBindingScope.SLOT_ONLY,
            )
        if proposed_identities.intersection(target_binding.identities):
            return SlotBindingDecision(
                status=SlotBindingStatus.IDEMPOTENT,
                reason="same_wake_same_slot",
                binding=proposed,
                scope=SlotBindingScope.WAKE_IDENTITY,
            )
        return _blocked("configured_slot_already_occupied")

    return SlotBindingDecision(
        status=SlotBindingStatus.READY,
        reason="slot_binding_ready",
        binding=proposed,
        scope=(
            SlotBindingScope.WAKE_IDENTITY if identities else SlotBindingScope.SLOT_ONLY
        ),
    )
