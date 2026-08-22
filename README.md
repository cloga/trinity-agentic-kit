# Trinity Agentic Kit

Reusable, safe-by-default agent Skills and deterministic domain components.

## Social Publish Core

The first package, [`social-publish-core`](packages/social-publish-core), provides
platform-neutral publication orchestration for Python 3.10+:

- versioned request, result, and approval-grant contracts with JSON Schemas;
- a deterministic prepare -> approval -> execute -> verify state machine;
- request-bound, capability-scoped, short-lived HMAC approval grants;
- in-memory and SQLite state stores with optimistic concurrency;
- a no-network `FakePublisherAdapter` for tests and local integration work.

```bash
python -m pip install -e "packages/social-publish-core[dev]"
pytest
ruff check .
pyright
```

See the [package README](packages/social-publish-core/README.md), the
[`social-publish` Skill](skills/social-publish/SKILL.md), and the
[basic example](examples/social_publish_basic.py).

## Explicit exclusions

This repository does **not** contain platform web adapters, site selectors,
browser automation, cookies, private messages, account details, credentials,
anti-detection behavior, production databases, media, or private strategy and
runtime configuration. Integrators own platform-specific adapters and must keep
secrets and authenticated runtime state outside the contracts and state stores.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
