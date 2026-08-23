from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from trinity_agentic_kit.github_resilience import (
    CommandOutcome,
    FailureKind,
    GitHubTransportError,
    OperationLockedError,
    RepositoryAccess,
    ResilientGitTransport,
    RetryPolicy,
    classify_failure,
    operation_lock,
)


class FakeRunner:
    def __init__(self, outcomes: list[CommandOutcome]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[list[str], Mapping[str, str]]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> CommandOutcome:
        del cwd, timeout_seconds
        self.calls.append((list(command), env))
        return self.outcomes.pop(0)


class FakeAccess:
    def __init__(
        self,
        *,
        login: str = "cloga",
        can_push: bool = True,
        transient_failures: int = 0,
    ) -> None:
        self.login = login
        self.can_push = can_push
        self.transient_failures = transient_failures
        self.calls = 0

    def verify(self, *, repository: str, token: str) -> RepositoryAccess:
        del token
        self.calls += 1
        if self.calls <= self.transient_failures:
            raise GitHubTransportError(
                "GitHub API connection failed",
                kind=FailureKind.TRANSIENT,
                exit_code=20,
            )
        return RepositoryAccess(self.login, repository, self.can_push)


def transport(
    runner: FakeRunner,
    access: FakeAccess,
    *,
    sleeps: list[float],
    attempts: int = 3,
) -> ResilientGitTransport:
    return ResilientGitTransport(
        runner=runner,
        access_client=access,
        policy=RetryPolicy(
            max_attempts=attempts,
            base_delay_seconds=1,
            jitter_ratio=0,
        ),
        sleep=sleeps.append,
        random_unit=lambda: 0.5,
    )


def execute(
    instance: ResilientGitTransport,
    tmp_path: Path,
    *,
    token: str = "secret-token",
):
    return instance.execute(
        git_args=["push", "origin", "HEAD"],
        cwd=tmp_path,
        repository="cloga/repo",
        expected_account="cloga",
        token=token,
        journal_path=tmp_path / "journal.json",
        lock_path=tmp_path / "operation.lock",
    )


def test_transient_reset_retries_then_succeeds_without_secret_in_command(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        [
            CommandOutcome(128, stderr="Recv failure: Connection was reset"),
            CommandOutcome(0, stdout="pushed"),
        ]
    )
    sleeps: list[float] = []

    result = execute(transport(runner, FakeAccess(), sleeps=sleeps), tmp_path)

    assert result.succeeded
    assert sleeps == [1]
    assert runner.calls[0][0] == ["git", "push", "origin", "HEAD"]
    assert "secret-token" not in " ".join(runner.calls[0][0])
    assert runner.calls[0][1]["GIT_CONFIG_VALUE_1"] == "HTTP/1.1"
    journal = (tmp_path / "journal.json").read_text(encoding="utf-8")
    assert "secret-token" not in journal
    assert json.loads(journal)["status"] == "succeeded"


def test_auth_and_permission_failures_do_not_retry(tmp_path: Path) -> None:
    runner = FakeRunner([CommandOutcome(0)])
    sleeps: list[float] = []
    with pytest.raises(GitHubTransportError, match="expected"):
        execute(
            transport(
                runner,
                FakeAccess(login="wrong-account"),
                sleeps=sleeps,
            ),
            tmp_path,
        )
    assert runner.calls == []
    assert sleeps == []

    with pytest.raises(GitHubTransportError, match="lacks push"):
        execute(
            transport(
                FakeRunner([CommandOutcome(0)]),
                FakeAccess(can_push=False),
                sleeps=[],
            ),
            tmp_path,
        )


def test_transient_preflight_is_bounded_and_resumable(tmp_path: Path) -> None:
    runner = FakeRunner([CommandOutcome(0, stdout="ok")])
    sleeps: list[float] = []
    result = execute(
        transport(
            runner,
            FakeAccess(transient_failures=2),
            sleeps=sleeps,
            attempts=3,
        ),
        tmp_path,
    )

    assert result.succeeded
    assert sleeps == [1, 2]
    assert len(result.attempts) == 3


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Failed to connect to github.com", FailureKind.TRANSIENT),
        ("remote: Repository not found.", FailureKind.REPOSITORY_NOT_FOUND),
        ("Authentication failed", FailureKind.AUTHENTICATION),
        ("non-fast-forward", FailureKind.REF_CONFLICT),
        ("write access to repository not granted", FailureKind.PERMISSION),
        ("unknown fatal error", FailureKind.PERMANENT),
    ],
)
def test_failure_classification(message: str, expected: FailureKind) -> None:
    assert classify_failure(message) is expected


def test_non_transient_git_failure_returns_stable_exit_code(tmp_path: Path) -> None:
    result = execute(
        transport(
            FakeRunner([CommandOutcome(128, stderr="non-fast-forward")]),
            FakeAccess(),
            sleeps=[],
        ),
        tmp_path,
    )

    assert not result.succeeded
    assert result.failure_kind is FailureKind.REF_CONFLICT
    assert result.exit_code == 21


def test_operation_lock_rejects_concurrent_owner_and_recovers_stale(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "operation.lock"
    with (
        operation_lock(lock, stale_seconds=60),
        pytest.raises(OperationLockedError),
        operation_lock(lock, stale_seconds=60),
    ):
        pass
    lock.write_text("stale", encoding="utf-8")
    lock.touch()
    with operation_lock(lock, stale_seconds=0.000001):
        assert lock.exists()
    assert not lock.exists()


def test_unsupported_operation_and_missing_token_fail_closed(
    tmp_path: Path,
) -> None:
    instance = transport(FakeRunner([]), FakeAccess(), sleeps=[])
    with pytest.raises(GitHubTransportError, match="Unsupported"):
        instance.execute(
            git_args=["commit"],
            cwd=tmp_path,
            repository="cloga/repo",
            expected_account="cloga",
            token="token",
            journal_path=tmp_path / "journal.json",
            lock_path=tmp_path / "lock",
        )
    with pytest.raises(GitHubTransportError, match="token"):
        execute(instance, tmp_path, token="")
