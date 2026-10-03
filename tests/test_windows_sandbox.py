"""
Unit and Integration Tests for Windows Sandbox & Binary Inspector
==================================================================
Tests headless sandbox initialization, process spawning, telemetry bridge,
inspection, execution hooks, and API endpoints.
"""

import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

from main import app
from services.windows_sandbox import (
    launch_binary,
    terminate_session,
    list_sessions,
    get_session,
    detect_runtime,
    clear_all_sessions,
    SANDBOX_ROOT_DIR
)
from services.binary_inspector import (
    inspect_session,
    execute_command_in_session,
    get_sandbox_telemetry_summary
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_sessions_fixture():
    """Ensure sessions are cleaned up before and after each test."""
    clear_all_sessions()
    yield
    clear_all_sessions()


def test_sandbox_router_mounted_on_app():
    from services.windows_sandbox import sandbox_router as s_router
    from main import sandbox_router as m_router
    assert s_router is not None
    assert m_router is not None

    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/sandbox/launch" in routes
    assert "/api/sandbox/inspect" in routes
    assert "/api/sandbox/execute" in routes
    assert "/api/sandbox/sessions" in routes
    assert "/api/sandbox/stop" in routes

    # Direct client call verification
    assert client.post("/api/sandbox/launch", json={}).status_code == 422
    assert client.post("/api/sandbox/inspect", json={}).status_code == 422


def test_detect_runtime():
    runtime = detect_runtime()
    assert runtime in ("native", "wine", "subprocess")


def test_launch_nonexistent_binary():
    res = launch_binary("non_existent_binary_xyz123.exe")
    assert res["success"] is False
    assert "not found" in res["error"]


def test_sandbox_process_lifecycle():
    # Use current python executable running a short python loop as target binary
    test_code = "import time; print('READY', flush=True); time.sleep(2); print('DONE', flush=True)"
    res = launch_binary(sys.executable, args=["-c", test_code])

    assert res["success"] is True
    session_id = res["session_id"]
    assert session_id.startswith("sbx_")
    assert res["status"] == "running"
    assert res["pid"] > 0

    session = get_session(session_id)
    assert session is not None
    assert session.pid == res["pid"]

    # Allow time for stdout capture
    time.sleep(0.5)

    # Inspect session
    telemetry = inspect_session(session_id)
    assert telemetry["success"] is True
    assert telemetry["session_id"] == session_id
    assert telemetry["status"] in ("running", "exited")
    assert telemetry["uptime_seconds"] >= 0
    assert "metrics" in telemetry
    assert "file_interactions" in telemetry
    assert any("READY" in line for line in telemetry["recent_stdout"])

    # Terminate session
    term_res = terminate_session(session_id, force=True)
    assert term_res["success"] is True

    time.sleep(0.2)
    post_term = inspect_session(session_id)
    assert post_term["status"] in ("terminated", "killed", "exited", "failed")


def test_execute_command_in_session():
    # Launch a longer-lived process
    test_code = "import time; time.sleep(5)"
    res = launch_binary(sys.executable, args=["-c", test_code])
    assert res["success"] is True
    session_id = res["session_id"]

    try:
        # Execute deterministic command in sandbox directory (e.g. creating a test file)
        cmd_res = execute_command_in_session(
            session_id=session_id,
            command=f"{sys.executable} -c \"print('DETERMINISTIC_OK')\""
        )
        assert cmd_res["success"] is True
        assert "DETERMINISTIC_OK" in cmd_res["output"]
        assert cmd_res["latency_ms"] >= 0

        # Create a file inside sandbox and verify inspection detects it
        file_cmd = execute_command_in_session(
            session_id=session_id,
            command=f"{sys.executable} -c \"with open('output_metric.json', 'w') as f: f.write('{{\\\"status\\\": \\\"ok\\\"}}')\""
        )
        assert file_cmd["success"] is True

        telemetry = inspect_session(session_id)
        assert telemetry["file_count"] >= 1
        found_files = [f["file_name"] for f in telemetry["file_interactions"]]
        assert "output_metric.json" in found_files
    finally:
        terminate_session(session_id, force=True)


def test_api_sandbox_launch_and_inspect_json():
    test_code = "import time; print('API_START'); time.sleep(3)"
    payload = {
        "binary_path": sys.executable,
        "args": f"-c \"{test_code}\"",
        "timeout": 10
    }

    launch_res = client.post("/api/sandbox/launch", json=payload)
    assert launch_res.status_code == 200
    data = launch_res.json()
    assert data["success"] is True
    session_id = data["session_id"]

    try:
        time.sleep(0.3)
        # Inspect via JSON
        inspect_res = client.post("/api/sandbox/inspect", json={"session_id": session_id})
        assert inspect_res.status_code == 200
        insp_data = inspect_res.json()
        assert insp_data["success"] is True
        assert insp_data["session_id"] == session_id
        assert insp_data["status"] == "running"

        # Execute hook via JSON
        exec_res = client.post("/api/sandbox/execute", json={
            "session_id": session_id,
            "command": f"{sys.executable} -c \"print('HOOK_SUCCESS')\""
        })
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["success"] is True
        assert "HOOK_SUCCESS" in exec_data["output"]

        # List sessions
        list_res = client.get("/api/sandbox/sessions")
        assert list_res.status_code == 200
        summary = list_res.json()
        assert summary["status"] == "active"
        assert summary["total_sessions_count"] >= 1

        # Stop via API
        stop_res = client.post("/api/sandbox/stop", json={"session_id": session_id, "force": True})
        assert stop_res.status_code == 200
        assert stop_res.json()["success"] is True
    finally:
        terminate_session(session_id, force=True)


def test_api_sandbox_form_data():
    test_code = "import time; print('FORM_START'); time.sleep(2)"
    res = client.post("/api/sandbox/launch", data={
        "binary_path": sys.executable,
        "args": f"-c \"{test_code}\"",
        "timeout": 15
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    session_id = data["session_id"]

    try:
        inspect_res = client.post("/api/sandbox/inspect", data={"session_id": session_id})
        assert inspect_res.status_code == 200
        assert inspect_res.json()["success"] is True

        exec_res = client.post("/api/sandbox/execute", data={
            "session_id": session_id,
            "command": f"{sys.executable} -c \"print('FORM_EXEC')\""
        })
        assert exec_res.status_code == 200
        assert "FORM_EXEC" in exec_res.json()["output"]
    finally:
        terminate_session(session_id, force=True)


def test_api_sandbox_error_cases():
    # Missing binary_path
    res1 = client.post("/api/sandbox/launch", json={})
    assert res1.status_code == 422

    # Non-existent binary
    res2 = client.post("/api/sandbox/launch", json={"binary_path": "invalid_binary_name.exe"})
    assert res2.status_code == 400
    assert res2.json()["success"] is False

    # Missing session_id on inspect
    res3 = client.post("/api/sandbox/inspect", json={})
    assert res3.status_code == 422

    # Non-existent session_id on inspect
    res4 = client.post("/api/sandbox/inspect", json={"session_id": "sbx_nonexistent"})
    assert res4.status_code == 404
    assert res4.json()["success"] is False

    # Missing fields on execute
    res5 = client.post("/api/sandbox/execute", json={"session_id": "sbx_nonexistent"})
    assert res5.status_code == 422

    # Non-existent session on execute
    res6 = client.post("/api/sandbox/execute", json={"session_id": "sbx_nonexistent", "command": "echo hi"})
    assert res6.status_code == 400
    assert res6.json()["success"] is False


def test_wine_routing_and_env_injection(monkeypatch, tmp_path):
    """Verify that .exe binaries or use_wine=True auto-route to Wine with clean environment injection."""
    from unittest.mock import MagicMock
    import subprocess

    # Create dummy .exe file
    dummy_exe = tmp_path / "mock_app.exe"
    dummy_exe.write_text("dummy binary content")

    captured_cmds = []
    captured_envs = []

    def mock_popen(cmd, **kwargs):
        captured_cmds.append(cmd)
        captured_envs.append(kwargs.get("env", {}))
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None
        mock_proc.stdout = None
        mock_proc.stderr = None
        return mock_proc

    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    # Ensure wine binary appears in path if not present
    monkeypatch.setattr("shutil.which", lambda bin_name: f"/usr/bin/{bin_name}" if "wine" in bin_name or "proton" in bin_name else "/usr/bin/mock")

    # 1. Launch with .exe on non-windows or default
    monkeypatch.setattr("sys.platform", "linux")
    res1 = launch_binary(str(dummy_exe), args=["--flag", "val"])
    assert res1["success"] is True
    assert res1["runtime"] == "wine"
    assert "wine" in captured_cmds[0][0]
    assert captured_cmds[0][1] == str(dummy_exe)
    assert captured_cmds[0][2:] == ["--flag", "val"]

    env1 = captured_envs[0]
    assert env1["DISPLAY"] == ""
    assert env1["WINEDEBUG"] == "-all"
    assert env1["WINEARCH"] == "win64"
    assert env1["WINEDLLOVERRIDES"] == "mscoree,mshtml="
    assert env1["WINEPREFIX"].endswith(".wine")

    # 2. Launch non-exe with use_wine=True
    dummy_script = tmp_path / "run.sh"
    dummy_script.write_text("echo hi")
    res2 = launch_binary(str(dummy_script), use_wine=True)
    assert res2["success"] is True
    assert res2["runtime"] == "wine"
    assert "wine" in captured_cmds[1][0]


def test_momento_cli_commands(monkeypatch):
    """Test Momento CLI command functions and parsing end-to-end."""
    import momento_cli

    # Test parser help
    assert momento_cli.main(["--help"]) == 0

    # Mock make_api_request to verify command handlers without network dependency
    mock_responses = {
        "/api/sandbox/launch": {
            "success": True,
            "session_id": "sbx_mock123",
            "pid": 5555,
            "runtime": "wine",
            "status": "running",
            "binary_path": "/app/test.exe"
        },
        "/api/sandbox/inspect": {
            "success": True,
            "session_id": "sbx_mock123",
            "status": "running",
            "pid": 5555,
            "runtime": "wine",
            "uptime_seconds": 15.5,
            "metrics": {"cpu_percent": 1.2, "memory_mb": 42.0, "num_threads": 4},
            "file_interactions": [{"file_name": "log.txt", "size_bytes": 100}],
            "recent_stdout": ["Session started", "Processing"]
        },
        "/api/sandbox/sessions": {
            "success": True,
            "total_sessions_count": 1,
            "sessions": [{
                "session_id": "sbx_mock123",
                "pid": 5555,
                "status": "running",
                "runtime": "wine",
                "binary_path": "/app/test.exe"
            }]
        },
        "/api/sandbox/stop": {
            "success": True,
            "session_id": "sbx_mock123",
            "status": "terminated"
        },
        "/api/sandbox/execute": {
            "success": True,
            "session_id": "sbx_mock123",
            "exit_code": 0,
            "output": "TEST_CLI_OUTPUT",
            "latency_ms": 5.0
        }
    }

    def fake_make_api_request(url, method="GET", data=None, timeout=15):
        for path, resp in mock_responses.items():
            if path in url:
                return resp
        return {"success": False, "error": "Endpoint not mocked"}

    monkeypatch.setattr(momento_cli, "make_api_request", fake_make_api_request)

    # 1. launch
    rc_launch = momento_cli.main(["launch", "/app/test.exe", "--args", "--headless", "--use-wine"])
    assert rc_launch == 0

    # 2. inspect (human format & json format)
    rc_inspect = momento_cli.main(["inspect", "sbx_mock123"])
    assert rc_inspect == 0
    rc_inspect_json = momento_cli.main(["inspect", "sbx_mock123", "--json"])
    assert rc_inspect_json == 0

    # 3. sessions
    rc_sessions = momento_cli.main(["sessions"])
    assert rc_sessions == 0
    rc_sessions_json = momento_cli.main(["sessions", "--json"])
    assert rc_sessions_json == 0

    # 4. execute
    rc_exec = momento_cli.main(["execute", "sbx_mock123", "echo hi"])
    assert rc_exec == 0

    # 5. stop
    rc_stop = momento_cli.main(["stop", "sbx_mock123", "--force"])
    assert rc_stop == 0


def test_bin_momento_delegates_to_cli():
    """Verify bin/momento runs and outputs Momento CLI help without error."""
    import subprocess
    bin_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bin", "momento"))
    assert os.path.exists(bin_path)

    proc = subprocess.run([sys.executable, bin_path, "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Momento Control CLI" in proc.stdout
    assert "launch" in proc.stdout
    assert "sessions" in proc.stdout

