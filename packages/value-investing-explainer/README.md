# Value Investing Explainer

`trinity-agentic-kit-value-explainer` turns an evidence-backed topic candidate
into a plain-language explanation, short narration chunks, provider-neutral
scene directions, and deterministic QA.

```python
from trinity_agentic_kit.value_explainer import (
    DeterministicFakeProvider,
    explain_value_topic,
)

result = explain_value_topic(candidate, provider=DeterministicFakeProvider())
assert result.qa.passed
```

The input and output contracts are version `1.0`. Every explanatory claim and
scene must cite known evidence IDs. Evidence must be a caller-supplied
paraphrase, factual summary, public-domain-like summary, or a public
`value-audit-core` output. The package rejects unsupported source references,
recommendations, guaranteed-return language, verbatim reuse of long evidence
text, and missing disclaimers.

Semantic generation is an optional port. Implement `SemanticGenerationPort`
for any provider and keep credentials, network clients, model settings, and
provider-specific payloads outside this package. `DeterministicFakeProvider`
is suitable for tests and offline examples.

`candidate_from_value_audit_result` consumes the public mapping returned by
`AuditResult.to_dict()` without importing or depending on `value-audit-core`.

This package is educational software, not investment advice or a
recommendation. It is not affiliated with or endorsed by any investor, author,
publisher, estate, employer, or related organization. Do not place verbatim
copyrighted text in its inputs or outputs.
