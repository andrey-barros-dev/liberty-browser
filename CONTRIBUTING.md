# Contributing

Thanks for considering a contribution. Keep changes focused and preserve the separation between the MCP stdio server and the standalone CLI.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q
```

Tests must use temporary browser profiles and local fixture pages. Do not include browser profiles, credentials, cookies, screenshots of private accounts, test outputs, or personal data in commits. Never design tests that attempt to evade CAPTCHA, bot checks, or account protections.

## Pull requests

Describe the user-visible change and how it was tested. Update the README when commands, configuration, or privacy behavior change. Keep dependencies pinned unless a tested update is part of the change.
