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

## Evidence attribution

`EvidenceSource.attribution` optionally carries an `EvidenceAttribution` with
author, work title, stable source location, declared license name/URI, and
attribution text. It round-trips through topic-candidate input and explanation
output; omitting it preserves the legacy shape. The existing `uri` remains the
source URI, while `source_location` can identify a stable section, chapter, or
other location within that source. Conflicting metadata on a reused source ID
is a source identity conflict because attribution participates in the immutable
`EvidenceSource` value.

Attribution and license fields are caller-supplied declarations, not proof of
authorship, ownership, license applicability, permission, public-domain status,
or compliance. A URI or license label must never be treated as authorization to
reuse material; unknown rights remain unknown and need independent review by
the consuming workflow.

## Researching and replenishing topics

`research_and_replenish_topic_catalog` runs one research cycle through an
injected `TopicResearchPort` and an injected `TopicCandidateCatalog`. A
researcher must actively retrieve and verify classic value-investing sources
and return candidates whose claims cite those sources; the package requires
absolute HTTP(S) evidence URIs and passes existing topic/source IDs to the
researcher. It does not establish that a source was really retrieved or that a
claim is true, and there is deliberately no `verified` flag that can substitute
for research.

The frozen catalog interface is:

- `identities() -> TopicCatalogIndex(topic_ids, sources)`, where `sources` is
  the tuple of persisted `EvidenceSource` records.
- `TopicResearchRequest` includes `known_sources`, the same immutable tuple of
  canonical persisted source records, so a researcher can reuse their exact
  identity across cycles.
- `add_if_new(candidate) -> CatalogInsertResult(status, added_source_ids)`.
  `status` is `INSERTED`, `DUPLICATE_TOPIC`, or `SOURCE_CONFLICT`; only
  `INSERTED` may report newly created source records.
- `research_and_replenish_topic_catalog(...) -> TopicResearchReport`, with
  separate `added_topic_ids`, `added_source_ids`, and `duplicate_topic_ids`.

The consumer owns the real agent/model, credentials, durable catalog, atomic
topic-ID uniqueness, and recurring invocation schedule. The catalog index
exposes full evidence records so the API can reject a reused source ID with
conflicting content. Reusing an identical source across distinct topics is
allowed; `added_source_ids` reports only source records newly inserted by the
catalog. Each catalog call must be atomic, but the complete research cycle is
not a batch transaction and can leave earlier candidates persisted if a later
write fails. Missing adapters and catalog write failures are errors. An empty
research result is reported as `no_candidates`, not as a successful pool
refill. `added` means the injected catalog reported durable insertion; that
guarantee depends on the consumer's catalog implementation. Test doubles can
exercise orchestration mechanics only; they are not evidence of live research
or persistence.

## Provider-neutral slot binding

`evaluate_wakeup_slot_binding` is pure logic over caller-supplied
`ConfiguredSlot` windows, an independently established Beijing `business_date`,
optional `HostValidatedWakeEvidence`, and a persisted `SlotBindingIndex`.
It returns `READY`, `IDEMPOTENT`, or an explicit `BLOCKED` reason, with an
explicit guarantee scope:

- `SLOT_ONLY`: no trusted wake ID is available. The caller's explicit date and
  canonical configured slot can still be deduplicated; no IDs, source fields,
  validation references, or trigger times are invented or required. An occupied
  slot is an idempotent review, not permission to execute it again. Distinct
  configured slots can each be used, but the same unidentified wake cannot be
  proven absent from the other slot.
- `WAKE_IDENTITY`: the entrypoint supplies trusted message/occurrence identities
  or a `SourceOccurrenceIdentity`;
  those identities must not bind to another date/slot. A supplied source window
  must be timezone-aware and fit exactly one configured slot on the supplied
  Beijing date. Such a window does not itself establish a wake identity.

`HostValidatedWakeEvidence.source_occurrence` optionally accepts
`SourceOccurrenceIdentity(source_namespace, source_id, occurred_at)`. This is a
separate typed identity, not text disguised as a message or occurrence ID.
Namespace and source ID are separate non-empty canonical strings; the original
instant must be timezone-aware and is normalized to UTC, including historical
folds. The instant must lie within the requested slot and any supplied source
window, using half-open containment. Equal source tuples with equivalent
timezone representations compare equal; different namespace/source/instant
components remain distinct. Persist these components separately or with a
collision-safe encoding, preserving the exact UTC instant.
Rebuild persisted identities as their declared typed objects: raw serialized
tuples/strings and invalid message/occurrence enum kinds are rejected by the
binding index. Optional composite evidence also rejects non-composite objects.

Only a trusted host/entrypoint that actually authenticates the stable source,
original trigger instant, and uniqueness of that combination may supply this
identity. Constructor validation establishes none of those facts. A source
alone, timestamp alone, source window, window boundary, processing/receipt time,
`lastRunAt`, or caller assertion is not a substitute. There is no required
source-occurrence fallback: absent genuine evidence, retain `SLOT_ONLY`.

An unknown original business date must be passed as `None` and is blocked;
receipt time is not a fallback. Source validation and authorization belong to
the actual entrypoint. The evidence type and any optional validation reference
record caller assertions, not authentication performed by this package. The
package cannot authenticate fields, verify configuration authorization, or
recognize a Desktop wake.

Receiving message IDs do not automatically identify the original wake. The host
must establish the original identity or verify any forwarded identity aliases;
this contract assumes neither stable redelivery IDs nor equivalence between
manual forwarding and scheduled triggers. The binding interval describes the
original source event, never receipt or processing time. Delayed or cross-day
delivery must not move that event to a different Beijing business date.
Automation-level `lastRunAt`/`nextRunAt` observations do not bind a particular
queued message to an occurrence or prove its original business date.

`SlotBindingPersistencePort.read_binding_index` must include the supplied
identity history and all occupied slots for that business date;
`bind_and_claim` must atomically recheck available identity bindings and slot occupancy,
then persist both in the same transaction or equivalent atomic critical
section. Consumers submit every non-blocked proposal (including idempotent
review) to that adapter. Same-wake reviews retain every snapshot alias and add
incoming aliases **in the adapter**, not in the proposal: every proposal contains
only this request's actual input identities. The adapter must atomically merge
these with all aliases in the current database, recheck conflicts for the merged
set, and never replace or remove stored aliases based on a snapshot proposal.
For an occupied slot and an empty incoming identity tuple, the adapter must
return `SLOT_OCCUPIED`, not same-wake `IDEMPOTENT`, preserving the stored aliases
without attributing them to the unknown request. Only `CLAIMED` represents a
new claim; neither result permits a second execution. The shared package
provides no scheduler, database, cross-process atomicity, or persistence
implementation; a preflight snapshot alone is not safe against concurrent claims.
An empty identity tuple requires atomic uniqueness only on `(business_date,
slot_id)`, not a claim of cross-slot wake deduplication.

Beijing business dates use IANA `Asia/Shanghai`, including historical offset
rules. Windows installs include `tzdata` because Windows does not normally
provide an IANA timezone database; no fixed-offset fallback is used.
Windows are half-open: an interval ending exactly at the following Beijing
midnight still lies within the original business date. Non-empty whitespace
IDs are invalid, not silently treated as missing identities.

This package is educational software, not investment advice or a
recommendation. It is not affiliated with or endorsed by any investor, author,
publisher, estate, employer, or related organization. Do not place verbatim
copyrighted text in its inputs or outputs.
