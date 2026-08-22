# Security Policy

## Supported versions

Security fixes are provided for the latest release on the default branch.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
security advisory flow for this repository and include reproduction steps,
affected versions, and the expected impact.

## Security boundary

`social-publish-core` coordinates publication; it does not authenticate to
social platforms. Keep credentials, cookies, private messages, browser state,
account details, platform selectors, and anti-detection behavior outside this
repository.

Approval signing keys are sensitive. Generate at least 32 random bytes, store
them in a secret manager, scope them to one deployment, and rotate them after
suspected exposure. Approval issuance belongs on a trusted operator surface,
not in an agent-callable tool. Grants must remain short-lived and request-bound.

Asset references and metadata are untrusted integration inputs. Adapters must
validate them before accessing files, URLs, or external services.
