from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from trinity_agentic_kit.douyin_adapter import SelectorProfile

from .models import EXIT_CONFIG, CliFailure


@dataclass(frozen=True, slots=True)
class CliConfig:
    selector_profile: SelectorProfile
    browser_name: str = "chromium"
    use_keyring: bool = False


def load_config(path: Path) -> CliConfig:
    try:
        raw_object: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CliFailure(
            "config_not_found",
            f"Configuration file not found: {path}",
            EXIT_CONFIG,
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CliFailure(
            "config_invalid",
            f"Cannot read configuration: {exc}",
            EXIT_CONFIG,
        ) from exc
    if not isinstance(raw_object, dict):
        raise CliFailure(
            "config_invalid",
            "Configuration must be a JSON object",
            EXIT_CONFIG,
        )
    raw = cast(dict[str, object], raw_object)
    allowed = {"selector_profile", "browser_name", "use_keyring"}
    unknown = raw.keys() - allowed
    if unknown:
        raise CliFailure(
            "config_invalid",
            "Unknown configuration keys: " + ", ".join(sorted(unknown)),
            EXIT_CONFIG,
        )
    profile_object = raw.get("selector_profile")
    if not isinstance(profile_object, dict):
        raise CliFailure(
            "config_invalid",
            "selector_profile must be an object",
            EXIT_CONFIG,
        )
    profile_values = cast(dict[str, object], profile_object)
    selectors = _string_mapping(
        profile_values.get("selectors"),
        "selector_profile.selectors",
    )
    try:
        profile = SelectorProfile(
            name=_required_string(profile_values, "name"),
            version=_required_string(profile_values, "version"),
            login_url=_required_string(profile_values, "login_url"),
            publish_url=_required_string(profile_values, "publish_url"),
            verification_url_template=_required_string(
                profile_values, "verification_url_template"
            ),
            selectors=selectors,
            schema_version=_optional_int(profile_values, "schema_version", default=1),
        )
    except ValueError as exc:
        raise CliFailure(
            "config_invalid",
            str(exc),
            EXIT_CONFIG,
        ) from exc
    browser_name = raw.get("browser_name", "chromium")
    if browser_name not in {"chromium", "firefox", "webkit"}:
        raise CliFailure(
            "config_invalid",
            "browser_name must be chromium, firefox, or webkit",
            EXIT_CONFIG,
        )
    use_keyring = raw.get("use_keyring", False)
    if not isinstance(use_keyring, bool):
        raise CliFailure(
            "config_invalid",
            "use_keyring must be a boolean",
            EXIT_CONFIG,
        )
    return CliConfig(
        selector_profile=profile,
        browser_name=cast(str, browser_name),
        use_keyring=use_keyring,
    )


def _required_string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"selector_profile.{key} must be a non-empty string")
    return value


def _optional_int(
    values: Mapping[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = values.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"selector_profile.{key} must be an integer")
    return value


def _string_mapping(value: object, name: str) -> Mapping[str, str]:
    if not isinstance(value, dict):
        raise CliFailure(
            "config_invalid",
            f"{name} must be an object",
            EXIT_CONFIG,
        )
    objects = cast(dict[object, object], value)
    if not all(
        isinstance(key, str) and isinstance(item, str) for key, item in objects.items()
    ):
        raise CliFailure(
            "config_invalid",
            f"{name} keys and values must be strings",
            EXIT_CONFIG,
        )
    return cast(dict[str, str], objects)
