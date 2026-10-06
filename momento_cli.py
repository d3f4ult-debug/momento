#!/usr/bin/env python3
"""
Momento Control CLI & Local Client
==================================
Command-line interface and local client for Momento.
Connects local workflows to the remote Momento VPS Sandbox backend.

Usage:
    momento setup [--force]
    momento shell
    momento open <app_name> [--args ...]
    momento run <app_name> [--args ...]
    momento scan [--json]
    momento launch <path/to/binary.exe> [--args ...] [--timeout 300] [--use-wine]
    momento inspect <session_id> [--json]
    momento sessions [--json]
    momento stop <session_id> [--force]
    momento execute <session_id> <command>
    momento "Momento, open notepad"
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.config import (
    DEFAULT_BACKEND_URL,
    get_backend_url,
    is_setup_completed,
    load_config,
    save_config
)
from client.nlp_router import NLPRouter
from client.onboarding import run_onboarding
from client.scanner import AppScanner
from client.shell import start_interactive_shell

DEFAULT_API_URL = os.environ.get("MOMENTO_API_URL", DEFAULT_BACKEND_URL)


def make_api_request(
    url: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 15
) -> Dict[str, Any]:
    """Execute an HTTP request against the Momento backend API."""
    req_data = None
    headers = {"Accept": "application/json"}
    if data is not None:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                return json.loads(body)
            except Exception:
                return {"success": True, "raw_response": body}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.fp else ""
        try:
            parsed = json.loads(err_body)
            return parsed
        except Exception:
            return {
                "success": False,
                "error": f"HTTP {e.code}: {e.reason}",
                "details": err_body
            }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"Failed to connect to Momento server at {url}: {e.reason}. Is the server running?"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def cmd_launch(args: argparse.Namespace, api_url: str) -> int:
    """Launch a binary inside an isolated sandbox session."""
    url = f"{api_url.rstrip('/')}/api/sandbox/launch"
    payload: Dict[str, Any] = {
        "binary_path": args.binary_path,
        "timeout": args.timeout
    }
    if args.args:
        payload["args"] = args.args.strip() if isinstance(args.args, str) else " ".join(args.args)
    if args.use_wine is not None:
        payload["use_wine"] = args.use_wine

    res = make_api_request(url, method="POST", data=payload)
    if res.get("success"):
        print("[*] Sandbox session launched successfully:")
        print(f"    Session ID:  {res.get('session_id')}")
        print(f"    PID:         {res.get('pid')}")
        print(f"    Runtime:     {res.get('runtime')}")
        print(f"    Status:      {res.get('status')}")
        print(f"    Binary:      {res.get('binary_path')}")
        if res.get("working_dir"):
            print(f"    Sandbox Dir: {res.get('working_dir')}")
        return 0
    else:
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Failed to launch binary: {err}", file=sys.stderr)
        return 1


def cmd_inspect(args: argparse.Namespace, api_url: str) -> int:
    """Inspect telemetry, active window, and UI hierarchy of a session or desktop."""
    target = getattr(args, "session_id", None)

    # If target is not a remote VPS session ID, inspect locally via DesktopAppBridge
    if not target or not target.startswith("sbx_vps_"):
        from client.desktop_bridge import DesktopAppBridge
        bridge = DesktopAppBridge(backend_url=api_url)
        res = bridge.send_message(f"inspect {target or 'active'}")
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
            return 0 if res.get("success") else 1
        msg = res.get("message", "")
        if msg:
            print(msg)
        return 0 if res.get("success") else 1

    url = f"{api_url.rstrip('/')}/api/sandbox/inspect"
    payload = {"session_id": target}
    res = make_api_request(url, method="POST", data=payload)

    if not res.get("success"):
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Inspection failed: {err}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0


def cmd_windows(args: argparse.Namespace, api_url: str) -> int:
    """List active visible desktop application windows."""
    from client.desktop_bridge import DesktopAppBridge
    bridge = DesktopAppBridge(backend_url=api_url)
    res = bridge.send_message("list active windows")
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0 if res.get("success") else 1
    msg = res.get("message", "")
    if msg:
        print(msg)
    return 0 if res.get("success") else 1

    print(f"[*] Session Inspection: {res.get('session_id')}")
    print(f"    Status:         {res.get('status')}")
    print(f"    PID:            {res.get('pid')}")
    print(f"    Runtime:        {res.get('runtime')}")
    print(f"    Uptime:         {res.get('uptime_seconds', 0):.1f}s")

    metrics = res.get("metrics", {})
    if metrics:
        cpu = metrics.get("cpu_percent", 0.0)
        mem = metrics.get("memory_mb", 0.0)
        threads = metrics.get("num_threads", 0)
        print(f"    CPU Usage:      {cpu}%")
        print(f"    Memory:         {mem} MB")
        print(f"    Threads:        {threads}")

    files = res.get("file_interactions", [])
    print(f"    Files Tracked:  {len(files)}")
    if files:
        for f in files[:5]:
            fname = f.get("file_name", "")
            fsize = f.get("size_bytes", 0)
            print(f"      - {fname} ({fsize} bytes)")
        if len(files) > 5:
            print(f"      ... and {len(files) - 5} more")

    stdout = res.get("recent_stdout", [])
    if stdout:
        print("    Recent Stdout:")
        for line in stdout[-5:]:
            print(f"      | {line}")
    return 0


def cmd_sessions(args: argparse.Namespace, api_url: str) -> int:
    """List all tracked sandbox sessions."""
    url = f"{api_url.rstrip('/')}/api/sandbox/sessions"
    res = make_api_request(url, method="GET")

    if not res.get("success", False) and "sessions" not in res:
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Failed to list sessions: {err}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0

    sessions = res.get("sessions", [])
    total = res.get("total_sessions_count", len(sessions))
    print(f"[*] Momento Sandbox Sessions ({total} total):")
    if not sessions:
        print("    No active sessions found.")
        return 0

    header = f"{'SESSION ID':<18} {'PID':<8} {'STATUS':<12} {'RUNTIME':<10} {'BINARY'}"
    print(f"    {header}")
    print(f"    {'-' * len(header)}")
    for s in sessions:
        s_id = s.get("session_id", "N/A")
        pid = str(s.get("pid", "N/A"))
        status = s.get("status", "N/A")
        runtime = s.get("runtime", "N/A")
        bin_path = s.get("binary_path", "N/A")
        if len(bin_path) > 40:
            bin_path = "..." + bin_path[-37:]
        print(f"    {s_id:<18} {pid:<8} {status:<12} {runtime:<10} {bin_path}")
    return 0


def cmd_stop(args: argparse.Namespace, api_url: str) -> int:
    """Terminate or kill a sandbox session."""
    url = f"{api_url.rstrip('/')}/api/sandbox/stop"
    payload = {
        "session_id": args.session_id,
        "force": args.force
    }
    res = make_api_request(url, method="POST", data=payload)
    if res.get("success"):
        mode = "force killed" if args.force else "terminated"
        print(f"[*] Session {args.session_id} successfully {mode}.")
        return 0
    else:
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Failed to stop session {args.session_id}: {err}", file=sys.stderr)
        return 1


def cmd_execute(args: argparse.Namespace, api_url: str) -> int:
    """Execute a deterministic inspection command inside a sandbox session."""
    url = f"{api_url.rstrip('/')}/api/sandbox/execute"
    payload = {
        "session_id": args.session_id,
        "command": args.cmd
    }
    res = make_api_request(url, method="POST", data=payload)
    if res.get("success"):
        exit_code = res.get("exit_code", 0)
        latency = res.get("latency_ms", 0.0)
        print(f"[*] Executed command in session {args.session_id} (exit: {exit_code}, latency: {latency:.1f}ms):")
        out = res.get("output", "")
        if out:
            print(out)
        return 0
    else:
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Execution failed: {err}", file=sys.stderr)
        return 1


def cmd_setup(args: argparse.Namespace, api_url: str) -> int:
    """Run onboarding and permission setup wizard."""
    success = run_onboarding(
        force=getattr(args, "force", False),
        non_interactive=getattr(args, "non_interactive", False),
        backend_url=api_url
    )
    return 0 if success else 1


def cmd_shell(args: argparse.Namespace, api_url: str) -> int:
    """Start interactive conversational Momento shell."""
    return start_interactive_shell(backend_url=api_url)


def cmd_scan(args: argparse.Namespace, api_url: str) -> int:
    """Scan and catalog local applications into registry."""
    scanner = AppScanner()
    reg = scanner.scan_environment()
    if getattr(args, "json", False):
        print(json.dumps(reg, indent=2))
        return 0

    apps = reg.get("apps", {})
    total = reg.get("total_apps", len(apps))
    print(f"[*] Local Environment Scan Complete ({total} applications discovered):")
    print(f"    Registry: {scanner.registry_file}\n")
    header = f"{'APP ID':<16} {'NAME':<24} {'CATEGORY':<12} {'BINARY PATH'}"
    print(f"    {header}")
    print(f"    {'-' * len(header)}")
    for app_id, app in sorted(apps.items())[:30]:
        name = app.get("name", app_id)
        cat = app.get("category", "utility")
        bpath = app.get("binary_path", "")
        if len(bpath) > 40:
            bpath = "..." + bpath[-37:]
        print(f"    {app_id:<16} {name:<24} {cat:<12} {bpath}")
    if len(apps) > 30:
        print(f"\n    ... and {len(apps) - 30} more applications indexed.")
    return 0


def cmd_open_or_run(args: argparse.Namespace, api_url: str) -> int:
    """Resolve application from local registry and launch via hybrid/local execution."""
    from client.desktop_bridge import DesktopAppBridge
    bridge = DesktopAppBridge(backend_url=api_url)
    app_query = args.app_name
    if getattr(args, "args", None):
        app_query += f" with args {' '.join(args.args)}"
    res = bridge.send_message(f"open {app_query}", execution_mode="hybrid")
    msg = res.get("message", "")
    if res.get("success"):
        if msg:
            print(msg)
        return 0
    else:
        if msg:
            print(f"[!] {msg}", file=sys.stderr)
        return 1


def cmd_ask(args: argparse.Namespace, api_url: str) -> int:
    """Process natural language conversational command."""
    from client.desktop_bridge import DesktopAppBridge
    bridge = DesktopAppBridge(backend_url=api_url)
    mode = getattr(args, "mode", "hybrid") or "hybrid"
    res = bridge.send_message(args.query, execution_mode=mode)
    if getattr(args, "json", False):
        print(json.dumps(res))
        return 0 if res.get("success") else 1
    msg = res.get("message", "")
    if res.get("success"):
        if msg:
            print(msg)
        return 0
    else:
        if msg:
            print(f"[!] {msg}", file=sys.stderr)
        return 1


def cmd_chat(args: argparse.Namespace, api_url: str) -> int:
    """Process natural language conversational command using DesktopAppBridge."""
    from client.desktop_bridge import DesktopAppBridge
    bridge = DesktopAppBridge(backend_url=api_url)
    mode = getattr(args, "mode", "hybrid") or "hybrid"
    res = bridge.send_message(args.query, execution_mode=mode)
    if getattr(args, "json", False):
        print(json.dumps(res))
        return 0 if res.get("success") else 1
    msg = res.get("message", "")
    if res.get("success"):
        if msg:
            print(msg)
        return 0
    else:
        if msg:
            print(f"[!] {msg}", file=sys.stderr)
def cmd_register(args: argparse.Namespace, api_url: str) -> int:
    """Manually register a custom application into the local registry."""
    from client.desktop_bridge import DesktopAppBridge
    bridge = DesktopAppBridge(backend_url=api_url)
    res = bridge.register_app(
        name=args.name,
        binary_path=args.binary_path,
        aliases=args.aliases,
        category=getattr(args, "category", "custom"),
        working_dir=getattr(args, "working_dir", None),
        args=getattr(args, "args", None),
        data_file_path=getattr(args, "data_file", None),
    )
    if getattr(args, "json", False):
        print(json.dumps(res))
        return 0 if res.get("success") else 1
    msg = res.get("message", "")
    if res.get("success"):
        if msg:
            print(msg)
        return 0
    else:
        if msg:
            print(f"[!] {msg}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="momento",
        description="Momento Control CLI & Local Client - Host runtime & process inspection"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"Base URL of Momento API (default: {DEFAULT_API_URL} or $MOMENTO_API_URL)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # setup
    p_setup = subparsers.add_parser("setup", help="Run initial onboarding & permission setup wizard")
    p_setup.add_argument("--force", action="store_true", help="Force rerun onboarding even if completed")
    p_setup.add_argument("--non-interactive", action="store_true", help="Run onboarding without prompts")

    # shell
    subparsers.add_parser("shell", help="Start conversational interactive shell")

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan and catalog local applications into registry")
    p_scan.add_argument("--json", action="store_true", help="Output raw registry JSON")

    # open
    p_open = subparsers.add_parser("open", help="Resolve application and launch on VPS core")
    p_open.add_argument("app_name", help="Name or alias of application (e.g. notepad, calc, chrome)")
    p_open.add_argument("--args", nargs="*", default=None, help="Arguments to pass to application")

    # run
    p_run = subparsers.add_parser("run", help="Alias for open: resolve and run application")
    p_run.add_argument("app_name", help="Name or alias of application")
    p_run.add_argument("--args", nargs="*", default=None, help="Arguments to pass to application")

    # ask
    p_ask = subparsers.add_parser("ask", help="Send conversational command to Momento")
    p_ask.add_argument("query", help="Conversational query (e.g. 'Momento, open notepad')")
    p_ask.add_argument("--mode", default="hybrid", choices=["hybrid", "local", "vps"], help="Execution mode (default: hybrid)")
    p_ask.add_argument("--json", action="store_true", help="Output raw JSON response")

    # chat
    p_chat = subparsers.add_parser("chat", help="Send conversational command via desktop bridge (local/hybrid/vps)")
    p_chat.add_argument("query", help="Conversational query (e.g. 'Momento, open notepad')")
    p_chat.add_argument("--mode", default="hybrid", choices=["hybrid", "local", "vps"], help="Execution mode (default: hybrid)")
    p_chat.add_argument("--json", action="store_true", help="Output raw JSON response")

    # register
    p_reg = subparsers.add_parser("register", help="Register a custom application into the local registry")
    p_reg.add_argument("name", help="Display name of the application")
    p_reg.add_argument("binary_path", help="Path to application binary/executable")
    p_reg.add_argument("--aliases", nargs="*", default=None, help="Optional search aliases")
    p_reg.add_argument("--category", default="custom", help="Application category (default: custom)")
    p_reg.add_argument("--working-dir", "-w", default=None, help="Working directory for the application")
    p_reg.add_argument("--args", "-a", default=None, help="Default arguments to pass to the binary")
    p_reg.add_argument("--data-file", "-d", default=None, help="Associated data file path (e.g. database or config)")
    p_reg.add_argument("--json", action="store_true", help="Output raw JSON response")

    # launch
    p_launch = subparsers.add_parser("launch", help="Launch a binary inside an isolated sandbox session")
    p_launch.add_argument("binary_path", help="Path to executable or binary (e.g. app.exe or script)")
    p_launch.add_argument("--args", type=str, default=None, help="Arguments to pass to the binary")
    p_launch.add_argument("--timeout", type=int, default=300, help="Execution timeout in seconds (default: 300)")
    p_launch.add_argument("--use-wine", dest="use_wine", action="store_true", default=None, help="Force execution with Wine/Proton")
    p_launch.add_argument("--no-wine", dest="use_wine", action="store_false", help="Disable Wine wrapper")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect active application window, UI hierarchy, or session telemetry")
    p_inspect.add_argument("session_id", nargs="?", default=None, help="Optional session ID or app name to inspect (defaults to active foreground window)")
    p_inspect.add_argument("--json", action="store_true", help="Output raw JSON response")

    # windows
    p_windows = subparsers.add_parser("windows", help="List active visible desktop application windows")
    p_windows.add_argument("--json", action="store_true", help="Output raw JSON response")

    # sessions
    p_sessions = subparsers.add_parser("sessions", help="List all tracked sandbox sessions")
    p_sessions.add_argument("--json", action="store_true", help="Output raw JSON response")

    # stop
    p_stop = subparsers.add_parser("stop", help="Stop or kill a sandbox session")
    p_stop.add_argument("session_id", help="Session ID to stop")
    p_stop.add_argument("--force", action="store_true", default=False, help="Force kill immediately")

    # execute
    p_exec = subparsers.add_parser("execute", help="Execute an inspection command inside session sandbox")
    p_exec.add_argument("session_id", help="Session ID")
    p_exec.add_argument("cmd", help="Command string to execute")

    return parser


def preprocess_argv(argv: Optional[list]) -> Optional[list]:
    """Preprocess arguments to allow clean flag and argument passing under --args."""
    if argv is None:
        raw = sys.argv[1:]
    else:
        raw = list(argv)

    if not raw:
        return raw

    # If first argument is a conversational sentence like "Momento, open notepad" or "what is on screen"
    if len(raw) == 1 and not raw[0].startswith("-"):
        first = raw[0].strip().lower()
        if any(first.startswith(p) for p in ("momento", "hey momento", "open ", "run ", "launch ", "start ", "stop ", "inspect", "what", "list ")):
            return ["ask", raw[0]]

    # If launch command is present with --args
    if "launch" in raw and "--args" in raw:
        new_argv = []
        i = 0
        known_flags = {"--timeout", "--use-wine", "--no-wine", "--url", "--help", "-h"}
        while i < len(raw):
            if raw[i] == "--args":
                i += 1
                collected = []
                while i < len(raw) and raw[i] not in known_flags:
                    collected.append(raw[i])
                    i += 1
                new_argv.append(f"--args={' '.join(collected)}")
            else:
                new_argv.append(raw[i])
                i += 1
        return new_argv

    return raw


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    processed_argv = preprocess_argv(argv)
    try:
        args = parser.parse_args(processed_argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0

    if not args.command:
        # If running in non-interactive/automated environment without args, show help
        if not sys.stdin.isatty():
            parser.print_help()
            return 0

        # Interactive default: onboarding if needed, otherwise shell
        if not is_setup_completed():
            success = run_onboarding(backend_url=args.url)
            return 0 if success else 1
        else:
            return start_interactive_shell(backend_url=args.url)

    api_url = args.url

    commands = {
        "setup": cmd_setup,
        "shell": cmd_shell,
        "scan": cmd_scan,
        "open": cmd_open_or_run,
        "run": cmd_open_or_run,
        "ask": cmd_ask,
        "chat": cmd_chat,
        "register": cmd_register,
        "launch": cmd_launch,
        "inspect": cmd_inspect,
        "windows": cmd_windows,
        "sessions": cmd_sessions,
        "stop": cmd_stop,
        "execute": cmd_execute
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, api_url)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
