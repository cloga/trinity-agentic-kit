from __future__ import annotations

from .contracts import FailureKind

_TRANSIENT = (
    "connection was reset",
    "connection reset",
    "could not connect",
    "failed to connect",
    "operation timed out",
    "timed out",
    "timeout",
    "temporary failure",
    "remote end hung up",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "the requested url returned error: 5",
)
_AUTH = (
    "authentication failed",
    "bad credentials",
    "invalid username or password",
    "permission denied (publickey)",
)
_NOT_FOUND = ("repository not found", "not found (http 404)")
_PERMISSION = (
    "permission to ",
    "write access to repository not granted",
    "requested url returned error: 403",
)
_CONFLICT = (
    "non-fast-forward",
    "fetch first",
    "stale info",
    "would clobber existing tag",
)


def classify_failure(message: str, *, timed_out: bool = False) -> FailureKind:
    if timed_out:
        return FailureKind.TRANSIENT
    text = str(message or "").lower()
    if any(item in text for item in _AUTH):
        return FailureKind.AUTHENTICATION
    if any(item in text for item in _NOT_FOUND):
        return FailureKind.REPOSITORY_NOT_FOUND
    if any(item in text for item in _PERMISSION):
        return FailureKind.PERMISSION
    if any(item in text for item in _CONFLICT):
        return FailureKind.REF_CONFLICT
    if any(item in text for item in _TRANSIENT):
        return FailureKind.TRANSIENT
    return FailureKind.PERMANENT
