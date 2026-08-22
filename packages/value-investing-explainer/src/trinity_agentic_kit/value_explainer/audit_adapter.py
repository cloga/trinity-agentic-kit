from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import cast

from .contracts import EvidenceClaim, EvidenceSource, TopicCandidate


def _mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return cast(Mapping[str, object], value)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return tuple(
        item for item in cast(Sequence[object], value) if isinstance(item, str)
    )


def _stable_mapping(value: object, path: str) -> str:
    mapping = _mapping(value, path)
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


def candidate_from_value_audit_result(
    audit_result: Mapping[str, object],
    *,
    topic_id: str,
    title: str,
    concept: str,
    audience: str = "general learners",
    objective: str = (
        "Explain the selected audit observations without recommending action."
    ),
    model_names: tuple[str, ...] = ("graham", "buffett", "greenwald", "lynch"),
) -> TopicCandidate:
    if audit_result.get("schema_version") != "1.0":
        raise ValueError("value-audit result schema_version must be 1.0")
    as_of_raw = audit_result.get("as_of_date")
    if not isinstance(as_of_raw, str):
        raise ValueError("value-audit result as_of_date must be an ISO date")
    try:
        as_of_date = date.fromisoformat(as_of_raw)
    except ValueError as error:
        raise ValueError("value-audit result as_of_date must be valid") from error
    models = _mapping(audit_result.get("models"), "models")
    top_level_warnings = _strings(audit_result.get("warnings", []))
    top_level_gaps = _strings(audit_result.get("data_gaps", []))
    assumptions = _stable_mapping(audit_result.get("assumptions", {}), "assumptions")
    company = str(
        audit_result.get("company_name") or audit_result.get("company_id") or ""
    )
    evidence: list[EvidenceSource] = []
    claims: list[EvidenceClaim] = []
    for model_name in model_names:
        if model_name not in models:
            continue
        model = _mapping(models[model_name], f"models.{model_name}")
        status = str(model.get("status") or "unavailable")
        metrics = _mapping(model.get("metrics", {}), f"models.{model_name}.metrics")
        metric_summary = ", ".join(
            f"{key}={metrics[key]}"
            for key in sorted(metrics)
            if metrics[key] is not None
        )
        source_id = f"value-audit:{model_name}"
        warnings = (*top_level_warnings, *_strings(model.get("warnings", [])))
        data_gaps = (*top_level_gaps, *_strings(model.get("data_gaps", [])))
        assumption_ids = _strings(model.get("assumption_ids", []))
        evidence.append(
            EvidenceSource(
                source_id=source_id,
                title=f"{company or 'Company'} {model_name} audit output",
                source_type="value-audit-core",
                as_of_date=as_of_date,
                content_summary=(
                    f"Model status is {status}. Reported metrics: "
                    f"{metric_summary or 'none'}. Assumption IDs: "
                    f"{', '.join(assumption_ids) or 'none'}. Audit assumptions: "
                    f"{assumptions or 'none'}. Warnings: "
                    f"{'; '.join(warnings) or 'none'}. Data gaps: "
                    f"{'; '.join(data_gaps) or 'none'}."
                ),
                content_kind="audit_output",
                provenance_ids=_strings(model.get("provenance_ids", [])),
            )
        )
        claims.append(
            EvidenceClaim(
                text=(
                    f"The {model_name} audit is {status}, with "
                    f"{len(warnings)} warning(s) and {len(data_gaps)} data gap(s); "
                    "its metrics must be read with the recorded assumptions."
                ),
                source_ids=(source_id,),
            )
        )
    if not evidence:
        raise ValueError("value-audit result contains none of the requested models")
    return TopicCandidate(
        topic_id=topic_id,
        title=title,
        concept=concept,
        audience=audience,
        objective=objective,
        evidence=tuple(evidence),
        claims=tuple(claims),
    )
