---
name: douyin-publish
description: Use the unofficial user-operated Douyin adapter through the social-publish approval lifecycle.
---

# Douyin Publish

Use this Skill for a single prepared video, image, or text publication through
an operator-configured `trinity_agentic_kit.douyin_adapter` integration.

## Safety boundary

This integration is unofficial and may conflict with current platform terms or
cause account restrictions. Confirm authorization and accept the operational
risk before use.

The operator must supply a reviewed, versioned `SelectorProfile`. This Skill
contains no site URLs or selectors. Login is user-driven in a visible browser.
Never add stealth flags, identity spoofing, simulated-human behavior, challenge
bypass, private messaging, or authenticated state to the Skill.

## Required flow

1. If no valid saved session exists, ask the operator to run
   `login_interactively` and complete login personally.
2. Call the social-publish coordinator's `prepare`. Preparation validates the
   media contract, selector profile, session, and composer readiness without
   publishing.
3. Present the exact prepared request for trusted operator approval. Require a
   short-lived request-bound grant with `publish.execute`.
4. Call coordinator `execute` once. If the outcome is uncertain, retain the
   platform reference and move to verification; do not submit again.
5. Call coordinator `verify`. Verification performs lookup only and must never
   upload, compose, or submit content.

Use `FakeBrowserDriver` for offline tests. Real-site tests require an explicit
manual test plan outside this repository.

## CLI boundary

When using `douyin-publish`, preserve the same phases as separate commands:

`login` -> `prepare` -> `approve` -> `execute` -> `verify`

- `approve` must display the exact request digest, title, asset reference, and
  platform, then receive a direct operator confirmation from an interactive
  terminal.
- `execute` must receive an explicit pre-issued grant file. Never add an
  automatic confirmation flag or print grant contents.
- `verify` is lookup-only. Never replace it with another execute attempt.
- Use `status` for inspection and `cancel` only through the core state machine.

CLI state, session material, and approval keys belong under OS app-data, never
the current working directory.
