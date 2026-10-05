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
        created_at: str
    ):
        self.session_id = session_id
        self.app_name = app_name
        self.binary_path = binary_path
        self.process = process
        self.pid = process.pid
        self.status = "running"
        self.created_at = created_at
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
        app_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch an application binary natively on the local Windows laptop.
        Captures output asynchronously in real-time.
        """
        arg_list = args or []
        target_path = binary_path
        if not os.path.isabs(target_path):
            which_path = shutil.which(target_path)
            if which_path:
                target_path = which_path

        cmd = [target_path] + arg_list
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session_id = f"sbx_local_{uuid.uuid4().hex[:10]}"
        display_name = app_name or os.path.basename(target_path)

        try:
            # On Windows, hide command window for GUI apps if not in console mode
            creationflags = 0
            shell = False
            if sys.platform == "win32":
                # If target is a shell command or not directly an executable file, enable shell
                if not os.path.isabs(target_path) and not shutil.which(target_path):
                    shell = True

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                shell=shell
            )

            session = LocalSession(
                session_id=session_id,
                app_name=display_name,
                binary_path=target_path,
                process=proc,
                created_at=now
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
        app_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Launch application process and execute automated GUI interaction steps asynchronously,
        streaming logs in real-time into the session terminal card.
        """
        res = self.launch(binary_path, args=args, app_name=app_name)
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
