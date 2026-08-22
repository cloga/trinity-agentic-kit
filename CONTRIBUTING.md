# Contributing

## Development

Python 3.10 or newer is required.

```bash
python -m pip install -e "packages/social-publish-core[dev]" \
  -e "packages/value-audit-core[dev]" \
  -e "packages/value-investing-explainer[dev]" \
  -e "packages/douyin-publish-adapter[dev]" \
  -e "packages/douyin-publish-cli[dev]"
pytest
ruff check .
ruff format --check .
pyright
python -m build packages/social-publish-core
python -m build packages/value-audit-core
python -m build packages/value-investing-explainer
python -m build packages/douyin-publish-adapter
python -m build packages/douyin-publish-cli
```

Add tests for every behavior change. Keep core contracts platform-neutral and
deterministic. Adapter tests must use fake drivers and require no network,
authenticated state, production database, or media files.

## Pull requests

Keep changes focused, document public API changes, and explain any security or
compatibility impact. By contributing, you agree that your contribution is
licensed under Apache-2.0.

The branch prefix must match the GitHub account that is actually used to push
the branch. This repository currently publishes with `cloga`, so branches use
`cloga/<topic>`. If repository automation deliberately switches to another
account, update `expected_account` in `.github/branch-policy.json` in the same
reviewed change. Never reuse an employer or unrelated account prefix. CI
enforces this rule.
