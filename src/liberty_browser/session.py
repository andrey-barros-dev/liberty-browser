"""Start stdio MCP and verify the dedicated Chrome profile before connecting."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .chrome import default_profile
from .server import main as run_server


def _verify_chrome(port: int, profile: Path) -> bool:
    script = r'''
$ErrorActionPreference="Stop"
$portNumber=[int]$env:LIBERTY_EXPECTED_PORT
$profilePath=$env:LIBERTY_EXPECTED_PROFILE
$connections=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $portNumber -State Listen -ErrorAction SilentlyContinue)
if ($connections.Count -eq 0) { exit 2 }
if ($connections.Count -ne 1) { exit 6 }
$browserProcess=Get-CimInstance Win32_Process -Filter ("ProcessId=" + $connections[0].OwningProcess)
if ($null -eq $browserProcess -or $browserProcess.Name -ne 'chrome.exe' -or -not $browserProcess.CommandLine) { exit 3 }
$profilePattern=[regex]::Escape("--user-data-dir=$profilePath") + '(?:"|\s|$)'
$portPattern=[regex]::Escape("--remote-debugging-port=$portNumber") + '(?:"|\s|$)'
if ($browserProcess.CommandLine -notmatch $profilePattern) { exit 4 }
if ($browserProcess.CommandLine -notmatch $portPattern) { exit 5 }
'''
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            env=dict(os.environ, LIBERTY_EXPECTED_PORT=str(port), LIBERTY_EXPECTED_PROFILE=str(profile)),
            capture_output=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Could not verify the local Chrome debugging session.") from exc
    # A missing listener is recoverable: the MCP server can start Chrome lazily
    # when the first browser tool is called.
    if result.returncode == 2:
        return False
    if result.returncode:
        raise RuntimeError(
            f"A process on 127.0.0.1:{port} is not the expected Liberty Browser Chrome profile. "
            "Close it and run `liberty-browser attach` with the dedicated profile."
        )
    return True


def main() -> None:
    if os.name != "nt":
        print("The verified Chrome session launcher currently supports Windows only.", file=sys.stderr, flush=True)
        raise SystemExit(1)
    try:
        port = int(os.environ.get("BROWSER_MCP_CDP_PORT", "9224"))
        if not 1024 <= port <= 65535:
            raise ValueError
        profile = default_profile()
        profile.mkdir(parents=True, exist_ok=True)
        _verify_chrome(port, profile)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
    os.environ["BROWSER_MCP_CDP_URL"] = f"http://127.0.0.1:{port}"
    run_server()


if __name__ == "__main__":
    main()
