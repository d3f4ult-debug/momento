"""
Unit and Integration Tests for Momento's Core Platform Engines
==============================================================
Tests the 4 newly unified engines alongside Maestro:
- Lumo (Image Generation & Visual Asset Suite)
- Echo (Speech Synthesis TTS & STT Transcription Core)
- Forge (Custom App Builder & Zero-Vision Native Control)
- Autopilot (Autonomous Background Worker & Task Queue)
"""

import time
import pytest
from fastapi.testclient import TestClient

from client.lumo_engine import LumoEngine
from client.echo_engine import EchoEngine
from client.forge_engine import ForgeEngine
from client.autopilot_engine import AutopilotEngine
from client.nlp_router import NLPRouter
from client.desktop_bridge import DesktopAppBridge
from client.bridge_server import create_standalone_bridge_app

standalone_client = TestClient(create_standalone_bridge_app())


def test_lumo_engine_direct(tmp_path):
    """Test Lumo engine image generation, gallery persistence, and asset retrieval."""
    engine = LumoEngine(output_dir=str(tmp_path / "lumo"))
    res = engine.generate_image(
        prompt="Cyberpunk inventory terminal HUD",
        style="cyberpunk",
        resolution="512x512"
    )
    assert res["success"] is True
    asset = res["asset"]
    assert "Cyberpunk inventory terminal HUD" in asset["prompt"]
    assert asset["style"] == "cyberpunk"
    assert asset["format"] == "svg"

    retrieved = engine.get_asset(asset["id"])
    assert retrieved is not None
    assert retrieved["id"] == asset["id"]

    gallery = engine.get_gallery()
    assert len(gallery) >= 1
    assert any(g["id"] == asset["id"] for g in gallery)


def test_echo_engine_direct(tmp_path):
    """Test Echo speech synthesis (TTS) and audio transcription (STT)."""
    engine = EchoEngine(output_dir=str(tmp_path / "echo"))
    tts_res = engine.synthesize_speech(
        text="Momento autonomous core activated",
        voice="nova",
        pitch=1.0,
        rate=1.0
    )
    assert tts_res["success"] is True
    speech = tts_res["speech"]
    assert speech["duration"] > 0
    assert speech["audio_format"] == "wav"

    recordings = engine.get_recordings()
    assert len(recordings) >= 1
    assert any(r["id"] == speech["id"] for r in recordings)

    # Transcription
    stt_res = engine.transcribe_audio(speech["file_path"], simulated_text="Momento autonomous core activated")
    assert stt_res["success"] is True
    assert "Momento autonomous core activated" in stt_res["text"]


def test_forge_engine_and_zero_vision_hooks(tmp_path):
    """Test Forge app generation and zero-vision native programmatic control hooks."""
    engine = ForgeEngine(output_dir=str(tmp_path / "forge"))
    app_meta = engine.build_app(
        name="Warehouse Stock Tracker",
        category="inventory",
        description="Warehouse stock control app",
        initial_data=[]
    )
    assert app_meta["success"] is True
    app = app_meta["app"]
    app_id = app["id"]
    assert "Warehouse Stock Tracker" in app["name"]
    assert len(app["fields"]) >= 2

    # Zero-vision programmatic hooks: Add record
    add_res = engine.execute_app_hook(
        app_id=app_id,
        action="add_record",
        payload={"item_name": "Widget A", "sku": "WID-001", "quantity": 50, "price": 12.99}
    )
    assert add_res["success"] is True

    # Read back records via get_app
    app_state = engine.get_app(app_id)
    assert len(app_state["data"]) == 1
    assert app_state["data"][0]["item_name"] == "Widget A"

    # Zero-vision hook: Update record
    upd_res = engine.execute_app_hook(
        app_id=app_id,
        action="update_record",
        payload={"id_field": "sku", "value": "WID-001", "updates": {"quantity": 75}}
    )
    assert upd_res["success"] is True
    app_state = engine.get_app(app_id)
    assert app_state["data"][0]["quantity"] == 75

    # Zero-vision hook: Delete record
    del_res = engine.execute_app_hook(
        app_id=app_id,
        action="delete_record",
        payload={"id_field": "sku", "value": "WID-001"}
    )
    assert del_res["success"] is True
    assert len(engine.get_app(app_id)["data"]) == 0


def test_autopilot_engine_workflow(tmp_path):
    """Test Autopilot background workflow execution and task progress tracking."""
    autopilot = AutopilotEngine(output_dir=str(tmp_path / "autopilot"))
    steps = [
        {"action": "wait", "delay_sec": 0.1},
        {"action": "log", "message": "Transaction verified successfully"}
    ]

    task_res = autopilot.enqueue_workflow(name="Daily POS Sync", steps=steps)
    assert task_res["success"] is True
    task_id = task_res["task_id"]

    # Wait for completion (steps run quickly)
    for _ in range(30):
        t = autopilot.get_task(task_id)
        if t and t["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)

    task_final = autopilot.get_task(task_id)
    assert task_final["status"] == "completed"
    assert task_final["progress"] == 1.0
    assert len(task_final["logs"]) >= 2


def test_nlp_intent_router_platform_engines():
    """Verify NLP router parses intent for Lumo, Echo, Forge, and Autopilot."""
    router = NLPRouter()

    # Lumo
    action, target, args = router.parse_command("lumo generate futuristic robot logo")
    assert action == "lumo_generate"
    assert "futuristic robot logo" in target

    # Echo TTS
    action, target, args = router.parse_command("echo speak Welcome to Momento AI Platform")
    assert action == "echo_speak"
    assert "Welcome to Momento AI Platform" in target

    # Echo STT
    action, target, args = router.parse_command("transcribe audio")
    assert action == "echo_transcribe"

    # Forge Build
    action, target, args = router.parse_command("forge build restaurant ordering system")
    assert action == "forge_build"
    assert "restaurant ordering system" in target

    # Autopilot Enqueue
    action, target, args = router.parse_command("autopilot run batch reconciliation")
    assert action == "autopilot_enqueue"


def test_platform_engines_rest_endpoints():
    """Verify REST endpoints for Lumo, Echo, Forge, and Autopilot in standalone bridge app."""
    # 1. Lumo REST
    res_lumo = standalone_client.post(
        "/api/client/lumo/generate",
        json={"prompt": "Modern gradient icon", "style": "vector", "resolution": "512x512"}
    )
    assert res_lumo.status_code == 200
    assert res_lumo.json()["success"] is True

    res_lumo_gallery = standalone_client.get("/api/client/lumo/gallery")
    assert res_lumo_gallery.status_code == 200
    assert "assets" in res_lumo_gallery.json()

    # 2. Echo REST
    res_echo_tts = standalone_client.post(
        "/api/client/echo/synthesize",
        json={"text": "Test speech synthesis", "voice": "echo"}
    )
    assert res_echo_tts.status_code == 200
    assert res_echo_tts.json()["success"] is True

    res_echo_recs = standalone_client.get("/api/client/echo/recordings")
    assert res_echo_recs.status_code == 200
    assert "recordings" in res_echo_recs.json()

    # 3. Forge REST
    res_forge_build = standalone_client.post(
        "/api/client/forge/build",
        json={"app_name": "Contacts Manager", "category": "utility"}
    )
    assert res_forge_build.status_code == 200
    f_data = res_forge_build.json()
    assert f_data["success"] is True
    forge_app_id = f_data["app"]["id"]

    res_forge_apps = standalone_client.get("/api/client/forge/apps")
    assert res_forge_apps.status_code == 200
    assert any(a["id"] == forge_app_id for a in res_forge_apps.json()["apps"])

    res_forge_exec = standalone_client.post(
        f"/api/client/forge/apps/{forge_app_id}/execute",
        json={"action": "add_record", "payload": {"name": "Alice Smith", "email": "alice@test.com"}}
    )
    assert res_forge_exec.status_code == 200
    assert res_forge_exec.json()["success"] is True

    # 4. Autopilot REST
    res_ap_enqueue = standalone_client.post(
        "/api/client/autopilot/enqueue",
        json={
            "name": "Automated Contact Sync",
            "steps": [{"action": "log", "message": "Synchronizing contact entries"}]
        }
    )
    assert res_ap_enqueue.status_code == 200
    ap_data = res_ap_enqueue.json()
    assert ap_data["success"] is True
    task_id = ap_data["task_id"]

    res_ap_tasks = standalone_client.get("/api/client/autopilot/tasks")
    assert res_ap_tasks.status_code == 200
    assert any(t["id"] == task_id for t in res_ap_tasks.json()["tasks"])
