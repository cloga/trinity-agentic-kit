from __future__ import annotations

import base64
import os
import random
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .classify import classify_failure
from .contracts import (
    AttemptRecord,
    FailureKind,
    RetryPolicy,
    TransportResult,
)
from .errors import GitHubTransportError, OperationLockedError
from .protocols import CommandRunner, GitHubAccessClient
from .runtime import atomic_write_json, unix_time

_ALLOWED_OPERATIONS = {"fetch", "push", "ls-remote"}


def _exit_code(kind: FailureKind) -> int:
    return {
        FailureKind.AUTHENTICATION: 11,
        FailureKind.REPOSITORY_NOT_FOUND: 12,
        FailureKind.PERMISSION: 13,
        FailureKind.TRANSIENT: 20,
        FailureKind.REF_CONFLICT: 21,
        FailureKind.PERMANENT: 22,
    }[kind]


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    result = str(text or "")
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]")
    return result[-4000:]


@contextmanager
def operation_lock(path: Path, *, stale_seconds: float) -> Generator[None, None, None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()} {unix_time()}".encode("ascii"))
            os.close(descriptor)
            break
        except FileExistsError:
            try:
                stale = unix_time() - path.stat().st_mtime > stale_seconds
            except FileNotFoundError:
                continue
            if stale:
                path.unlink(missing_ok=True)
                continue
            raise OperationLockedError(
                f"Git operation lock is active: {path}",
                kind=FailureKind.REF_CONFLICT,
                exit_code=21,
            ) from None
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


class ResilientGitTransport:
    def __init__(
        self,
        *,
        runner: CommandRunner,
        access_client: GitHubAccessClient,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_unit: Callable[[], float] = random.random,
    ) -> None:
        self._runner = runner
        self._access_client = access_client
        self._policy = policy or RetryPolicy()
        self._sleep = sleep
        self._random_unit = random_unit

    def execute(
        self,
        *,
        git_args: list[str],
        cwd: Path,
        repository: str,
        expected_account: str,
        token: str,
        journal_path: Path,
        lock_path: Path,
    ) -> TransportResult:
        if not git_args or git_args[0] not in _ALLOWED_OPERATIONS:
            raise GitHubTransportError(
                f"Unsupported Git operation: {git_args[:1]}",
                exit_code=10,
            )
        if not token:
            raise GitHubTransportError(
                "GitHub token is required",
                kind=FailureKind.AUTHENTICATION,
                exit_code=11,
            )
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode("ascii")
        secret_values = (token, basic)
        safe_git_args = [_redact(argument, secret_values) for argument in git_args]
        attempts: list[AttemptRecord] = []
        preflight_complete = False
        with operation_lock(
            lock_path,
            stale_seconds=self._policy.stale_lock_seconds,
        ):
            for attempt in range(1, self._policy.max_attempts + 1):
                try:
                    if not preflight_complete:
                        access = self._access_client.verify(
                            repository=repository,
                            token=token,
                        )
                        if access.login != expected_account:
                            raise GitHubTransportError(
                                f"GitHub token belongs to {access.login!r}, "
                                f"expected {expected_account!r}",
                                kind=FailureKind.AUTHENTICATION,
                                exit_code=11,
                            )
                        if git_args[0] == "push" and not access.can_push:
                            raise GitHubTransportError(
                                f"{access.login} lacks push permission for "
                                f"{repository}",
                                kind=FailureKind.PERMISSION,
                                exit_code=13,
                            )
                        preflight_complete = True
                except GitHubTransportError as exc:
                    if (
                        exc.kind is FailureKind.TRANSIENT
                        and attempt < self._policy.max_attempts
                    ):
                        delay = self._policy.delay_for(
                            attempt,
                            random_unit=self._random_unit(),
                        )
                        attempts.append(
                            AttemptRecord(
                                attempt=attempt,
                                failure_kind=exc.kind,
                                returncode=exc.exit_code,
                                message=str(exc),
                                delay_seconds=delay,
                            )
                        )
                        self._write_journal(
                            journal_path,
                            git_args=safe_git_args,
                            repository=repository,
                            status="retrying",
                            attempts=attempts,
                        )
                        self._sleep(delay)
                        continue
                    raise
                environment = self._git_environment(basic)
                outcome = self._runner.run(
                    ["git", *git_args],
                    cwd=cwd,
                    env=environment,
                    timeout_seconds=self._policy.command_timeout_seconds,
                )
                if outcome.returncode == 0:
                    attempts.append(
                        AttemptRecord(
                            attempt=attempt,
                            failure_kind=None,
                            returncode=0,
                            message="success",
                        )
                    )
                    result = TransportResult(
                        succeeded=True,
                        attempts=tuple(attempts),
                        stdout=_redact(outcome.stdout, secret_values),
                    )
                    self._write_journal(
                        journal_path,
                        git_args=safe_git_args,
                        repository=repository,
                        status="succeeded",
                        attempts=attempts,
                    )
                    return result
                message = _redact(
                    outcome.stderr or outcome.stdout,
                    secret_values,
                )
                kind = classify_failure(message, timed_out=outcome.timed_out)
                delay = 0.0
                if (
                    kind is FailureKind.TRANSIENT
                    and attempt < self._policy.max_attempts
                ):
                    delay = self._policy.delay_for(
                        attempt,
                        random_unit=self._random_unit(),
                    )
                attempts.append(
                    AttemptRecord(
                        attempt=attempt,
                        failure_kind=kind,
                        returncode=outcome.returncode,
                        message=message,
                        delay_seconds=delay,
                    )
                )
                status = "retrying" if delay > 0 else "failed"
                self._write_journal(
                    journal_path,
                    git_args=safe_git_args,
                    repository=repository,
                    status=status,
                    attempts=attempts,
                )
                if delay > 0:
                    self._sleep(delay)
                    continue
                return TransportResult(
                    succeeded=False,
                    attempts=tuple(attempts),
                    failure_kind=kind,
                    exit_code=_exit_code(kind),
                )
        raise AssertionError("retry loop exhausted unexpectedly")

    @staticmethod
    def _git_environment(basic: str) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "3",
                "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": "",
                "GIT_CONFIG_KEY_1": "http.version",
                "GIT_CONFIG_VALUE_1": "HTTP/1.1",
                "GIT_CONFIG_KEY_2": "http.extraHeader",
                "GIT_CONFIG_VALUE_2": f"Authorization: Basic {basic}",
            }
        )
        return environment

    @staticmethod
    def _write_journal(
        path: Path,
        *,
        git_args: list[str],
        repository: str,
        status: str,
        attempts: list[AttemptRecord],
    ) -> None:
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "repository": repository,
                "operation": git_args[0],
                "arguments": git_args[1:],
                "status": status,
                "attempts": [
                    {
                        **asdict(item),
                        "failure_kind": (
                            item.failure_kind.value
                            if item.failure_kind is not None
                            else None
                        ),
                    }
                    for item in attempts
                ],
            },
        )
