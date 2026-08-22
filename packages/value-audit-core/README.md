# Value Audit Core

`trinity-agentic-kit-value-audit` is a deterministic, provider-neutral Python
package for running Graham-, Buffett-, Greenwald-, and Lynch-style company
value audits. It has no network, database, credential, token, or vendor-adapter
dependency.

```python
from trinity_agentic_kit.value_audit import audit_company

result = audit_company(
    {
        "schema_version": "1.0",
        "company_id": "SYNTH-001",
        "company_name": "Synthetic Tools",
        "industry": "industrial",
        "as_of_date": "2025-06-30",
        "currency": "USD",
        "monetary_unit": "millions",
        "share_unit": "millions",
        "market": {
            "date": "2025-06-30",
            "price": 24.0,
            "shares_outstanding": 100.0,
            "dividend_per_share_ttm": 0.48,
            "source_ids": ["market.synthetic"],
        },
        "periods": [],
        "provenance": [],
    }
)
```

The public entry point accepts either `CompanyFinancialPayload` or a mapping
matching `company-financial-payload-v1.json`. `AuditResult.to_dict()` matches
`value-audit-result-v1.json`.

## Point-in-time and EPS rules

Only periods whose `visible_at` date is on or before `as_of_date` are used.
When duplicate periods are present, the latest visible version wins. Historical
EPS is restated as historical attributable net income divided by the latest
point-in-time share count, so split and issuance effects do not create false
growth. Interim TTM values use current YTD + prior annual - prior comparable YTD.

## Assumptions

Every threshold is part of `AuditConfig` and is emitted in the result. Defaults
are transparent implementation assumptions inspired by common interpretations
of the named frameworks; they are not official, authoritative, or universal
"master rules." Callers should review and override them for their context.

## Important disclaimer

This software provides reproducible research calculations, not investment,
legal, tax, accounting, or other professional advice. Outputs can be incomplete
or wrong and must not be treated as recommendations, guarantees, price targets,
or a substitute for primary-source review and qualified judgment.

This project is not affiliated with, endorsed by, or sponsored by Benjamin
Graham, Warren Buffett, Bruce Greenwald, Peter Lynch, their estates, employers,
publishers, or related organizations. Names identify broad analytical styles
only.
