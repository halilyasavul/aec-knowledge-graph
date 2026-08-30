# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, use GitHub's private vulnerability reporting: go to the
repository's **Security** tab and click **Report a vulnerability**.
Alternatively, contact the maintainer directly (see the email in
`CITATION.cff`).

Include:

- A description of the vulnerability and its impact.
- Steps to reproduce.
- Any suggested fix, if you have one.

You can expect an acknowledgement within a week. Once fixed, the
vulnerability will be disclosed in the release notes with credit to the
reporter (unless you prefer to remain anonymous).

## Scope

Of particular interest:

- Bypasses of the read-only Cypher restriction in the chat agent's
  `run_cypher` tool (write operations reaching the database).
- Authentication bypasses on protected or admin API endpoints.
- Prompt-injection paths that cause the agent to expose credentials or
  perform destructive actions.

## Supported versions

Only the latest release receives security fixes.
