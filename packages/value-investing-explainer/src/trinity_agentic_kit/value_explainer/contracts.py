from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from typing import Literal, cast

PACKAGE_VERSION = "0.1.0"
EXPLAINER_INPUT_SCHEMA_VERSION = "1.0"
EXPLAINER_OUTPUT_SCHEMA_VERSION = "1.0"
DISCLAIMER = (
    "Educational explanation only; not investment, legal, tax, or accounting "
    "advice or a recommendation. No affiliation with or endorsement by any "
    "investor, author, publisher, estate, employer, or related organization."
)

EvidenceKind = Literal["paraphrase", "facts", "public_domain_like", "audit_output"]


def _load_schema(filename: str) -> dict[str, object]:
    value: object = json.loads(
        files("trinity_agentic_kit.value_explainer.schemas")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid bundled JSON Schema: {filename}")
    return cast(dict[str, object], value)


TOPIC_CANDIDATE_SCHEMA = _load_schema("topic-candidate-v1.json")
EXPLANATION_PACKAGE_SCHEMA = _load_schema("explanation-package-v1.json")


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    raw = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{path} keys must be strings")
    return cast(Mapping[str, object], raw)


def _sequence(value: object, path: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{path} must be an array")
    return cast(Sequence[object], value)


def _text(mapping: Mapping[str, object], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _optional_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def _strings(value: object, path: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(_sequence(value, path)):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}[{index}] must be a non-empty string")
        result.append(item.strip())
    return tuple(result)


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    source_id: str
    title: str
    source_type: str
    as_of_date: date
    content_summary: str
    content_kind: EvidenceKind
    uri: str = ""
    provenance_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: object) -> EvidenceSource:
        data = _mapping(value, "evidence[]")
        kind = data.get("content_kind")
        if kind not in ("paraphrase", "facts", "public_domain_like", "audit_output"):
            raise ValueError("evidence[].content_kind is unsupported")
        try:
            as_of_date = date.fromisoformat(_text(data, "as_of_date", "evidence[]"))
        except ValueError as error:
            raise ValueError(
                "evidence[].as_of_date must be a valid ISO date"
            ) from error
        return cls(
            source_id=_text(data, "source_id", "evidence[]"),
            title=_text(data, "title", "evidence[]"),
            source_type=_text(data, "source_type", "evidence[]"),
            as_of_date=as_of_date,
            content_summary=_text(data, "content_summary", "evidence[]"),
            content_kind=kind,
            uri=_optional_text(data, "uri"),
            provenance_ids=_strings(
                data.get("provenance_ids", []), "evidence[].provenance_ids"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_type": self.source_type,
            "as_of_date": self.as_of_date.isoformat(),
            "content_summary": self.content_summary,
            "content_kind": self.content_kind,
            "uri": self.uri,
            "provenance_ids": list(self.provenance_ids),
        }


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    text: str
    source_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> EvidenceClaim:
        data = _mapping(value, "claims[]")
        return cls(
            text=_text(data, "text", "claims[]"),
            source_ids=_strings(data.get("source_ids"), "claims[].source_ids"),
        )

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "source_ids": list(self.source_ids)}


@dataclass(frozen=True, slots=True)
class TopicCandidate:
    topic_id: str
    title: str
    concept: str
    audience: str
    objective: str
    evidence: tuple[EvidenceSource, ...]
    claims: tuple[EvidenceClaim, ...]
    schema_version: str = EXPLAINER_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXPLAINER_INPUT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported input schema version: {self.schema_version}")
        if not self.evidence:
            raise ValueError("At least one evidence source is required")
        if not self.claims:
            raise ValueError("At least one evidence-backed claim is required")
        if any(not claim.source_ids for claim in self.claims):
            raise ValueError("Every claim must cite at least one evidence source")
        source_ids = [source.source_id for source in self.evidence]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Evidence source_ids must be unique")
        unknown = {
            source_id
            for claim in self.claims
            for source_id in claim.source_ids
            if source_id not in source_ids
        }
        if unknown:
            raise ValueError(
                "Claim source_ids missing from evidence: " + ", ".join(sorted(unknown))
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TopicCandidate:
        return cls(
            schema_version=_text(value, "schema_version", "$"),
            topic_id=_text(value, "topic_id", "$"),
            title=_text(value, "title", "$"),
            concept=_text(value, "concept", "$"),
            audience=_text(value, "audience", "$"),
            objective=_text(value, "objective", "$"),
            evidence=tuple(
                EvidenceSource.from_dict(item)
                for item in _sequence(value.get("evidence"), "evidence")
            ),
            claims=tuple(
                EvidenceClaim.from_dict(item)
                for item in _sequence(value.get("claims"), "claims")
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "topic_id": self.topic_id,
            "title": self.title,
            "concept": self.concept,
            "audience": self.audience,
            "objective": self.objective,
            "evidence": [source.to_dict() for source in self.evidence],
            "claims": [claim.to_dict() for claim in self.claims],
        }


@dataclass(frozen=True, slots=True)
class ScriptScene:
    index: int
    narration: str
    visual_direction: str
    source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "narration": self.narration,
            "visual_direction": self.visual_direction,
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True, slots=True)
class QACheck:
    check_id: str
    passed: bool
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class QAResult:
    passed: bool
    checks: tuple[QACheck, ...]

    @property
    def issues(self) -> tuple[str, ...]:
        return tuple(check.message for check in self.checks if not check.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "issues": list(self.issues),
        }


@dataclass(frozen=True, slots=True)
class ExplanationPackage:
    topic_id: str
    title: str
    summary: EvidenceClaim
    key_points: tuple[EvidenceClaim, ...]
    caveats: tuple[EvidenceClaim, ...]
    scenes: tuple[ScriptScene, ...]
    evidence: tuple[EvidenceSource, ...]
    qa: QAResult
    provider_name: str
    disclaimer: str = DISCLAIMER
    schema_version: str = EXPLAINER_OUTPUT_SCHEMA_VERSION
    package_version: str = PACKAGE_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_version": self.package_version,
            "topic_id": self.topic_id,
            "title": self.title,
            "summary": self.summary.to_dict(),
            "key_points": [point.to_dict() for point in self.key_points],
            "caveats": [caveat.to_dict() for caveat in self.caveats],
            "scenes": [scene.to_dict() for scene in self.scenes],
            "evidence": [source.to_dict() for source in self.evidence],
            "qa": self.qa.to_dict(),
            "provider_name": self.provider_name,
            "disclaimer": self.disclaimer,
        }
