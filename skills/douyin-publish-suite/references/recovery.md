# Recovery

Start by inspecting structured state:

```bash
douyin-publish status --request-id <REQUEST_ID>
```

## Missing or expired session

Ask the operator to run `login` again, then repeat only the non-side-effecting
step that failed.

## Uncertain execution

Do not call `execute` again. Preserve the request and use `verify`. If lookup
remains pending, pause under the operator's rate policy.

## Definitive failure

Do not reuse the old grant. Follow the public core transition reported by
`status`; any retry requires a new preparation or approval as indicated.

## Cancellation

```bash
douyin-publish cancel --request-id <REQUEST_ID>
```

Cancellation uses the public state machine. It does not remove already
published content.
