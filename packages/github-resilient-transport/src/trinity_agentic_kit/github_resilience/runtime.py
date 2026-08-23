from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from .classify import classify_failure
from .contracts import (
    CommandOutcome,
    FailureKind,
    RepositoryAccess,
)
from .errors import GitHubTransportError


class SubprocessCommandRunner:
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> CommandOutcome:
        try:
            completed = subprocess.run(
                list(command),
                cwd=cwd,
                env=dict(env),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandOutcome(
                returncode=124,
                stdout=str(exc.stdout or ""),
                stderr=str(exc.stderr or ""),
                timed_out=True,
            )
        return CommandOutcome(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class UrllibGitHubAccessClient:
    def __init__(
        self,
        *,
        api_base: str = "https://api.github.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def _get(self, path: str, token: str) -> dict[str, object]:
        request = urllib.request.Request(
            f"{self._api_base}{path}",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "trinity-agentic-kit-github-resilience",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                payload: object = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            kind = {
                401: FailureKind.AUTHENTICATION,
                403: FailureKind.PERMISSION,
                404: FailureKind.REPOSITORY_NOT_FOUND,
            }.get(exc.code, classify_failure(f"http {exc.code}"))
            exit_code = {
                FailureKind.AUTHENTICATION: 11,
                FailureKind.REPOSITORY_NOT_FOUND: 12,
                FailureKind.PERMISSION: 13,
                FailureKind.TRANSIENT: 20,
            }.get(kind, 22)
            raise GitHubTransportError(
                f"GitHub API request failed with HTTP {exc.code}",
                kind=kind,
                exit_code=exit_code,
            ) from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            raise GitHubTransportError(
                "GitHub API connection failed",
                kind=FailureKind.TRANSIENT,
                exit_code=20,
            ) from exc
        if not isinstance(payload, dict):
            raise GitHubTransportError("GitHub API returned an invalid object")
        return cast(dict[str, object], payload)

    def verify(self, *, repository: str, token: str) -> RepositoryAccess:
        user = self._get("/user", token)
        repo = self._get(f"/repos/{repository}", token)
        permissions = repo.get("permissions")
        permission_map = (
            cast(dict[str, object], permissions)
            if isinstance(permissions, dict)
            else {}
        )
        can_push = bool(permission_map.get("push"))
        return RepositoryAccess(
            login=str(user.get("login") or ""),
            repository=str(repo.get("full_name") or repository),
            can_push=can_push,
        )


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def unix_time() -> float:
    return time.time()
