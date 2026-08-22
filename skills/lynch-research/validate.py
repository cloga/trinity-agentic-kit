from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

_CATEGORIES = {
    "slow_grower",
    "stalwart",
    "fast_grower",
    "cyclical",
    "asset_play",
    "turnaround",
    "unverified",
}
_VERDICTS = {
    "lynch_style_candidate",
    "watchlist",
    "wrong_framework",
    "reject",
    "data_gap",
}


def _mapping(value: object, path: str, errors: list[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return cast(Mapping[str, object], value)


def _string_list(value: object, path: str, errors: list[str]) -> None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        errors.append(f"{path} must be an array")
        return
    items = cast(Sequence[object], value)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            errors.append(f"{path}[{index}] must be a string")


def validate_audit_input(payload: object) -> list[str]:
    errors: list[str] = []
    root = _mapping(payload, "$", errors)
    if root.get("schema_version") != "1.0":
        errors.append("$.schema_version must be 1.0")
    for key in (
        "package_version",
        "company_id",
        "as_of_date",
        "assumptions",
        "provenance",
        "disclaimer",
    ):
        if key not in root:
            errors.append(f"$.{key} is required")
    models = _mapping(root.get("models"), "$.models", errors)
    for model_name in ("graham", "buffett", "greenwald", "lynch"):
        if model_name not in models:
            errors.append(f"$.models.{model_name} is required")
    lynch = _mapping(models.get("lynch"), "$.models.lynch", errors)
    metrics = _mapping(lynch.get("metrics"), "$.models.lynch.metrics", errors)
    if metrics.get("category") not in _CATEGORIES:
        errors.append("$.models.lynch.metrics.category is invalid")
    for key in ("warnings", "data_gaps", "provenance_ids"):
        _string_list(lynch.get(key), f"$.models.lynch.{key}", errors)
    for key in ("warnings", "data_gaps"):
        _string_list(root.get(key), f"$.{key}", errors)
    return errors


def validate_research_output(payload: object, *, audit_input: object) -> list[str]:
    errors: list[str] = []
    root = _mapping(payload, "$", errors)
    trusted = _mapping(audit_input, "audit_input", errors)
    if root.get("schema_version") != "1.0":
        errors.append("$.schema_version must be 1.0")
    if root.get("company_id") != trusted.get("company_id"):
        errors.append("$.company_id must match the audit input")
    category = root.get("verified_category")
    if category not in _CATEGORIES:
        errors.append("$.verified_category is invalid")
    verdict = root.get("verdict")
    if verdict not in _VERDICTS:
        errors.append("$.verdict is invalid")
    if root.get("confidence") not in {"high", "medium", "low"}:
        errors.append("$.confidence is invalid")
    ranking_framework = root.get("ranking_framework")
    trusted_models = _mapping(trusted.get("models"), "audit_input.models", errors)
    trusted_lynch = _mapping(
        trusted_models.get("lynch"), "audit_input.models.lynch", errors
    )
    trusted_metrics = _mapping(
        trusted_lynch.get("metrics"), "audit_input.models.lynch.metrics", errors
    )
    if trusted_metrics.get("is_financial") is True:
        if ranking_framework != "financial_sector":
            errors.append(
                "$.ranking_framework must be financial_sector for a trusted "
                "financial-company input"
            )
    elif ranking_framework != category:
        errors.append("$.ranking_framework must match verified_category")
    for key in ("vetoes", "warnings", "data_gaps", "follow_up_checks"):
        _string_list(root.get(key), f"$.{key}", errors)
    thesis = root.get("thesis")
    if not isinstance(thesis, str) or not thesis.strip():
        errors.append("$.thesis must be a non-empty string")
    evidence = root.get("evidence")
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        errors.append("$.evidence must be an array")
    return errors


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit_input = _load_json(args.input)
    errors = validate_audit_input(audit_input)
    if args.output is not None:
        errors.extend(
            validate_research_output(_load_json(args.output), audit_input=audit_input)
        )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
