from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = PROJECT_ROOT / ".github" / "branch-policy.json"


class BranchNameError(RuntimeError):
    """Raised when a branch name leaks a prohibited identity."""


def validate_branch_name(branch: str, policy_path: Path = DEFAULT_POLICY) -> str:
    normalized = str(branch or "").strip()
    if not normalized:
        raise BranchNameError("Branch name is required")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    lowered = normalized.lower()
    forbidden = [
        str(item).lower()
        for item in policy.get("forbidden_fragments", [])
        if str(item).strip()
    ]
    leaked = [fragment for fragment in forbidden if fragment in lowered]
    if leaked:
        raise BranchNameError(
            f"Branch name contains prohibited identity fragment(s): {', '.join(leaked)}"
        )
    if normalized in {"main", "master"}:
        return normalized
    expected_account = str(policy.get("expected_account") or "").strip()
    if not expected_account:
        raise BranchNameError("Branch policy expected_account is required")
    required_prefix = f"{expected_account}/"
    if not normalized.startswith(required_prefix):
        raise BranchNameError(
            f"Branch name must match the active GitHub account prefix: "
            f"{required_prefix}"
        )
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate neutral branch naming")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    branch = validate_branch_name(args.branch, args.policy.resolve())
    print(f"Branch name valid: {branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
