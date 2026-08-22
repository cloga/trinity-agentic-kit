# Value Audit Tushare

`trinity-agentic-kit-value-audit-tushare` is a point-in-time Tushare transport
adapter for `trinity-agentic-kit-value-audit`. It fetches provider rows, maps
them into the public `CompanyFinancialPayload` contract, and delegates all
valuation and EPS-restatement logic to `value-audit-core`.

```bash
python -m pip install trinity-agentic-kit-value-audit-tushare
export TUSHARE_TOKEN=...
value-audit-tushare 600000.SH --as-of 2025-06-30 --output result.json
```

Python callers can inject any `TushareClient` implementation:

```python
from datetime import date

from trinity_agentic_kit.value_audit_tushare import audit_tushare_company

result = audit_tushare_company(
    "600000.SH",
    date(2025, 6, 30),
    client=my_client,
)
```

`audit_tushare_company`, `fetch_tushare_frames`, and
`map_tushare_frames_to_payload` are separate public layers. A client implements
one `query(api_name, fields="", **params)` method. Fetch retries are bounded and
raise typed errors that identify the endpoint and attempt count without
including provider payloads or tokens.

The default `HttpsTushareClient` uses `https://api.tushare.pro` through the
Python standard library. It does not use the SDK's legacy plaintext endpoint.

## Fields, units, and visibility

The adapter requests:

| Endpoint | Public payload use |
| --- | --- |
| `stock_basic` | company name, industry, financial-sector classification |
| `daily_basic` | latest close, total shares, trailing dividend yield |
| `income` | revenue, operating/gross/pretax/net income, tax, R&D |
| `balancesheet` | assets, liabilities, equity, cash, debt, intangibles, operating liabilities |
| `cashflow` | depreciation/amortization, capital expenditure, operating cash flow |

Tushare statement amounts are mapped as CNY `ones`. `daily_basic.total_share`
is documented by Tushare in 10,000-share units and is multiplied by 10,000,
then emitted as `share_unit="shares"`. `dv_ttm` is interpreted as a percent and
converted to trailing dividend per share from the same row's close.

Financial rows require `f_ann_date` or `ann_date`. The preferred
`f_ann_date`, otherwise `ann_date`, becomes `visible_at`; rows announced after
the explicit audit date are excluded. `end_date` is never treated as evidence
that a filing was visible. Only cumulative consolidated report types (`1`,
adjusted `4`, pre-adjustment `5`, or an omitted type) are mapped; single-quarter
and parent-only rows are excluded. Duplicate/restated rows resolve to the latest
announcement visible at the audit date, preferring adjusted consolidated rows
when announcement dates tie. Market rows require
`trade_date <= as_of`. Core recalculates historical EPS from visible net income
using the latest point-in-time share count.

`stock_basic` is queried across listed, delisted, and paused statuses; listing
and delisting dates are checked against `as_of`. Tushare does not provide
historical industry classifications through this endpoint. The default `auto`
classification therefore uses current industry metadata. For a historical
classification change, pass `is_financial=` in Python or
`--company-type financial|non-financial` on the CLI. The provenance label keeps
this limitation explicit.

Each selected provider row emits a stable provenance ID. Missing fields are
omitted rather than zero-filled, except absent dividend yield which maps to
zero. `value-audit-core` then reports model-specific warnings and data gaps.
Missing identity, market price, shares, or all visible financial rows are
contract errors rather than success-shaped results.

## Token and redistribution safety

Pass a token explicitly or set `TUSHARE_TOKEN`. Explicit values take
precedence. This package does not log, persist, cache, serialize, or include
tokens in errors. The HTTPS client retains the credential only in process
memory for authenticated calls and has no token-bearing representation.

Tushare data access, display, caching, and redistribution are governed by
Tushare's current license, terms, permissions, and point requirements. This
Apache-2.0 package does not grant rights to Tushare data. Review provider terms
before storing or redistributing fetched rows or derived outputs.

This software provides research calculations, not investment advice. Tushare
does not sponsor, endorse, or affiliate with this project.
