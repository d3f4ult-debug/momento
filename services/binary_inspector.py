"""
Momento - Process Telemetry Bridge & Binary Inspector
=====================================================
Low-overhead programmatic inspection and execution bridge for headless Windows
processes running within the Momento sandbox. Captures execution metrics,
process activity, file system interactions, and log streams at machine speed.
"""

import os
import sys
import time
import json
import logging
import subprocess
from typing import Dict, Any, Optional, List

from services.windows_sandbox import get_session, list_sessions, SandboxSession

logger = logging.getLogger("momento.inspector")
logger.setLevel(logging.INFO)


def _get_process_metrics(pid: Optional[int]) -> Dict[str, Any]:
    """
    Retrieve CPU, memory RSS, and status metrics for a given PID.
    Uses Linux /proc filesystem or platform-native inspection with graceful fallback.
    """
    metrics = {
        "pid": pid,
        "rss_bytes": 0,
        "vms_bytes": 0,
        "cpu_percent": 0.0,
        "threads": 1,
        "is_alive": False
    }

    if not pid:
        return metrics

    # Try psutil if available
    try:
        import psutil
        if psutil.pid_exists(pid):
            p = psutil.Process(pid)
            mem = p.memory_info()
            metrics["is_alive"] = p.is_running()
            metrics["rss_bytes"] = mem.rss
            metrics["vms_bytes"] = mem.vms
            metrics["threads"] = p.num_threads()
            metrics["cpu_percent"] = p.cpu_percent(interval=None)
            return metrics
    except Exception:
        pass

    # Linux /proc introspection fallback (zero external dependencies)
    if sys.platform != "win32" and os.path.exists(f"/proc/{pid}"):
        try:
            metrics["is_alive"] = True
            statm_path = f"/proc/{pid}/statm"
            if os.path.exists(statm_path):
                with open(statm_path, "r") as f:
                    parts = f.read().strip().split()
                    if len(parts) >= 2:
                        page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
                        metrics["vms_bytes"] = int(parts[0]) * page_size
                        metrics["rss_bytes"] = int(parts[1]) * page_size

            status_path = f"/proc/{pid}/status"
            if os.path.exists(status_path):
                with open(status_path, "r") as f:
                    for line in f:
                        if line.startswith("Threads:"):
                            metrics["threads"] = int(line.split(":")[1].strip())
                            break
            return metrics
        except Exception as e:
            logger.debug("Failed /proc inspection for PID %d: %s", pid, e)

    # Windows native liveness check fallback
    if sys.platform == "win32" and pid:
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                metrics["is_alive"] = True
        except Exception:
            metrics["is_alive"] = True

    return metrics


def _scan_file_interactions(sandbox_dir: str) -> List[Dict[str, Any]]:
    """Scan sandbox directory to track file interactions and outputs created by the process."""
    interactions = []
    if not os.path.exists(sandbox_dir):
        return interactions

    try:
        for root, dirs, files in os.walk(sandbox_dir):
            # Skip Wine internal prefix trees to focus on application files
            if ".wine" in root:
                continue

            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    st = os.stat(fpath)
                    rel_path = os.path.relpath(fpath, sandbox_dir)
                    interactions.append({
                        "file_name": fname,
                        "relative_path": rel_path,
                        "size_bytes": st.st_size,
                        "modified_time": st.st_mtime,
                        "is_output": not fname.startswith(".")
                    })
                except Exception:
                    pass
    except Exception as e:
        logger.debug("Error scanning file interactions in %s: %s", sandbox_dir, e)

    return sorted(interactions, key=lambda x: x["modified_time"], reverse=True)


def inspect_session(session_id: str) -> Dict[str, Any]:
    """
    Programmatically query process activity, track file interactions,
    capture execution telemetry, and stream structured JSON logs back to the host.
    """
    session = get_session(session_id)
    if not session:
        return {
            "success": False,
            "session_id": session_id,
            "error": f"Session '{session_id}' not found."
        }

    status = session.update_liveness()
    uptime = round((session.end_time or time.time()) - session.start_time, 2)
    process_metrics = _get_process_metrics(session.pid)
    file_interactions = _scan_file_interactions(session.sandbox_dir)

    with session.lock:
        recent_stdout = session.stdout_lines[-50:] if session.stdout_lines else []
        recent_stderr = session.stderr_lines[-30:] if session.stderr_lines else []

    telemetry = {
        "success": True,
        "session_id": session.session_id,
        "binary_name": os.path.basename(session.binary_path),
        "binary_path": session.binary_path,
        "pid": session.pid,
        "status": status,
        "runtime": session.runtime,
        "uptime_seconds": uptime,
        "exit_code": session.exit_code,
        "metrics": process_metrics,
        "file_interactions": file_interactions,
        "file_count": len(file_interactions),
        "recent_stdout": recent_stdout,
        "recent_stderr": recent_stderr,
        "total_stdout_lines": len(session.stdout_lines),
        "total_stderr_lines": len(session.stderr_lines),
        "sandbox_dir": session.sandbox_dir
    }

    return telemetry


def execute_command_in_session(
    session_id: str,
    command: str,
    input_data: Optional[str] = None
) -> Dict[str, Any]:
    """
    Trigger a specific deterministic command, stdin message, or hook
    against the target session environment and return raw diagnostics.
    """
    session = get_session(session_id)
    if not session:
        return {
            "success": False,
            "session_id": session_id,
            "error": f"Session '{session_id}' not found."
        }

    start_exec = time.time()
    result = {
        "success": True,
        "session_id": session_id,
        "command": command,
        "latency_ms": 0.0,
        "output": "",
        "action": "stdin_input" if input_data else "sandbox_eval"
    }

    # 1. If input_data is provided and process is running with an open stdin pipe, write to stdin
    if input_data and session.process and session.process.poll() is None:
        try:
            if session.process.stdin:
                session.process.stdin.write(input_data + "\n")
                session.process.stdin.flush()
                result["output"] = f"Piped {len(input_data)} bytes into process stdin."
                result["latency_ms"] = round((time.time() - start_exec) * 1000, 2)
                return result
        except Exception as e:
            logger.warning("Failed writing to process stdin for session %s: %s", session_id, e)

    # 2. Execute deterministic diagnostic command or hook within session sandbox directory
    try:
        # Run sub-command in session context
        sub_proc = subprocess.run(
            command,
            shell=True,
            cwd=session.sandbox_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        result["latency_ms"] = round((time.time() - start_exec) * 1000, 2)
        result["exit_code"] = sub_proc.returncode
        result["stdout"] = sub_proc.stdout.strip()
        result["stderr"] = sub_proc.stderr.strip()
        result["output"] = sub_proc.stdout.strip() or sub_proc.stderr.strip() or f"Exited with code {sub_proc.returncode}"
        result["success"] = (sub_proc.returncode == 0)
    except subprocess.TimeoutExpired:
        result["success"] = False
        result["error"] = "Command timed out after 30 seconds."
        result["latency_ms"] = round((time.time() - start_exec) * 1000, 2)
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["latency_ms"] = round((time.time() - start_exec) * 1000, 2)

    return result


def get_sandbox_telemetry_summary() -> Dict[str, Any]:
    """Retrieve high-level status across all managed sandbox sessions."""
    sessions = list_sessions()
    active_count = sum(1 for s in sessions if s.get("status") == "running")
    total_count = len(sessions)

    return {
        "status": "active",
        "engine": "Momento Headless Sandbox Engine",
        "active_sessions_count": active_count,
        "total_sessions_count": total_count,
        "sessions": sessions
    }
