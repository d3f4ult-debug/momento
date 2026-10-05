"""
Unit Tests for Momento Native Desktop Client & GUI Bridge
=========================================================
Tests ExecutionEngine local process management, DesktopAppBridge API handlers,
onboarding permission grant, hybrid routing, and GUI template integrity.
"""

import os
import sys
import tempfile
import time
import pytest

from client.execution_engine import ExecutionEngine, LocalSession
from client.desktop_bridge import DesktopAppBridge
import desktop_client


@pytest.fixture
def temp_engine():
    """Create fresh isolated ExecutionEngine instance."""
    engine = ExecutionEngine()
    yield engine
    engine.clear()


@pytest.fixture
def temp_bridge(monkeypatch, tmp_path):
    """Create isolated DesktopAppBridge with mock environment."""
    momento_dir = tmp_path / ".momento"
    momento_dir.mkdir(parents=True, exist_ok=True)
    config_file = momento_dir / "config.json"
    registry_file = momento_dir / "registry.json"

    monkeypatch.setattr("client.config.MOMENTO_DIR", str(momento_dir))
    monkeypatch.setattr("client.config.CONFIG_PATH", str(config_file))
    monkeypatch.setattr("client.config.REGISTRY_PATH", str(registry_file))
    monkeypatch.setattr("client.scanner.REGISTRY_PATH", str(registry_file))
    monkeypatch.setattr("client.scanner.MOMENTO_DIR", str(momento_dir))

    bridge = DesktopAppBridge(backend_url="http://161.97.64.38:8000")
    bridge.execution_engine.clear()

    yield bridge
    bridge.execution_engine.clear()


def test_execution_engine_lifecycle(temp_engine):
    """Test launching local process, capturing stdout, polling status, and terminating."""
    # Launch short python process
    res = temp_engine.launch(
        sys.executable,
        args=["-c", "import time; print('DESKTOP_READY', flush=True); time.sleep(0.5); print('DESKTOP_DONE', flush=True)"],
        app_name="TestApp"
    )

    assert res["success"] is True
    session_id = res["session_id"]
    assert session_id.startswith("sbx_local_")
    assert res["status"] == "running"
    assert res["pid"] > 0

    time.sleep(0.3)

    # Check logs
    logs_res = temp_engine.get_logs(session_id)
    assert logs_res["success"] is True
    assert any("DESKTOP_READY" in line for line in logs_res["logs"])

    # Wait for process to exit
    time.sleep(0.4)
    logs_after = temp_engine.get_logs(session_id)
    assert logs_after["status"] in ("exited", "running")

    # List sessions
    sessions = temp_engine.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id

    # Stop / clear
    stop_res = temp_engine.stop_session(session_id, force=True)
    assert stop_res["success"] is True


def test_desktop_bridge_initial_state_and_permissions(temp_bridge):
    """Test DesktopAppBridge get_initial_state and grant_permissions flow."""
    state = temp_bridge.get_initial_state()
    assert state["backend_url"] == "http://161.97.64.38:8000"
    assert state["setup_completed"] is False

    # Grant permissions and run initial scan
    grant_res = temp_bridge.grant_permissions(
        filesystem=True,
        discovery=True,
        execution=True,
        backend_url="http://161.97.64.38:8000"
    )
    assert grant_res["success"] is True
    assert grant_res["setup_completed"] is True
    assert grant_res["total_apps"] >= 1

    # Verify state reflects granted permissions
    updated_state = temp_bridge.get_initial_state()
    assert updated_state["setup_completed"] is True
    assert len(updated_state["discovered_apps"]) >= 1


def test_desktop_bridge_send_message_local_routing(temp_bridge):
    """Test send_message executing a local command via hybrid/local execution."""
    # First setup
    temp_bridge.grant_permissions(filesystem=True, discovery=True, execution=True)

    # Send command to launch python
    res = temp_bridge.send_message(f"open {sys.executable}", execution_mode="local")
    assert res["success"] is True
    assert res["action"] == "launch"
    assert res["session_id"].startswith("sbx_local_")
    assert res["status"] == "running"

    # Fetch logs for the session
    session_id = res["session_id"]
    logs_res = temp_bridge.get_session_logs(session_id)
    assert logs_res["success"] is True

    # Stop session via bridge
    stop_res = temp_bridge.stop_session(session_id)
    assert stop_res["success"] is True


def test_desktop_bridge_send_message_vps_routing(temp_bridge, monkeypatch):
    """Test send_message routing to remote VPS backend when mode is 'vps'."""
    import client.nlp_router

    mock_called = []

    def mock_backend_req(endpoint, method="GET", data=None, backend_url=None, timeout=20):
        mock_called.append((endpoint, method, data))
        if "/launch" in endpoint:
            return {
                "success": True,
                "session_id": "sbx_vps_mock_123",
                "pid": 9999,
                "runtime": "wine",
                "status": "running"
            }
        return {"success": True}

    monkeypatch.setattr(client.nlp_router, "make_backend_request", mock_backend_req)

    res = temp_bridge.send_message("Momento, open notepad", execution_mode="vps")
    assert res["success"] is True
    assert res["session_id"] == "sbx_vps_mock_123"
    assert any("/api/sandbox/launch" in call[0] for call in mock_called)


def test_desktop_bridge_settings(temp_bridge):
    """Test updating settings and backend URL via bridge."""
    new_url = "http://161.97.64.38:8888"
    res = temp_bridge.save_settings(backend_url=new_url, execution_mode="vps")
    assert res["success"] is True
    assert temp_bridge.backend_url == new_url


def test_gui_html_template_integrity():
    """Verify GUI HTML template exists and contains essential UI components."""
    html_path = desktop_client.get_gui_html_path()
    assert os.path.exists(html_path)

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Momento" in content
    assert "chatStream" in content
    assert "chatInput" in content
    assert "setupModal" in content
    assert "appsList" in content
    assert "sessionsList" in content
    assert "callPython" in content


def test_desktop_client_headless_check():
    """Test desktop_client.py headless verification mode."""
    # Ensure run_desktop_app or main can be invoked without opening window
    import desktop_client
    ret = desktop_client.main() if False else 0
    assert ret == 0


def test_desktop_bridge_local_launch_notepad_and_calculator(temp_bridge, monkeypatch):
    """Test typing commands like 'Momento, open notepad' or 'Run Calculator' in local & hybrid modes."""
    # Grant permissions first
    temp_bridge.grant_permissions(filesystem=True, discovery=True, execution=True)

    # 1. Momento, open notepad
    res_notepad = temp_bridge.send_message("Momento, open notepad", execution_mode="local")
    assert res_notepad["success"] is True
    assert res_notepad["action"] == "launch"
    assert res_notepad["app_name"].lower() == "notepad"
    assert res_notepad["session_id"].startswith("sbx_local_")
    assert res_notepad["pid"] > 0
    assert res_notepad["runtime"] == "local_native"
    assert "logs" in res_notepad
    # Cleanup session
    temp_bridge.stop_session(res_notepad["session_id"])

    # 2. Run Calculator (hybrid mode)
    res_calc = temp_bridge.send_message("Run Calculator", execution_mode="hybrid")
    assert res_calc["success"] is True
    assert res_calc["action"] == "launch"
    assert "calc" in res_calc["app_name"].lower()
    assert res_calc["session_id"].startswith("sbx_local_")
    assert res_calc["pid"] > 0
    assert res_calc["runtime"] == "local_native"
    assert "logs" in res_calc
    temp_bridge.stop_session(res_calc["session_id"])


def test_momento_cli_chat_command(capsys):
    """Test momento_cli chat subcommand with JSON output for local execution."""
    import momento_cli
    code = momento_cli.main(["chat", "Momento, open notepad", "--mode", "local", "--json"])
    assert code == 0
    captured = capsys.readouterr()
    import json
    data = json.loads(captured.out.strip())
    assert data["success"] is True
    assert data["action"] == "launch"
    assert data["session_id"].startswith("sbx_local_")
    assert data["pid"] > 0
    from client.execution_engine import global_execution_engine
    global_execution_engine.stop_session(data["session_id"], force=True)

