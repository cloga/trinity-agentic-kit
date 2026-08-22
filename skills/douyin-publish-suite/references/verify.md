# Verify

Verification is lookup-only:

```bash
douyin-publish verify --config <PROFILE_FILE> \
  --request-id <REQUEST_ID>
```

It uses the previously recorded platform reference. It must never upload,
compose, or submit content. Repeat verification only when the prior state is
`verification_pending` and the operator's rate policy permits another lookup.

Use:

```bash
douyin-publish status --request-id <REQUEST_ID>
```

to inspect state without opening a browser.
