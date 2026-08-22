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
  -e "packages/value-audit-tushare[dev]" \
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

## Value Audit Tushare

[`value-audit-tushare`](packages/value-audit-tushare) is an optional,
point-in-time transport adapter. It keeps Tushare network access and field/unit
mapping separate from `value-audit-core`, which remains the only valuation
implementation. Callers may inject the public `TushareClient` protocol or use
the standard-library `HttpsTushareClient`.

The adapter requires an explicit audit date, excludes filings announced later,
normalizes provider units, emits row-level provenance, uses bounded retry
errors, and never logs or stores tokens. See its
[field, licensing, and redistribution notes](packages/value-audit-tushare/README.md).

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

## Douyin Publish Adapter

[`douyin-publish-adapter`](packages/douyin-publish-adapter) is an unofficial,
user-operated integration package. It provides externally configured selector
profiles, visible-browser Playwright support, app-data session storage, offline
fakes, bounded operations, and structured diagnostics. Playwright and keyring
are optional extras.

The package ships no production selectors, URLs, authenticated state, or media.
Review its [terms and account-risk warning](packages/douyin-publish-adapter/README.md)
before use.

## Explicit exclusions

This repository contains no production site selectors, authenticated state,
private messages, account details, credentials, stealth or challenge-bypass
behavior, production databases, real media, or private strategy and runtime
configuration.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
