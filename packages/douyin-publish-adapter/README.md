# Douyin Publish Adapter

An unofficial, user-operated adapter connecting
`trinity_agentic_kit.social_publish` to a visible Playwright browser.

> [!WARNING]
> This project is not affiliated with or endorsed by Douyin or ByteDance.
> Browser-based publishing may violate platform terms, trigger review, restrict
> an account, or stop working when the site changes. Review current terms and
> obtain authorization before use. You accept all account and content risk.

## Security and scope

- Login is completed manually by the user in a visible browser.
- Browser session state is opaque, sensitive data. The default store uses the
  operating system's per-user app-data directory, atomic replacement, and
  restrictive permissions where supported. It never writes under the current
  working directory.
- A keyring-backed protector is available through the `keyring` extra.
- Selector profiles are versioned and supplied by the operator. This package
  ships no production URLs or selectors.
- Operations use bounded timeouts and structured errors with profile-version
  diagnostics.

This package deliberately has no stealth settings, identity spoofing,
simulated-human behavior, challenge bypass, private messaging, strategy logic,
production configuration, authenticated state, or media.

## Installation

```bash
python -m pip install \
  "trinity-agentic-kit-douyin-adapter[playwright,keyring]==0.1.0"
playwright install chromium
```

The base package depends only on
`trinity-agentic-kit-social-publish>=0.1.0,<0.2`. Playwright and keyring are
opt-in.

## Usage

Construct a `SelectorProfile` from configuration maintained in your secured
integration repository. The required logical keys are:

| Scope | Keys |
| --- | --- |
| all requests | `authenticated`, `composer_ready`, `description_input`, `submit_button`, `submission_reference` |
| video | `video_input` |
| image | `image_input` |
| text | `text_input` |
| optional | `title_input`, `published_link` |

```python
from trinity_agentic_kit.douyin_adapter import (
    AppDataSessionStore,
    DouyinPublisherAdapter,
    PlaywrightBrowserDriver,
    SelectorProfile,
)

profile = SelectorProfile(
    name="operator-maintained",
    version="2026-08",
    login_url=configured_login_url,
    publish_url=configured_publish_url,
    verification_url_template=configured_verification_url,
    selectors=configured_selectors,
)
adapter = DouyinPublisherAdapter(
    driver=PlaywrightBrowserDriver(),
    session_store=AppDataSessionStore(),
    selector_profile=profile,
)

# This opens a visible browser and waits for the user to finish login.
await adapter.login_interactively()
```

Pass the adapter to `SocialPublishCoordinator` for
prepare -> approval -> execute -> verify. Do not call `execute` directly from an
agent-facing surface; keep the core package's short-lived request-bound
approval boundary.

## Testing boundary

`FakeBrowserDriver` and `MemorySessionStore` support fully offline contract
tests. This repository does not perform real-site or real-account tests.
