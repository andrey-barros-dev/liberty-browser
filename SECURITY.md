# Security policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability or publish browser profile data, access tokens, cookies, or an exploit that exposes a live account. Use the repository's **Security → Advisories → Report a vulnerability** private reporting option. If that option is unavailable, contact the maintainers privately through GitHub before disclosing details.

## Sensitive data

Browser profiles can contain authenticated sessions. Keep profiles outside the repository and never upload them to issue trackers or public artifact storage. MCP clients and local debugging endpoints can act with the permissions of the connected browser session.
