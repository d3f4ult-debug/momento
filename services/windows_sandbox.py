"""
Momento - Headless Sandbox & Execution Layer
============================================
Lightweight, deterministic host engine for launching, managing, and monitoring
Windows executables (.exe) headlessly on Linux (via Wine/Proton/compatibility runtime)
or native Windows host environments without graphical display or vision-model overhead.
"""

import os
import sys
import time
import uuid
import shutil
import logging
import threading
import subprocess
from typing import Dict, Any, Optional, List

logger = logging.getLogger("momento.sandbox")
logger.setLevel(logging.INFO)

# Sandbox root directory
DEFAULT_SANDBOX_DIR = "/var/www/momento/sandbox" if os.path.exists("/var/www/momento") else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sandbox"))
SANDBOX_ROOT_DIR = os.getenv("MOMENTO_SANDBOX_DIR", DEFAULT_SANDBOX_DIR)


def ensure_sandbox_dirs() -> str:
    """Ensure base sandbox directories exist."""
    os.makedirs(SANDBOX_ROOT_DIR, exist_ok=True)
    sessions_dir = os.path.join(SANDBOX_ROOT_DIR, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    return SANDBOX_ROOT_DIR


def detect_runtime() -> str:
    """
    Detect the execution runtime:
    - 'native': when running directly on Windows.
    - 'wine': when running on Linux with wine/wine64 installed.
    - 'subprocess': generic fallback on Linux if wine is not installed.
    """
    if sys.platform == "win32":
        return "native"

    wine_bin = shutil.which("wine") or shutil.which("wine64")
    if wine_bin:
        return "wine"

    return "subprocess"


class SandboxSession:
    """Represents an active or terminated headless sandbox process session."""

    def __init__(
        self,
        session_id: str,
        binary_path: str,
        sandbox_dir: str,
        runtime: str,
        process: Optional[subprocess.Popen] = None,
        timeout: Optional[int] = None
    ):
        self.session_id: str = session_id
        self.binary_path: str = binary_path
        self.sandbox_dir: str = sandbox_dir
        self.runtime: str = runtime
        self.process: Optional[subprocess.Popen] = process
        self.pid: Optional[int] = process.pid if process else None
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.timeout: Optional[int] = timeout
        self.status: str = "running"
        self.exit_code: Optional[int] = None
        self.stdout_lines: List[str] = []
        self.stderr_lines: List[str] = []
        self.lock: threading.Lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

    def capture_streams(self):
        """Asynchronously stream stdout and stderr into memory buffers."""
        if not self.process:
            return

        def _reader(stream, line_list: List[str]):
            try:
                for line in iter(stream.readline, ""):
                    if not line:
                        break
                    with self.lock:
                        line_list.append(line.rstrip("\r\n"))
                        # Cap buffer at 2000 lines to avoid runaway memory
                        if len(line_list) > 2000:
                            line_list.pop(0)
            except Exception as e:
                logger.debug("Stream reader closed for session %s: %s", self.session_id, e)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        if self.process.stdout:
            self._stdout_thread = threading.Thread(target=_reader, args=(self.process.stdout, self.stdout_lines), daemon=True)
            self._stdout_thread.start()

        if self.process.stderr:
            self._stderr_thread = threading.Thread(target=_reader, args=(self.process.stderr, self.stderr_lines), daemon=True)
            self._stderr_thread.start()

    def update_liveness(self) -> str:
        """Poll the process and update session status."""
        if not self.process:
            self.status = "terminated"
            return self.status

        poll_res = self.process.poll()
        if poll_res is None:
            # Check timeout
            if self.timeout and (time.time() - self.start_time) > self.timeout:
                logger.warning("Session %s exceeded timeout of %ds; terminating.", self.session_id, self.timeout)
                self.terminate(force=True)
                self.status = "timed_out"
            else:
                self.status = "running"
        else:
            self.exit_code = poll_res
            if self.end_time is None:
                self.end_time = time.time()
            if self.status not in ("timed_out", "killed"):
                self.status = "exited" if poll_res == 0 else "failed"

        return self.status

    def terminate(self, force: bool = False) -> bool:
        """Terminate or kill the sandbox process."""
        if not self.process:
            self.status = "terminated"
            return True

        try:
            if force:
                self.process.kill()
                self.status = "killed"
            else:
                self.process.terminate()
                self.status = "terminated"

            self.exit_code = self.process.poll()
            if self.end_time is None:
                self.end_time = time.time()
            return True
        except Exception as e:
            logger.error("Error terminating process for session %s: %s", self.session_id, e)
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session state into JSON-compatible dictionary."""
        self.update_liveness()
        uptime = round((self.end_time or time.time()) - self.start_time, 2)
        with self.lock:
            recent_logs = (self.stdout_lines[-20:] if self.stdout_lines else []) + (self.stderr_lines[-10:] if self.stderr_lines else [])

        return {
            "session_id": self.session_id,
            "binary_path": self.binary_path,
            "binary_name": os.path.basename(self.binary_path),
            "pid": self.pid,
            "status": self.status,
            "runtime": self.runtime,
            "uptime_seconds": uptime,
            "exit_code": self.exit_code,
            "sandbox_dir": self.sandbox_dir,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "recent_logs": recent_logs,
            "stdout_count": len(self.stdout_lines),
            "stderr_count": len(self.stderr_lines)
        }


# Global session registry
_SESSIONS_LOCK = threading.Lock()
_ACTIVE_SESSIONS: Dict[str, SandboxSession] = {}


def get_session(session_id: str) -> Optional[SandboxSession]:
    """Retrieve a sandbox session by its unique ID."""
    with _SESSIONS_LOCK:
        return _ACTIVE_SESSIONS.get(session_id)


def list_sessions() -> List[Dict[str, Any]]:
    """List all registered sandbox sessions."""
    with _SESSIONS_LOCK:
        return [sess.to_dict() for sess in _ACTIVE_SESSIONS.values()]


def launch_binary(
    binary_path: str,
    args: Optional[List[str]] = None,
    env_vars: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = 300,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Launch a Windows binary headlessly inside an isolated sandbox session.
    
    Args:
        binary_path: Path to the target executable (.exe or script).
        args: Optional list of command-line arguments.
        env_vars: Optional custom environment variables.
        timeout: Maximum execution timeout in seconds (default: 300s).
        working_dir: Optional specific working directory.
    """
    ensure_sandbox_dirs()

    # Validate binary exists or is reachable
    clean_path = os.path.abspath(binary_path) if os.path.exists(binary_path) else binary_path
    if not os.path.exists(clean_path) and not shutil.which(clean_path):
        return {
            "success": False,
            "error": f"Target binary '{binary_path}' not found on host filesystem.",
            "session_id": None
        }

    session_id = f"sbx_{uuid.uuid4().hex[:12]}"
    session_sandbox_dir = working_dir or os.path.join(SANDBOX_ROOT_DIR, "sessions", session_id)
    os.makedirs(session_sandbox_dir, exist_ok=True)

    runtime = detect_runtime()
    cmd: List[str] = []

    # Configure headless environment
    exec_env = os.environ.copy()
    exec_env["WINEDEBUG"] = "-all"
    exec_env["DISPLAY"] = ""
    exec_env["PYTHONUNBUFFERED"] = "1"
    exec_env["WINEPREFIX"] = os.path.join(session_sandbox_dir, ".wine")

    if env_vars:
        exec_env.update(env_vars)

    arg_list = args or []

    if runtime == "wine":
        wine_bin = shutil.which("wine64") or shutil.which("wine") or "wine"
        cmd = [wine_bin, clean_path] + arg_list
    else:
        cmd = [clean_path] + arg_list

    try:
        logger.info("Launching sandbox session %s: %s (Runtime: %s)", session_id, cmd, runtime)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=session_sandbox_dir,
            env=exec_env,
            text=True,
            bufsize=1
        )

        session = SandboxSession(
            session_id=session_id,
            binary_path=clean_path,
            sandbox_dir=session_sandbox_dir,
            runtime=runtime,
            process=proc,
            timeout=timeout
        )
        session.capture_streams()

        with _SESSIONS_LOCK:
            _ACTIVE_SESSIONS[session_id] = session

        return {
            "success": True,
            "session_id": session_id,
            "pid": proc.pid,
            "status": "running",
            "runtime": runtime,
            "binary": os.path.basename(clean_path),
            "sandbox_dir": session_sandbox_dir,
            "message": f"Successfully launched '{os.path.basename(clean_path)}' in sandbox (PID {proc.pid})."
        }
    except Exception as e:
        logger.exception("Failed to launch binary in sandbox: %s", e)
        return {
            "success": False,
            "session_id": session_id,
            "error": str(e),
            "runtime": runtime
        }


def terminate_session(session_id: str, force: bool = False) -> Dict[str, Any]:
    """Terminate or kill a running sandbox session."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": f"Session '{session_id}' not found."}

    success = session.terminate(force=force)
    return {
        "success": success,
        "session_id": session_id,
        "status": session.status,
        "exit_code": session.exit_code
    }


def clear_all_sessions(max_age_seconds: Optional[int] = None) -> int:
    """Clean up terminated or stale sessions."""
    now = time.time()
    cleared = 0
    with _SESSIONS_LOCK:
        to_delete = []
        for sid, sess in _ACTIVE_SESSIONS.items():
            sess.update_liveness()
            if sess.status != "running":
                if max_age_seconds is None or (now - sess.start_time) >= max_age_seconds:
                    to_delete.append(sid)

        for sid in to_delete:
            sess = _ACTIVE_SESSIONS.pop(sid, None)
            if sess and os.path.exists(sess.sandbox_dir) and "sessions" in sess.sandbox_dir:
                try:
                    shutil.rmtree(sess.sandbox_dir, ignore_errors=True)
                except Exception:
                    pass
            cleared += 1

    return cleared


# ==============================================================================
# FastAPI Sandbox Router
# ==============================================================================

from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse

sandbox_router = APIRouter(tags=["Sandbox"])


@sandbox_router.post("/api/sandbox/launch")
@sandbox_router.post("/api/sandbox/launch/")
@sandbox_router.post("/sandbox/launch")
@sandbox_router.post("/launch")
async def sandbox_launch_endpoint(
    request: Request,
    binary_path: Optional[str] = Form(None),
    args: Optional[str] = Form(None),
    timeout: Optional[int] = Form(300)
):
    """Launch target application headlessly in an isolated sandbox session."""
    eff_binary = binary_path
    eff_args = args
    eff_timeout = timeout

    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            eff_binary = body.get("binary_path") or eff_binary
            eff_args = body.get("args") or eff_args
            eff_timeout = body.get("timeout", eff_timeout)
        except Exception:
            pass

    if not eff_binary:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "Field 'binary_path' is required."}
        )

    arg_list = None
    if eff_args:
        if isinstance(eff_args, list):
            arg_list = eff_args
        elif isinstance(eff_args, str):
            import shlex
            try:
                arg_list = shlex.split(eff_args)
            except Exception:
                arg_list = eff_args.split()

    res = launch_binary(binary_path=eff_binary, args=arg_list, timeout=eff_timeout)
    status_code = 200 if res.get("success") else 400
    return JSONResponse(status_code=status_code, content=res)


@sandbox_router.post("/api/sandbox/inspect")
@sandbox_router.post("/api/sandbox/inspect/")
@sandbox_router.post("/sandbox/inspect")
@sandbox_router.post("/inspect")
async def sandbox_inspect_endpoint(
    request: Request,
    session_id: Optional[str] = Form(None)
):
    """Query execution telemetry, state, and file interactions for a sandbox session."""
    eff_session_id = session_id
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            eff_session_id = body.get("session_id") or eff_session_id
        except Exception:
            pass

    if not eff_session_id:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "Field 'session_id' is required."}
        )

    from services.binary_inspector import inspect_session
    res = inspect_session(eff_session_id)
    status_code = 200 if res.get("success") else 404
    return JSONResponse(status_code=status_code, content=res)


@sandbox_router.post("/api/sandbox/execute")
@sandbox_router.post("/api/sandbox/execute/")
@sandbox_router.post("/sandbox/execute")
@sandbox_router.post("/execute")
async def sandbox_execute_endpoint(
    request: Request,
    session_id: Optional[str] = Form(None),
    command: Optional[str] = Form(None),
    input_data: Optional[str] = Form(None)
):
    """Trigger a deterministic command, stdin message, or hook against a sandbox session."""
    eff_session_id = session_id
    eff_command = command
    eff_input_data = input_data

    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            eff_session_id = body.get("session_id") or eff_session_id
            eff_command = body.get("command") or eff_command
            eff_input_data = body.get("input_data") or eff_input_data
        except Exception:
            pass

    if not eff_session_id or not eff_command:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "Fields 'session_id' and 'command' are required."}
        )

    from services.binary_inspector import execute_command_in_session
    res = execute_command_in_session(
        session_id=eff_session_id,
        command=eff_command,
        input_data=eff_input_data
    )
    status_code = 200 if res.get("success") else 400
    return JSONResponse(status_code=status_code, content=res)


@sandbox_router.get("/api/sandbox/sessions")
@sandbox_router.get("/api/sandbox/sessions/")
@sandbox_router.get("/sandbox/sessions")
@sandbox_router.get("/sessions")
async def sandbox_sessions_endpoint():
    """Retrieve high-level telemetry summary and active sessions."""
    from services.binary_inspector import get_sandbox_telemetry_summary
    return get_sandbox_telemetry_summary()


@sandbox_router.post("/api/sandbox/stop")
@sandbox_router.post("/api/sandbox/stop/")
@sandbox_router.post("/sandbox/stop")
@sandbox_router.post("/stop")
async def sandbox_stop_endpoint(
    request: Request,
    session_id: Optional[str] = Form(None),
    force: Optional[bool] = Form(False)
):
    """Terminate or kill an active sandbox session."""
    eff_session_id = session_id
    eff_force = force
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            eff_session_id = body.get("session_id") or eff_session_id
            eff_force = body.get("force", eff_force)
        except Exception:
            pass

    if not eff_session_id:
        return JSONResponse(status_code=422, content={"success": False, "error": "Field 'session_id' is required."})

    res = terminate_session(eff_session_id, force=bool(eff_force))
    status_code = 200 if res.get("success") else 404
    return JSONResponse(status_code=status_code, content=res)
