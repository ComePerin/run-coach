#!/usr/bin/env python3
"""Thin wrapper around the official COROS MCP helper (coroslab/COROS-MCP).

The official helper handles OAuth login, token refresh and the stateless MCP
transport. This wrapper adds: decoding of the double-encoded text payloads,
optional caching of raw responses, and a small CLI used by agents and plan.py.

Usage:
    python scripts/coros.py login            # print a browser login link (EU/US/CN auto)
    python scripts/coros.py login-finish     # wait for the browser login to complete
    python scripts/coros.py status           # check that the token works
    python scripts/coros.py tools [--refresh]
    python scripts/coros.py describe TOOL
    python scripts/coros.py call TOOL ['{"json": "args"}'] [--raw]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HELPER = (
    REPO_ROOT / ".vendor" / "COROS-MCP" / "skill" / "coros_mcp_login_gateway" / "scripts" / "coros_mcp_login.py"
)
CACHE_DIR = REPO_ROOT / ".cache" / "mcp"

WRITE_TOOLS = frozenset(
    {
        "createScheduledWorkout",
        "updateScheduledWorkout",
        "createSingleWorkout",
        "updateWorkoutDetails",
        "scheduleWorkout",
        "createTrainingPlan",
        "updateTrainingPlan",
    }
)


class CorosError(RuntimeError):
    """Raised when the helper fails or the MCP tool returns isError=true."""


def helper_path() -> Path:
    path = Path(os.environ.get("COROS_HELPER", DEFAULT_HELPER))
    if not path.exists():
        raise CorosError(f"COROS helper not found at {path}. Run scripts/setup.sh first (or set COROS_HELPER).")
    return path


def _run_helper(args: list[str], timeout: int = 180) -> str:
    cmd = [sys.executable, str(helper_path()), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        raise CorosError(f"helper {' '.join(args[:1])} failed: {msg[-1] if msg else 'unknown error'}")
    return proc.stdout


def decode_content(payload: dict[str, Any]) -> Any:
    """Return the tool output as a Python object.

    COROS returns ``content[0].text`` which is usually a JSON-encoded string
    (so it must be decoded twice) and sometimes a JSON object (lap data).
    """
    parts = []
    for item in payload.get("content", []):
        text = item.get("text", "")
        try:
            text = json.loads(text)
        except (TypeError, ValueError):
            pass
        parts.append(text)
    if len(parts) == 1:
        return parts[0]
    return parts


def call(tool: str, arguments: dict[str, Any] | None = None, *, cache: bool = True) -> Any:
    """Call a COROS MCP tool and return its decoded content.

    Text tools return a ``str``; structured tools (lap data) return ``dict``.
    """
    arguments = arguments or {}
    out = _run_helper(["call-tool", "--tool", tool, "--arguments-json", json.dumps(arguments)])
    try:
        payload = json.loads(out)
    except ValueError as exc:
        raise CorosError(f"unexpected helper output for {tool}: {out[:200]}") from exc
    if cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%dT%H%M%S")
        (CACHE_DIR / f"{stamp}-{tool}.json").write_text(json.dumps({"arguments": arguments, "response": payload}))
    result = decode_content(payload)
    if payload.get("isError"):
        raise CorosError(f"{tool} returned an error: {str(result)[:500]}")
    return result


def list_tools(refresh: bool = False) -> list[dict[str, Any]]:
    args = ["list-tools"] + (["--refresh"] if refresh else [])
    return json.loads(_run_helper(args))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="start browser login (prints a link)")
    p_finish = sub.add_parser("login-finish", help="wait for browser login to complete")
    p_finish.add_argument("--timeout", type=int, default=900)
    sub.add_parser("status", help="check that the saved login works")
    p_tools = sub.add_parser("tools", help="list tools (name, read/write)")
    p_tools.add_argument("--refresh", action="store_true")
    p_tools.add_argument("--json", action="store_true", help="full JSON schemas")
    p_desc = sub.add_parser("describe", help="show description and input schema of one tool")
    p_desc.add_argument("tool")
    p_call = sub.add_parser("call", help="call a tool")
    p_call.add_argument("tool")
    p_call.add_argument("arguments", nargs="?", default="{}", help="JSON object of arguments")
    p_call.add_argument("--raw", action="store_true", help="print raw MCP envelope")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "login":
            print(_run_helper(["login-start"]), end="")
        elif args.cmd == "login-finish":
            print(_run_helper(["login-finish", "--timeout", str(args.timeout)], timeout=args.timeout + 30), end="")
        elif args.cmd == "status":
            info = call("queryUserInfo", cache=False)
            nickname = next((ln.split(":", 1)[1].strip() for ln in str(info).splitlines() if ln.startswith("Nickname")), "?")
            print(f"COROS MCP OK — logged in as {nickname}")
        elif args.cmd == "tools":
            tools = list_tools(args.refresh)
            if args.json:
                print(json.dumps(tools, indent=2, ensure_ascii=False))
            else:
                for t in tools:
                    kind = "write" if not t.get("annotations", {}).get("readOnlyHint") else "read "
                    print(f"{kind}  {t['name']}")
        elif args.cmd == "describe":
            tool = next((t for t in list_tools() if t["name"] == args.tool), None)
            if tool is None:
                print(f"unknown tool {args.tool}", file=sys.stderr)
                return 1
            print(tool["description"])
            print(json.dumps(tool["inputSchema"], indent=2, ensure_ascii=False))
        elif args.cmd == "call":
            arguments = json.loads(args.arguments)
            if args.raw:
                print(_run_helper(["call-tool", "--tool", args.tool, "--arguments-json", json.dumps(arguments)]))
            else:
                result = call(args.tool, arguments)
                print(result if isinstance(result, str) else json.dumps(result, indent=1, ensure_ascii=False))
    except CorosError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
