# social-publish-core

Platform-neutral contracts and safe orchestration for agent-assisted social
publication.

```python
from trinity_agentic_kit.social_publish import (
    FakePublisherAdapter,
    HmacApprovalAuthority,
    InMemoryAuditSink,
    InMemoryPublishStateStore,
    SocialPublishCoordinator,
)
```

The coordinator enforces `prepare -> awaiting_approval -> approved -> execute
-> submitted -> verify -> published`. Execution requires a signed,
short-lived approval grant bound to the exact request digest and carrying the
`publish.execute` capability.

The package includes no network client or platform-specific behavior. Web
adapters, browser automation, selectors, cookies, private messages, accounts,
credentials, anti-detection behavior, production databases, and private
configuration are deliberately excluded.
