from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

REQUIRED_FILES = frozenset(
    {
        "SKILL.md",
        "README.md",
        "manifest.json",
        "references/login.md",
        "references/prepare.md",
        "references/approval.md",
        "references/execute.md",
        "references/verify.md",
        "references/recovery.md",
        "references/batch.md",
        "references/security.md",
        "schemas/request.schema.json",
        "schemas/result.schema.json",
        "examples/video.json",
        "examples/image-text.json",
    }
)

PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private repository name", re.compile(r"trinity-alpha", re.IGNORECASE)),
    ("database implementation", re.compile(r"\bsqlite\b", re.IGNORECASE)),
    ("private tool surface", re.compile(r"\bmcp[_ -]", re.IGNORECASE)),
    (
        "machine-specific path",
        re.compile(r"(?:[A-Za-z]:\\|/Users/|/home/[^ <]+/)"),
    ),
    (
        "secret material",
        re.compile(
            r"\b(?:password|credential|cookie[_ -]?value|access[_ -]?token)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "private interaction",
        re.compile(r"\b(?:private message|source comment)\b", re.IGNORECASE),
    ),
    (
        "operator identity",
        re.compile(r"\b(?:account[_ -]?id|account detail)\b", re.IGNORECASE),
    ),
    (
        "browser evasion",
        re.compile(
            r"\b(?:automationcontrolled|user-agent spoof|captcha bypass|"
            r"anti-detection)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "production site profile",
        re.compile(r"\bproduction selectors?\b", re.IGNORECASE),
    ),
)

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class SkillValidationError(ValueError):
    pass


def validate_suite(root: Path) -> list[str]:
    suite = root.resolve()
    errors: list[str] = []
    if not suite.is_dir():
        return [f"Skill directory not found: {suite}"]

    actual_files = {
        path.relative_to(suite).as_posix()
        for path in suite.rglob("*")
        if path.is_file()
    }
    missing = REQUIRED_FILES - actual_files
    errors.extend(f"Missing required file: {path}" for path in sorted(missing))

    for relative_path in sorted(actual_files):
        path = suite / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative_path}: cannot read UTF-8: {exc}")
            continue
        for label, pattern in PROHIBITED_PATTERNS:
            if pattern.search(text):
                errors.append(f"{relative_path}: prohibited {label}")
        if path.suffix == ".md":
            errors.extend(_validate_markdown_links(suite, path, text))
        if path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"{relative_path}: invalid JSON: {exc}")

    skill_path = suite / "SKILL.md"
    if skill_path.is_file():
        errors.extend(_validate_frontmatter(skill_path))
    manifest_path = suite / "manifest.json"
    if manifest_path.is_file():
        errors.extend(_validate_manifest(manifest_path))
    errors.extend(_validate_schemas_and_examples(suite))
    return errors


def _validate_frontmatter(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != "---":
        return ["SKILL.md: missing YAML frontmatter"]
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return ["SKILL.md: unterminated YAML frontmatter"]
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    errors: list[str] = []
    if fields.get("name") != "douyin-publish-suite":
        errors.append("SKILL.md: frontmatter name must be douyin-publish-suite")
    if not fields.get("description"):
        errors.append("SKILL.md: frontmatter description is required")
    return errors


def _validate_markdown_links(
    suite: Path,
    path: Path,
    text: str,
) -> list[str]:
    errors: list[str] = []
    for target in MARKDOWN_LINK.findall(text):
        if target.startswith(("http://", "https://", "#", "<")):
            continue
        clean_target = target.split("#", 1)[0]
        resolved = (path.parent / clean_target).resolve()
        if suite not in resolved.parents and resolved != suite:
            errors.append(
                f"{path.relative_to(suite).as_posix()}: link leaves suite: {target}"
            )
        elif not resolved.exists():
            errors.append(
                f"{path.relative_to(suite).as_posix()}: broken link: {target}"
            )
    return errors


def _validate_manifest(path: Path) -> list[str]:
    payload = _json_object(path)
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("manifest.json: schema_version must be 1")
    if payload.get("name") != "douyin-publish-suite":
        errors.append("manifest.json: name must be douyin-publish-suite")
    if payload.get("command") != "douyin-publish":
        errors.append("manifest.json: command must be douyin-publish")
    requires = payload.get("requires")
    expected = {
        "trinity-agentic-kit-social-publish",
        "trinity-agentic-kit-douyin-adapter",
        "trinity-agentic-kit-douyin",
    }
    if not isinstance(requires, dict):
        errors.append("manifest.json: required distributions are incomplete")
    else:
        require_values = cast(dict[object, object], requires)
        if set(require_values) != expected:
            errors.append("manifest.json: required distributions are incomplete")
    extras = payload.get("optional_extras")
    if extras != ["playwright", "keyring"]:
        errors.append("manifest.json: optional extras must be playwright and keyring")
    return errors


def _validate_schemas_and_examples(suite: Path) -> list[str]:
    request_schema_path = suite / "schemas" / "request.schema.json"
    result_schema_path = suite / "schemas" / "result.schema.json"
    if not request_schema_path.is_file() or not result_schema_path.is_file():
        return []
    request_schema = _json_object(request_schema_path)
    result_schema = _json_object(result_schema_path)
    errors = _validate_schema_document("request.schema.json", request_schema)
    errors.extend(_validate_schema_document("result.schema.json", result_schema))

    video_path = suite / "examples" / "video.json"
    combined_path = suite / "examples" / "image-text.json"
    if video_path.is_file():
        errors.extend(
            _validate_request_example(
                "examples/video.json",
                _json_object(video_path),
            )
        )
    if combined_path.is_file():
        combined = _json_object(combined_path)
        requests = combined.get("requests")
        if not isinstance(requests, list):
            errors.append("examples/image-text.json: requests must be an array")
        else:
            request_objects = cast(list[object], requests)
            if len(request_objects) != 2:
                errors.append(
                    "examples/image-text.json: expected image and text requests"
                )
            for index, request in enumerate(request_objects):
                if not isinstance(request, dict):
                    errors.append(
                        f"examples/image-text.json: requests[{index}] must be an object"
                    )
                    continue
                errors.extend(
                    _validate_request_example(
                        f"examples/image-text.json requests[{index}]",
                        cast(dict[str, Any], request),
                    )
                )
            media_types: set[object] = set()
            for request in request_objects:
                if isinstance(request, dict):
                    request_value = cast(dict[str, object], request)
                    media_types.add(request_value.get("media_type"))
            if media_types != {"image", "text"}:
                errors.append(
                    "examples/image-text.json: must contain image and text examples"
                )
    return errors


def _validate_schema_document(
    name: str,
    schema: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append(f"schemas/{name}: must use JSON Schema draft 2020-12")
    if schema.get("type") != "object":
        errors.append(f"schemas/{name}: root type must be object")
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict) or not properties:
        errors.append(f"schemas/{name}: properties are required")
    if not isinstance(required, list) or not required:
        errors.append(f"schemas/{name}: required fields are required")
    return errors


def _validate_request_example(
    name: str,
    request: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "request_id",
        "platform",
        "media_type",
        "asset_ref",
        "image_refs",
        "title",
        "description",
        "idempotency_key",
    }
    missing = required - request.keys()
    if missing:
        errors.append(f"{name}: missing fields: {', '.join(sorted(missing))}")
        return errors
    if request.get("schema_version") != 1:
        errors.append(f"{name}: schema_version must be 1")
    if request.get("platform") != "douyin":
        errors.append(f"{name}: platform must be douyin")
    media_type = request.get("media_type")
    if media_type not in {"video", "image", "text"}:
        errors.append(f"{name}: unsupported media_type")
    for key in ("request_id", "asset_ref", "idempotency_key"):
        value = request.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{name}: {key} must be a non-empty string")
    image_refs = request.get("image_refs")
    if not isinstance(image_refs, list):
        errors.append(f"{name}: image_refs must contain non-empty strings")
        return errors
    image_ref_values = cast(list[object], image_refs)
    if not all(isinstance(item, str) and bool(item) for item in image_ref_values):
        errors.append(f"{name}: image_refs must contain non-empty strings")
    elif media_type == "image" and not image_ref_values:
        errors.append(f"{name}: image requests require image_refs")
    elif media_type != "image" and image_ref_values:
        errors.append(f"{name}: only image requests may contain image_refs")
    return errors


def _json_object(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SkillValidationError(f"{path.name} must contain a JSON object")
    return cast(dict[str, Any], payload)


def main(argv: list[str] | None = None) -> int:
    arguments = argv if argv is not None else sys.argv[1:]
    root = Path(arguments[0]) if arguments else Path("skills") / "douyin-publish-suite"
    errors = validate_suite(root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Validated Douyin Skill suite: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
