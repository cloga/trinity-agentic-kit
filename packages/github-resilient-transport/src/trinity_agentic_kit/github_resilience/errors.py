from __future__ import annotations

from .contracts import FailureKind


class GitHubTransportError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: FailureKind = FailureKind.PERMANENT,
        exit_code: int = 22,
    ) -> None:
        self.kind = kind
        self.exit_code = exit_code
        super().__init__(message)


class OperationLockedError(GitHubTransportError):
    pass
