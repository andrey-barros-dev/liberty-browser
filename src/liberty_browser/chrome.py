"""Launch a dedicated Chrome profile for manual sign-in and MCP control."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse


def default_profile() -> Path:
    windows_default = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "LibertyBrowser" / "profile"
    default = windows_default if os.name == "nt" else Path.home() / ".liberty-browser" / "profile"
    return Path(os.environ.get("BROWSER_MCP_PROFILE", str(default))).expanduser().resolve()


def find_chrome() -> Path:
    if os.name == "nt":
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
        candidates = [Path(root) / "Google/Chrome/Application/chrome.exe" for root in roots if root]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeError("Google Chrome was not found. Install Chrome or set BROWSER_MCP_CHROME_PATH.")
    configured = os.environ.get("BROWSER_MCP_CHROME_PATH")
    found = configured or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return Path(found).expanduser().resolve()
    raise RuntimeError("Chrome/Chromium was not found. Set BROWSER_MCP_CHROME_PATH.")


def _assert_profile_closed(profile: Path) -> None:
    if os.name != "nt":
        return
    script = r'''
$ErrorActionPreference="Stop"
$profilePath=$env:LIBERTY_PROFILE_TO_CHECK
$pattern=[regex]::Escape("--user-data-dir=$profilePath") + '(?:"|\s|$)'
$matches=@(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine -match $pattern })
if ($matches.Count) { exit 1 }
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        env=dict(os.environ, LIBERTY_PROFILE_TO_CHECK=str(profile)),
        capture_output=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("Close every Chrome window using the Liberty Browser profile before switching modes.")


def launch_chrome(mode: str, *, profile: Path | None = None, port: int = 9224, login_url: str = "https://accounts.google.com/") -> int:
    if mode not in {"login", "attach"}:
        raise ValueError("mode must be login or attach")
    parsed = urlparse(login_url)
    if mode == "login" and parsed.scheme not in {"http", "https"}:
        raise ValueError("login_url must use HTTP(S)")
    if not 1024 <= port <= 65535:
        raise ValueError("port must be between 1024 and 65535")
    profile = (profile or default_profile()).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    _assert_profile_closed(profile)
    args = ["--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check"]
    if mode == "login":
        args.append(login_url)
    else:
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise RuntimeError(f"Local port {port} is already in use.") from exc
        args.extend((f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1", "about:blank"))
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen([str(find_chrome()), *args], close_fds=True, creationflags=flags)
    return process.pid
