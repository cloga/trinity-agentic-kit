---
name: value-investing-explainer
description: Create a short, plain-language value-investing explanation from caller-supplied, provenance-bound evidence.
---

# Value Investing Explainer

Use this Skill to turn one version `1.0` topic candidate into an educational
explanation package. Validate inputs and outputs with `validate.py`.

## Procedure

1. Require at least one evidence record and one claim. Every claim must cite
   evidence by `source_id`.
   Preserve available author, work title, stable source location, and declared
   license/attribution metadata through the explanation output. These fields
   support traceability only; they do not prove permission or license validity.
2. Accept only caller-supplied paraphrases, factual summaries,
   public-domain-like paraphrases, or public `value-audit-core` output. Never
   retrieve or invent missing evidence.
3. Explain the concept in plain language. Preserve uncertainty, assumptions,
   warnings, data gaps, and dates.
4. Split narration into short scenes. Each scene must cite at least one known
   `source_id`; visual directions must remain provider-neutral.
5. Run deterministic QA and emit all checks and issues. A failed QA result is
   not publication-ready.
6. Keep the standard non-advice and non-affiliation disclaimer unchanged.

Topic discovery is a separate consumer-owned workflow. A consumer may run
`research_and_replenish_topic_catalog` with a real source-research agent and a
durable catalog; repeat scheduling, source retrieval/verification, and atomic
persistence stay outside this Skill. Candidate schema validity and a source URI
do not establish that a source was retrieved or that its claims are correct.

```bash
python skills/value-investing-explainer/validate.py \
  --input skills/value-investing-explainer/examples/input.json \
  --output skills/value-investing-explainer/examples/output.json
```

## Safety boundaries

- Never give personalized advice, buy/sell/hold instructions, price targets,
  guaranteed returns, or claims of suitability.
- Never imply affiliation, endorsement, or official interpretation by an
  investor, author, publisher, estate, employer, or organization.
- Never copy book passages or other copyrighted text. Store concise
  caller-authored paraphrases and source metadata instead.
- Never add facts that are absent from the supplied evidence. Missing evidence
  is a data gap, not an invitation to infer.
- Keep model clients, credentials, network access, media generation, publishing,
  databases, schedules, and provider-specific settings outside this Skill.
