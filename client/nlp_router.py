"""
Momento Natural Language Router
===============================
Parses natural language requests (e.g. "Momento, open [app]", "run [app]")
and coordinates app resolution with remote Momento VPS Sandbox execution.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from client.config import get_backend_url
from client.scanner import AppScanner, resolve_app_binary


def make_backend_request(
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict[str, Any]] = None,
    backend_url: Optional[str] = None,
    timeout: int = 20
) -> Dict[str, Any]:
    """Execute an HTTP request against the Momento backend API."""
    base_url = (backend_url or get_backend_url()).rstrip("/")
    url = f"{base_url}{endpoint}"

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
            "error": f"Cannot connect to Momento VPS at {base_url} ({e.reason})."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class NLPRouter:
    """Interprets conversational intents and routes to Momento execution core."""

    def __init__(self, backend_url: Optional[str] = None):
        self.backend_url = backend_url

    def parse_command(self, text: str) -> Tuple[str, Optional[str], Optional[List[str]]]:
        """
        Parse raw user input into (action, target, args).
        Supports:
          - "Momento, open [app_name]"
          - "Momento, run [app_name]"
          - "open [app_name]"
          - "run [app_name]"
          - "stop [session_id]"
          - "sessions" / "list"
          - "scan"
        """
        clean = text.strip()
        # Strip conversational prefixes: "Momento, ", "hey momento ", "please "
        clean = re.sub(r"^(momento\s*[,:]?\s*|hey momento\s*[,:]?\s*|please\s+)", "", clean, flags=re.IGNORECASE).strip()

        # Check for utility commands
        lower = clean.lower()
        if lower in ("sessions", "list", "show sessions", "active sessions"):
            return ("sessions", None, None)
        if lower in ("scan", "rescan", "update registry", "index"):
            return ("scan", None, None)
        if lower in ("help", "?", "commands"):
            return ("help", None, None)

        # Stop / kill command
        m_stop = re.match(r"^(?:stop|kill|terminate|close)\s+([a-zA-Z0-9_\-\.]+)", clean, flags=re.IGNORECASE)
        if m_stop:
            return ("stop", m_stop.group(1).strip(), None)

        # Inspect / status command
        m_inspect = re.match(r"^(?:inspect|status|info)\s+([a-zA-Z0-9_\-\.]+)", clean, flags=re.IGNORECASE)
        if m_inspect:
            return ("inspect", m_inspect.group(1).strip(), None)

        # Open / Run / Launch command
        m_launch = re.match(r"^(?:open|run|launch|start|execute)\s+(.+)$", clean, flags=re.IGNORECASE)
        if m_launch:
            raw_target = m_launch.group(1).strip()
            # Check for trailing arguments, e.g. "python --version" or "code with args ..."
            parts = raw_target.split(" with args ", 1)
            if len(parts) == 2:
                target_app = parts[0].strip()
                extra_args = parts[1].strip().split()
                return ("launch", target_app, extra_args)

            # If no explicit "with args", check if first token is app name or entire string
            return ("launch", raw_target, None)

        # Direct app name typed (fallback)
        return ("launch", clean, None)

    def execute(self, text: str) -> Dict[str, Any]:
        """Execute a conversational command and return structured result with user message."""
        action, target, args = self.parse_command(text)

        if action == "help":
            return {
                "success": True,
                "action": "help",
                "message": (
                    "Momento Conversational Commands:\n"
                    "  - Momento, open <app_name>   (e.g., Momento, open notepad)\n"
                    "  - Momento, run <app_name>    (e.g., Momento, run calc)\n"
                    "  - sessions                   (list active sandbox sessions)\n"
                    "  - inspect <session_id>       (view telemetry & metrics)\n"
                    "  - stop <session_id>          (terminate sandbox session)\n"
                    "  - scan                       (rescan local applications)"
                )
            }

        if action == "sessions":
            res = make_backend_request("/api/sandbox/sessions", method="GET", backend_url=self.backend_url)
            if not res.get("success", False) and "sessions" not in res:
                return {
                    "success": False,
                    "action": "sessions",
                    "message": f"Failed to list sessions: {res.get('error', 'Unknown error')}"
                }
            sessions = res.get("sessions", [])
            total = res.get("total_sessions_count", len(sessions))
            msg = f"Momento Active Sandbox Sessions ({total} total):\n"
            if not sessions:
                msg += "  No active sessions currently running."
            else:
                for s in sessions:
                    msg += f"  - [{s.get('session_id')}] PID {s.get('pid')} | {s.get('status')} | {s.get('binary_path')}\n"
            return {"success": True, "action": "sessions", "sessions": sessions, "message": msg.rstrip()}

        if action == "scan":
            scanner = AppScanner()
            reg = scanner.scan_environment()
            count = reg.get("total_apps", 0)
            return {
                "success": True,
                "action": "scan",
                "total_apps": count,
                "message": f"App discovery complete: {count} applications indexed in local registry."
            }

        if action == "stop":
            res = make_backend_request(
                "/api/sandbox/stop",
                method="POST",
                data={"session_id": target, "force": True},
                backend_url=self.backend_url
            )
            if res.get("success"):
                return {
                    "success": True,
                    "action": "stop",
                    "session_id": target,
                    "message": f"Session '{target}' successfully terminated."
                }
            return {
                "success": False,
                "action": "stop",
                "session_id": target,
                "message": f"Failed to stop session '{target}': {res.get('error', 'Unknown error')}"
            }

        if action == "inspect":
            res = make_backend_request(
                "/api/sandbox/inspect",
                method="POST",
                data={"session_id": target},
                backend_url=self.backend_url
            )
            if res.get("success"):
                status = res.get("status")
                pid = res.get("pid")
                runtime = res.get("runtime")
                uptime = res.get("uptime_seconds", 0)
                msg = f"Session '{target}': Status={status}, PID={pid}, Runtime={runtime}, Uptime={uptime:.1f}s"
                return {"success": True, "action": "inspect", "session_id": target, "message": msg, "data": res}
            return {
                "success": False,
                "action": "inspect",
                "session_id": target,
                "message": f"Inspection failed for '{target}': {res.get('error', 'Unknown error')}"
            }

        if action == "launch" and target:
            # 1. Resolve application from local registry
            app_record = resolve_app_binary(target)
            if not app_record:
                # If cannot resolve in registry, attempt direct binary launch
                binary_path = target
                display_name = target
                use_wine = target.lower().endswith(".exe")
            else:
                binary_path = app_record["binary_path"]
                display_name = app_record["name"]
                use_wine = binary_path.lower().endswith(".exe")

            # 2. Dispatch launch command to Momento VPS execution core
            payload: Dict[str, Any] = {
                "binary_path": binary_path,
                "timeout": 300,
                "use_wine": use_wine
            }
            if args:
                payload["args"] = " ".join(args)

            res = make_backend_request(
                "/api/sandbox/launch",
                method="POST",
                data=payload,
                backend_url=self.backend_url
            )

            if res.get("success"):
                session_id = res.get("session_id")
                pid = res.get("pid")
                runtime = res.get("runtime")
                status = res.get("status")
                msg = (
                    f"Momento: Launching '{display_name}' ({binary_path})\n"
                    f"  [+] Session ID: {session_id}\n"
                    f"  [+] Remote PID: {pid}\n"
                    f"  [+] Runtime:    {runtime}\n"
                    f"  [+] Status:     {status}"
                )
                return {
                    "success": True,
                    "action": "launch",
                    "app_name": display_name,
                    "binary_path": binary_path,
                    "session_id": session_id,
                    "pid": pid,
                    "runtime": runtime,
                    "status": status,
                    "message": msg,
                    "raw_response": res
                }
            else:
                err = res.get("error") or res.get("detail") or "Unknown error"
                return {
                    "success": False,
                    "action": "launch",
                    "app_name": display_name,
                    "binary_path": binary_path,
                    "message": f"Momento: Failed to launch '{display_name}': {err}",
                    "raw_response": res
                }

        return {
            "success": False,
            "action": "unknown",
            "message": f"Command not understood: '{text}'. Type 'help' for examples."
        }
