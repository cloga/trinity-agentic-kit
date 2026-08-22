from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

DOUYIN_ADAPTER_VERSION = "0.1.0"
SELECTOR_PROFILE_SCHEMA_VERSION = 1
SUPPORTED_MEDIA_TYPES = frozenset({"video", "image", "text"})

_COMMON_SELECTORS = frozenset(
    {
        "authenticated",
        "composer_ready",
        "description_input",
        "submit_button",
        "submission_reference",
    }
)
_MEDIA_SELECTORS = {
    "video": frozenset({"video_input"}),
    "image": frozenset({"image_input"}),
    "text": frozenset({"text_input"}),
}


def _empty_selectors() -> Mapping[str, str]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class SelectorProfile:
    """Versioned, externally supplied URLs and selectors."""

    name: str
    version: str
    login_url: str
    publish_url: str
    verification_url_template: str
    selectors: Mapping[str, str] = field(default_factory=_empty_selectors)
    schema_version: int = SELECTOR_PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = {
            "name": self.name,
            "version": self.version,
            "login_url": self.login_url,
            "publish_url": self.publish_url,
            "verification_url_template": self.verification_url_template,
        }
        missing = [
            key for key, value in required.items() if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(
                f"Missing selector profile fields: {', '.join(sorted(missing))}"
            )
        if self.schema_version != SELECTOR_PROFILE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported selector profile schema: {self.schema_version}"
            )
        if "{platform_reference}" not in self.verification_url_template:
            raise ValueError(
                "verification_url_template must contain {platform_reference}"
            )
        normalized = {
            str(key).strip(): str(value).strip()
            for key, value in self.selectors.items()
        }
        if any(not key or not value for key, value in normalized.items()):
            raise ValueError("Selector profile entries cannot be blank")
        object.__setattr__(self, "selectors", MappingProxyType(normalized))

    def required_selectors(self, media_type: str) -> frozenset[str]:
        media = media_type.strip().lower()
        if media not in SUPPORTED_MEDIA_TYPES:
            raise ValueError(f"Unsupported media type: {media_type}")
        return _COMMON_SELECTORS | _MEDIA_SELECTORS[media]

    def validate_for(self, media_type: str) -> None:
        missing = self.required_selectors(media_type) - self.selectors.keys()
        if missing:
            raise ValueError(
                "Selector profile is missing: " + ", ".join(sorted(missing))
            )


@dataclass(frozen=True, slots=True)
class OperationTimeouts:
    login_seconds: float = 300.0
    prepare_seconds: float = 30.0
    execute_seconds: float = 120.0
    verify_seconds: float = 30.0

    def __post_init__(self) -> None:
        values = {
            "login_seconds": self.login_seconds,
            "prepare_seconds": self.prepare_seconds,
            "execute_seconds": self.execute_seconds,
            "verify_seconds": self.verify_seconds,
        }
        invalid = [name for name, value in values.items() if value <= 0 or value > 600]
        if invalid:
            raise ValueError(
                "Timeouts must be greater than 0 and at most 600 seconds: "
                + ", ".join(invalid)
            )


@dataclass(frozen=True, slots=True)
class DriverDiagnostics:
    operation: str
    profile_name: str
    profile_version: str
    checkpoint: str
    elapsed_seconds: float
    current_url: str = ""
    selector_name: str = ""


@dataclass(frozen=True, slots=True)
class DriverPublishResult:
    submitted: bool
    platform_reference: str = ""
    published_url: str = ""
    evidence: tuple[str, ...] = ()
    diagnostics: DriverDiagnostics | None = None


@dataclass(frozen=True, slots=True)
class DriverVerificationResult:
    found: bool
    published_url: str = ""
    evidence: tuple[str, ...] = ()
    diagnostics: DriverDiagnostics | None = None
