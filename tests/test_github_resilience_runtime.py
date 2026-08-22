# pyright: reportUnknownParameterType=false, reportMissingParameterType=false
# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportPrivateUsage=false
# pyright: reportArgumentType=false

from __future__ import annotations

import json
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from trinity_agentic_kit.github_resilience import cli
from trinity_agentic_kit.github_resilience.contracts import (
    AttemptRecord,
    FailureKind,
    RetryPolicy,
    TransportResult,
)
from trinity_agentic_kit.github_resilience.errors import GitHubTransportError
from trinity_agentic_kit.github_resilience.runtime import (
    SubprocessCommandRunner,
    UrllibGitHubAccessClient,
)


def test_retry_policy_validation_and_bounded_jitter() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="delays"):
        RetryPolicy(base_delay_seconds=-1)
    with pytest.raises(ValueError, match="jitter"):
        RetryPolicy(jitter_ratio=2)
    with pytest.raises(ValueError, match="timeouts"):
        RetryPolicy(command_timeout_seconds=0)

    policy = RetryPolicy(
        base_delay_seconds=2,
        max_delay_seconds=3,
        jitter_ratio=0.5,
    )
    assert policy.delay_for(1, random_unit=0) == 1
    assert policy.delay_for(5, random_unit=1) == 4.5


def test_subprocess_runner_success_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        ),
    )
    runner = SubprocessCommandRunner()
    result = runner.run(
        ["git", "status"],
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
    )
    assert result.returncode == 0
    assert result.stdout == "ok"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["git", "status"],
            timeout=1,
            output="partial",
            stderr="late",
        )

    monkeypatch.setattr(subprocess, "run", timeout)
    timed_out = runner.run(
        ["git", "status"],
        cwd=tmp_path,
        env={},
        timeout_seconds=1,
    )
    assert timed_out.timed_out
    assert timed_out.returncode == 124


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_urllib_access_client_success_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            FakeResponse({"login": "cloga"}),
            FakeResponse(
                {
                    "full_name": "cloga/repo",
                    "permissions": {"push": True},
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: next(responses),
    )
    access = UrllibGitHubAccessClient().verify(
        repository="cloga/repo",
        token="token",
    )
    assert access.login == "cloga"
    assert access.can_push

    def not_found(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            404,
            "not found",
            {},
            None,
        )

    monkeypatch.setattr("urllib.request.urlopen", not_found)
    with pytest.raises(GitHubTransportError) as missing:
        UrllibGitHubAccessClient().verify(
            repository="cloga/missing",
            token="token",
        )
    assert missing.value.kind is FailureKind.REPOSITORY_NOT_FOUND

    def unavailable(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    with pytest.raises(GitHubTransportError) as offline:
        UrllibGitHubAccessClient().verify(
            repository="cloga/repo",
            token="token",
        )
    assert offline.value.kind is FailureKind.TRANSIENT

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: FakeResponse([]),
    )
    with pytest.raises(GitHubTransportError, match="invalid object"):
        UrllibGitHubAccessClient().verify(
            repository="cloga/repo",
            token="token",
        )


class FakeTransport:
    result = TransportResult(
        succeeded=True,
        attempts=(AttemptRecord(1, None, 0, "success"),),
        stdout="pushed",
    )
    error: GitHubTransportError | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def execute(self, **kwargs) -> TransportResult:
        assert kwargs["expected_account"] == "cloga"
        if self.error is not None:
            raise self.error
        return self.result


def test_cli_success_dotenv_and_structured_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# comment\nexport GITHUB_TOKEN='dotenv-token'\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli, "ResilientGitTransport", FakeTransport)
    monkeypatch.setattr(
        cli,
        "_git_state_root",
        lambda cwd: tmp_path / "git-state",
    )
    arguments = [
        "--repo",
        "cloga/repo",
        "--expected-account",
        "cloga",
        "--cwd",
        str(tmp_path),
        "--dotenv",
        str(dotenv),
        "--",
        "push",
        "origin",
        "HEAD",
    ]

    assert cli.main(arguments) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli._load_dotenv_value(tmp_path / "missing", "GITHUB_TOKEN") == ""
    assert cli._load_dotenv_value(dotenv, "MISSING") == ""

    FakeTransport.error = GitHubTransportError(
        "forbidden",
        kind=FailureKind.PERMISSION,
        exit_code=13,
    )
    try:
        assert cli.main(arguments) == 13
    finally:
        FakeTransport.error = None
    error = json.loads(capsys.readouterr().err)
    assert error["failure_kind"] == "permission"


def test_git_state_root_supports_worktrees_and_rejects_non_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "trinity_agentic_kit.github_resilience.cli.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=str(tmp_path / "common.git" / "worktrees" / "one"),
            stderr="",
        ),
    )
    assert cli._git_state_root(tmp_path).is_absolute()

    monkeypatch.setattr(
        "trinity_agentic_kit.github_resilience.cli.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=128,
            stdout="",
            stderr="not a repository",
        ),
    )
    with pytest.raises(GitHubTransportError, match="not a Git"):
        cli._git_state_root(tmp_path)
