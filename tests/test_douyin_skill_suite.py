from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Protocol, cast

from jsonschema import Draft202012Validator
from scripts.validate_douyin_skill import REQUIRED_FILES, validate_suite

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = REPOSITORY_ROOT / "skills" / "douyin-publish-suite"


class SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def schema_validator(schema: dict[str, Any]) -> SchemaValidator:
    Draft202012Validator.check_schema(schema)
    return cast(SchemaValidator, Draft202012Validator(schema))


def json_object(path: Path) -> dict[str, Any]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def test_suite_validator_accepts_public_progressive_skill() -> None:
    assert validate_suite(SUITE_ROOT) == []
    files = {
        path.relative_to(SUITE_ROOT).as_posix()
        for path in SUITE_ROOT.rglob("*")
        if path.is_file()
    }
    assert files >= REQUIRED_FILES
    assert not (REPOSITORY_ROOT / "skills" / "douyin-publish").exists()
    assert (REPOSITORY_ROOT / "skills" / "social-publish" / "SKILL.md").exists()


def test_request_schema_validates_all_examples() -> None:
    schema = json_object(SUITE_ROOT / "schemas" / "request.schema.json")
    validator = schema_validator(schema)
    validator.validate(json_object(SUITE_ROOT / "examples" / "video.json"))
    combined = json_object(SUITE_ROOT / "examples" / "image-text.json")
    requests: object = combined["requests"]
    assert isinstance(requests, list)
    for request in cast(list[object], requests):
        validator.validate(request)


def test_result_schema_validates_success_and_failure_contracts() -> None:
    schema = json_object(SUITE_ROOT / "schemas" / "result.schema.json")
    validator = schema_validator(schema)
    validator.validate(
        {
            "ok": True,
            "command": "status",
            "record": {
                "request_id": "request-1",
                "state": "published",
                "request_digest": "a" * 64,
                "title": "Title",
                "asset_ref": "asset://example",
                "platform": "douyin",
                "media_type": "video",
                "platform_reference": "reference-1",
                "published_url": "https://example.invalid/item/1",
                "error": {"code": "", "message": ""},
                "revision": 1,
            },
        }
    )
    validator.validate(
        {
            "ok": False,
            "error": {
                "code": "config_invalid",
                "message": "Invalid configuration",
                "details": {},
            },
        }
    )


def test_validator_rejects_prohibited_content_and_broken_links(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "suite"
    shutil.copytree(SUITE_ROOT, copied)
    reference = copied / "references" / "security.md"
    reference.write_text(
        reference.read_text(encoding="utf-8")
        + "\nA forbidden Trinity-Alpha note and [bad](missing.md).\n",
        encoding="utf-8",
    )

    errors = validate_suite(copied)

    assert any("private repository name" in error for error in errors)
    assert any("broken link" in error for error in errors)


def test_manifest_pins_public_distribution_family() -> None:
    manifest = json_object(SUITE_ROOT / "manifest.json")
    requires = manifest["requires"]
    assert isinstance(requires, dict)
    assert requires == {
        "trinity-agentic-kit-social-publish": ">=0.1.0,<0.2",
        "trinity-agentic-kit-douyin-adapter": ">=0.1.0,<0.2",
        "trinity-agentic-kit-douyin": ">=0.1.0,<0.2",
    }
