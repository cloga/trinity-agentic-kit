from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from trinity_agentic_kit.value_explainer import (
    ConfiguredSlot,
    HostValidatedWakeEvidence,
    SlotBindingIndex,
    SlotBindingPersistencePort,
    SlotBindingScope,
    SlotBindingStatus,
    SlotPersistenceResult,
    SlotPersistenceStatus,
    SourceOccurrenceIdentity,
    WakeBindingIdentity,
    WakeIdentity,
    WakeIdentityKind,
    WakeSlotBinding,
    WakeTimeWindow,
    evaluate_wakeup_slot_binding,
)

_BEIJING = ZoneInfo("Asia/Shanghai")
_BUSINESS_DATE = date(2026, 11, 12)


@dataclass
class _MemorySlotAdapter:
    """Synthetic sequential contract example, not durable or concurrency evidence."""

    bindings: tuple[WakeSlotBinding, ...] = ()
    incoming: WakeSlotBinding | None = None

    def read_binding_index(
        self, *, identities: tuple[WakeBindingIdentity, ...], business_date: date
    ) -> SlotBindingIndex:
        return SlotBindingIndex(self.bindings)

    def bind_and_claim(self, binding: WakeSlotBinding) -> SlotPersistenceResult:
        self.incoming = binding
        incoming_identities = set(binding.identities)
        target = (binding.business_date, binding.slot_id)
        current: WakeSlotBinding | None = None
        for stored in self.bindings:
            address = (stored.business_date, stored.slot_id)
            if (
                incoming_identities.intersection(stored.identities)
                and address != target
            ):
                return SlotPersistenceResult(
                    SlotPersistenceStatus.IDENTITY_BOUND_ELSEWHERE, "identity_conflict"
                )
            if address == target:
                current = stored
        if current is None:
            self.bindings = (*self.bindings, binding)
            return SlotPersistenceResult(SlotPersistenceStatus.CLAIMED, "new_slot")
        if not incoming_identities.intersection(current.identities):
            return SlotPersistenceResult(
                SlotPersistenceStatus.SLOT_OCCUPIED, "occupied_without_shared_identity"
            )
        merged = WakeSlotBinding(
            binding.business_date,
            binding.slot_id,
            tuple(dict.fromkeys((*current.identities, *binding.identities))),
        )
        self.bindings = tuple(
            merged if stored == current else stored for stored in self.bindings
        )
        return SlotPersistenceResult(SlotPersistenceStatus.IDEMPOTENT, "same_wake")


def _window(start_hour: int, end_hour: int) -> WakeTimeWindow:
    return WakeTimeWindow(
        starts_at=datetime(
            _BUSINESS_DATE.year,
            _BUSINESS_DATE.month,
            _BUSINESS_DATE.day,
            start_hour,
            tzinfo=_BEIJING,
        ),
        ends_at=datetime(
            _BUSINESS_DATE.year,
            _BUSINESS_DATE.month,
            _BUSINESS_DATE.day,
            end_hour,
            tzinfo=_BEIJING,
        ),
    )


def _source_window(start_hour: int, end_hour: int) -> WakeTimeWindow:
    return WakeTimeWindow(
        starts_at=datetime(
            _BUSINESS_DATE.year,
            _BUSINESS_DATE.month,
            _BUSINESS_DATE.day,
            start_hour,
            15,
            tzinfo=_BEIJING,
        ),
        ends_at=datetime(
            _BUSINESS_DATE.year,
            _BUSINESS_DATE.month,
            _BUSINESS_DATE.day,
            end_hour,
            45,
            tzinfo=_BEIJING,
        ),
    )


def _configured_slots() -> tuple[ConfiguredSlot, ...]:
    return (
        ConfiguredSlot("configured-a", _window(9, 10)),
        ConfiguredSlot("configured-b", _window(10, 11)),
    )


def _evidence(
    *,
    message_id: str = "fixture-message",
    occurrence_id: str = "fixture-occurrence",
    window: WakeTimeWindow | None = None,
    validation_reference: str = "fixture-host-validation",
) -> HostValidatedWakeEvidence:
    return HostValidatedWakeEvidence(
        source_kind="synthetic-host-event",
        host_validation_reference=validation_reference,
        bindable_window=window or _source_window(9, 9),
        message_id=message_id,
        occurrence_id=occurrence_id,
    )


def test_missing_wake_metadata_allows_only_explicit_date_slot_guarantee() -> None:
    no_metadata = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=None,
        existing=SlotBindingIndex(),
    )
    empty_metadata = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(),
        existing=SlotBindingIndex(),
    )

    assert no_metadata.status is SlotBindingStatus.READY
    assert no_metadata.scope is SlotBindingScope.SLOT_ONLY
    assert no_metadata.binding == WakeSlotBinding(
        _BUSINESS_DATE, "configured-a", identities=()
    )
    assert empty_metadata == no_metadata


def test_unknown_original_business_date_blocks_even_with_wake_metadata() -> None:
    for evidence in (None, _evidence()):
        unknown_date = evaluate_wakeup_slot_binding(
            configured_slots=_configured_slots(),
            business_date=None,
            requested_slot_id="configured-a",
            evidence=evidence,
            existing=SlotBindingIndex(),
        )
        assert unknown_date.status is SlotBindingStatus.BLOCKED
        assert unknown_date.reason == "business_date_unknown"
        assert unknown_date.binding is None


def test_no_id_retries_preserve_slot_occupancy_and_allow_another_configured_slot() -> (
    None
):
    original = WakeSlotBinding(_BUSINESS_DATE, "configured-a", identities=())
    existing = SlotBindingIndex(bindings=(original,))
    repeated = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=None,
        existing=existing,
    )
    other_slot = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=None,
        existing=existing,
    )
    assert repeated.status is SlotBindingStatus.IDEMPOTENT
    assert repeated.scope is SlotBindingScope.SLOT_ONLY
    assert repeated.reason == "slot_already_occupied_wake_identity_unknown"
    assert repeated.binding == original
    assert other_slot.status is SlotBindingStatus.READY
    assert other_slot.scope is SlotBindingScope.SLOT_ONLY


def test_trusted_identity_does_not_require_fabricated_source_fields() -> None:
    result = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(message_id="host-established-message"),
        existing=SlotBindingIndex(),
    )

    assert result.status is SlotBindingStatus.READY
    assert result.scope is SlotBindingScope.WAKE_IDENTITY
    assert result.binding is not None
    assert result.binding.identities == (
        WakeIdentity(WakeIdentityKind.MESSAGE, "host-established-message"),
    )


def test_identity_free_proposal_does_not_inherit_stored_wake_identity() -> None:
    original = WakeSlotBinding(
        _BUSINESS_DATE,
        "configured-a",
        (WakeIdentity(WakeIdentityKind.MESSAGE, "already-bound-message"),),
    )
    adapter = _MemorySlotAdapter(bindings=(original,))
    port: SlotBindingPersistencePort = adapter
    result = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=None,
        existing=SlotBindingIndex(bindings=(original,)),
    )

    assert result.status is SlotBindingStatus.IDEMPOTENT
    assert result.scope is SlotBindingScope.SLOT_ONLY
    assert result.binding is not None
    assert result.binding.identities == ()
    persisted = port.bind_and_claim(result.binding)
    assert adapter.incoming == WakeSlotBinding(
        _BUSINESS_DATE, "configured-a", identities=()
    )
    assert persisted.status is SlotPersistenceStatus.SLOT_OCCUPIED
    assert adapter.bindings == (original,)


@pytest.mark.parametrize(
    ("message_id", "occurrence_id", "reason"),
    (
        (" \t ", "", "wake_message_id_not_canonical"),
        ("", " \t ", "wake_occurrence_id_not_canonical"),
    ),
)
def test_whitespace_wake_ids_do_not_silently_downgrade_scope(
    message_id: str, occurrence_id: str, reason: str
) -> None:
    result = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(
            message_id=message_id, occurrence_id=occurrence_id
        ),
        existing=SlotBindingIndex(),
    )
    assert result.status is SlotBindingStatus.BLOCKED
    assert result.reason == reason
    assert result.binding is None
    assert result.scope is None


def test_source_window_must_bind_to_exactly_the_requested_configured_slot() -> None:
    decision = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=SlotBindingIndex(),
    )
    wrong_slot = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=SlotBindingIndex(),
    )

    assert decision.status is SlotBindingStatus.READY
    assert decision.binding == WakeSlotBinding(
        business_date=_BUSINESS_DATE,
        slot_id="configured-a",
        identities=(
            WakeIdentity(WakeIdentityKind.MESSAGE, "fixture-message"),
            WakeIdentity(WakeIdentityKind.OCCURRENCE, "fixture-occurrence"),
        ),
    )
    assert wrong_slot.status is SlotBindingStatus.BLOCKED
    assert wrong_slot.reason == "source_window_does_not_match_requested_slot"


def test_same_wake_is_idempotent_in_its_slot_and_blocked_from_another() -> None:
    original = WakeSlotBinding(
        business_date=_BUSINESS_DATE,
        slot_id="configured-a",
        identities=(
            WakeIdentity(WakeIdentityKind.MESSAGE, "fixture-message"),
            WakeIdentity(WakeIdentityKind.OCCURRENCE, "fixture-occurrence"),
        ),
    )
    existing = SlotBindingIndex(bindings=(original,))

    repeated = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=existing,
    )
    rebound = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=_evidence(window=_source_window(10, 10)),
        existing=existing,
    )

    assert repeated.status is SlotBindingStatus.IDEMPOTENT
    assert repeated.reason == "same_wake_same_slot"
    assert rebound.status is SlotBindingStatus.BLOCKED
    assert rebound.reason == "wake_identity_already_bound_to_different_slot"


def test_partial_identity_retry_preserves_all_existing_aliases() -> None:
    original = WakeSlotBinding(
        business_date=_BUSINESS_DATE,
        slot_id="configured-a",
        identities=(
            WakeIdentity(WakeIdentityKind.MESSAGE, "original-message"),
            WakeIdentity(WakeIdentityKind.OCCURRENCE, "shared-occurrence"),
        ),
    )
    repeated = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(message_id="", occurrence_id="shared-occurrence"),
        existing=SlotBindingIndex(bindings=(original,)),
    )

    assert repeated.status is SlotBindingStatus.IDEMPOTENT
    assert repeated.binding is not None
    assert repeated.binding.identities == (
        WakeIdentity(WakeIdentityKind.OCCURRENCE, "shared-occurrence"),
    )
    adapter = _MemorySlotAdapter(bindings=(original,))
    persisted = adapter.bind_and_claim(repeated.binding)
    assert persisted.status is SlotPersistenceStatus.IDEMPOTENT
    assert adapter.bindings == (original,)
    rebound = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=_evidence(
            message_id="original-message",
            occurrence_id="",
            window=_source_window(10, 10),
        ),
        existing=SlotBindingIndex(bindings=adapter.bindings),
    )
    assert rebound.reason == "wake_identity_already_bound_to_different_slot"


def test_idempotent_review_adds_new_alias_without_losing_old_aliases() -> None:
    original = WakeSlotBinding(
        business_date=_BUSINESS_DATE,
        slot_id="configured-a",
        identities=(
            WakeIdentity(WakeIdentityKind.MESSAGE, "original-message"),
            WakeIdentity(WakeIdentityKind.OCCURRENCE, "shared-occurrence"),
        ),
    )
    repeated = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(message_id="new-message", occurrence_id="shared-occurrence"),
        existing=SlotBindingIndex(bindings=(original,)),
    )

    assert repeated.status is SlotBindingStatus.IDEMPOTENT
    assert repeated.binding is not None
    assert repeated.binding.identities == (
        WakeIdentity(WakeIdentityKind.MESSAGE, "new-message"),
        WakeIdentity(WakeIdentityKind.OCCURRENCE, "shared-occurrence"),
    )
    adapter = _MemorySlotAdapter(bindings=(original,))
    persisted = adapter.bind_and_claim(repeated.binding)
    assert persisted.status is SlotPersistenceStatus.IDEMPOTENT
    assert adapter.bindings[0].identities == (
        *original.identities,
        WakeIdentity(WakeIdentityKind.MESSAGE, "new-message"),
    )
    for message_id in ("original-message", "new-message"):
        rebound = evaluate_wakeup_slot_binding(
            configured_slots=_configured_slots(),
            business_date=_BUSINESS_DATE,
            requested_slot_id="configured-b",
            evidence=_evidence(
                message_id=message_id,
                occurrence_id="",
                window=_source_window(10, 10),
            ),
            existing=SlotBindingIndex(bindings=adapter.bindings),
        )
        assert rebound.reason == "wake_identity_already_bound_to_different_slot"


def test_distinct_configured_slots_can_each_bind_distinct_wakes() -> None:
    first = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(
            message_id="first-message",
            occurrence_id="first-occurrence",
            window=_source_window(9, 9),
        ),
        existing=SlotBindingIndex(),
    )
    assert first.binding is not None
    second = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=_evidence(
            message_id="second-message",
            occurrence_id="second-occurrence",
            window=_source_window(10, 10),
        ),
        existing=SlotBindingIndex(bindings=(first.binding,)),
    )

    assert first.status is SlotBindingStatus.READY
    assert second.status is SlotBindingStatus.READY
    assert second.binding is not None
    assert second.binding.slot_id == "configured-b"


def test_ambiguous_or_wrong_date_windows_are_blocked() -> None:
    ambiguous_slots = (
        ConfiguredSlot("overlap-a", _window(9, 11)),
        ConfiguredSlot("overlap-b", _window(9, 10)),
    )
    ambiguous = evaluate_wakeup_slot_binding(
        configured_slots=ambiguous_slots,
        business_date=_BUSINESS_DATE,
        requested_slot_id="overlap-a",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=SlotBindingIndex(),
    )
    wrong_date = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=date(2026, 11, 13),
        requested_slot_id="configured-a",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=SlotBindingIndex(),
    )

    assert ambiguous.reason == "source_window_matches_multiple_slots"
    assert wrong_date.reason == "source_window_invalid_for_business_date"


def test_business_date_uses_historical_beijing_daylight_saving_rules() -> None:
    window = WakeTimeWindow(
        starts_at=datetime(1991, 7, 1, 15, 10, tzinfo=timezone.utc),
        ends_at=datetime(1991, 7, 1, 15, 50, tzinfo=timezone.utc),
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=(ConfiguredSlot("historical-slot", window),),
        business_date=date(1991, 7, 2),
        requested_slot_id="historical-slot",
        evidence=_evidence(window=window),
        existing=SlotBindingIndex(),
    )

    assert result.status is SlotBindingStatus.READY


@pytest.mark.parametrize(
    ("end_offset", "expected_status"),
    (
        (timedelta(), SlotBindingStatus.READY),
        (timedelta(microseconds=1), SlotBindingStatus.BLOCKED),
    ),
)
def test_half_open_business_day_window_can_end_exactly_at_next_midnight(
    end_offset: timedelta, expected_status: SlotBindingStatus
) -> None:
    next_midnight = datetime(2026, 11, 13, tzinfo=_BEIJING)
    window = WakeTimeWindow(
        starts_at=datetime(2026, 11, 12, 23, tzinfo=_BEIJING),
        ends_at=next_midnight + end_offset,
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=(ConfiguredSlot("late-slot", window),),
        business_date=_BUSINESS_DATE,
        requested_slot_id="late-slot",
        evidence=HostValidatedWakeEvidence(bindable_window=window),
        existing=SlotBindingIndex(),
    )

    assert result.status is expected_status
    if expected_status is SlotBindingStatus.BLOCKED:
        assert result.reason == "source_window_invalid_for_business_date"


@pytest.mark.parametrize(
    ("source_start", "source_end", "expected_status"),
    (
        (
            datetime(1991, 9, 15, 1, 45, tzinfo=_BEIJING, fold=0),
            datetime(1991, 9, 15, 1, 15, tzinfo=_BEIJING, fold=1),
            SlotBindingStatus.READY,
        ),
        (
            datetime(1991, 9, 15, 1, 15, tzinfo=_BEIJING, fold=1),
            datetime(1991, 9, 15, 1, 45, tzinfo=_BEIJING, fold=0),
            SlotBindingStatus.BLOCKED,
        ),
    ),
)
def test_repeated_hour_source_order_and_containment_use_actual_instants(
    source_start: datetime,
    source_end: datetime,
    expected_status: SlotBindingStatus,
) -> None:
    configured_window = WakeTimeWindow(
        datetime(1991, 9, 15, 1, 30, tzinfo=_BEIJING, fold=0),
        datetime(1991, 9, 15, 1, 30, tzinfo=_BEIJING, fold=1),
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=(ConfiguredSlot("repeated-hour-slot", configured_window),),
        business_date=date(1991, 9, 15),
        requested_slot_id="repeated-hour-slot",
        evidence=HostValidatedWakeEvidence(
            bindable_window=WakeTimeWindow(source_start, source_end)
        ),
        existing=SlotBindingIndex(),
    )

    assert result.status is expected_status
    if expected_status is SlotBindingStatus.BLOCKED:
        assert result.reason == "source_window_invalid_for_business_date"


def test_same_wall_time_in_later_fold_does_not_fit_first_fold_slot() -> None:
    configured_window = WakeTimeWindow(
        datetime(1991, 9, 15, 1, 10, tzinfo=_BEIJING, fold=0),
        datetime(1991, 9, 15, 1, 50, tzinfo=_BEIJING, fold=0),
    )
    source_window = WakeTimeWindow(
        datetime(1991, 9, 15, 1, 20, tzinfo=_BEIJING, fold=1),
        datetime(1991, 9, 15, 1, 30, tzinfo=_BEIJING, fold=1),
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=(ConfiguredSlot("first-fold-only", configured_window),),
        business_date=date(1991, 9, 15),
        requested_slot_id="first-fold-only",
        evidence=HostValidatedWakeEvidence(bindable_window=source_window),
        existing=SlotBindingIndex(),
    )
    assert result.status is SlotBindingStatus.BLOCKED
    assert result.reason == "source_window_not_bindable"


def test_another_wake_cannot_reuse_an_occupied_slot() -> None:
    existing = SlotBindingIndex(
        bindings=(
            WakeSlotBinding(
                business_date=_BUSINESS_DATE,
                slot_id="configured-a",
                identities=(WakeIdentity(WakeIdentityKind.MESSAGE, "other-message"),),
            ),
        )
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=_evidence(window=_source_window(9, 9)),
        existing=existing,
    )

    assert result.status is SlotBindingStatus.BLOCKED
    assert result.reason == "configured_slot_already_occupied"


def _source_occurrence(
    *,
    namespace: str = "fixture-host",
    source_id: str = "fixture-source",
    instant: datetime | None = None,
) -> SourceOccurrenceIdentity:
    return SourceOccurrenceIdentity(
        namespace,
        source_id,
        instant or datetime(2026, 11, 12, 9, 30, tzinfo=_BEIJING),
    )


@pytest.mark.parametrize(
    "invalid_identity",
    (
        ("fixture-host", "fixture-source", "2026-11-12T01:30:00+00:00"),
        "serialized-source-occurrence",
        None,
    ),
)
def test_persisted_identity_must_be_a_supported_typed_object(
    invalid_identity: object,
) -> None:
    with pytest.raises(ValueError, match="Unsupported persisted wake identity type"):
        SlotBindingIndex(
            (
                WakeSlotBinding(
                    _BUSINESS_DATE,
                    "configured-a",
                    (cast(WakeBindingIdentity, invalid_identity),),
                ),
            )
        )


@pytest.mark.parametrize(
    "invalid_kind",
    ("message", "source_occurrence", None),
)
def test_persisted_wake_kind_must_be_supported_enum(invalid_kind: object) -> None:
    with pytest.raises(ValueError, match="supported WakeIdentityKind"):
        SlotBindingIndex(
            (
                WakeSlotBinding(
                    _BUSINESS_DATE,
                    "configured-a",
                    (
                        WakeIdentity(
                            cast(WakeIdentityKind, invalid_kind), "fixture-message"
                        ),
                    ),
                ),
            )
        )


@pytest.mark.parametrize("invalid_value", ("", " ", " message "))
def test_persisted_wake_value_must_remain_canonical(invalid_value: str) -> None:
    with pytest.raises(ValueError, match="canonical string"):
        SlotBindingIndex(
            (
                WakeSlotBinding(
                    _BUSINESS_DATE,
                    "configured-a",
                    (WakeIdentity(WakeIdentityKind.MESSAGE, invalid_value),),
                ),
            )
        )


@pytest.mark.parametrize(
    "invalid_source_occurrence", ("serialized", ("host", "source"), 1)
)
def test_source_evidence_rejects_untyped_composite(
    invalid_source_occurrence: object,
) -> None:
    with pytest.raises(ValueError, match="source_occurrence must be"):
        HostValidatedWakeEvidence(
            source_occurrence=cast(SourceOccurrenceIdentity, invalid_source_occurrence)
        )


def _overlapping_slots() -> tuple[ConfiguredSlot, ...]:
    return (
        ConfiguredSlot("configured-a", _window(9, 10)),
        ConfiguredSlot("configured-b", _window(9, 10)),
    )


def test_source_occurrence_normalizes_equal_instants_and_blocks_cross_slot() -> None:
    original_identity = _source_occurrence()
    equivalent_identity = _source_occurrence(
        instant=datetime(2026, 11, 12, 1, 30, tzinfo=timezone.utc)
    )
    assert original_identity == equivalent_identity
    assert len({original_identity, equivalent_identity}) == 1
    assert original_identity.occurred_at.tzinfo is timezone.utc
    original = WakeSlotBinding(_BUSINESS_DATE, "configured-a", (original_identity,))
    adapter = _MemorySlotAdapter(bindings=(original,))
    port: SlotBindingPersistencePort = adapter
    snapshot = port.read_binding_index(
        identities=(equivalent_identity,), business_date=_BUSINESS_DATE
    )
    repeated = evaluate_wakeup_slot_binding(
        configured_slots=_overlapping_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(source_occurrence=equivalent_identity),
        existing=snapshot,
    )
    assert repeated.status is SlotBindingStatus.IDEMPOTENT
    assert repeated.scope is SlotBindingScope.WAKE_IDENTITY
    rebound = evaluate_wakeup_slot_binding(
        configured_slots=_overlapping_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=HostValidatedWakeEvidence(source_occurrence=equivalent_identity),
        existing=snapshot,
    )
    assert rebound.reason == "wake_identity_already_bound_to_different_slot"
    assert (
        port.bind_and_claim(
            WakeSlotBinding(_BUSINESS_DATE, "configured-b", (equivalent_identity,))
        ).status
        is SlotPersistenceStatus.IDENTITY_BOUND_ELSEWHERE
    )


@pytest.mark.parametrize(
    "different_identity",
    (
        _source_occurrence(namespace="another-host"),
        _source_occurrence(source_id="another-source"),
        _source_occurrence(instant=datetime(2026, 11, 12, 9, 31, tzinfo=_BEIJING)),
    ),
)
def test_distinct_source_occurrences_are_not_mistaken_for_one_wake(
    different_identity: SourceOccurrenceIdentity,
) -> None:
    original = WakeSlotBinding(_BUSINESS_DATE, "configured-a", (_source_occurrence(),))
    result = evaluate_wakeup_slot_binding(
        configured_slots=_overlapping_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-b",
        evidence=HostValidatedWakeEvidence(source_occurrence=different_identity),
        existing=SlotBindingIndex((original,)),
    )
    assert result.status is SlotBindingStatus.READY


def test_source_namespace_and_id_are_separate_collision_safe_fields() -> None:
    first = _source_occurrence(namespace="host:group", source_id="source")
    second = _source_occurrence(namespace="host", source_id="group:source")
    assert first != second
    assert len({first, second}) == 2
    assert first != WakeIdentity(WakeIdentityKind.OCCURRENCE, "host:group:source")


@pytest.mark.parametrize(
    ("namespace", "source_id", "instant"),
    (
        ("", "source", datetime(2026, 11, 12, tzinfo=timezone.utc)),
        ("host", "", datetime(2026, 11, 12, tzinfo=timezone.utc)),
        ("  ", "source", datetime(2026, 11, 12, tzinfo=timezone.utc)),
        ("host", "source ", datetime(2026, 11, 12, tzinfo=timezone.utc)),
        ("host", "source", datetime(2026, 11, 12)),
    ),
)
def test_invalid_or_partial_source_occurrences_are_rejected(
    namespace: str, source_id: str, instant: datetime
) -> None:
    with pytest.raises(ValueError):
        SourceOccurrenceIdentity(namespace, source_id, instant)


def test_source_occurrence_requires_all_parts_not_a_window() -> None:
    with pytest.raises(TypeError):
        SourceOccurrenceIdentity("host", "source")  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        SourceOccurrenceIdentity(  # type: ignore[call-arg]
            occurred_at=datetime(2026, 11, 12, tzinfo=timezone.utc)
        )
    decision = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(
            source_kind="not-a-stable-source-identity",
            host_validation_reference="not-authentication",
            bindable_window=_source_window(9, 9),
        ),
        existing=SlotBindingIndex(),
    )
    assert decision.scope is SlotBindingScope.SLOT_ONLY
    assert decision.binding is not None
    assert decision.binding.identities == ()


def test_source_occurrence_alias_merge_preserves_all_identity_types() -> None:
    original_message = WakeIdentity(WakeIdentityKind.MESSAGE, "original-message")
    original_occurrence = WakeIdentity(
        WakeIdentityKind.OCCURRENCE, "original-occurrence"
    )
    source_identity = _source_occurrence()
    adapter = _MemorySlotAdapter(
        (
            WakeSlotBinding(
                _BUSINESS_DATE, "configured-a", (original_message, original_occurrence)
            ),
        )
    )
    first = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(
            message_id=original_message.value,
            source_occurrence=source_identity,
        ),
        existing=SlotBindingIndex(adapter.bindings),
    )
    assert first.binding is not None
    assert first.binding.identities == (original_message, source_identity)
    assert (
        adapter.bind_and_claim(first.binding).status is SlotPersistenceStatus.IDEMPOTENT
    )
    assert adapter.bindings[0].identities == (
        original_message,
        original_occurrence,
        source_identity,
    )
    second = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(
            message_id="new-message", source_occurrence=source_identity
        ),
        existing=SlotBindingIndex(adapter.bindings),
    )
    assert second.binding is not None
    assert (
        adapter.bind_and_claim(second.binding).status
        is SlotPersistenceStatus.IDEMPOTENT
    )
    assert adapter.bindings[0].identities == (
        original_message,
        original_occurrence,
        source_identity,
        WakeIdentity(WakeIdentityKind.MESSAGE, "new-message"),
    )
    no_id = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=None,
        existing=SlotBindingIndex(adapter.bindings),
    )
    assert no_id.binding is not None
    assert no_id.binding.identities == ()
    stored = adapter.bindings
    assert (
        adapter.bind_and_claim(no_id.binding).status
        is SlotPersistenceStatus.SLOT_OCCUPIED
    )
    assert adapter.bindings == stored


@pytest.mark.parametrize(
    ("instant", "reason"),
    (
        (datetime(2026, 11, 12, 9, 30, tzinfo=_BEIJING), None),
        (
            datetime(2026, 11, 12, 9, 45, tzinfo=_BEIJING),
            "source_occurrence_outside_source_window",
        ),
        (
            datetime(2026, 11, 12, 10, tzinfo=_BEIJING),
            "source_occurrence_outside_requested_slot",
        ),
        (
            datetime(2026, 11, 13, 9, 30, tzinfo=_BEIJING),
            "source_occurrence_business_date_mismatch",
        ),
    ),
)
def test_source_occurrence_respects_half_open_config_and_source_windows(
    instant: datetime,
    reason: str | None,
) -> None:
    result = evaluate_wakeup_slot_binding(
        configured_slots=_configured_slots(),
        business_date=_BUSINESS_DATE,
        requested_slot_id="configured-a",
        evidence=HostValidatedWakeEvidence(
            source_occurrence=_source_occurrence(instant=instant),
            bindable_window=_source_window(9, 9),
        ),
        existing=SlotBindingIndex(),
    )
    if reason is None:
        assert result.status is SlotBindingStatus.READY
    else:
        assert result.status is SlotBindingStatus.BLOCKED
        assert result.reason == reason


def test_source_occurrence_fold_identity_uses_utc_instant_not_wall_clock() -> None:
    first_fold = _source_occurrence(
        instant=datetime(1991, 9, 15, 1, 30, tzinfo=_BEIJING, fold=0)
    )
    second_fold = _source_occurrence(
        instant=datetime(1991, 9, 15, 1, 30, tzinfo=_BEIJING, fold=1)
    )
    equivalent_second = _source_occurrence(
        instant=datetime(1991, 9, 14, 17, 30, tzinfo=timezone.utc)
    )
    assert first_fold != second_fold
    assert second_fold == equivalent_second
    assert len({first_fold, second_fold, equivalent_second}) == 2
    slots = (
        ConfiguredSlot(
            "first-fold",
            WakeTimeWindow(
                datetime(1991, 9, 15, 1, tzinfo=_BEIJING, fold=0),
                datetime(1991, 9, 15, 1, tzinfo=_BEIJING, fold=1),
            ),
        ),
        ConfiguredSlot(
            "second-fold",
            WakeTimeWindow(
                datetime(1991, 9, 15, 1, tzinfo=_BEIJING, fold=1),
                datetime(1991, 9, 15, 2, tzinfo=_BEIJING),
            ),
        ),
    )
    result = evaluate_wakeup_slot_binding(
        configured_slots=slots,
        business_date=date(1991, 9, 15),
        requested_slot_id="second-fold",
        evidence=HostValidatedWakeEvidence(source_occurrence=equivalent_second),
        existing=SlotBindingIndex(
            (WakeSlotBinding(date(1991, 9, 15), "first-fold", (first_fold,)),)
        ),
    )
    assert result.status is SlotBindingStatus.READY
