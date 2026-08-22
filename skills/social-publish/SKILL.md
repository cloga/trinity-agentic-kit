---
name: social-publish
description: Safely coordinate one platform-neutral social publication request from preparation through approval, execution, and verification.
---

# Social Publish

Use this Skill for one publication request whose content and asset are ready for
platform-specific validation.

## Required lifecycle

Follow this sequence without skipping or combining boundaries:

`prepare` -> `awaiting_approval` -> `approved` -> `execute` -> `submitted` ->
`verify` -> `published`

1. **Prepare:** Call the adapter's validation-only preparation step. Record a
   versioned request digest and an idempotency key. Preparation must not publish.
2. **Approval:** Present the exact prepared request to a trusted human operator.
   Obtain a signed, short-lived, request-bound approval grant containing the
   `publish.execute` capability. Approval issuance must not be exposed as an
   agent-callable tool.
3. **Execute:** Verify the grant's signature, issuer, capability, request
   identity, request digest, activation time, and expiry immediately before the
   side effect. Consume the grant once before invoking the adapter.
4. **Verify:** Query platform state using the recorded platform reference.
   Verification must never upload or publish again. Record `published` only
   with a public URL or equally strong platform-neutral evidence defined by the
   integration.

If execution has an uncertain outcome, move to `verification_pending`; do not
retry the side effect. If execution definitively fails, a retry must return to
`awaiting_approval` and use a fresh grant.

## Contract boundary

Depend only on versioned contracts from
`trinity_agentic_kit.social_publish`. Use a `PublisherAdapter` implementation
for platform behavior and a `PublishStateStore` for persistence. Contract tests
should use `FakePublisherAdapter` with no network or authenticated state.

## Exclusions

This Skill does not define or contain platform web adapters, browser
automation, selectors, cookies, private messages, account details, credentials,
anti-detection behavior, production database data, media, or private strategy
and runtime configuration. Keep those concerns in a separately secured
integration layer.
