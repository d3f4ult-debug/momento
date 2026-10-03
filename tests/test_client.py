"""
Unit Tests for Momento Local Client
===================================
Tests configuration management, application scanner, onboarding flow,
conversational NLP router, and CLI subcommands.
"""

import json
import os
import sys
import tempfile
import pytest

from client.config import (
    load_config,
    save_config,
    get_backend_url,
    set_backend_url,
    set_permissions,
    is_setup_completed,
    DEFAULT_BACKEND_URL
)
from client.scanner import AppScanner, resolve_app_binary
from client.onboarding import run_onboarding
from client.nlp_router import NLPRouter
import momento_cli


@pytest.fixture
def temp_momento_env(monkeypatch, tmp_path):
    """Isolate MOMENTO_DIR to temporary directory for test isolation."""
    momento_dir = tmp_path / ".momento"
    momento_dir.mkdir(parents=True, exist_ok=True)
    config_file = momento_dir / "config.json"
    registry_file = momento_dir / "registry.json"

    monkeypatch.setattr("client.config.MOMENTO_DIR", str(momento_dir))
    monkeypatch.setattr("client.config.CONFIG_PATH", str(config_file))
    monkeypatch.setattr("client.config.REGISTRY_PATH", str(registry_file))
    monkeypatch.setattr("client.scanner.REGISTRY_PATH", str(registry_file))
    monkeypatch.setattr("client.scanner.MOMENTO_DIR", str(momento_dir))

    yield {
        "dir": momento_dir,
        "config": config_file,
        "registry": registry_file
    }


def test_config_lifecycle(temp_momento_env):
    """Test loading, saving, permissions, and URL overrides in client config."""
    # Fresh config defaults
    cfg = load_config()
    assert cfg["backend_url"] == DEFAULT_BACKEND_URL
    assert is_setup_completed() is False

    # Update backend URL
    set_backend_url("http://161.97.64.38:8000")
    assert get_backend_url() == "http://161.97.64.38:8000"

    # Set permissions & complete setup
    set_permissions(filesystem=True, discovery=True, execution=True)
    assert is_setup_completed() is True

    loaded = load_config()
    assert loaded["setup_completed"] is True
    assert loaded["permissions"]["filesystem_indexing"] is True


def test_app_scanner_and_resolution(temp_momento_env):
    """Test environment scanning and application fuzzy resolution."""
    registry_path = str(temp_momento_env["registry"])
    scanner = AppScanner(registry_file=registry_path)
    res = scanner.scan_environment()

    assert res["total_apps"] >= 1
    assert os.path.exists(registry_path)

    # Test resolving common binaries
    resolved_notepad = resolve_app_binary("notepad", registry_file=registry_path)
    if sys.platform == "win32":
        assert resolved_notepad is not None
        assert "notepad" in resolved_notepad["binary_path"].lower()

    # Test query with prefix "open "
    resolved_open = resolve_app_binary("open notepad", registry_file=registry_path)
    if sys.platform == "win32":
        assert resolved_open is not None


def test_onboarding_non_interactive(temp_momento_env):
    """Test initial onboarding flow with non-interactive execution."""
    success = run_onboarding(force=True, non_interactive=True, backend_url="http://161.97.64.38:8000")
    assert success is True
    assert is_setup_completed() is True
    assert get_backend_url() == "http://161.97.64.38:8000"


def test_nlp_router_parsing():
    """Test natural language intent parsing."""
    router = NLPRouter()

    action, target, args = router.parse_command("Momento, open notepad")
    assert action == "launch"
    assert target == "notepad"
    assert args is None

    action, target, args = router.parse_command("Momento, run calc with args --mode scientific")
    assert action == "launch"
    assert target == "calc"
    assert args == ["--mode", "scientific"]

    action, target, _ = router.parse_command("hey momento stop sbx_123456")
    assert action == "stop"
    assert target == "sbx_123456"

    action, _, _ = router.parse_command("sessions")
    assert action == "sessions"

    action, _, _ = router.parse_command("scan")
    assert action == "scan"


def test_nlp_router_execution(monkeypatch):
    """Test NLPRouter execution against mocked VPS backend responses."""
    import client.nlp_router

    mock_responses = {
        "/api/sandbox/launch": {
            "success": True,
            "session_id": "sbx_client_test",
            "pid": 7777,
            "runtime": "wine",
            "status": "running"
        },
        "/api/sandbox/sessions": {
            "success": True,
            "total_sessions_count": 1,
            "sessions": [{"session_id": "sbx_client_test", "pid": 7777, "status": "running", "binary_path": "notepad.exe"}]
        },
        "/api/sandbox/stop": {
            "success": True,
            "session_id": "sbx_client_test",
            "status": "terminated"
        }
    }

    def fake_backend_req(endpoint, method="GET", data=None, backend_url=None, timeout=20):
        for path, resp in mock_responses.items():
            if path in endpoint:
                return resp
        return {"success": False, "error": "Not mocked"}

    monkeypatch.setattr(client.nlp_router, "make_backend_request", fake_backend_req)

    router = NLPRouter(backend_url="http://161.97.64.38:8000")

    # 1. Launch command
    res_launch = router.execute("Momento, open notepad")
    assert res_launch["success"] is True
    assert res_launch["session_id"] == "sbx_client_test"
    assert "Launching" in res_launch["message"]

    # 2. Sessions command
    res_sessions = router.execute("sessions")
    assert res_sessions["success"] is True
    assert "sbx_client_test" in res_sessions["message"]

    # 3. Stop command
    res_stop = router.execute("stop sbx_client_test")
    assert res_stop["success"] is True
    assert "terminated" in res_stop["message"]


def test_cli_client_subcommands(monkeypatch, temp_momento_env):
    """Test Momento CLI client subcommands: setup, scan, open, run, ask."""
    import client.nlp_router

    def fake_backend_req(endpoint, method="GET", data=None, backend_url=None, timeout=20):
        return {
            "success": True,
            "session_id": "sbx_mock",
            "pid": 8888,
            "runtime": "wine",
            "status": "running"
        }

    monkeypatch.setattr(client.nlp_router, "make_backend_request", fake_backend_req)

    # 1. setup
    assert momento_cli.main(["setup", "--non-interactive"]) == 0

    # 2. scan
    assert momento_cli.main(["scan", "--json"]) == 0

    # 3. open
    assert momento_cli.main(["open", "notepad"]) == 0

    # 4. run
    assert momento_cli.main(["run", "calc"]) == 0

    # 5. conversational query via preprocess_argv
    assert momento_cli.main(["Momento, open notepad"]) == 0
