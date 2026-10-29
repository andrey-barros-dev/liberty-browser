from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import sysconfig
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from liberty_browser.chrome import launch_chrome

HTML = b'''<!doctype html><title>Liberty smoke test</title><label>Name <input id="name"></label><button id="save" onclick="localStorage.setItem('saved',document.querySelector('#name').value);document.querySelector('#result').textContent=document.querySelector('#name').value">Save</button><div id="result"></div><script>document.querySelector('#result').textContent=localStorage.getItem('saved')||''</script>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML)
    def log_message(self, *_args):
        pass

class ProductSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}/"
        self.tmp = tempfile.TemporaryDirectory(prefix="liberty-browser-test-")
        self.env = dict(os.environ)
        for name in ("BROWSER_MCP_CDP_URL", "BROWSER_SESSION_PORT", "BROWSER_SESSION_PROFILE"):
            self.env.pop(name, None)
        import socket
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.env.update(BROWSER_MCP_PROFILE=str(Path(self.tmp.name).resolve()), BROWSER_MCP_CDP_PORT=str(port), BROWSER_MCP_TIMEOUT_MS="15000")

    async def asyncTearDown(self):
        self.http.shutdown()
        self.http.server_close()
        script = r"""$pattern=[regex]::Escape("--user-data-dir="+$env:BROWSER_MCP_PROFILE)+'(?:"|\s|$)'
$processes=@(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -match $pattern })
foreach ($browserProcess in $processes) {
    taskkill /PID $browserProcess.ProcessId /T /F 2>$null | Out-Null
}
"""
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script], env=self.env, capture_output=True, timeout=20)
        # Windows can release Chrome's profile locks after the process exits.
        # Retry cleanup, and still fail the test if files remain locked.
        for attempt in range(20):
            try:
                self.tmp.cleanup()
                break
            except OSError:
                if attempt == 19:
                    raise
                await asyncio.sleep(0.5)

    async def test_installed_cli_shell_navigate_fill_click_and_inspect(self):
        proc = await asyncio.create_subprocess_exec(
            str(Path(sysconfig.get_path("scripts")) / ("liberty-browser.exe" if os.name == "nt" else "liberty-browser")), "shell",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=self.env,
        )
        commands = f'navigate {self.url}\nfill #name "MCP test"\nclick #save\ninspect\nexit\n'.encode()
        stdout, stderr = await asyncio.wait_for(proc.communicate(commands), timeout=90)
        self.assertEqual(proc.returncode, 0, stderr.decode(errors="replace"))
        self.assertNotIn(b"Error:", stderr, stderr.decode(errors="replace"))
        self.assertIn(b"Liberty smoke test", stdout)
        self.assertIn(b"MCP test", stdout)

    async def test_installed_mcp_stdio_protocol_and_browser_actions(self):
        params = StdioServerParameters(command=str(Path(sysconfig.get_path("scripts")) / ("liberty-browser-mcp.exe" if os.name == "nt" else "liberty-browser-mcp")), args=[], env=self.env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                self.assertIn("navigate", {tool.name for tool in tools.tools})
                nav = await session.call_tool("navigate", {"url": self.url})
                self.assertFalse(nav.isError, nav)
                import statistics
                import time
                fill_times, click_times = [], []
                for i in range(20):
                    started = time.perf_counter()
                    filled = await session.call_tool("fill", {"selector": "#name", "value": f"MCP action {i}"})
                    fill_times.append((time.perf_counter() - started) * 1000)
                    self.assertFalse(filled.isError, filled)
                    started = time.perf_counter()
                    clicked = await session.call_tool("click", {"selector": "#save"})
                    click_times.append((time.perf_counter() - started) * 1000)
                    self.assertFalse(clicked.isError, clicked)
                self.assertLess(statistics.median(fill_times), 1000)
                self.assertLess(statistics.median(click_times), 1000)
                page = await session.call_tool("inspect_page", {})
                self.assertIn("MCP action 19", str(page.content))
                await session.call_tool("close_browser", {})
                await session.call_tool("navigate", {"url": self.url})
                restored = await session.call_tool("inspect_page", {})
                self.assertIn("MCP action 19", str(restored.content))

class CliHelpTests(unittest.TestCase):
    def test_cli_help_runs_without_codex_registration(self):
        result = subprocess.run([sys.executable, "-m", "liberty_browser.cli", "--help"], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("navigate", result.stdout)
        self.assertIn("shell", result.stdout)

class ChromeHandoffTests(unittest.TestCase):
    @patch("liberty_browser.chrome.subprocess.Popen")
    @patch("liberty_browser.chrome._assert_profile_closed")
    @patch("liberty_browser.chrome.find_chrome", return_value=Path("C:/Program Files/Google/Chrome/Application/chrome.exe"))
    def test_login_mode_is_plain_chrome_and_attach_mode_is_local_cdp(self, _chrome, _profile, popen):
        with tempfile.TemporaryDirectory() as profile:
            launch_chrome("login", profile=Path(profile))
            login_args = popen.call_args.args[0]
            self.assertIn("https://accounts.google.com/", login_args)
            self.assertFalse(any(arg.startswith("--remote-debugging-") for arg in login_args))
            import socket
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            launch_chrome("attach", profile=Path(profile), port=port)
            attach_args = popen.call_args.args[0]
            self.assertIn(f"--remote-debugging-port={port}", attach_args)
            self.assertIn("--remote-debugging-address=127.0.0.1", attach_args)

if __name__ == "__main__":
    unittest.main()
