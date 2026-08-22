from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .contracts import RetryPolicy
from .errors import GitHubTransportError
from .runtime import SubprocessCommandRunner, UrllibGitHubAccessClient
from .transport import ResilientGitTransport

PACKAGE_VERSION = "0.1.0"


def _load_dotenv_value(path: Path, name: str) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.removeprefix("export ").strip() == name:
            return value.strip().strip("\"'")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run resilient GitHub Git operations")
    parser.add_argument("--version", action="version", version=PACKAGE_VERSION)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--expected-account", required=True)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--dotenv", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("git_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    git_args = list(args.git_args)
    if git_args[:1] == ["--"]:
        git_args = git_args[1:]
    token = str(os.getenv(args.token_env) or "")
    if not token and args.dotenv is not None:
        token = _load_dotenv_value(args.dotenv, args.token_env)
    state_root = args.cwd / ".git" / "agentic-network"
    journal = args.journal or state_root / "last-operation.json"
    lock = args.lock or state_root / "operation.lock"
    transport = ResilientGitTransport(
        runner=SubprocessCommandRunner(),
        access_client=UrllibGitHubAccessClient(),
        policy=RetryPolicy(max_attempts=args.max_attempts),
    )
    try:
        result = transport.execute(
            git_args=git_args,
            cwd=args.cwd.resolve(),
            repository=args.repo,
            expected_account=args.expected_account,
            token=token,
            journal_path=journal.resolve(),
            lock_path=lock.resolve(),
        )
    except GitHubTransportError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "failure_kind": exc.kind.value,
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        return exc.exit_code
    print(
        json.dumps(
            {
                "ok": result.succeeded,
                "attempts": len(result.attempts),
                "stdout": result.stdout,
                "failure_kind": (
                    result.failure_kind.value
                    if result.failure_kind is not None
                    else None
                ),
            }
        )
    )
    return result.exit_code
