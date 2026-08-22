from __future__ import annotations

import io
import json
from pathlib import Path
from typing import cast

import pytest

from trinity_agentic_kit.douyin_adapter import (
    AdapterTimeoutError,
    DriverDiagnostics,
    FakeBrowserDriver,
    SelectorProfile,
)
from trinity_agentic_kit.douyin_cli import (
    EXIT_APPROVAL,
    EXIT_BROWSER,
    EXIT_CONFIG,
    EXIT_CONFIRMATION,
    EXIT_STATE,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    EXIT_USAGE,
    CliFailure,
    CliPaths,
    run,
)
from trinity_agentic_kit.douyin_cli.config import load_config
from trinity_agentic_kit.social_publish import SocialPublishRequest


class TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def paths_for(root: Path) -> CliPaths:
    data = root / "data"
    return CliPaths(
        data_dir=data,
        state_db=data / "state.db",
        approval_key=data / "approval.key",
        session_file=data / "session.bin",
        grants_dir=data / "grants",
        default_config=data / "config.json",
    )


def write_config(path: Path, *, use_keyring: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "browser_name": "chromium",
                "use_keyring": use_keyring,
                "selector_profile": {
                    "name": "offline",
                    "version": "1",
                    "schema_version": 1,
                    "login_url": "https://example.invalid/login",
                    "publish_url": "https://example.invalid/publish",
                    "verification_url_template": (
                        "https://example.invalid/items/{platform_reference}"
                    ),
                    "selectors": {
                        "authenticated": "auth",
                        "composer_ready": "composer",
                        "description_input": "description",
                        "submit_button": "submit",
                        "submission_reference": "reference",
                        "video_input": "video",
                        "image_input": "image",
                        "text_input": "text",
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def invoke(
    arguments: list[str],
    *,
    paths: CliPaths,
    driver: FakeBrowserDriver,
    stdin: io.StringIO | None = None,
) -> tuple[int, dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = run(
        arguments,
        paths=paths,
        driver_factory=lambda _config: driver,
        stdin=stdin or io.StringIO(),
        stdout=stdout,
        stderr=stderr,
    )
    payload: object = json.loads(stdout.getvalue())
    assert isinstance(payload, dict)
    return code, cast(dict[str, object], payload), stderr.getvalue()


def error_code(payload: dict[str, object]) -> str:
    error = payload["error"]
    assert isinstance(error, dict)
    code = cast(dict[str, object], error)["code"]
    assert isinstance(code, str)
    return code


def prepare_arguments(config: Path, request_id: str = "request-1") -> list[str]:
    return [
        "prepare",
        "--config",
        str(config),
        "--request-id",
        request_id,
        "--media-type",
        "video",
        "--asset-ref",
        "asset://video",
        "--title",
        "Exact title",
        "--description",
        "Description",
        "--idempotency-key",
        f"key-{request_id}",
    ]


def test_full_fake_driver_cli_lifecycle(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()

    login_code, login, _ = invoke(
        ["login", "--config", str(config)],
        paths=paths,
        driver=driver,
    )
    assert login_code == EXIT_SUCCESS
    assert login["session"] == "stored"
    assert paths.session_file.exists()

    prepare_code, prepared, _ = invoke(
        prepare_arguments(config),
        paths=paths,
        driver=driver,
    )
    assert prepare_code == EXIT_SUCCESS
    prepared_record = prepared["record"]
    assert isinstance(prepared_record, dict)
    assert prepared_record["state"] == "awaiting_approval"

    approve_code, approved, review = invoke(
        [
            "approve",
            "--config",
            str(config),
            "--request-id",
            "request-1",
        ],
        paths=paths,
        driver=driver,
        stdin=TtyInput("APPROVE\n"),
    )
    assert approve_code == EXIT_SUCCESS
    assert "Exact title" in review
    assert "asset://video" in review
    assert "douyin" in review
    assert prepared_record["request_digest"] in review
    grant_file = Path(str(approved["grant_file"]))
    assert grant_file.exists()
    grant_contents = grant_file.read_text(encoding="utf-8")
    assert grant_contents not in json.dumps(approved)
    assert grant_contents not in review

    execute_code, executed, _ = invoke(
        [
            "execute",
            "--config",
            str(config),
            "--request-id",
            "request-1",
            "--grant-file",
            str(grant_file),
        ],
        paths=paths,
        driver=driver,
    )
    assert execute_code == EXIT_SUCCESS
    executed_record = executed["record"]
    assert isinstance(executed_record, dict)
    assert executed_record["state"] == "submitted"
    assert not grant_file.exists()

    verify_code, verified, _ = invoke(
        [
            "verify",
            "--config",
            str(config),
            "--request-id",
            "request-1",
        ],
        paths=paths,
        driver=driver,
    )
    assert verify_code == EXIT_SUCCESS
    verified_record = verified["record"]
    assert isinstance(verified_record, dict)
    assert verified_record["state"] == "published"

    status_code, status, _ = invoke(
        ["status", "--request-id", "request-1"],
        paths=paths,
        driver=driver,
    )
    assert status_code == EXIT_SUCCESS
    assert status["record"] == verified_record
    operation_names = [call[0] for call in driver.calls]
    assert operation_names.count("publish_video") == 1
    assert operation_names.count("verify") == 1


def test_cancel_uses_core_transition_without_browser(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)
    invoke(prepare_arguments(config, "cancel-me"), paths=paths, driver=driver)
    calls_before = len(driver.calls)

    code, payload, _ = invoke(
        ["cancel", "--request-id", "cancel-me"],
        paths=paths,
        driver=driver,
    )

    assert code == EXIT_SUCCESS
    record = payload["record"]
    assert isinstance(record, dict)
    assert record["state"] == "cancelled"
    assert len(driver.calls) == calls_before


def test_prepare_dry_run_does_not_persist_state(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)

    code, payload, _ = invoke(
        [*prepare_arguments(config, "dry-run"), "--dry-run"],
        paths=paths,
        driver=driver,
    )
    assert code == EXIT_SUCCESS
    assert payload["dry_run"] is True
    assert payload["state_persisted"] is False

    status_code, status, _ = invoke(
        ["status", "--request-id", "dry-run"],
        paths=paths,
        driver=driver,
    )
    assert status_code == EXIT_STATE
    assert status["ok"] is False


def test_prepare_supports_image_and_text_arguments(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)
    image = [
        "prepare",
        "--config",
        str(config),
        "--request-id",
        "image-1",
        "--media-type",
        "image",
        "--asset-ref",
        "asset://image-set",
        "--image-ref",
        "asset://image-1",
        "--title",
        "Images",
        "--idempotency-key",
        "image-key",
    ]
    text = [
        "prepare",
        "--config",
        str(config),
        "--request-id",
        "text-1",
        "--media-type",
        "text",
        "--asset-ref",
        "asset://text",
        "--title",
        "Text",
        "--idempotency-key",
        "text-key",
    ]

    assert invoke(image, paths=paths, driver=driver)[0] == EXIT_SUCCESS
    assert invoke(text, paths=paths, driver=driver)[0] == EXIT_SUCCESS


def test_approval_requires_tty_and_has_no_yes_bypass(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)
    invoke(prepare_arguments(config), paths=paths, driver=driver)

    code, payload, review = invoke(
        [
            "approve",
            "--config",
            str(config),
            "--request-id",
            "request-1",
        ],
        paths=paths,
        driver=driver,
    )
    assert code == EXIT_CONFIRMATION
    assert payload["ok"] is False
    assert "request_digest" in review

    bypass_code, bypass, _ = invoke(
        [
            "execute",
            "--config",
            str(config),
            "--request-id",
            "request-1",
            "--grant-file",
            str(tmp_path / "missing"),
            "--yes",
        ],
        paths=paths,
        driver=driver,
    )
    assert bypass_code == EXIT_USAGE
    assert error_code(bypass) == "usage_error"


def test_declined_and_invalid_ttl_are_stable_errors(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)
    invoke(prepare_arguments(config), paths=paths, driver=driver)

    declined = invoke(
        [
            "approve",
            "--config",
            str(config),
            "--request-id",
            "request-1",
        ],
        paths=paths,
        driver=driver,
        stdin=TtyInput("NO\n"),
    )
    assert declined[0] == EXIT_CONFIRMATION

    invalid_ttl = invoke(
        [
            "approve",
            "--config",
            str(config),
            "--request-id",
            "request-1",
            "--ttl-seconds",
            "901",
        ],
        paths=paths,
        driver=driver,
        stdin=TtyInput("APPROVE\n"),
    )
    assert invalid_ttl[0] == EXIT_USAGE


def test_malformed_grant_is_not_consumed(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    driver = FakeBrowserDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=driver)
    invoke(prepare_arguments(config), paths=paths, driver=driver)
    grant = tmp_path / "malformed.grant"
    grant.write_text("not-a-grant", encoding="utf-8")

    code, payload, _ = invoke(
        [
            "execute",
            "--config",
            str(config),
            "--request-id",
            "request-1",
            "--grant-file",
            str(grant),
        ],
        paths=paths,
        driver=driver,
    )
    assert code == EXIT_APPROVAL
    assert payload["ok"] is False
    assert grant.exists()


def test_malformed_session_and_timeout_have_stable_codes(
    tmp_path: Path,
) -> None:
    class InvalidSessionDriver(FakeBrowserDriver):
        async def restore_session(
            self,
            session: bytes,
            profile: SelectorProfile,
            *,
            timeout_seconds: float,
        ) -> bool:
            del session, profile, timeout_seconds
            raise ValueError("session payload is malformed")

    class SlowDriver(FakeBrowserDriver):
        async def prepare(
            self,
            request: SocialPublishRequest,
            profile: SelectorProfile,
            *,
            timeout_seconds: float,
        ) -> DriverDiagnostics:
            del request, profile, timeout_seconds
            raise AdapterTimeoutError(
                "prepare timed out",
                code="operation_timeout",
                operation="prepare",
            )

    paths = paths_for(tmp_path)
    config = write_config(paths.default_config)
    invalid = InvalidSessionDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=invalid)
    malformed = invoke(
        prepare_arguments(config),
        paths=paths,
        driver=invalid,
    )
    assert malformed[0] == EXIT_BROWSER

    slow = SlowDriver()
    invoke(["login", "--config", str(config)], paths=paths, driver=slow)
    timeout = invoke(
        prepare_arguments(config, "timeout"),
        paths=paths,
        driver=slow,
    )
    assert timeout[0] == EXIT_TIMEOUT
    assert error_code(timeout[1]) == "operation_timeout"


def test_config_validation_and_missing_state(tmp_path: Path) -> None:
    paths = paths_for(tmp_path)
    driver = FakeBrowserDriver()
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    code, payload, _ = invoke(
        ["login", "--config", str(malformed)],
        paths=paths,
        driver=driver,
    )
    assert code == EXIT_CONFIG
    assert error_code(payload) == "config_invalid"

    missing_code, _, _ = invoke(
        ["status", "--request-id", "missing"],
        paths=paths,
        driver=driver,
    )
    assert missing_code == EXIT_STATE


def test_load_config_rejects_unknown_and_malformed_fields(
    tmp_path: Path,
) -> None:
    config_path = write_config(tmp_path / "config.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["unknown"] = True
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CliFailure, match="Unknown configuration"):
        load_config(config_path)

    payload.pop("unknown")
    payload["selector_profile"]["selectors"] = {"key": 1}
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CliFailure, match="strings"):
        load_config(config_path)
