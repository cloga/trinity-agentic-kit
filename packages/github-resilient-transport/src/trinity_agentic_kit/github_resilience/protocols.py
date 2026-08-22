from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .contracts import CommandOutcome, RepositoryAccess


class CommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> CommandOutcome: ...


class GitHubAccessClient(Protocol):
    def verify(
        self,
        *,
        repository: str,
        token: str,
    ) -> RepositoryAccess: ...
