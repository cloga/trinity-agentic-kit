from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn, TextIO

from trinity_agentic_kit.douyin_adapter import (
    AdapterConfigurationError,
    AdapterTimeoutError,
    BrowserOperationError,
    DouyinAdapterError,
    SessionRequiredError,
)
from trinity_agentic_kit.social_publish import (
    ApprovalGrantError,
    HmacApprovalAuthority,
    InMemoryAuditSink,
    PublishRecord,
    PublishState,
    PublishStateStore,
    SocialPublishCoordinator,
    SocialPublishError,
    SocialPublishRequest,
    request_digest,
)

from .config import CliConfig, load_config
from .models import (
    DOUYIN_CLI_VERSION,
    EXIT_APPROVAL,
    EXIT_BROWSER,
    EXIT_CONFIG,
    EXIT_CONFIRMATION,
    EXIT_INTERNAL,
    EXIT_SESSION,
    EXIT_STATE,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    EXIT_USAGE,
    CliFailure,
    CliPaths,
)
from .runtime import (
    CliRuntime,
    DriverFactory,
    build_runtime,
    default_driver_factory,
    load_authority,
    open_store,
    read_secret_file,
    write_secret_file,
)


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CliFailure("usage_error", message, EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    parser = StructuredArgumentParser(prog="douyin-publish")
    parser.add_argument("--version", action="version", version=DOUYIN_CLI_VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    login = commands.add_parser("login")
    _add_config(login)

    prepare = commands.add_parser("prepare")
    _add_config(prepare)
    prepare.add_argument("--request-id", required=True)
    prepare.add_argument(
        "--media-type", choices=("video", "image", "text"), required=True
    )
    prepare.add_argument("--asset-ref", required=True)
    prepare.add_argument("--image-ref", action="append", default=[])
    prepare.add_argument("--title", required=True)
    prepare.add_argument("--description", default="")
    prepare.add_argument("--idempotency-key", required=True)
    prepare.add_argument("--dry-run", action="store_true")

    approve = commands.add_parser("approve")
    _add_config(approve)
    approve.add_argument("--request-id", required=True)
    approve.add_argument("--ttl-seconds", type=_approval_ttl, default=300)
    approve.add_argument("--grant-file", type=Path)

    execute = commands.add_parser("execute")
    _add_config(execute)
    execute.add_argument("--request-id", required=True)
    execute.add_argument("--grant-file", type=Path, required=True)

    verify = commands.add_parser("verify")
    _add_config(verify)
    verify.add_argument("--request-id", required=True)

    status = commands.add_parser("status")
    status.add_argument("--request-id", required=True)

    cancel = commands.add_parser("cancel")
    cancel.add_argument("--request-id", required=True)
    return parser


def run(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    paths: CliPaths | None = None,
    driver_factory: DriverFactory = default_driver_factory,
) -> int:
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    try:
        cli_paths = paths or CliPaths.from_environment()
        arguments = build_parser().parse_args(argv)
        payload = asyncio.run(
            _dispatch(
                arguments,
                input_stream,
                error_stream,
                cli_paths,
                driver_factory,
            )
        )
    except CliFailure as exc:
        _emit(
            output_stream,
            {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": dict(exc.details or {}),
                },
            },
        )
        return exc.exit_code
    except AdapterConfigurationError as exc:
        return _adapter_failure(output_stream, exc, EXIT_CONFIG)
    except SessionRequiredError as exc:
        return _adapter_failure(output_stream, exc, EXIT_SESSION)
    except AdapterTimeoutError as exc:
        return _adapter_failure(output_stream, exc, EXIT_TIMEOUT)
    except BrowserOperationError as exc:
        return _adapter_failure(output_stream, exc, EXIT_BROWSER)
    except ApprovalGrantError as exc:
        _emit_error(output_stream, "approval_invalid", str(exc))
        return EXIT_APPROVAL
    except SocialPublishError as exc:
        _emit_error(output_stream, "publish_state_error", str(exc))
        return EXIT_STATE
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        _emit_error(output_stream, "internal_error", str(exc))
        return EXIT_INTERNAL
    _emit(output_stream, {"ok": True, **payload})
    return EXIT_SUCCESS


def main() -> int:
    return run()


async def _dispatch(
    arguments: argparse.Namespace,
    stdin: TextIO,
    stderr: TextIO,
    paths: CliPaths,
    driver_factory: DriverFactory,
) -> dict[str, object]:
    command = str(arguments.command)
    if command == "status":
        record = _record(open_store(paths), str(arguments.request_id))
        return {"command": command, "record": _record_payload(record)}
    if command == "cancel":
        store = open_store(paths)
        coordinator = SocialPublishCoordinator(
            adapters={},
            store=store,
            approval_authority=HmacApprovalAuthority(
                b"\x00" * 32,
                issuer="cancel-only",
            ),
            audit_sink=InMemoryAuditSink(),
        )
        record = coordinator.cancel(str(arguments.request_id))
        return {"command": command, "record": _record_payload(record)}

    config = load_config(_config_path(arguments, paths))
    if command == "approve":
        return _approve(arguments, stdin, stderr, paths, config)

    runtime = build_runtime(
        config,
        paths,
        driver_factory=driver_factory,
    )
    try:
        if command == "login":
            await runtime.adapter.login_interactively()
            return {
                "command": command,
                "session": "stored",
                "data_dir": str(paths.data_dir),
            }
        if command == "prepare":
            request = _request_from_arguments(arguments)
            if bool(arguments.dry_run):
                await runtime.adapter.prepare(request)
                return {
                    "command": command,
                    "dry_run": True,
                    "request_digest": _request_digest(request),
                    "profile": {
                        "name": config.selector_profile.name,
                        "version": config.selector_profile.version,
                    },
                    "state_persisted": False,
                }
            record = await runtime.coordinator.prepare(request)
            return {"command": command, "record": _record_payload(record)}
        if command == "execute":
            return await _execute(arguments, runtime)
        if command == "verify":
            record = _record(runtime.store, str(arguments.request_id))
            verified = await runtime.coordinator.verify(record.request.request_id)
            return {"command": command, "record": _record_payload(verified)}
        raise CliFailure("usage_error", f"Unknown command: {command}", EXIT_USAGE)
    finally:
        await runtime.close()


def _approve(
    arguments: argparse.Namespace,
    stdin: TextIO,
    stderr: TextIO,
    paths: CliPaths,
    config: CliConfig,
) -> dict[str, object]:
    store = open_store(paths)
    record = _record(store, str(arguments.request_id))
    if record.state is not PublishState.AWAITING_APPROVAL:
        raise CliFailure(
            "request_not_awaiting_approval",
            f"Request state is {record.state.value}",
            EXIT_STATE,
        )
    _emit(
        stderr,
        {
            "approval_confirmation": {
                "request_digest": record.request_digest,
                "title": record.request.title,
                "asset_ref": record.request.asset_ref,
                "platform": record.request.platform,
            }
        },
    )
    if not stdin.isatty():
        raise CliFailure(
            "tty_required",
            "Approval issuance requires an interactive terminal",
            EXIT_CONFIRMATION,
        )
    stderr.write("Type APPROVE to issue a short-lived one-time grant: ")
    stderr.flush()
    if stdin.readline().strip() != "APPROVE":
        raise CliFailure(
            "approval_declined",
            "Approval was not confirmed",
            EXIT_CONFIRMATION,
        )
    authority = load_authority(paths, use_keyring=config.use_keyring)
    token = authority.issue(
        record.request,
        grant_id=str(uuid.uuid4()),
        ttl_seconds=int(arguments.ttl_seconds),
    )
    grant_path = (
        (
            Path(arguments.grant_file)
            if arguments.grant_file is not None
            else paths.grants_dir / f"{record.request.request_id}.grant"
        )
        .expanduser()
        .resolve()
    )
    write_secret_file(grant_path, token)
    return {
        "command": "approve",
        "request_id": record.request.request_id,
        "grant_file": str(grant_path),
        "ttl_seconds": int(arguments.ttl_seconds),
    }


async def _execute(
    arguments: argparse.Namespace,
    runtime: CliRuntime,
) -> dict[str, object]:
    grant_path = Path(arguments.grant_file).expanduser().resolve()
    token = read_secret_file(grant_path)
    record = _record(runtime.store, str(arguments.request_id))
    grant = runtime.authority.verify(token, record.request)
    try:
        executed = await runtime.coordinator.execute(
            record.request.request_id,
            token,
        )
    finally:
        latest = runtime.store.get(record.request.request_id)
        if latest is not None and grant.grant_id in latest.consumed_approval_grant_ids:
            grant_path.unlink(missing_ok=True)
    return {"command": "execute", "record": _record_payload(executed)}


def _request_from_arguments(
    arguments: argparse.Namespace,
) -> SocialPublishRequest:
    image_refs = [str(item) for item in arguments.image_ref]
    metadata: dict[str, object] = {}
    if str(arguments.media_type) == "image":
        metadata["image_refs"] = image_refs
    return SocialPublishRequest(
        request_id=str(arguments.request_id),
        platform="douyin",
        media_type=str(arguments.media_type),
        asset_ref=str(arguments.asset_ref),
        title=str(arguments.title),
        description=str(arguments.description),
        idempotency_key=str(arguments.idempotency_key),
        metadata=metadata,
    )


def _record(store: PublishStateStore, request_id: str) -> PublishRecord:
    record = store.get(request_id)
    if record is None:
        raise CliFailure(
            "request_not_found",
            f"Publish request not found: {request_id}",
            EXIT_STATE,
        )
    return record


def _record_payload(record: PublishRecord) -> dict[str, object]:
    return {
        "request_id": record.request.request_id,
        "state": record.state.value,
        "request_digest": record.request_digest,
        "title": record.request.title,
        "asset_ref": record.request.asset_ref,
        "platform": record.request.platform,
        "media_type": record.request.media_type,
        "platform_reference": record.platform_reference,
        "published_url": record.published_url,
        "error": {
            "code": record.last_error_code,
            "message": record.last_error_message,
        },
        "revision": record.revision,
    }


def _request_digest(request: SocialPublishRequest) -> str:
    return request_digest(request)


def _config_path(arguments: argparse.Namespace, paths: CliPaths) -> Path:
    value = arguments.config
    return (
        Path(value).expanduser().resolve()
        if value is not None
        else paths.default_config
    )


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)


def _approval_ttl(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("approval TTL must be an integer") from exc
    if parsed <= 0 or parsed > 900:
        raise argparse.ArgumentTypeError(
            "approval TTL must be between 1 and 900 seconds"
        )
    return parsed


def _adapter_failure(
    stream: TextIO,
    error: DouyinAdapterError,
    exit_code: int,
) -> int:
    details = asdict(error.details)
    _emit(
        stream,
        {
            "ok": False,
            "error": {
                "code": error.details.code,
                "message": str(error),
                "details": details,
            },
        },
    )
    return exit_code


def _emit_error(stream: TextIO, code: str, message: str) -> None:
    _emit(
        stream,
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": {},
            },
        },
    )


def _emit(stream: TextIO, payload: object) -> None:
    stream.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    stream.flush()
