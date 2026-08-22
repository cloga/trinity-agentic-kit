---
name: douyin-publish-suite
description: Route an operator-approved Douyin publication through the installed douyin-publish CLI.
---

# Douyin Publish Suite

Use this progressive Skill as the single Douyin-specific entry point. Route all
operations through the installed `douyin-publish` command and the public
`trinity_agentic_kit.social_publish` contracts. Do not recreate adapter or
workflow logic in the Skill.

## Operating modes

- **Offline Fake mode:** use fake-driver tests and examples to validate request,
  output, approval, state, and recovery contracts without network access.
- **Manual real-account mode:** an authorized operator supplies a reviewed
  profile, opens the visible browser, completes login personally, reviews every
  approval, and accepts current terms and account risk.

Never treat offline success as evidence that a real account or current site
profile works.

## Progressive router

| Need | Read |
| --- | --- |
| install and complete visible login | [Login](references/login.md) |
| validate video, image, or text input | [Prepare](references/prepare.md) |
| obtain per-request operator approval | [Approval](references/approval.md) |
| perform one approved submission | [Execute](references/execute.md) |
| perform lookup-only verification | [Verify](references/verify.md) |
| inspect, cancel, or handle uncertain outcomes | [Recovery](references/recovery.md) |
| process multiple independent items | [Batch](references/batch.md) |
| review the complete safety boundary | [Security](references/security.md) |

## Invariants

1. Follow `login` -> `prepare` -> `approve` -> `execute` -> `verify`.
2. Require one short-lived, request-bound operator approval per item.
3. Never print, paste, or summarize grant contents or browser session state.
4. Execute once. If the outcome is uncertain, move to verification or recovery.
5. Verification is lookup-only and must never upload or submit.
6. Batch work requires per-item approval plus an operator-defined rate policy.

See [README.md](README.md) for required distributions and optional extras.
