from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import EvidenceClaim, TopicCandidate


@dataclass(frozen=True, slots=True)
class SemanticRequest:
    candidate: TopicCandidate
    requirements: tuple[str, ...] = (
        "Use only the supplied claims and source IDs.",
        "Use plain language and preserve uncertainty.",
        "Do not provide investment advice, recommendations, or guarantees.",
        "Do not imply affiliation or endorsement.",
        "Do not reproduce verbatim copyrighted text.",
    )


@dataclass(frozen=True, slots=True)
class DraftScene:
    narration: str
    visual_direction: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticDraft:
    summary: EvidenceClaim
    key_points: tuple[EvidenceClaim, ...]
    caveats: tuple[EvidenceClaim, ...]
    scenes: tuple[DraftScene, ...]


class SemanticGenerationPort(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, request: SemanticRequest) -> SemanticDraft: ...


@dataclass(frozen=True, slots=True)
class DeterministicFakeProvider:
    draft: SemanticDraft | None = None

    @property
    def name(self) -> str:
        return "deterministic-fake"

    def generate(self, request: SemanticRequest) -> SemanticDraft:
        if self.draft is not None:
            return self.draft
        candidate = request.candidate
        source_ids = tuple(
            dict.fromkeys(
                source_id
                for claim in candidate.claims
                for source_id in claim.source_ids
            )
        )
        scenes = tuple(
            DraftScene(
                narration=claim.text,
                visual_direction=(
                    f"Show a simple, unlabeled comparison for {candidate.concept}; "
                    "avoid logos, people, and price predictions."
                ),
                source_ids=claim.source_ids,
            )
            for claim in candidate.claims
        )
        return SemanticDraft(
            summary=EvidenceClaim(
                text=(
                    f"{candidate.title} explains {candidate.concept} for "
                    f"{candidate.audience}. The explanation is limited to the "
                    "supplied evidence."
                ),
                source_ids=source_ids,
            ),
            key_points=candidate.claims,
            caveats=(
                EvidenceClaim(
                    text="The evidence may be incomplete or become stale.",
                    source_ids=source_ids,
                ),
                EvidenceClaim(
                    text=(
                        "A concept explanation does not determine whether a "
                        "security is suitable."
                    ),
                    source_ids=source_ids,
                ),
            ),
            scenes=scenes,
        )
