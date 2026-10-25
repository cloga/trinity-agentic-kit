# Agent guide

## Repository map

- `packages/` contains the reusable Python libraries; `skills/` contains their
  agent-facing workflows and contracts.
- `components/cross_repo_routing/ownership.json` is the canonical public/private
  ownership map. `scripts/plan_cross_repo_change.py` reports the required work
  before changing a shared component.
- `tests/` contains deterministic, offline tests. Package-specific `pyproject.toml`
  files define development dependencies and build configuration.

## Development loop

Install the same editable packages used by CI:

```bash
python -m pip install -r requirements-dev.in
```

For a focused change, run the relevant test file first, for example:

```bash
python -m pytest tests/test_value_audit_core.py
ruff check packages/value-audit-core tests/test_value_audit_core.py
ruff format --check packages/value-audit-core tests/test_value_audit_core.py
```

Choose the test file matching the changed area (`test_social_publish_core.py`,
`test_github_resilience.py`, `test_value_audit_tushare.py`,
`test_value_explainer.py`, or `test_douyin_adapter.py` are other entry points).
Before handoff, run the broader checks in [CONTRIBUTING.md](CONTRIBUTING.md).
Run commands from the repository root. The pytest `pythonpath` and Pyright
`extraPaths` settings select this worktree's six package source directories,
ahead of editable installs from other checkouts; no manual `PYTHONPATH` is needed.

`requirements-dev.in` is an install input, not a lockfile. Keep each package's
development dependencies in its own `pyproject.toml`; do not use this file as
evidence of a reproducible or production environment.

## Evidence boundaries

Offline fakes establish deterministic contract behavior only. They do not prove
that a live external integration worked or that a real business side effect
completed. Report the exact test or external observation that supports a claim.

Never weaken permission, approval, idempotency, deduplication, or fail-closed
behavior to make a check pass.
