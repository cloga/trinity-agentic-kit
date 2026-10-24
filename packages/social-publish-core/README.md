# social-publish-core

Platform-neutral contracts and safe orchestration for agent-assisted social
publication.

```python
from trinity_agentic_kit.social_publish import (
    FakePublisherAdapter,
    HmacApprovalAuthority,
    InMemoryAuditSink,
    InMemoryPublishStateStore,
    SocialPublishCoordinator,
)
```

The coordinator enforces `prepare -> awaiting_approval -> approved -> execute
-> submitted -> verify -> published`. Execution requires a signed,
short-lived approval grant bound to the exact request digest and carrying the
`publish.execute` capability.

The package includes no network client or platform-specific behavior. Web
adapters, browser automation, selectors, cookies, private messages, accounts,
credentials, anti-detection behavior, production databases, and private
configuration are deliberately excluded.

## Comment collection

The public API also provides a provider-neutral `CommentCollectionCoordinator`
and version-1 request/result schemas. Requests bind consent to the exact
platform and resource, declare permitted and requested fields, and carry an
expiry and retention deadline. The coordinator follows opaque cursors,
deduplicates by comment ID within the scoped request, limits page size/pages
and retries, minimizes stored fields to the explicit allowlist, and reports
`complete`, `partial`, or `failed` with any continuation cursor. The fake
collector is deterministic and performs no network activity.

The core does not establish that a person has legal authority to grant consent,
authenticate an account, define platform policy, or enforce deletion from
downstream durable stores. Callers must verify consent and authorization,
provide a store with an appropriate retention/deletion policy, and remove
collected data no later than `retention_until`. Keep transport, selectors,
cookies, account identity, credentials, and platform-specific policy in
provider adapters, not this package.

This is an additive contract: existing publish requests and adapters do not
need to change to continue publishing. It does not by itself make a downstream
publisher safe to migrate to this coordinator. Before any consumer cutover,
the public publish implementation and its adapter must preserve the existing
consumer's `no_submission_proven` outcome, immutable media byte-digest binding,
and atomic persistence of approval consumption with the `EXECUTING` transition;
the v0.2.0 consumer pin does not provide those guarantees. No consumer migration
is included here.
