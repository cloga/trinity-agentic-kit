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
python -m pip install -e "packages/social-publish-core[dev]" \
  -e "packages/value-audit-core[dev]" \
  -e "packages/value-investing-explainer[dev]"
pytest
ruff check .
pyright
```

See the [package README](packages/social-publish-core/README.md), the
[`social-publish` Skill](skills/social-publish/SKILL.md), and the
[basic example](examples/social_publish_basic.py).

## Value Audit Core

[`value-audit-core`](packages/value-audit-core) provides versioned,
provider-neutral financial payload and unified result contracts plus
deterministic Graham-, Buffett-, Greenwald-, and Lynch-style models. It
preserves point-in-time report visibility, restates historical EPS against the
latest visible share count, makes units explicit, and emits assumptions,
warnings, data gaps, and provenance.

The package has no network, database, credential, token, or vendor-adapter
dependency. See the [`lynch-research` Skill](skills/lynch-research/SKILL.md) for
a public-output-only research workflow.

## Value Investing Explainer

[`value-investing-explainer`](packages/value-investing-explainer) provides
versioned topic and explanation contracts plus deterministic
topic -> evidence -> explanation -> scenes -> QA orchestration. It supports
caller-supplied concept evidence and can adapt public `value-audit-core`
results without taking a package dependency.

Semantic generation is an explicit optional port; the package includes a
no-network deterministic fake for tests. Every claim and scene must cite known
evidence IDs. Recommendation language, guaranteed returns, long verbatim reuse,
and missing non-advice/non-affiliation disclosures fail QA. See the
[`value-investing-explainer` Skill](skills/value-investing-explainer/SKILL.md)
and [basic example](examples/value_investing_explainer_basic.py).

All model thresholds are documented, overridable implementation assumptions,
not official or universal master rules. Outputs are research calculations, not
investment advice or recommendations. This project is not affiliated with or
endorsed by the people or organizations whose names identify the analytical
styles.

## Explicit exclusions

This repository does **not** contain platform web adapters, site selectors,
browser automation, cookies, private messages, account details, credentials,
anti-detection behavior, production databases, media, or private strategy and
runtime configuration. Integrators own platform-specific adapters and must keep
secrets and authenticated runtime state outside the contracts and state stores.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
