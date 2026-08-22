# Douyin Publish Suite dependencies

Required compatible public distributions:

- `trinity-agentic-kit-social-publish>=0.1.0,<0.2`
- `trinity-agentic-kit-douyin-adapter>=0.1.0,<0.2`
- `trinity-agentic-kit-douyin>=0.1.0,<0.2`

Install the CLI with the browser extra for manual real-account mode:

```bash
python -m pip install "trinity-agentic-kit-douyin[playwright]>=0.1.0,<0.2"
playwright install chromium
```

Add the keyring extra when an approved native keyring backend is available:

```bash
python -m pip install \
  "trinity-agentic-kit-douyin[playwright,keyring]>=0.1.0,<0.2"
```

Offline Fake mode needs no browser or keyring service. It validates contracts
only and cannot demonstrate real-account compatibility.

This suite is unofficial. Review current platform terms and account risk before
manual use. The operator owns the external profile and authorization decision.
