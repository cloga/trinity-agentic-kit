# Batch

The CLI intentionally handles one request per command. A batch runner may
coordinate multiple independent CLI invocations only when the operator defines:

1. a maximum item count;
2. a minimum interval and maximum rate for execute and verify operations;
3. stop conditions for session, timeout, browser, approval, and uncertain
   outcome errors;
4. a per-item review record.

Each item must have its own request ID, idempotency key, preparation, operator
approval, and grant file. A batch-level confirmation cannot authorize multiple
items.

Do not parallelize browser side effects unless an explicit operator policy and
platform authorization permit it. Never infer a recurring schedule from this
Skill. Verification for one item must not execute or reupload any item.
