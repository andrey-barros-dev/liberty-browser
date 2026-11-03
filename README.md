# Liberty Browser

[![Tests](https://github.com/andrey-barros-dev/liberty-browser/actions/workflows/ci.yml/badge.svg)](https://github.com/andrey-barros-dev/liberty-browser/actions/workflows/ci.yml)

Liberty Browser is a local Python MCP server and CLI that controls installed Google Chrome through Chrome DevTools Protocol (CDP), using a dedicated persistent profile.

## Open-web focus

Liberty Browser supports navigation across HTTP and HTTPS sites without a built-in website allowlist. Websites retain their own sign-in, verification, and access requirements.

## How it works

1. Run `liberty-browser login` to open installed Google Chrome with a dedicated profile for manual sign-in.
2. Close the Chrome windows using that profile.
3. Call an MCP browser tool. Liberty Browser starts the same Chrome profile with loopback CDP, waits for readiness, verifies the process and profile, and connects.

Playwright provides the CDP connection API. All browser actions use installed Google Chrome. Cookies and signed-in state remain in the local profile outside this repository.

## Requirements

- Windows
- Python 3.10 or newer
- Google Chrome installed

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install "git+https://github.com/andrey-barros-dev/liberty-browser.git"
.\.venv\Scripts\Activate.ps1
```

## MCP configuration

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

Use the absolute path to `.venv/Scripts/liberty-browser-mcp.exe` when the command is not on PATH. `liberty-browser-codex` is a compatibility alias for the same persistent Chrome MCP runtime. MCP messages use stdio.

## CLI

```powershell
liberty-browser login
liberty-browser tabs list
liberty-browser navigate https://example.com
liberty-browser inspect
liberty-browser shell
```

Browser actions automatically launch or reconnect to the dedicated Chrome profile. Closing the MCP connection leaves Chrome running.

Downloads triggered in Chrome use the download settings of the dedicated profile. Chrome handles download prompts, naming, and security checks.

## Upload files

Use inspect_page to find file inputs, including hidden input[type=file] controls. Then call the upload_file MCP tool with the input selector and one or more absolute local file paths. If the selector is a button that opens the file chooser, Liberty Browser captures that chooser and supplies the files directly through Playwright.

upload_file accepts up to 20 regular files at a time. The default per-file limit is 256 MiB; set BROWSER_MCP_MAX_UPLOAD_BYTES to change it. Selecting files makes them available to the current page, which may upload or process them, so call this tool only for files and destinations the user has requested.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `BROWSER_MCP_PROFILE` | Dedicated persistent Chrome profile | `%LOCALAPPDATA%/LibertyBrowser/profile` |
| `BROWSER_MCP_CDP_PORT` | Loopback CDP port | `9224` |
| `BROWSER_MCP_TIMEOUT_MS` | Browser action timeout | `10000` |

## Development

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
```

Tests use temporary Chrome profiles and local fixture pages. See [Architecture](ARCHITECTURE.md), [Contributing](CONTRIBUTING.md), and [Security](SECURITY.md).

## Privacy and security

The persistent profile contains browser session data. Keep it private and outside source control. A connected MCP client can act with that session's permissions. Website verification remains under the website's control.

## License

MIT. See [LICENSE](LICENSE).
