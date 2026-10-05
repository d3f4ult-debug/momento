"""
Momento Desktop Bridge
======================
Python bridge exposed to the native desktop GUI (pywebview JavaScript API).
Coordinates local application discovery, natural-language command dispatch,
hybrid execution routing, and real-time process monitoring.
"""

import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

from client.config import (
    DEFAULT_BACKEND_URL,
    get_backend_url,
    is_setup_completed,
    load_config,
    save_config,
    set_backend_url,
    set_permissions
)
from client.execution_engine import global_execution_engine
from client.nlp_router import NLPRouter, make_backend_request
from client.scanner import AppScanner, resolve_app_binary


class DesktopAppBridge:
    """JS-to-Python Bridge exposed as window.pywebview.api in desktop window."""

    def __init__(self, backend_url: Optional[str] = None):
        self.backend_url = backend_url or get_backend_url()
        self.nlp_router = NLPRouter(backend_url=self.backend_url)
        self.execution_engine = global_execution_engine

    def get_initial_state(self) -> Dict[str, Any]:
        """Fetch all initial configuration, permissions, apps, and active sessions."""
        cfg = load_config()
        setup_done = is_setup_completed()

        scanner = AppScanner()
        registry = scanner.load_registry() if setup_done else {"apps": {}, "total_apps": 0}
        apps_dict = registry.get("apps", {})
        apps_list = list(apps_dict.values())

        # Collect local sessions
        local_sessions = self.execution_engine.list_sessions()

        return {
            "setup_completed": setup_done,
            "permissions": cfg.get("permissions", {}),
            "backend_url": self.backend_url,
            "execution_mode": cfg.get("execution_mode", "hybrid"),
            "discovered_apps": apps_list,
            "total_apps": len(apps_list),
            "active_sessions": local_sessions
        }

    def grant_permissions(
        self,
        filesystem: bool = True,
        discovery: bool = True,
        execution: bool = True,
        backend_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the initial permission approval and trigger local application scan."""
        if backend_url:
            self.backend_url = backend_url.rstrip("/")
            set_backend_url(self.backend_url)
            self.nlp_router.backend_url = self.backend_url

        set_permissions(filesystem=filesystem, discovery=discovery, execution=execution)

        # Trigger application scan
        scanner = AppScanner()
        registry = scanner.scan_environment()
        apps_list = list(registry.get("apps", {}).values())

        return {
            "success": True,
            "setup_completed": True,
            "total_apps": len(apps_list),
            "apps": apps_list,
            "message": f"Setup complete! {len(apps_list)} applications discovered."
        }

    def rescan_apps(self) -> Dict[str, Any]:
        """Rescan local environment for installed applications."""
        scanner = AppScanner()
        registry = scanner.scan_environment()
        apps_list = list(registry.get("apps", {}).values())
        return {
            "success": True,
            "total_apps": len(apps_list),
            "apps": apps_list
        }

    def send_message(self, message: str, execution_mode: str = "hybrid") -> Dict[str, Any]:
        """
        Parse human natural language message and dispatch to local or VPS execution.
        Supports:
          - "Momento, open notepad"
          - "run calc"
          - "open chrome with args --incognito"
          - "stop [session_id]"
          - "sessions"
          - "scan"
        """
        clean_text = (message or "").strip()
        if not clean_text:
            return {"success": False, "message": "Empty message."}

        action, target, args = self.nlp_router.parse_command(clean_text)

        # 1. Handle non-launch commands
        if action in ("sessions", "stop", "inspect", "scan", "help"):
            # For sessions, combine local sessions and remote VPS sessions
            if action == "sessions":
                local_sess = self.execution_engine.list_sessions()
                vps_res = make_backend_request("/api/sandbox/sessions", method="GET", backend_url=self.backend_url)
                vps_sess = vps_res.get("sessions", []) if vps_res.get("success") else []
                total = len(local_sess) + len(vps_sess)
                return {
                    "success": True,
                    "action": "sessions",
                    "total_sessions": total,
                    "local_sessions": local_sess,
                    "vps_sessions": vps_sess,
                    "message": f"Active Sessions: {len(local_sess)} local, {len(vps_sess)} remote VPS."
                }

            if action == "stop" and target:
                # Check if it is a local session
                if target.startswith("sbx_local_"):
                    res = self.execution_engine.stop_session(target, force=True)
                    msg = f"Local session '{target}' terminated." if res.get("success") else res.get("error")
                    return {"success": res.get("success", False), "action": "stop", "session_id": target, "message": msg}
                else:
                    return self.nlp_router.execute(f"stop {target}")

            if action == "scan":
                return self.rescan_apps()

            return self.nlp_router.execute(clean_text)

        # 2. Handle Launch action
        if action == "launch" and target:
            app_record = resolve_app_binary(target)
            if app_record:
                binary_path = app_record["binary_path"]
                app_name = app_record["name"]
            else:
                which_bin = shutil.which(target)
                if which_bin:
                    binary_path = which_bin
                    app_name = os.path.splitext(os.path.basename(which_bin))[0].title()
                else:
                    binary_path = target
                    app_name = target

            # Determine routing: local vs vps vs hybrid
            eff_mode = (execution_mode or "hybrid").lower().strip()
            should_run_locally = False

            if eff_mode in ("local", "local host", "local_host", "localhost"):
                should_run_locally = True
            elif eff_mode in ("vps", "vps sandbox", "vps_sandbox"):
                should_run_locally = False
            else:  # hybrid / hybrid auto
                # Run locally if binary exists on host, in app registry, or on PATH
                should_run_locally = (
                    os.path.exists(binary_path)
                    or bool(app_record)
                    or bool(shutil.which(binary_path))
                    or bool(shutil.which(target))
                )

            if should_run_locally:
                local_res = self.execution_engine.launch(binary_path, args=args, app_name=app_name)
                if local_res.get("success"):
                    session_id = local_res["session_id"]
                    pid = local_res["pid"]
                    status = local_res.get("status", "running")
                    logs = local_res.get("logs", [])
                    if not logs:
                        time.sleep(0.05)
                        logs = self.execution_engine.get_logs(session_id).get("logs", [])
                    msg = (
                        f"Momento: Launched '{app_name}' natively on local Windows host.\n"
                        f"  [+] Session ID: {session_id}\n"
                        f"  [+] Local PID:  {pid}\n"
                        f"  [+] Status:     {status}"
                    )
                    return {
                        "success": True,
                        "action": "launch",
                        "app_name": app_name,
                        "binary_path": binary_path,
                        "session_id": session_id,
                        "pid": pid,
                        "runtime": "local_native",
                        "status": status,
                        "message": msg,
                        "logs": logs
                    }
                elif eff_mode in ("local", "local host", "local_host", "localhost"):
                    err = local_res.get("error", "Execution failed")
                    return {
                        "success": False,
                        "action": "launch",
                        "app_name": app_name,
                        "binary_path": binary_path,
                        "session_id": None,
                        "pid": None,
                        "runtime": "local_native",
                        "status": "failed",
                        "message": f"Momento: Failed to launch '{app_name}' locally: {err}",
                        "logs": []
                    }

            # Remote VPS routing / fallback
            vps_res = self.nlp_router.execute(clean_text)
            if vps_res.get("success") and "logs" not in vps_res:
                vps_res["logs"] = []
            return vps_res

        return {"success": False, "message": f"Could not interpret: '{clean_text}'."}

    def get_session_logs(self, session_id: str) -> Dict[str, Any]:
        """Fetch live logs and telemetry for a session."""
        if session_id.startswith("sbx_local_"):
            return self.execution_engine.get_logs(session_id)
        else:
            res = make_backend_request(
                "/api/sandbox/inspect",
                method="POST",
                data={"session_id": session_id},
                backend_url=self.backend_url
            )
            if res.get("success"):
                return {
                    "success": True,
                    "session_id": session_id,
                    "status": res.get("status"),
                    "exit_code": None,
                    "logs": res.get("recent_stdout", [])
                }
            return {"success": False, "error": res.get("error", "Session not found")}

    def stop_session(self, session_id: str) -> Dict[str, Any]:
        """Stop an active session (local or VPS)."""
        if session_id.startswith("sbx_local_"):
            return self.execution_engine.stop_session(session_id, force=True)
        else:
            return make_backend_request(
                "/api/sandbox/stop",
                method="POST",
                data={"session_id": session_id, "force": True},
                backend_url=self.backend_url
            )

    def save_settings(self, backend_url: str, execution_mode: str = "hybrid") -> Dict[str, Any]:
        """Save settings updates."""
        clean_url = backend_url.rstrip("/")
        self.backend_url = clean_url
        self.nlp_router.backend_url = clean_url
        set_backend_url(clean_url)

        cfg = load_config()
        cfg["execution_mode"] = execution_mode
        save_config(cfg)
        return {"success": True, "backend_url": clean_url, "execution_mode": execution_mode}
