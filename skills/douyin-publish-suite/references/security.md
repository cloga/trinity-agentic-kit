# Security and policy boundary

This unofficial suite is not affiliated with or endorsed by the platform
vendor. Manual real-account mode may conflict with current terms, trigger
review, restrict an account, or stop working after site changes.

Required controls:

- use only the installed `douyin-publish` CLI and public package contracts;
- keep external profile configuration reviewed and versioned;
- let the operator complete visible-browser login personally;
- keep grants and saved sessions out of chat, logs, issues, and repositories;
- require one short-lived approval per exact request;
- use bounded commands and structured error handling;
- keep verification lookup-only;
- use Fake mode for offline contract tests.

Do not disguise the browser or operator, imitate human interaction, solve
platform safeguards, evade access controls, or automate approval.

This suite ships no site profile, authenticated state, content files, or
operator identity. Manual operation requires explicit authorization.
