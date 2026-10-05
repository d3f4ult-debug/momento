"""
Unit and Integration Tests for Client Bridge REST API
=====================================================
Tests endpoints used by Flutter Desktop Client to communicate with Python Core:
/api/client/state, /api/client/permissions, /api/client/scan, /api/client/chat,
/api/client/logs, /api/client/stop, /api/client/settings.
"""

import pytest
from fastapi.testclient import TestClient

from main import app
from client.bridge_server import client_router, create_standalone_bridge_app

http_client = TestClient(app)
standalone_client = TestClient(create_standalone_bridge_app())


def test_client_state_endpoint():
    """Verify /api/client/state returns configuration, permissions, and app catalog."""
    res = http_client.get("/api/client/state")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "backend_url" in data
    assert "discovered_apps" in data
    assert "active_sessions" in data
    assert "execution_mode" in data


def test_standalone_bridge_app():
    """Verify standalone bridge server instance initializes cleanly."""
    res = standalone_client.get("/api/client/state")
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_client_permissions_and_scan_endpoints():
    """Verify /api/client/permissions records consent and triggers scan."""
    payload = {
        "filesystem": True,
        "discovery": True,
        "execution": True,
        "backend_url": "http://161.97.64.38:8000"
    }
    res = http_client.post("/api/client/permissions", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["setup_completed"] is True
    assert data["total_apps"] >= 1

    # Verify /api/client/scan
    res_scan = http_client.post("/api/client/scan")
    assert res_scan.status_code == 200
    assert res_scan.json()["success"] is True
    assert res_scan.json()["total_apps"] >= 1


def test_client_chat_and_execution_endpoints(monkeypatch):
    """Verify conversational chat dispatch and session control via client API."""
    import client.nlp_router as nlp_mod

    # Mock VPS request to isolate test
    def fake_vps_req(endpoint, method="GET", data=None, backend_url=None, timeout=20):
        if "/launch" in endpoint:
            return {
                "success": True,
                "session_id": "sbx_mock_flutter_1",
                "pid": 5432,
                "runtime": "wine",
                "status": "running"
            }
        return {"success": True}

    monkeypatch.setattr("client.nlp_router.make_backend_request", fake_vps_req)
    monkeypatch.setattr("client.desktop_bridge.make_backend_request", fake_vps_req)

    # 1. Chat dispatch
    chat_payload = {
        "message": "Momento, open notepad",
        "execution_mode": "vps"
    }
    res = http_client.post("/api/client/chat", json=chat_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["session_id"] == "sbx_mock_flutter_1"
    assert data["pid"] == 5432

    # 2. Stop session
    res_stop = http_client.post("/api/client/stop", json={"session_id": "sbx_mock_flutter_1"})
    assert res_stop.status_code == 200

    # 3. Save settings
    res_settings = http_client.post("/api/client/settings", json={
        "backend_url": "http://161.97.64.38:8000",
        "execution_mode": "hybrid"
    })
    assert res_settings.status_code == 200
    assert res_settings.json()["execution_mode"] == "hybrid"


def test_client_chat_empty_message():
    """Verify empty message validation."""
    res = http_client.post("/api/client/chat", json={"message": "   "})
    assert res.status_code == 400
    assert "empty" in res.json()["message"].lower()


def test_client_register_app_endpoint():
    """Verify POST /api/client/apps/register adds custom app and returns success."""
    import sys
    payload = {
        "name": "CustomApiTool",
        "binary_path": sys.executable,
        "aliases": ["apitool"],
        "category": "development"
    }
    res = http_client.post("/api/client/apps/register", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["app"]["name"] == "CustomApiTool"
    assert data["app"]["source"] == "manual_registration"


def test_client_register_app_with_working_dir_and_args(tmp_path):
    """Verify POST /api/client/apps/register persists working_dir and args."""
    import sys
    custom_dir = str(tmp_path / "workdir")
    data_file = str(tmp_path / "data.db")
    payload = {
        "name": "DatabaseTool",
        "binary_path": sys.executable,
        "working_dir": custom_dir,
        "args": f"--db {data_file}",
        "data_file_path": data_file,
        "category": "development"
    }
    res = http_client.post("/api/client/apps/register", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["app"]["working_dir"] == custom_dir
    assert data["app"]["default_args"] == ["--db", data_file]
    assert data["app"]["data_file_path"] == data_file


