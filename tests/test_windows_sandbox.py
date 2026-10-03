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
