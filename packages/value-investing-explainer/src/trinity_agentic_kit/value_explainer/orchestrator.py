from __future__ import annotations

import re
from collections.abc import Mapping
from difflib import SequenceMatcher

from .contracts import (
    DISCLAIMER,
    ExplanationPackage,
    QACheck,
    QAResult,
    ScriptScene,
    TopicCandidate,
)
from .providers import SemanticGenerationPort, SemanticRequest

_ADVICE_PATTERNS = (
    re.compile(r"\b(buy|sell|hold)\s+(this|the|these|those)\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\s+(buy|sell|hold|invest)\b", re.IGNORECASE),
    re.compile(
        r"\b(i|we)\s+(recommend|advise|urge)\s+(buying|selling|purchasing|investing)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(invest|buy|sell)\s+now\b", re.IGNORECASE),
    re.compile(r"\bguaranteed?\s+(return|profit|gain)s?\b", re.IGNORECASE),
    re.compile(r"\b(can't|cannot|will not)\s+lose\b", re.IGNORECASE),
    re.compile(r"\bprice\s+target\b", re.IGNORECASE),
)
_AFFILIATION_PATTERNS = (
    re.compile(r"\bofficial\s+.+\s+(explanation|guidance|analysis)\b", re.IGNORECASE),
    re.compile(r"\b(endorsed|sponsored|approved)\s+by\b", re.IGNORECASE),
    re.compile(r"(?<!not )\baffiliated\s+with\b", re.IGNORECASE),
)


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _has_verbatim_overlap(generated: str, evidence_summary: str) -> bool:
    generated_normalized = _normalized_text(generated)
    evidence_normalized = _normalized_text(evidence_summary)
    if min(len(generated_normalized), len(evidence_normalized)) < 40:
        return False
    match = SequenceMatcher(
        None, generated_normalized, evidence_normalized, autojunk=False
    ).find_longest_match()
    return match.size >= 40


def _check(check_id: str, passed: bool, success: str, failure: str) -> QACheck:
    return QACheck(
        check_id=check_id, passed=passed, message=success if passed else failure
    )


def validate_explanation_package(
    package: ExplanationPackage,
    *,
    candidate: TopicCandidate,
) -> QAResult:
    known_sources = {source.source_id for source in candidate.evidence}
    provenance_bound = all(
        claim.source_ids and set(claim.source_ids) <= known_sources
        for claim in (package.summary, *package.key_points, *package.caveats)
    ) and all(
        scene.source_ids and set(scene.source_ids) <= known_sources
        for scene in package.scenes
    )
    all_text = " ".join(
        [
            package.summary.text,
            *(point.text for point in package.key_points),
            *(caveat.text for caveat in package.caveats),
            *(scene.narration for scene in package.scenes),
            *(scene.visual_direction for scene in package.scenes),
        ]
    )
    checks = (
        _check(
            "evidence-present",
            bool(candidate.evidence and package.key_points),
            "Evidence and key points are present.",
            "Evidence and at least one key point are required.",
        ),
        _check(
            "known-provenance",
            bool(package.key_points and package.scenes) and provenance_bound,
            "All explanation blocks and scenes cite known evidence.",
            "Every explanation block and scene must cite known evidence IDs.",
        ),
        _check(
            "scene-provenance",
            bool(package.scenes) and all(scene.source_ids for scene in package.scenes),
            "Every scene has provenance.",
            "At least one scene is required and every scene must cite evidence.",
        ),
        _check(
            "content-complete",
            bool(package.summary.text.strip())
            and all(point.text.strip() for point in package.key_points)
            and all(caveat.text.strip() for caveat in package.caveats)
            and all(
                scene.narration.strip() and scene.visual_direction.strip()
                for scene in package.scenes
            ),
            "Explanation and scene content are complete.",
            "Summary, key points, narration, and visual directions cannot be empty.",
        ),
        _check(
            "advice-language",
            not any(pattern.search(all_text) for pattern in _ADVICE_PATTERNS),
            "No recommendation or guarantee language detected.",
            "Recommendation or guaranteed-return language is prohibited.",
        ),
        _check(
            "affiliation-language",
            not any(pattern.search(all_text) for pattern in _AFFILIATION_PATTERNS),
            "No affiliation or endorsement claim detected.",
            "Affiliation, endorsement, sponsorship, and official-status claims "
            "are prohibited.",
        ),
        _check(
            "copyright",
            not any(
                _has_verbatim_overlap(all_text, source.content_summary)
                for source in candidate.evidence
            ),
            "No substantial evidence passage is reused verbatim.",
            "Substantial evidence passages must be paraphrased, not copied verbatim.",
        ),
        _check(
            "disclaimer",
            package.disclaimer == DISCLAIMER,
            "Required advice and affiliation disclaimer is present.",
            "The standard non-advice and non-affiliation disclaimer is required.",
        ),
        _check(
            "topic-binding",
            package.topic_id == candidate.topic_id,
            "Output is bound to the input topic.",
            "Output topic_id must match the candidate.",
        ),
    )
    return QAResult(passed=all(check.passed for check in checks), checks=checks)


def explain_value_topic(
    candidate: TopicCandidate | Mapping[str, object],
    *,
    provider: SemanticGenerationPort,
) -> ExplanationPackage:
    parsed = (
        candidate
        if isinstance(candidate, TopicCandidate)
        else TopicCandidate.from_dict(candidate)
    )
    draft = provider.generate(SemanticRequest(candidate=parsed))
    provisional = ExplanationPackage(
        topic_id=parsed.topic_id,
        title=parsed.title,
        summary=draft.summary,
        key_points=draft.key_points,
        caveats=draft.caveats,
        scenes=tuple(
            ScriptScene(
                index=index,
                narration=scene.narration,
                visual_direction=scene.visual_direction,
                source_ids=scene.source_ids,
            )
            for index, scene in enumerate(draft.scenes, start=1)
        ),
        evidence=parsed.evidence,
        qa=QAResult(passed=False, checks=()),
        provider_name=provider.name,
    )
    qa = validate_explanation_package(provisional, candidate=parsed)
    return ExplanationPackage(
        topic_id=provisional.topic_id,
        title=provisional.title,
        summary=provisional.summary,
        key_points=provisional.key_points,
        caveats=provisional.caveats,
        scenes=provisional.scenes,
        evidence=provisional.evidence,
        qa=qa,
        provider_name=provisional.provider_name,
    )
