# Douyin Publish CLI

`douyin-publish` is an operator-facing command line workflow built on
`social-publish-core` and `douyin-publish-adapter`.

> [!WARNING]
> This unofficial project is not affiliated with or endorsed by Douyin or
> ByteDance. Browser publishing may conflict with current platform terms,
> trigger review, restrict an account, or stop working after site changes.
> Obtain authorization and accept the operational risk before use.

## Install

```bash
python -m pip install \
  "trinity-agentic-kit-douyin[playwright,keyring]==0.1.0"
playwright install chromium
```

The base CLI depends only on the core and adapter distributions. Playwright and
keyring remain optional extras.

## Configuration

Pass `--config` to commands that use a browser or approval key. If omitted, the
CLI looks for `config.json` in its operating-system app-data directory.

```json
{
  "browser_name": "chromium",
  "use_keyring": false,
  "selector_profile": {
    "name": "operator-maintained",
    "version": "2026-08",
    "schema_version": 1,
    "login_url": "CONFIGURE_OUTSIDE_THIS_REPOSITORY",
    "publish_url": "CONFIGURE_OUTSIDE_THIS_REPOSITORY",
    "verification_url_template": "CONFIGURE_WITH_{platform_reference}",
    "selectors": {
      "authenticated": "CONFIGURE",
      "composer_ready": "CONFIGURE",
      "description_input": "CONFIGURE",
      "submit_button": "CONFIGURE",
      "submission_reference": "CONFIGURE",
      "video_input": "CONFIGURE"
    }
  }
}
```

No production profile ships with this package.

## Workflow

```bash
douyin-publish login --config /absolute/path/config.json

douyin-publish prepare --config /absolute/path/config.json \
  --request-id request-1 --media-type video --asset-ref asset://video-1 \
  --title "Title" --description "Description" --idempotency-key key-1

douyin-publish approve --config /absolute/path/config.json \
  --request-id request-1

douyin-publish execute --config /absolute/path/config.json \
  --request-id request-1 \
  --grant-file /absolute/app-data/path/grants/request-1.grant

douyin-publish verify --config /absolute/path/config.json \
  --request-id request-1

douyin-publish status --request-id request-1
```

`approve` displays the exact digest, title, asset reference, and platform on
standard error, then requires an interactive terminal confirmation. There is no
non-interactive confirmation bypass. `execute` accepts only an explicit grant
file and deletes it after the core records consumption. Grant contents, signing
keys, and browser session state are never printed.

`prepare --dry-run` validates the configured profile, session, request, and
composer readiness without persisting a request. Image requests use repeated
`--image-ref`; text requests use `--asset-ref` as their content artifact
reference.

State uses SQLite under per-user OS app-data, never the working directory.
`verify` delegates only to the adapter's lookup operation and cannot upload.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | success |
| 2 | command usage |
| 10 | configuration or local secret file |
| 11 | request state |
| 12 | approval grant |
| 13 | browser session |
| 14 | bounded timeout |
| 15 | browser operation |
| 16 | operator confirmation |
| 20 | local internal error |

All command results and failures are emitted as one JSON object on standard
output. Approval review and prompts use standard error.

## Scope

The package contains no production selectors, private paths, authenticated
state, real media, private messaging, strategy logic, identity spoofing,
stealth behavior, or challenge bypass. Tests use `FakeBrowserDriver` and no
network. Real-site and real-account testing is intentionally manual and outside
this repository.
