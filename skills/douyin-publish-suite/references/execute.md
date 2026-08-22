# Execute

Execute exactly one prepared and approved request:

```bash
douyin-publish execute --config <PROFILE_FILE> \
  --request-id <REQUEST_ID> --grant-file <GRANT_FILE>
```

The CLI validates and consumes the grant through public core contracts before
the side effect. After recorded consumption, the local grant file is removed.

Interpret results:

- `submitted`: proceed to verification.
- `published`: a public result was already observed; status remains inspectable.
- `verification_pending`: the side-effect outcome is uncertain; do not execute
  again.
- `failed`: follow recovery and obtain a fresh approval only if the core state
  permits retry.

Never add an automatic confirmation argument or route around the approval
command.
