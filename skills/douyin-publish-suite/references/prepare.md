# Prepare

Preparation validates the request, external profile, saved session, and
composer readiness. It must not publish.

## Video

```bash
douyin-publish prepare --config <PROFILE_FILE> \
  --request-id <REQUEST_ID> --media-type video \
  --asset-ref <ASSET_REFERENCE> --title <TITLE> \
  --description <DESCRIPTION> --idempotency-key <IDEMPOTENCY_KEY>
```

## Image

Use one `--image-ref` per ordered image:

```bash
douyin-publish prepare --config <PROFILE_FILE> \
  --request-id <REQUEST_ID> --media-type image \
  --asset-ref <SET_REFERENCE> --image-ref <IMAGE_REFERENCE> \
  --title <TITLE> --description <DESCRIPTION> \
  --idempotency-key <IDEMPOTENCY_KEY>
```

## Text

Use `--media-type text` and an artifact-style `--asset-ref`.

## Dry run

Add `--dry-run` to validate readiness and profile diagnostics without
persisting a request. Offline Fake mode uses this path to test contracts.

The command output must validate against
[`result.schema.json`](../schemas/result.schema.json). Keep the returned request
digest for operator review; it is not secret.
