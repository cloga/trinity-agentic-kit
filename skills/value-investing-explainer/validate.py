# pyright: reportArgumentType=false, reportUnknownMemberType=false

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from jsonschema import Draft202012Validator, FormatChecker

_KINDS = {"paraphrase", "facts", "public_domain_like", "audit_output"}
_ROOT = Path(__file__).parent
_INPUT_SCHEMA = json.loads(
    (_ROOT / "schemas" / "input.schema.json").read_text(encoding="utf-8")
)
_OUTPUT_SCHEMA = json.loads(
    (_ROOT / "schemas" / "output.schema.json").read_text(encoding="utf-8")
)


def _mapping(value: object, path: str, errors: list[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return cast(Mapping[str, object], value)


def _items(value: object, path: str, errors: list[str]) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        errors.append(f"{path} must be an array")
        return ()
    return cast(Sequence[object], value)


def _source_ids(value: object, path: str, errors: list[str]) -> set[str]:
    result: set[str] = set()
    for index, item in enumerate(_items(value, path, errors)):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{path}[{index}] must be a non-empty string")
        else:
            result.add(item)
    return result


def _schema_errors(payload: object, schema: object) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"schema: {error.json_path}: {error.message}"
        for error in sorted(
            validator.iter_errors(payload), key=lambda item: item.json_path
        )
    ]


def validate_input(payload: object) -> list[str]:
    errors = _schema_errors(payload, _INPUT_SCHEMA)
    root = _mapping(payload, "$", errors)
    if root.get("schema_version") != "1.0":
        errors.append("$.schema_version must be 1.0")
    for key in ("topic_id", "title", "concept", "audience", "objective"):
        if not isinstance(root.get(key), str) or not str(root.get(key)).strip():
            errors.append(f"$.{key} must be a non-empty string")
    known: set[str] = set()
    for index, item in enumerate(_items(root.get("evidence"), "$.evidence", errors)):
        source = _mapping(item, f"$.evidence[{index}]", errors)
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"$.evidence[{index}].source_id must be a non-empty string")
        elif source_id in known:
            errors.append(f"$.evidence[{index}].source_id must be unique")
        else:
            known.add(source_id)
        if source.get("content_kind") not in _KINDS:
            errors.append(f"$.evidence[{index}].content_kind is unsupported")
        if not isinstance(source.get("content_summary"), str):
            errors.append(f"$.evidence[{index}].content_summary must be a string")
    claims = _items(root.get("claims"), "$.claims", errors)
    if not claims:
        errors.append("$.claims must contain at least one claim")
    for index, item in enumerate(claims):
        claim = _mapping(item, f"$.claims[{index}]", errors)
        references = _source_ids(
            claim.get("source_ids"), f"$.claims[{index}].source_ids", errors
        )
        if not references:
            errors.append(f"$.claims[{index}] must cite evidence")
        unknown = references - known
        if unknown:
            errors.append(
                f"$.claims[{index}].source_ids contains unknown IDs: "
                + ", ".join(sorted(unknown))
            )
    return errors


def validate_output(payload: object, *, explainer_input: object) -> list[str]:
    errors = _schema_errors(payload, _OUTPUT_SCHEMA)
    root = _mapping(payload, "$", errors)
    trusted = _mapping(explainer_input, "input", errors)
    if root.get("schema_version") != "1.0":
        errors.append("$.schema_version must be 1.0")
    if root.get("topic_id") != trusted.get("topic_id"):
        errors.append("$.topic_id must match the input")
    evidence = _items(trusted.get("evidence"), "input.evidence", errors)
    known = {
        str(source.get("source_id"))
        for item in evidence
        if (source := _mapping(item, "input.evidence[]", errors)).get("source_id")
    }
    provenance_paths = ("summary", "key_points", "caveats", "scenes")
    for path in provenance_paths:
        raw_value = root.get(path)
        values = (
            (raw_value,)
            if path == "summary"
            else _items(raw_value, f"$.{path}", errors)
        )
        if not values:
            errors.append(f"$.{path} must not be empty")
        for index, item in enumerate(values):
            entry = _mapping(item, f"$.{path}[{index}]", errors)
            references = _source_ids(
                entry.get("source_ids"), f"$.{path}[{index}].source_ids", errors
            )
            if not references:
                errors.append(f"$.{path}[{index}] must cite evidence")
            if references - known:
                errors.append(f"$.{path}[{index}] cites unknown evidence")
    disclaimer = str(root.get("disclaimer") or "").lower()
    if "not investment" not in disclaimer or "no affiliation" not in disclaimer:
        errors.append("$.disclaimer must state non-advice and non-affiliation")
    qa = _mapping(root.get("qa"), "$.qa", errors)
    if qa.get("passed") is not True:
        errors.append("$.qa.passed must be true for a publishable output")
    return errors


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    explainer_input = _load(args.input)
    errors = validate_input(explainer_input)
    if args.output is not None:
        errors.extend(
            validate_output(_load(args.output), explainer_input=explainer_input)
        )
    if errors:
        for error in errors:
            print(error)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
