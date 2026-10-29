"""Terminal interface for the Liberty Browser runtime."""
from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from . import server
from .chrome import default_profile, launch_chrome


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="liberty-browser", description="Control a persistent local browser profile.")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("navigate", help="Open an HTTP(S) URL")
    p.add_argument("url")
    p = commands.add_parser("tabs", help="List or manage tabs")
    p.add_argument("action", nargs="?", choices=("list", "new", "select", "close"), default="list")
    p.add_argument("index", nargs="?", type=int, default=0)
    commands.add_parser("inspect", help="Inspect visible text and interactive elements")
    commands.add_parser("frames", help="List page frames")
    commands.add_parser("diagnostics", help="Check common browser rejection/challenge indicators")
    commands.add_parser("media", help="Inspect audio/video playback state")
    p = commands.add_parser("click", help="Click the first matching selector")
    p.add_argument("selector")
    p = commands.add_parser("fill", help="Fill a field; use --value-stdin for private values")
    p.add_argument("selector")
    value = p.add_mutually_exclusive_group(required=True)
    value.add_argument("value", nargs="?")
    value.add_argument("--value-stdin", action="store_true", help="Read the field value from stdin")
    p = commands.add_parser("press", help="Press a key on a matching element")
    p.add_argument("selector")
    p.add_argument("key")
    p = commands.add_parser("select-option", help="Choose a select option by value")
    p.add_argument("selector")
    p.add_argument("value")
    p = commands.add_parser("scroll", help="Scroll the current page")
    p.add_argument("--x", type=int, default=0)
    p.add_argument("--y", type=int, default=600)
    p = commands.add_parser("wait", help="Wait for a selector to become visible")
    p.add_argument("selector")
    p.add_argument("--timeout-ms", type=int, default=30000)
    p = commands.add_parser("screenshot", help="Save a full-page PNG")
    p.add_argument("--path", default="screenshot.png")
    commands.add_parser("back", help="Go back in history")
    commands.add_parser("forward", help="Go forward in history")
    commands.add_parser("reload", help="Reload the current page")
    commands.add_parser("shell", help="Keep a browser session open for multiple commands")
    p = commands.add_parser("login", help="Open installed Chrome for a person to sign in manually")
    p.add_argument("--profile", type=Path, default=None)
    p.add_argument("--url", default="https://accounts.google.com/")
    p = commands.add_parser("attach", help="Reopen the same profile with local CDP enabled for MCP control")
    p.add_argument("--profile", type=Path, default=None)
    p.add_argument("--port", type=int, default=9224)
    return parser


async def _dispatch(args: argparse.Namespace) -> Any:
    if args.command == "navigate": return await server.navigate(args.url)
    if args.command == "tabs": return await server.tabs(args.action, args.index)
    if args.command == "inspect": return await server.inspect_page()
    if args.command == "frames": return await server.inspect_frames()
    if args.command == "diagnostics": return await server.page_diagnostics()
    if args.command == "media": return await server.media_info()
    if args.command == "click": return await server.click(args.selector)
    if args.command == "fill":
        value = sys.stdin.read() if args.value_stdin else args.value
        return await server.fill(args.selector, value)
    if args.command == "press": return await server.press(args.selector, args.key)
    if args.command == "select-option": return await server.select_option(args.selector, args.value)
    if args.command == "scroll": return await server.scroll(args.x, args.y)
    if args.command == "wait": return await server.wait_for(args.selector, args.timeout_ms)
    if args.command == "screenshot": return await server.screenshot(args.path)
    if args.command in ("back", "forward", "reload"): return await server.history(args.command)
    if args.command == "login":
        pid = launch_chrome("login", profile=args.profile, login_url=args.url)
        return {"mode": "manual_login", "pid": pid, "next": "After signing in, close every window for this profile and run liberty-browser attach."}
    if args.command == "attach":
        pid = launch_chrome("attach", profile=args.profile, port=args.port)
        return {"mode": "cdp_control", "pid": pid, "endpoint": f"http://127.0.0.1:{args.port}", "next": "The Codex MCP can now connect to this Chrome session."}
    raise ValueError(f"Unsupported command: {args.command}")


def _print(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


async def _one_shot(args: argparse.Namespace) -> None:
    await server.browser()
    try:
        _print(await _dispatch(args))
    finally:
        await server.close_browser()


async def _shell(parser: argparse.ArgumentParser) -> None:
    print("Liberty Browser shell. Type help for commands; exit to close this session.")
    try:
        while True:
            try:
                line = input("liberty> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in {"exit", "quit"}:
                break
            if line.lower() == "help":
                parser.print_help()
                continue
            try:
                args = parser.parse_args(shlex.split(line))
                if args.command == "shell":
                    print("Already in the interactive shell.")
                    continue
                if args.command not in {"login", "attach"}:
                    await server.browser()
                _print(await _dispatch(args))
            except SystemExit:
                continue
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
    finally:
        await server.close_browser()


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.command in {"login", "attach"}:
            _print(asyncio.run(_dispatch(args)))
        elif args.command == "shell":
            asyncio.run(_shell(parser))
        else:
            asyncio.run(_one_shot(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"liberty-browser: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
