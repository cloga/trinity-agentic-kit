# Approval

Every request requires a separate operator approval after preparation.

```bash
douyin-publish approve --config <PROFILE_FILE> \
  --request-id <REQUEST_ID>
```

The CLI displays the exact request digest, title, asset reference, and platform
on the operator surface. The operator must compare those values with the
intended publication and type the required confirmation in an interactive
terminal.

The command returns only a grant-file path and lifetime. Grant contents are
secret, short-lived, request-bound, and single-use. Never print, read, copy, or
put them into chat. There is no automatic confirmation option.

An explicitly pre-issued grant file may be passed to `execute`; it must come
from this operator workflow for the exact prepared request.
