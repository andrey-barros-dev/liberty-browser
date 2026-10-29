# Liberty Browser

[![Tests](https://github.com/andrey-barros-dev/liberty-browser/actions/workflows/ci.yml/badge.svg)](https://github.com/andrey-barros-dev/liberty-browser/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

**Liberty Browser** is an open-source Python browser automation project with an MCP server for agent clients and a standalone terminal CLI. It uses Playwright and keeps a dedicated persistent browser profile.

> This project is an independent implementation. It is not affiliated with Google or the Chrome DevTools MCP project.

[Install](#install-from-a-source-checkout) · [CLI](#cli-examples) · [Persistent profile](#persistent-profile-and-browser-options) · [MCP](#use-as-an-mcp-server) · [Tests](#tests) · [Security](#privacy-and-security)

## What it provides

- Standard MCP over stdio, with tools for navigation, tabs, page inspection, forms, frames, screenshots, and media.
- A standalone CLI for one-off browser actions and interactive sessions.
- A dedicated persistent profile, with a guarded local Chrome CDP connection for Codex.
- Automatic Chrome startup and short retries on the first browser action when the CDP connection is not ready yet.

## Requirements

- Python 3.10 or newer
- Windows, macOS, or Linux
- Chromium installed by Playwright, or a compatible local browser

## Install from a source checkout

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m playwright install chromium
```

Activate the environment so the commands are available in your PowerShell session:

```powershell
.\.venv\Scripts\Activate.ps1
```

The package installs three commands:

- `liberty-browser-mcp` starts the MCP server over stdio with its normal Playwright-managed browser.
- `liberty-browser-codex` starts the stdio server, launches the dedicated Chrome profile on the first browser action when needed, and verifies the local debugging connection.
- `liberty-browser` controls browser actions from a terminal and provides the manual sign-in/Chrome attach steps.

The Codex CDP launcher currently supports Windows. The generic stdio server and CLI can also be used on macOS and Linux.

On macOS/Linux, activate `.venv` and use `python -m pip install .` and `python -m playwright install chromium`.

## CLI examples

```powershell
liberty-browser navigate https://example.com
liberty-browser inspect
liberty-browser click "text=More information"
liberty-browser fill "#search" "browser tools"
liberty-browser press "#search" Enter
liberty-browser tabs list
liberty-browser tabs new
liberty-browser screenshot --path .\page.png
liberty-browser back
liberty-browser shell
```

A one-shot command starts the configured browser, performs one action, prints JSON, then closes a browser it owns. Cookies and local storage remain in the dedicated profile. Use `liberty-browser shell` to keep one browser process and page session open across multiple commands; enter `help` for command syntax and `exit` to close it. To avoid putting a private form value in shell history, pipe it through stdin:

```powershell
Get-Content .\private-value.txt -Raw | liberty-browser fill "input[name=email]" --value-stdin
```

Keep private value files out of source control and delete them when no longer needed.

## Persistent profile and browser options

By default, Liberty Browser creates a new profile at `%LOCALAPPDATA%\LibertyBrowser\profile` on Windows and `~/.liberty-browser/profile` elsewhere. The repository and installable package contain no browser profile, cookies, credentials, or session data. On first use, sign in to accounts yourself in the visible browser. Use a dedicated profile directory; do not point it at a profile currently open in Chrome.

### Manual sign-in in Chrome on Windows

For accounts that reject automation-controlled browser windows, use the installed Chrome application for sign-in. This keeps the project free of account data while allowing the owner to create their own local session:

1. Run `liberty-browser login`. Chrome opens with a new Liberty Browser profile and no remote-debugging flag. Sign in yourself in that window.
2. Close every Chrome window using that profile.
3. On the first browser action, the Codex MCP starts Chrome with that same profile and waits for its loopback-only CDP endpoint (default `9224`). You can still run `liberty-browser attach` yourself if you prefer to start it manually.

Never run both Chrome modes against the same profile at the same time. Do not copy an existing Chrome profile into this project. The session guard rejects a different process or profile and does not silently fall back to Playwright.

The stdio MCP server starts even when Chrome is not open, so Codex can complete MCP initialization and discover its tools. On the first browser action it starts the dedicated Chrome profile if needed, waits for CDP, and retries short connection races. If another process owns the configured CDP port or the profile is already open in a different Chrome mode, the server rejects the connection with an actionable error.

Options are supplied through environment variables. For example, to choose a fresh Windows profile location:

```powershell
$env:BROWSER_MCP_PROFILE = Join-Path $env:LOCALAPPDATA 'LibertyBrowser\profile'
```


| Variable | Purpose | Default |
| --- | --- | --- |
| `BROWSER_MCP_PROFILE` | Persistent profile path | `%LOCALAPPDATA%\LibertyBrowser\profile` on Windows; `~/.liberty-browser/profile` elsewhere |
| `BROWSER_MCP_ENGINE` | `chromium` or `firefox` | `chromium` |
| `BROWSER_MCP_HEADLESS` | Set to `1` for headless mode | `0` |
| `BROWSER_MCP_CHANNEL` | Playwright Chromium channel, e.g. `chrome` | Playwright Chromium |
| `BROWSER_MCP_TIMEOUT_MS` | Action timeout | `10000` |
| `BROWSER_MCP_CDP_URL` | Attach to a local Chrome DevTools endpoint | unset |

When attaching over CDP, the server validates that the endpoint is local; `close_browser` disconnects and leaves the externally managed Chrome running.

Sign in manually in the visible browser. The project does not store passwords or bypass CAPTCHA, anti-bot systems, account protections, or site access rules. A website can reject an automation-controlled browser; no tool can guarantee acceptance by every site. Diagnostics only report heuristic indicators and do not prove authentication.

## Use as an MCP server

The server uses stdio, so it can be launched by any MCP-compatible host. You can run it directly without adding it to Codex:

```powershell
liberty-browser-mcp
```

Generic MCP configuration for the Playwright-managed browser:

```json
{
  "mcpServers": {
    "liberty-browser": {
      "command": "liberty-browser-mcp",
      "args": []
    }
  }
}
```

For an isolated Python environment, use the absolute path to `.venv\Scripts\liberty-browser-mcp.exe` as `command`. The server's standard output is reserved for MCP messages; logs and errors go to standard error.

For the dedicated Chrome profile in Codex, configure `liberty-browser-codex` as the stdio command, with `BROWSER_MCP_PROFILE` set to the dedicated profile directory and `BROWSER_MCP_CDP_PORT` set to `9224`. Sign in through `liberty-browser login` once, close that Chrome window, then the first MCP browser action launches Chrome in CDP mode automatically. Do not run the generic Playwright server against the same account profile.

Example Codex configuration:

```toml
[mcp_servers.liberty-browser]
command = "liberty-browser-codex"
args = []
env = { BROWSER_MCP_PROFILE = "C:/Users/you/AppData/Local/LibertyBrowser/profile", BROWSER_MCP_CDP_PORT = "9224" }
```

If the command is not on `PATH`, set `command` to the absolute path of `.venv/Scripts/liberty-browser-codex.exe`.

## Tests

Install test dependencies and run the suite:

```powershell
python -m pip install -e ".[test]"
python -m playwright install chromium
python -m pytest
```

Tests use a temporary profile and a local test page. They do not access real accounts, reuse a personal profile, or attempt to solve challenges.

## Privacy and security

The browser profile contains cookies, local storage, and potentially signed-in sessions. Treat it as private data, exclude it from backups or public repositories unless protected, and never share it. A connected MCP client can act as the signed-in user. Keep the debugging endpoint bound to localhost and use this software only with accounts and sites you are authorized to access.

## License

MIT. See [LICENSE](LICENSE).
