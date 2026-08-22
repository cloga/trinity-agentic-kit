---
name: lynch-research
description: Turn a public value-audit-core result into evidence-aware Lynch-style research without private runtime dependencies.
---

# Lynch Research

Use this Skill only with a version `1.0` unified result emitted by
`trinity_agentic_kit.value_audit.audit_company`. Validate the input against
`schemas/input.schema.json` before analysis.

## Procedure

1. Confirm the audit date, currency, package version, warnings, data gaps, and
   provenance.
2. Use `models.lynch.metrics.category` as a preliminary classification, not a
   fact. Verify one primary category: `slow_grower`, `stalwart`, `fast_grower`,
   `cyclical`, `asset_play`, `turnaround`, or `unverified`.
3. Do not compare financial companies, cyclicals, asset plays, or turnarounds
   on an ordinary PEG leaderboard. Low cyclical P/E can reflect peak earnings.
4. Treat PEG and the Lynch ratio as supporting calculations only. Review
   resilience, contradictory evidence, freshness, and unresolved gaps.
5. Never invent business descriptions, cycle position, insider activity,
   hidden assets, catalysts, or recovery actions.
6. Produce one decision matching `schemas/output.schema.json`. Rank only
   candidate/watchlist decisions that share the same `ranking_framework`.

Run the dependency-free validator with:

```bash
python skills/lynch-research/validate.py --input audit.json --output decision.json
```

## Boundaries

This Skill consumes public package output only. It does not call Trinity,
SQLite, localhost services, private MCP tools, databases, finance adapters, or
credentialed providers. Any optional external research belongs to the caller
and must be cited separately; it must never overwrite conflicting audit
provenance.

The Skill and package provide research calculations, not investment advice,
recommendations, guarantees, or target returns. They are not affiliated with
or endorsed by Peter Lynch, his estate, employers, publishers, or related
organizations.
