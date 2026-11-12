from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from urllib.parse import urlparse

from .contracts import EvidenceSource, TopicCandidate


@dataclass(frozen=True, slots=True)
class TopicResearchRequest:
    """Novelty context for one caller-scheduled research cycle."""

    max_candidates: int
    known_topic_ids: frozenset[str]
    known_source_ids: frozenset[str]
    known_sources: tuple[EvidenceSource, ...]


class TopicResearchPort(Protocol):
    """Consumer-supplied agent for researching classic value-investing sources."""

    @property
    def name(self) -> str: ...

    def research(self, request: TopicResearchRequest) -> Sequence[TopicCandidate]:
        """Retrieve and verify cited sources; do not infer research from metadata."""
        ...


@dataclass(frozen=True, slots=True)
class TopicCatalogIndex:
    """Persisted topic identities and canonical evidence source records."""

    topic_ids: frozenset[str]
    sources: tuple[EvidenceSource, ...]

    def __post_init__(self) -> None:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Catalog source identities must be unique")

    @property
    def source_ids(self) -> frozenset[str]:
        return frozenset(source.source_id for source in self.sources)


class CatalogInsertStatus(str, Enum):
    INSERTED = "inserted"
    DUPLICATE_TOPIC = "duplicate_topic"
    SOURCE_CONFLICT = "source_conflict"


@dataclass(frozen=True, slots=True)
class CatalogInsertResult:
    status: CatalogInsertStatus
    added_source_ids: tuple[str, ...] = ()


class TopicCandidateCatalog(Protocol):
    """Consumer-owned durable catalog with atomic identity handling."""

    def identities(self) -> TopicCatalogIndex:
        """Return persisted topic IDs and the source records they reference."""
        ...

    def add_if_new(self, candidate: TopicCandidate) -> CatalogInsertResult:
        """Atomically insert a topic and report source records newly inserted.

        A source ID already present with identical content is reusable. The
        same ID with different content returns SOURCE_CONFLICT. DUPLICATE_TOPIC
        and SOURCE_CONFLICT must not add source records.
        """
        ...


class TopicResearchStatus(str, Enum):
    ADDED = "added"
    NO_CANDIDATES = "no_candidates"
    NO_NEW_CANDIDATES = "no_new_candidates"


@dataclass(frozen=True, slots=True)
class TopicResearchReport:
    researcher_name: str
    status: TopicResearchStatus
    candidate_count: int
    added_topic_ids: tuple[str, ...]
    added_source_ids: tuple[str, ...]
    duplicate_topic_ids: tuple[str, ...]


def _validate_research_candidate(candidate: object) -> TopicCandidate:
    if not isinstance(candidate, TopicCandidate):
        raise TypeError("researcher returned a non-TopicCandidate value")
    try:
        validated = TopicCandidate.from_dict(candidate.to_dict())
    except ValueError as error:
        raise ValueError(
            f"Research candidate {candidate.topic_id!r} is structurally invalid: "
            f"{error}"
        ) from error

    for source in validated.evidence:
        parsed = urlparse(source.uri)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"Research candidate {validated.topic_id!r} has an evidence "
                f"source without an absolute HTTP(S) URI: {source.source_id!r}"
            )
    return validated


def _validate_catalog_result(
    result: object,
    *,
    candidate: TopicCandidate,
    known_source_ids: set[str],
) -> CatalogInsertResult:
    if not isinstance(result, CatalogInsertResult):
        raise TypeError("catalog.add_if_new() must return CatalogInsertResult")
    if len(result.added_source_ids) != len(set(result.added_source_ids)):
        raise ValueError("catalog added_source_ids must be unique")

    candidate_source_ids = {source.source_id for source in candidate.evidence}
    if not set(result.added_source_ids) <= candidate_source_ids:
        raise ValueError(
            "catalog reported an added source not present in the candidate"
        )
    if set(result.added_source_ids) & known_source_ids:
        raise ValueError("catalog reported an existing source as newly inserted")
    if result.status is not CatalogInsertStatus.INSERTED and result.added_source_ids:
        raise ValueError("catalog cannot add source records without inserting a topic")
    return result


def research_and_replenish_topic_catalog(
    *,
    researcher: TopicResearchPort | None,
    catalog: TopicCandidateCatalog | None,
    max_candidates: int,
) -> TopicResearchReport:
    """Run one research cycle and persist only novel, traceable candidates.

    The researcher must retrieve and verify its cited sources; this package
    checks traceability and deduplication, not the truth of research claims.
    The catalog must provide durable, per-candidate atomic writes and topic-ID
    uniqueness. Identical source records may be reused; conflicting content
    for one source ID is rejected. The cycle is not a batch transaction.
    Callers schedule repeated cycles themselves.
    """
    if researcher is None or catalog is None:
        raise TypeError("researcher and durable catalog are required")
    if type(max_candidates) is not int:
        raise TypeError("max_candidates must be an integer")
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")

    researcher_name = researcher.name
    index = catalog.identities()

    candidates = researcher.research(
        TopicResearchRequest(
            max_candidates=max_candidates,
            known_topic_ids=index.topic_ids,
            known_source_ids=index.source_ids,
            known_sources=index.sources,
        )
    )
    if len(candidates) > max_candidates:
        raise ValueError("researcher returned more candidates than requested")
    if not candidates:
        return TopicResearchReport(
            researcher_name=researcher_name,
            status=TopicResearchStatus.NO_CANDIDATES,
            candidate_count=0,
            added_topic_ids=(),
            added_source_ids=(),
            duplicate_topic_ids=(),
        )

    validated_candidates = tuple(
        _validate_research_candidate(candidate) for candidate in candidates
    )
    known_source_records = {source.source_id: source for source in index.sources}
    batch_source_records = dict(known_source_records)
    prechecked_topic_ids = set(index.topic_ids)
    for candidate in validated_candidates:
        if candidate.topic_id in prechecked_topic_ids:
            continue
        prechecked_topic_ids.add(candidate.topic_id)
        for source in candidate.evidence:
            known = batch_source_records.get(source.source_id)
            if known is not None and known != source:
                raise ValueError(
                    f"Research candidate source ID {source.source_id!r} conflicts "
                    "with an existing source record"
                )
            batch_source_records[source.source_id] = source

    known_topic_ids = set(index.topic_ids)
    known_source_ids = set(index.source_ids)
    added_topic_ids: list[str] = []
    added_source_ids: list[str] = []
    duplicate_topic_ids: list[str] = []
    for candidate in validated_candidates:
        if candidate.topic_id in known_topic_ids:
            duplicate_topic_ids.append(candidate.topic_id)
            continue

        result = _validate_catalog_result(
            catalog.add_if_new(candidate),
            candidate=candidate,
            known_source_ids=known_source_ids,
        )
        if result.status is CatalogInsertStatus.INSERTED:
            added_topic_ids.append(candidate.topic_id)
            known_topic_ids.add(candidate.topic_id)
            added_source_ids.extend(result.added_source_ids)
            known_source_ids.update(source.source_id for source in candidate.evidence)
        elif result.status is CatalogInsertStatus.DUPLICATE_TOPIC:
            duplicate_topic_ids.append(candidate.topic_id)
            known_topic_ids.add(candidate.topic_id)
        elif result.status is CatalogInsertStatus.SOURCE_CONFLICT:
            raise ValueError(
                "catalog reported a source ID content conflict during insertion"
            )
        else:
            raise ValueError(f"Unsupported catalog insert status: {result.status!r}")

    status = (
        TopicResearchStatus.ADDED
        if added_topic_ids
        else TopicResearchStatus.NO_NEW_CANDIDATES
    )
    return TopicResearchReport(
        researcher_name=researcher_name,
        status=status,
        candidate_count=len(candidates),
        added_topic_ids=tuple(added_topic_ids),
        added_source_ids=tuple(added_source_ids),
        duplicate_topic_ids=tuple(duplicate_topic_ids),
    )
