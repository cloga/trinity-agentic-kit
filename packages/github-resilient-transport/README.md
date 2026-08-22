# GitHub Resilient Transport

`trinity-agentic-kit-github-resilience` provides bounded, secret-safe retries
for Git fetch/push operations used by autonomous agents.

```powershell
$env:GITHUB_TOKEN = "..."
resilient-git --repo cloga/example --expected-account cloga -- push origin HEAD
```

The transport:

- verifies the token identity and repository permission through the GitHub API;
- fails fast for authentication, authorization, repository, and ref errors;
- retries only timeouts, connection resets, and transient HTTP 5xx failures;
- injects Git authorization through child-process environment config, not
  command-line arguments;
- writes an atomic, redacted attempt journal and uses an exclusive operation
  lock to prevent concurrent pushes;
- uses HTTP/1.1 and configurable command/connect timeouts.

Tokens are never persisted or printed. Callers remain responsible for token
storage and repository authorization.
