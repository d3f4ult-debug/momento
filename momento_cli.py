#!/usr/bin/env python3
"""
Momento Control CLI
===================
Command-line interface for the Momento Windows Sandbox and Process Inspector.
Communicates with the local FastAPI backend (/api/sandbox/...) over HTTP.

Usage:
    momento launch <path/to/binary.exe> [--args ...] [--timeout 300] [--use-wine]
    momento inspect <session_id> [--json]
    momento sessions [--json]
    momento stop <session_id> [--force]
    momento execute <session_id> <command>
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_API_URL = os.environ.get("MOMENTO_API_URL", "http://127.0.0.1:8000")


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
    """Inspect telemetry and runtime status of a sandbox session."""
    url = f"{api_url.rstrip('/')}/api/sandbox/inspect"
    payload = {"session_id": args.session_id}
    res = make_api_request(url, method="POST", data=payload)

    if not res.get("success"):
        err = res.get("error") or res.get("detail") or "Unknown error"
        print(f"[!] Inspection failed: {err}", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
        return 0

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


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="momento",
        description="Momento Control CLI - Host runtime & process inspection client"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"Base URL of Momento API (default: {DEFAULT_API_URL} or $MOMENTO_API_URL)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # launch
    p_launch = subparsers.add_parser("launch", help="Launch a binary inside an isolated sandbox session")
    p_launch.add_argument("binary_path", help="Path to executable or binary (e.g. app.exe or script)")
    p_launch.add_argument("--args", type=str, default=None, help="Arguments to pass to the binary")
    p_launch.add_argument("--timeout", type=int, default=300, help="Execution timeout in seconds (default: 300)")
    p_launch.add_argument("--use-wine", dest="use_wine", action="store_true", default=None, help="Force execution with Wine/Proton")
    p_launch.add_argument("--no-wine", dest="use_wine", action="store_false", help="Disable Wine wrapper")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect telemetry and status of a session")
    p_inspect.add_argument("session_id", help="Session ID to inspect")
    p_inspect.add_argument("--json", action="store_true", help="Output raw JSON response")

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

    if not raw or "launch" not in raw or "--args" not in raw:
        return raw

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


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    processed_argv = preprocess_argv(argv)
    try:
        args = parser.parse_args(processed_argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0

    if not args.command:
        parser.print_help()
        return 0

    api_url = args.url

    commands = {
        "launch": cmd_launch,
        "inspect": cmd_inspect,
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
