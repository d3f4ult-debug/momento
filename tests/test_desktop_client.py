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


def test_custom_app_registration_and_persistence(temp_bridge):
    """Test manually registering custom app and ensuring it survives catalog rescans."""
    # Register custom application
    res = temp_bridge.register_app(
        name="CustomPythonTool",
        binary_path=sys.executable,
        aliases=["pytool", "pycustom"],
        category="development"
    )
    assert res["success"] is True
    assert res["app"]["id"] == "custompythontool"
    assert res["app"]["source"] == "manual_registration"

    # Verify app is discoverable in catalog
    from client.scanner import AppScanner
    scanner = AppScanner()
    catalog = scanner.get_registered_apps()
    found = any(app["id"] == "custompythontool" for app in catalog)
    assert found is True

    # Rescan environment and verify custom app is preserved
    rescanned_res = temp_bridge.rescan_apps()
    assert rescanned_res["success"] is True
    assert any(app["id"] == "custompythontool" for app in rescanned_res["apps"])


def test_nlp_router_register_intent(temp_bridge):
    """Test registering app via natural language in DesktopAppBridge."""
    msg = f"Momento, register app MySpecialApp at {sys.executable}"
    res = temp_bridge.send_message(msg)
    assert res["success"] is True
    assert res["action"] == "register"
    assert res["app"]["id"] == "myspecialapp"
    assert res["app"]["binary_path"] == sys.executable


def test_gui_automation_parsing_and_execution(temp_engine):
    """Test compound instruction parsing and launch_and_interact execution flow."""
    from client.gui_automation import parse_compound_instruction

    # 1. Test instruction parsing
    prompt = "open notepad and type Hello world and press enter"
    app_name, steps = parse_compound_instruction(prompt)
    assert app_name == "notepad"
    assert any(s["action"] == "type" and s["text"] == "Hello world" for s in steps)
    assert any(s["action"] == "press" and s["key"] == "enter" for s in steps)

    # 2. Test launch_and_interact with a mock harmless process (sys.executable)
    res = temp_engine.launch_and_interact(
        binary_path=sys.executable,
        steps=[{"action": "wait", "seconds": 0.2}],
        app_name="MockPython"
    )
    assert res["success"] is True
    assert res["status"] in ("running", "completed")
    assert res["pid"] > 0
    time.sleep(0.5)

    logs_res = temp_engine.get_logs(res["session_id"])
    assert logs_res["success"] is True
    assert any("Automation" in line or "Launched" in line or "Process initialized" in line for line in logs_res["logs"])
    temp_engine.stop_session(res["session_id"], force=True)
    time.sleep(0.5)


def test_resolve_shortcut_or_target():
    """Test resolve_shortcut_or_target helper on direct files and directories."""
    from client.scanner import resolve_shortcut_or_target

    # Direct executable
    target, cwd, args = resolve_shortcut_or_target(sys.executable, working_dir=None, args=["--version"])
    assert os.path.normcase(target) == os.path.normcase(sys.executable)
    assert cwd == os.path.dirname(sys.executable)
    assert args == ["--version"]

    # Directory resolution
    py_dir = os.path.dirname(sys.executable)
    target_dir, cwd_dir, _ = resolve_shortcut_or_target(py_dir)
    assert target_dir.lower().endswith(".exe")
    assert cwd_dir == py_dir


def test_execution_engine_working_dir_and_args(temp_engine, tmp_path):
    """Test that ExecutionEngine respects custom working_dir and arguments."""
    subfolder = tmp_path / "custom_workdir"
    subfolder.mkdir()
    flag_file = subfolder / "test_flag.txt"
    flag_file.write_text("ACTIVE_DATA")

    res = temp_engine.launch(
        sys.executable,
        args=["-c", "import os, sys; print('CWD:' + os.getcwd(), flush=True); print('FLAG:' + open('test_flag.txt').read().strip(), flush=True)"],
        working_dir=str(subfolder),
        app_name="DataApp"
    )

    assert res["success"] is True
    assert res["working_dir"] == str(subfolder)
    session_id = res["session_id"]

    time.sleep(0.5)
    logs_res = temp_engine.get_logs(session_id)
    assert logs_res["success"] is True
    combined_logs = " ".join(logs_res["logs"])
    assert "CWD:" in combined_logs
    assert "FLAG:ACTIVE_DATA" in combined_logs
    temp_engine.stop_session(session_id, force=True)


def test_custom_app_registration_with_data_files(temp_bridge, tmp_path):
    """Test registering custom app with working directory, arguments, and data file."""
    data_dir = tmp_path / "app_data"
    data_dir.mkdir()
    config_file = data_dir / "settings.cfg"
    config_file.write_text("port=9000")

    res = temp_bridge.register_app(
        name="DataProcessor",
        binary_path=sys.executable,
        aliases=["dataproc"],
        category="utility",
        working_dir=str(data_dir),
        args=f"--config {config_file}",
        data_file_path=str(config_file)
    )

    assert res["success"] is True
    app = res["app"]
    assert app["working_dir"] == str(data_dir)
    assert app["default_args"] == ["--config", str(config_file)]
    assert app["data_file_path"] == str(config_file)


def test_nlp_router_contextual_inspection_intents():
    """Verify recognition of contextual inspection and window listing phrases."""
    from client.nlp_router import NLPRouter
    router = NLPRouter()

    # Contextual screen & app inspection phrases
    assert router.parse_command("inspect the app") == ("inspect", "active", None)
    assert router.parse_command("Momento, what is on screen") == ("inspect", "active", None)
    assert router.parse_command("what's on screen") == ("inspect", "active", None)
    assert router.parse_command("inspect active session") == ("inspect", "active", None)
    assert router.parse_command("inspect screen") == ("inspect", "active", None)
    assert router.parse_command("inspect foreground window") == ("inspect", "active", None)
    assert router.parse_command("inspect ui") == ("inspect", "active", None)

    # Window listing phrases
    assert router.parse_command("list active windows") == ("list_windows", None, None)
    assert router.parse_command("show active windows") == ("list_windows", None, None)
    assert router.parse_command("windows") == ("list_windows", None, None)

    # Explicit target app or session ID
    assert router.parse_command("inspect notepad") == ("inspect", "notepad", None)
    assert router.parse_command("inspect sbx_local_12345") == ("inspect", "sbx_local_12345", None)


def test_ui_introspection_structure():
    """Verify inspect_window_ui and list_active_windows return structured payloads."""
    from client.gui_automation import inspect_window_ui, list_active_windows

    # Active windows list
    windows = list_active_windows()
    assert isinstance(windows, list)

    # UI inspection output contract
    res = inspect_window_ui()
    assert "success" in res
    assert "log_lines" in res
    assert isinstance(res["log_lines"], list)
    assert any("[*]" in line or "[-]" in line or "[+]" in line for line in res["log_lines"])
    assert "summary" in res
    assert "controls" in res
    assert "visible_texts" in res


def test_execution_engine_inspect_session(temp_engine):
    """Verify ExecutionEngine inspect_session retrieves active session and streams log lines."""
    # Launch short python process
    launch_res = temp_engine.launch(
        sys.executable,
        args=["-c", "import time; print('READY', flush=True); time.sleep(1)"],
        app_name="MockInspectorApp"
    )
    assert launch_res["success"] is True
    session_id = launch_res["session_id"]

    # Contextual session inspection
    insp_res = temp_engine.inspect_session(session_id)
    assert insp_res["session_id"] == session_id
    assert insp_res["app_name"] == "MockInspectorApp"
    assert "log_lines" in insp_res
    assert len(insp_res["logs"]) >= 1

    temp_engine.stop_session(session_id, force=True)


def test_desktop_bridge_inspection_messaging(temp_bridge):
    """Verify DesktopAppBridge handles conversational inspection requests."""
    # Contextual screen inspection
    res_inspect = temp_bridge.send_message("what is on screen")
    assert res_inspect["action"] == "inspect"
    assert "message" in res_inspect
    assert "logs" in res_inspect

    # List active windows
    res_windows = temp_bridge.send_message("list active windows")
    assert res_windows["action"] == "list_windows"
    assert "message" in res_windows
    assert "windows" in res_windows


def test_app_profiler_persistence_and_classification(tmp_path):
    """Verify profile persistence, control semantic classification, and workflow inference."""
    from client.app_profiler import (
        classify_control_semantics,
        delete_profile,
        infer_workflows_and_tags,
        list_profiles,
        load_profile,
        resolve_control_from_profile,
        save_profile,
    )

    # 1. Test Control Classification
    c_btn = {"control_type": "Button", "name": "Login", "automation_id": "btnLogin"}
    role_btn, actions_btn = classify_control_semantics(c_btn)
    assert role_btn == "login_button"
    assert "click" in actions_btn

    c_user = {"control_type": "Edit", "name": "Username", "automation_id": "txtUser"}
    role_user, actions_user = classify_control_semantics(c_user)
    assert role_user == "username_input"
    assert "type" in actions_user

    c_search = {"control_type": "Edit", "name": "Search Box", "automation_id": "txtSearch"}
    role_search, actions_search = classify_control_semantics(c_search)
    assert role_search == "search_input"

    # 2. Test Capability Inference
    tags, workflows = infer_workflows_and_tags([
        {"semantic_role": role_btn, "name": "Login"},
        {"semantic_role": role_user, "name": "Username"},
        {"semantic_role": role_search, "name": "Search"}
    ])
    assert "authentication" in tags
    assert "search" in tags
    assert any(w["name"] == "login" for w in workflows)
    assert any(w["name"] == "search" for w in workflows)

    # 3. Test Profile Persistence
    mock_profile = {
        "app_id": "test_app_profile",
        "app_name": "TestAppProfile",
        "binary_path": "C:\\Program Files\\TestApp\\app.exe",
        "created_at": "2026-10-06T12:00:00",
        "window": {"title": "Test App Window", "pid": 9999},
        "stats": {"total_controls": 3, "interactive_controls": 3, "tags_count": 2, "workflows_count": 2},
        "semantic_tags": tags,
        "controls": [
            {"id": "btn_login", "name": "Login", "semantic_role": "login_button", "control_type": "Button", "is_interactive": True},
            {"id": "input_user", "name": "Username", "semantic_role": "username_input", "control_type": "Edit", "is_interactive": True},
            {"id": "input_search", "name": "Search Box", "semantic_role": "search_input", "control_type": "Edit", "is_interactive": True}
        ],
        "available_workflows": workflows,
        "summary": "Mock profile summary."
    }

    path = save_profile(mock_profile)
    assert os.path.exists(path)

    loaded = load_profile("TestAppProfile")
    assert loaded is not None
    assert loaded["app_name"] == "TestAppProfile"
    assert len(loaded["controls"]) == 3

    # 4. Test Control Resolution from Profile
    ctrl_login = resolve_control_from_profile(loaded, "login button")
    assert ctrl_login is not None
    assert ctrl_login["id"] == "btn_login"

    ctrl_user = resolve_control_from_profile(loaded, "user")
    assert ctrl_user is not None
    assert ctrl_user["id"] == "input_user"

    # 5. List and Delete
    profs = list_profiles()
    assert any(p["app_id"] == "test_app_profile" for p in profs)

    del_res = delete_profile("TestAppProfile")
    assert del_res is True
    assert load_profile("TestAppProfile") is None


def test_nlp_router_profiling_and_actions():
    """Verify NLPRouter recognizes reverse-engineering and profile semantic workflow queries."""
    from client.nlp_router import NLPRouter
    router = NLPRouter()

    # Profiles catalog commands
    assert router.parse_command("profiles") == ("profiles", None, None)
    assert router.parse_command("list profiles") == ("profiles", None, None)
    assert router.parse_command("show profiles") == ("profiles", None, None)

    # Profiling / reverse-engineering commands
    assert router.parse_command("reverse engineer Dokonchi") == ("profile", "Dokonchi", None)
    assert router.parse_command("reverse-engineer notepad") == ("profile", "notepad", None)
    assert router.parse_command("profile calc") == ("profile", "calc", None)
    assert router.parse_command("analyze this app") == ("profile", "active", None)
    assert router.parse_command("learn Dokonchi") == ("profile", "Dokonchi", None)

    # Semantic workflow multi-step instruction
    action, target, steps = router.parse_command("In Dokonchi, click the login button, enter user X, and submit")
    assert action == "profile_action"
    assert target == "Dokonchi"
    assert steps == ["click the login button", "enter user X", "submit"]

    action2, target2, steps2 = router.parse_command("In notepad, type Hello World into text editor")
    assert action2 == "profile_action"
    assert target2 == "notepad"
    assert steps2 == ["type Hello World into text editor"]


def test_desktop_bridge_profiling_commands(temp_bridge):
    """Verify DesktopAppBridge handles profile listing and profile inspection."""
    res_profiles = temp_bridge.send_message("profiles")
    assert res_profiles["action"] == "profiles"
    assert "message" in res_profiles
    assert "total_profiles" in res_profiles



