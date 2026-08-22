"""Secret-safe bounded retries for GitHub Git operations."""

from .classify import classify_failure
from .contracts import (
    AttemptRecord,
    CommandOutcome,
    FailureKind,
    RepositoryAccess,
    RetryPolicy,
    TransportResult,
)
from .errors import GitHubTransportError, OperationLockedError
from .protocols import CommandRunner, GitHubAccessClient
from .runtime import SubprocessCommandRunner, UrllibGitHubAccessClient
from .transport import ResilientGitTransport, operation_lock

__all__ = [
    "AttemptRecord",
    "CommandOutcome",
    "CommandRunner",
    "FailureKind",
    "GitHubAccessClient",
    "GitHubTransportError",
    "OperationLockedError",
    "RepositoryAccess",
    "ResilientGitTransport",
    "RetryPolicy",
    "SubprocessCommandRunner",
    "TransportResult",
    "UrllibGitHubAccessClient",
    "classify_failure",
    "operation_lock",
]
