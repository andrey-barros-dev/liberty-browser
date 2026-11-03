# Changelog

All notable changes to Liberty Browser are recorded here.

## Unreleased

- Preserve Chrome's configured download behavior when connecting over CDP.
- Launch MCP-controlled Chrome headlessly by default to avoid stealing desktop focus.
- Add MCP file uploads for hidden file inputs and page-triggered file choosers.
- Include hidden file inputs in page inspection and enforce a per-file upload size limit.

## 0.1.0 — 2026-10-28

- Initial open-source release of the Python CLI and MCP server.
- Added a dedicated persistent browser profile and a guarded Chrome CDP mode for Codex.
- Added first-action Chrome startup and CDP connection retries.
