# Contributing

## Development

Python 3.10 or newer is required.

```bash
python -m pip install -e "packages/social-publish-core[dev]"
pytest
ruff check .
ruff format --check .
pyright
```

Add tests for every behavior change. Keep core contracts platform-neutral and
deterministic. Tests must not require network access, browser state, accounts,
cookies, credentials, production databases, or media files.

## Pull requests

Keep changes focused, document public API changes, and explain any security or
compatibility impact. By contributing, you agree that your contribution is
licensed under Apache-2.0.
