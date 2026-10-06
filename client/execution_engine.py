"""
Momento Local & Hybrid Process Execution Engine
===============================================
Manages native desktop subprocess execution on the user's machine,
with real-time stdout/stderr log capture, lifecycle monitoring, and process termination.
"""

import datetime
import os
import subprocess
import sys
import threading
import uuid
from typing import Any, Dict, List, Optional


class LocalSession:
    """Represents an active or completed local subprocess session."""

    def __init__(
        self,
        session_id: str,
        app_name: str,
        binary_path: str,
        process: subprocess.Popen,
        created_at: str,
        working_dir: Optional[str] = None,
        args: Optional[List[str]] = None
    ):
        self.session_id = session_id
        self.app_name = app_name
        self.binary_path = binary_path
        self.process = process
        self.pid = process.pid
        self.status = "running"
        self.created_at = created_at
        self.working_dir = working_dir
        self.args = args or []
        self.exit_code: Optional[int] = None
        self.logs: List[str] = []
        self._lock = threading.Lock()

    def append_log(self, line: str) -> None:
        """Thread-safe append log line with max capacity."""
        clean = line.rstrip("\r\n")
        if not clean:
            return
        with self._lock:
            self.logs.append(clean)
            if len(self.logs) > 500:
                self.logs.pop(0)

    def check_status(self) -> str:
        """Poll the process status without blocking."""
        if self.process is None:
            return self.status
        ret = self.process.poll()
        if ret is not None:
            self.exit_code = ret
            if self.status != "terminated":
                self.status = "exited" if ret == 0 else "failed"
        return self.status

    def to_dict(self) -> Dict[str, Any]:
        """Convert session state to dictionary representation."""
        self.check_status()
        with self._lock:
            recent_logs = list(self.logs[-20:])
            all_logs = list(self.logs)
        return {
            "session_id": self.session_id,
            "app_name": self.app_name,
            "binary_path": self.binary_path,
            "pid": self.pid,
            "status": self.status,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "working_dir": self.working_dir,
            "args": self.args,
            "recent_logs": recent_logs,
            "logs": all_logs,
            "runtime": "local_native"
        }


class ExecutionEngine:
    """Thread-safe manager for local application execution and monitoring."""

    def __init__(self):
        self._sessions: Dict[str, LocalSession] = {}
        self._lock = threading.Lock()

    def launch(
        self,
        binary_path: str,
        args: Optional[List[str]] = None,
        app_name: Optional[str] = None,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch an application binary natively on the local Windows laptop.
        Supports custom arguments, working directories, shortcut resolution, and directory targets.
        Captures output asynchronously in real-time.
        """
        from client.scanner import resolve_shortcut_or_target

        resolved_bin, resolved_cwd, resolved_args = resolve_shortcut_or_target(
            binary_path, working_dir=working_dir, args=args
        )

        arg_list = (args if args is not None else resolved_args) or []
        target_path = resolved_bin

        if not os.path.isabs(target_path):
            which_path = shutil.which(target_path)
            if which_path:
                target_path = which_path

        effective_cwd = working_dir or resolved_cwd
        if effective_cwd and os.path.isdir(effective_cwd):
            effective_cwd = os.path.normpath(os.path.abspath(effective_cwd))
        elif os.path.isabs(target_path) and os.path.isfile(target_path):
            effective_cwd = os.path.dirname(os.path.abspath(target_path))
        else:
            effective_cwd = None

        cmd = [target_path] + arg_list
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session_id = f"sbx_local_{uuid.uuid4().hex[:10]}"
        display_name = app_name or os.path.basename(target_path)

        try:
            creationflags = 0
            shell = False
            if sys.platform == "win32":
                if not os.path.isabs(target_path) and not shutil.which(target_path):
                    shell = True

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=effective_cwd,
                creationflags=creationflags,
                shell=shell
            )

            session = LocalSession(
                session_id=session_id,
                app_name=display_name,
                binary_path=target_path,
                process=proc,
                created_at=now,
                working_dir=effective_cwd,
                args=arg_list
            )

            with self._lock:
                self._sessions[session_id] = session

            # Start background reader thread for real-time stdout capture
            reader_thread = threading.Thread(
                target=self._stream_output_reader,
                args=(session,),
                daemon=True,
                name=f"Reader-{session_id}"
            )
            reader_thread.start()

            return {
                "success": True,
                "session_id": session_id,
                "pid": proc.pid,
                "status": "running",
                "app_name": display_name,
                "binary_path": target_path,
                "working_dir": effective_cwd,
                "args": arg_list,
                "runtime": "local_native",
                "created_at": now,
                "logs": list(session.logs)
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to launch '{binary_path}': {str(e)}",
                "session_id": None
            }

    def launch_and_interact(
        self,
        binary_path: str,
        steps: List[Dict[str, Any]],
        args: Optional[List[str]] = None,
        app_name: Optional[str] = None,
        working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch application process and execute automated GUI interaction steps asynchronously,
        streaming logs in real-time into the session terminal card.
        """
        res = self.launch(binary_path, args=args, app_name=app_name, working_dir=working_dir)
        if not res.get("success"):
            return res

        session_id = res["session_id"]
        session = self.get_session(session_id)
        if session:
            session.append_log(f"[*] Process initialized (PID: {res['pid']}). Queued {len(steps)} GUI interaction step(s).")
            auto_thread = threading.Thread(
                target=self._run_automation_steps,
                args=(session, steps),
                daemon=True,
                name=f"Automation-{session_id}"
            )
            auto_thread.start()
            res["logs"] = list(session.logs)

        return res

    def _run_automation_steps(self, session: LocalSession, steps: List[Dict[str, Any]]) -> None:
        """Run automation sequence in background thread and stream progress into session logs."""
        try:
            from client.gui_automation import execute_steps
            execute_steps(steps, log_callback=session.append_log)
        except Exception as e:
            session.append_log(f"[!] GUI automation error: {e}")

    def _stream_output_reader(self, session: LocalSession) -> None:
        """Stream lines from process stdout into session logs buffer."""
        try:
            if session.process and session.process.stdout:
                for line in iter(session.process.stdout.readline, ''):
                    if not line:
                        break
                    session.append_log(line)
        except Exception:
            pass
        finally:
            session.check_status()

    def get_session(self, session_id: str) -> Optional[LocalSession]:
        """Retrieve local session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_active_session(self) -> Optional[LocalSession]:
        """Retrieve the most recently launched active/running local session."""
        with self._lock:
            # Check for running sessions first, most recent first
            running = [s for s in reversed(list(self._sessions.values())) if s.process and s.process.poll() is None]
            if running:
                return running[0]
            # Fall back to latest session
            if self._sessions:
                return list(self._sessions.values())[-1]
        return None

    def inspect_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Introspect active application window, UI hierarchy, and telemetry for a session.
        Appends live inspection log lines into session logs for streaming to live cards.
        """
        from client.gui_automation import inspect_window_ui

        session = self.get_session(session_id) if session_id else self.get_active_session()
        target_pid = session.process.pid if (session and session.process) else None
        target_name = session.app_name if session else None

        inspection = inspect_window_ui(target=target_name, pid=target_pid)

        if session:
            # Append inspection stream into live session log buffer
            for line in inspection.get("log_lines", []):
                session.append_log(line)
            inspection["session_id"] = session.session_id
            inspection["app_name"] = session.app_name
            inspection["logs"] = list(session.logs)
        else:
            inspection["session_id"] = None
            inspection["logs"] = inspection.get("log_lines", [])

        return inspection

    def profile_app(
        self,
        app_name_or_path: str,
        session_id: Optional[str] = None,
        pid: Optional[int] = None,
        hwnd: Optional[int] = None,
        binary_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Deep reverse-engineer and profile target application.
        Appends live reverse-engineering log lines into session logs for streaming to live cards.
        Supports direct targeting via PID, HWND, and binary path.
        """
        from client.app_profiler import profile_application

        session = self.get_session(session_id) if session_id else None

        captured_logs: List[str] = []
        def _stream(msg: str):
            captured_logs.append(msg)
            if session:
                session.append_log(msg)

        profile = profile_application(
            app_name_or_path=app_name_or_path,
            session_id=session_id,
            pid=pid,
            hwnd=hwnd,
            binary_path=binary_path,
            log_callback=_stream
        )

        active = session or (self.get_session(profile.get("session_id")) if profile.get("session_id") else None) or self.get_active_session()
        profile["session_id"] = profile.get("session_id") or (active.session_id if active else None)
        profile["logs"] = list(active.logs) if active else captured_logs
        profile["success"] = True
        return profile

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active and recent local sessions."""
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.to_dict() for s in sessions]

    def stop_session(self, session_id: str, force: bool = False) -> Dict[str, Any]:
        """Terminate a running local session."""
        session = self.get_session(session_id)
        if not session:
            return {"success": False, "error": f"Session '{session_id}' not found"}

        if session.process and session.process.poll() is None:
            try:
                if force:
                    session.process.kill()
                else:
                    session.process.terminate()
                session.status = "terminated"
                return {"success": True, "session_id": session_id, "status": "terminated"}
            except Exception as e:
                return {"success": False, "error": f"Failed to stop process: {e}"}

        return {"success": True, "session_id": session_id, "status": session.status}

    def get_logs(self, session_id: str, tail: int = 50) -> Dict[str, Any]:
        """Get recent logs and status for a local session."""
        session = self.get_session(session_id)
        if not session:
            return {"success": False, "error": f"Session '{session_id}' not found"}

        session.check_status()
        with session._lock:
            lines = list(session.logs[-tail:])
        return {
            "success": True,
            "session_id": session_id,
            "status": session.status,
            "exit_code": session.exit_code,
            "logs": lines
        }

    def clear(self) -> None:
        """Clear all sessions (useful for tests)."""
        with self._lock:
            for s in self._sessions.values():
                if s.process and s.process.poll() is None:
                    try:
                        s.process.kill()
                    except Exception:
                        pass
            self._sessions.clear()


# Global execution engine instance
global_execution_engine = ExecutionEngine()
