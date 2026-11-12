from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

import pytest

from trinity_agentic_kit.value_explainer import (
    CatalogInsertResult,
    CatalogInsertStatus,
    EvidenceAttribution,
    EvidenceClaim,
    EvidenceSource,
    TopicCandidate,
    TopicCatalogIndex,
    TopicResearchRequest,
    TopicResearchStatus,
    research_and_replenish_topic_catalog,
)


def _candidate(
    topic_id: str = "synthetic-topic",
    source_id: str = "synthetic-source",
    uri: str = "https://example.invalid/source",
    summary: str = "Synthetic summary for contract tests.",
    attribution: EvidenceAttribution | None = None,
) -> TopicCandidate:
    source = EvidenceSource(
        source_id=source_id,
        title="Synthetic source",
        source_type="synthetic fixture",
        as_of_date=date(2026, 1, 1),
        content_summary=summary,
        content_kind="paraphrase",
        uri=uri,
        attribution=attribution,
    )
    return TopicCandidate(
        topic_id=topic_id,
        title="Synthetic topic",
        concept="synthetic concept",
        audience="contract tests",
        objective="exercise the research contract",
        evidence=(source,),
        claims=(EvidenceClaim("A synthetic claim.", (source_id,)),),
    )


@dataclass
class _Researcher:
    candidates: tuple[TopicCandidate, ...]
    request: TopicResearchRequest | None = None

    @property
    def name(self) -> str:
        return "synthetic-test-researcher"

    def research(self, request: TopicResearchRequest) -> tuple[TopicCandidate, ...]:
        self.request = request
        return self.candidates


@dataclass
class _Catalog:
    topic_ids: set[str] = field(default_factory=lambda: set[str]())
    sources: dict[str, EvidenceSource] = field(
        default_factory=lambda: dict[str, EvidenceSource]()
    )
    additions: list[TopicCandidate] = field(
        default_factory=lambda: list[TopicCandidate]()
    )

    def identities(self) -> TopicCatalogIndex:
        return TopicCatalogIndex(
            topic_ids=frozenset(self.topic_ids),
            sources=tuple(self.sources.values()),
        )

    def add_if_new(self, candidate: TopicCandidate) -> CatalogInsertResult:
        if candidate.topic_id in self.topic_ids:
            return CatalogInsertResult(CatalogInsertStatus.DUPLICATE_TOPIC)
        if any(
            source.source_id in self.sources
            and self.sources[source.source_id] != source
            for source in candidate.evidence
        ):
            return CatalogInsertResult(CatalogInsertStatus.SOURCE_CONFLICT)
        added_source_ids = tuple(
            source.source_id
            for source in candidate.evidence
            if source.source_id not in self.sources
        )
        self.topic_ids.add(candidate.topic_id)
        self.sources.update((source.source_id, source) for source in candidate.evidence)
        self.additions.append(candidate)
        return CatalogInsertResult(
            CatalogInsertStatus.INSERTED,
            added_source_ids=added_source_ids,
        )


class _ConcurrentDuplicateCatalog(_Catalog):
    calls: int = 0

    def add_if_new(self, candidate: TopicCandidate) -> CatalogInsertResult:
        self.calls += 1
        if self.calls == 1:
            return CatalogInsertResult(CatalogInsertStatus.DUPLICATE_TOPIC)
        return super().add_if_new(candidate)


class _FailingSecondWriteCatalog(_Catalog):
    calls: int = 0

    def add_if_new(self, candidate: TopicCandidate) -> CatalogInsertResult:
        self.calls += 1
        if self.calls == 2:
            raise OSError("synthetic catalog write failure")
        return super().add_if_new(candidate)


def test_research_cycle_forwards_known_ids_and_adds_novel_candidate() -> None:
    candidate = _candidate()
    researcher = _Researcher((candidate,))
    catalog = _Catalog(topic_ids={"existing-topic"})

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=3,
    )

    assert researcher.request == TopicResearchRequest(
        max_candidates=3,
        known_topic_ids=frozenset({"existing-topic"}),
        known_source_ids=frozenset(),
        known_sources=(),
    )
    assert report.status is TopicResearchStatus.ADDED
    assert report.added_topic_ids == ("synthetic-topic",)
    assert report.added_source_ids == ("synthetic-source",)
    assert catalog.additions == [candidate]

    duplicate_report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=3,
    )
    assert duplicate_report.status is TopicResearchStatus.NO_NEW_CANDIDATES
    assert duplicate_report.added_topic_ids == ()
    assert duplicate_report.added_source_ids == ()
    assert duplicate_report.duplicate_topic_ids == ("synthetic-topic",)
    assert len(catalog.additions) == 1


def test_duplicate_topic_does_not_mark_its_unpersisted_source_as_known() -> None:
    source_id = "shared-source"
    researcher = _Researcher(
        (
            _candidate(topic_id="existing-topic", source_id=source_id),
            _candidate(topic_id="novel-topic", source_id=source_id),
        )
    )
    catalog = _Catalog(topic_ids={"existing-topic"})

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=2,
    )

    assert report.added_topic_ids == ("novel-topic",)
    assert report.added_source_ids == (source_id,)
    assert report.duplicate_topic_ids == ("existing-topic",)


def test_skipped_duplicate_topic_does_not_cause_source_identity_conflict() -> None:
    source_id = "unpersisted-source"
    researcher = _Researcher(
        (
            _candidate(
                topic_id="existing-topic",
                source_id=source_id,
                summary="Source record attached only to the duplicate topic.",
            ),
            _candidate(
                topic_id="novel-topic",
                source_id=source_id,
                summary="Source record for the new topic.",
            ),
        )
    )
    catalog = _Catalog(topic_ids={"existing-topic"})

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=2,
    )

    assert report.added_topic_ids == ("novel-topic",)
    assert report.added_source_ids == (source_id,)
    assert report.duplicate_topic_ids == ("existing-topic",)


def test_skipped_in_batch_duplicate_topic_does_not_pollute_source_precheck() -> None:
    source_id = "unpersisted-source"
    researcher = _Researcher(
        (
            _candidate(topic_id="first-topic", source_id="first-source"),
            _candidate(
                topic_id="first-topic",
                source_id=source_id,
                summary="Unpersisted source from duplicate candidate.",
            ),
            _candidate(
                topic_id="second-topic",
                source_id=source_id,
                summary="Source record for second topic.",
            ),
        )
    )
    catalog = _Catalog()

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=3,
    )

    assert report.added_topic_ids == ("first-topic", "second-topic")
    assert report.added_source_ids == ("first-source", source_id)
    assert report.duplicate_topic_ids == ("first-topic",)


def test_distinct_pending_topics_with_conflicting_source_id_are_rejected() -> None:
    source_id = "conflicting-source"
    researcher = _Researcher(
        (
            _candidate(
                topic_id="first-topic",
                source_id=source_id,
                summary="First candidate's source content.",
            ),
            _candidate(
                topic_id="second-topic",
                source_id=source_id,
                summary="Different source content under the same ID.",
            ),
        )
    )
    catalog = _Catalog()

    with pytest.raises(ValueError, match="conflicts"):
        research_and_replenish_topic_catalog(
            researcher=researcher,
            catalog=catalog,
            max_candidates=2,
        )

    assert catalog.additions == []


def test_researcher_receives_canonical_source_for_cross_cycle_reuse() -> None:
    source_id = "reused-source"

    @dataclass
    class _ReuseSourceResearcher:
        calls: int = 0
        requests: list[TopicResearchRequest] = field(
            default_factory=lambda: list[TopicResearchRequest]()
        )

        @property
        def name(self) -> str:
            return "synthetic-source-reuser"

        def research(self, request: TopicResearchRequest) -> tuple[TopicCandidate, ...]:
            self.requests.append(request)
            self.calls += 1
            if self.calls == 1:
                return (_candidate(topic_id="first-topic", source_id=source_id),)
            canonical_source = request.known_sources[0]
            assert canonical_source.source_id == source_id
            return (
                TopicCandidate(
                    topic_id="second-topic",
                    title="Second synthetic topic",
                    concept="another concept",
                    audience="contract tests",
                    objective="reuse a canonical source",
                    evidence=(canonical_source,),
                    claims=(EvidenceClaim("A second synthetic claim.", (source_id,)),),
                ),
            )

    researcher = _ReuseSourceResearcher()
    catalog = _Catalog()

    first_report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=1,
    )
    second_report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=1,
    )

    assert first_report.added_source_ids == (source_id,)
    assert second_report.added_topic_ids == ("second-topic",)
    assert second_report.added_source_ids == ()
    assert researcher.requests[1].known_sources == (catalog.sources[source_id],)


def test_concurrent_duplicate_topic_does_not_pollute_source_index() -> None:
    source_id = "shared-source"
    researcher = _Researcher(
        (
            _candidate(topic_id="raced-topic", source_id=source_id),
            _candidate(topic_id="novel-topic", source_id=source_id),
        )
    )
    catalog = _ConcurrentDuplicateCatalog()

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=2,
    )

    assert report.added_topic_ids == ("novel-topic",)
    assert report.added_source_ids == (source_id,)
    assert report.duplicate_topic_ids == ("raced-topic",)


def test_identical_source_can_be_reused_without_counting_it_as_new() -> None:
    source_id = "shared-classic-source"
    researcher = _Researcher(
        (
            _candidate(topic_id="first-topic", source_id=source_id),
            _candidate(topic_id="second-topic", source_id=source_id),
        )
    )
    catalog = _Catalog()

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=2,
    )

    assert report.status is TopicResearchStatus.ADDED
    assert report.added_topic_ids == ("first-topic", "second-topic")
    assert report.added_source_ids == (source_id,)
    assert report.duplicate_topic_ids == ()
    assert len(catalog.additions) == 2


def test_identical_attribution_metadata_allows_source_reuse() -> None:
    source_id = "shared-classic-source"
    attribution = EvidenceAttribution(
        author="Synthetic Author",
        work_title="Synthetic Work",
        source_location="chapter 2",
    )
    researcher = _Researcher(
        (
            _candidate(
                topic_id="first-topic",
                source_id=source_id,
                attribution=attribution,
            ),
            _candidate(
                topic_id="second-topic",
                source_id=source_id,
                attribution=attribution,
            ),
        )
    )
    catalog = _Catalog()

    report = research_and_replenish_topic_catalog(
        researcher=researcher,
        catalog=catalog,
        max_candidates=2,
    )

    assert report.added_topic_ids == ("first-topic", "second-topic")
    assert report.added_source_ids == (source_id,)


def test_conflicting_attribution_for_reused_source_id_is_rejected() -> None:
    source_id = "shared-classic-source"
    researcher = _Researcher(
        (
            _candidate(
                topic_id="first-topic",
                source_id=source_id,
                attribution=EvidenceAttribution(author="Author One"),
            ),
            _candidate(
                topic_id="second-topic",
                source_id=source_id,
                attribution=EvidenceAttribution(author="Author Two"),
            ),
        )
    )
    catalog = _Catalog()

    with pytest.raises(ValueError, match="conflicts"):
        research_and_replenish_topic_catalog(
            researcher=researcher,
            catalog=catalog,
            max_candidates=2,
        )

    assert catalog.additions == []


def test_conflicting_source_id_content_fails_before_any_write() -> None:
    candidate = _candidate(topic_id="new-topic", source_id="stored-source")
    existing_source = replace(
        candidate.evidence[0],
        content_summary="Different source content under the same ID.",
    )
    catalog = _Catalog(sources={"stored-source": existing_source})

    with pytest.raises(ValueError, match="conflicts"):
        research_and_replenish_topic_catalog(
            researcher=_Researcher((candidate, _candidate(topic_id="other-topic"))),
            catalog=catalog,
            max_candidates=2,
        )

    assert catalog.additions == []


def test_entire_batch_is_structurally_validated_before_any_write() -> None:
    valid = _candidate(topic_id="valid-topic")
    source_without_id = replace(valid.evidence[0], source_id="")
    invalid_candidates = (
        replace(valid, topic_id=""),
        replace(valid, title=" "),
        replace(
            valid,
            evidence=(source_without_id,),
            claims=(EvidenceClaim("Claim.", ("",)),),
        ),
        replace(
            valid,
            claims=(EvidenceClaim(" ", ("synthetic-source",)),),
        ),
    )

    for invalid in invalid_candidates:
        catalog = _Catalog()
        with pytest.raises(ValueError, match="structurally invalid"):
            research_and_replenish_topic_catalog(
                researcher=_Researcher((valid, invalid)),
                catalog=catalog,
                max_candidates=2,
            )
        assert catalog.additions == []


def test_catalog_failure_propagates_without_claiming_batch_atomicity() -> None:
    catalog = _FailingSecondWriteCatalog()
    researcher = _Researcher(
        (
            _candidate(topic_id="first-topic", source_id="first-source"),
            _candidate(topic_id="second-topic", source_id="second-source"),
        )
    )

    with pytest.raises(OSError, match="synthetic catalog write failure"):
        research_and_replenish_topic_catalog(
            researcher=researcher,
            catalog=catalog,
            max_candidates=2,
        )

    assert [candidate.topic_id for candidate in catalog.additions] == ["first-topic"]


def test_empty_result_is_not_reported_as_refill_success() -> None:
    report = research_and_replenish_topic_catalog(
        researcher=_Researcher(()),
        catalog=_Catalog(),
        max_candidates=1,
    )

    assert report.status is TopicResearchStatus.NO_CANDIDATES
    assert report.candidate_count == 0


def test_research_cycle_requires_durable_catalog_and_traceable_evidence() -> None:
    with pytest.raises(TypeError, match="required"):
        research_and_replenish_topic_catalog(
            researcher=_Researcher(()),
            catalog=None,
            max_candidates=1,
        )

    with pytest.raises(ValueError, match="absolute HTTP"):
        research_and_replenish_topic_catalog(
            researcher=_Researcher((_candidate(uri=""),)),
            catalog=_Catalog(),
            max_candidates=1,
        )
