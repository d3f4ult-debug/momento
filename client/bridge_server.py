"""
Momento Client API Bridge Server
================================
Exposes DesktopAppBridge methods via clean RESTful HTTP endpoints for
the native Flutter Windows desktop application or external local clients.
"""

import os
import sys
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Ensure root directory is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.desktop_bridge import DesktopAppBridge

client_router = APIRouter(prefix="/api/client", tags=["Client Bridge"])
_bridge_instance = DesktopAppBridge()


@client_router.get("/state")
async def get_state_endpoint():
    """Retrieve setup status, permissions, discovered apps, and active sessions."""
    try:
        data = _bridge_instance.get_initial_state()
        return JSONResponse(status_code=200, content={"success": True, **data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/permissions")
async def grant_permissions_endpoint(payload: Dict[str, Any] = Body(...)):
    """Record granted permissions and trigger initial environment scan."""
    try:
        fs = payload.get("filesystem", True)
        disc = payload.get("discovery", True)
        exec_rights = payload.get("execution", True)
        backend_url = payload.get("backend_url")
        res = _bridge_instance.grant_permissions(
            filesystem=fs,
            discovery=disc,
            execution=exec_rights,
            backend_url=backend_url
        )
        return JSONResponse(status_code=200, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/scan")
async def rescan_apps_endpoint():
    """Perform local application discovery and return registered apps."""
    try:
        res = _bridge_instance.rescan_apps()
        return JSONResponse(status_code=200, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/apps/register")
async def register_custom_app_endpoint(payload: Dict[str, Any] = Body(...)):
    """Manually register a custom application into the local registry."""
    name = payload.get("name", "").strip()
    binary_path = payload.get("binary_path", "").strip()
    aliases = payload.get("aliases")
    category = payload.get("category", "custom")
    working_dir = payload.get("working_dir")
    args = payload.get("args") or payload.get("arguments")
    data_file_path = payload.get("data_file_path") or payload.get("data_file")

    if not name or not binary_path:
        return JSONResponse(status_code=400, content={"success": False, "error": "Both 'name' and 'binary_path' are required."})

    try:
        res = _bridge_instance.register_app(
            name=name,
            binary_path=binary_path,
            aliases=aliases,
            category=category,
            working_dir=working_dir,
            args=args,
            data_file_path=data_file_path,
        )
        return JSONResponse(status_code=200, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/chat")
async def chat_message_endpoint(payload: Dict[str, Any] = Body(...)):
    """Process natural language conversational command and execute via hybrid/local engine."""
    message = payload.get("message", "")
    mode = payload.get("execution_mode", "hybrid")
    if not message.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "Message cannot be empty"})

    try:
        res = _bridge_instance.send_message(message=message, execution_mode=mode)
        return JSONResponse(status_code=200, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.get("/logs/{session_id}")
async def get_session_logs_endpoint(session_id: str):
    """Retrieve live stdout/stderr streams and process exit status."""
    try:
        res = _bridge_instance.get_session_logs(session_id)
        status_code = 200 if res.get("success", False) else 404
        return JSONResponse(status_code=status_code, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/stop")
async def stop_session_endpoint(payload: Dict[str, Any] = Body(...)):
    """Terminate an active local or VPS process session."""
    session_id = payload.get("session_id", "")
    if not session_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "session_id required"})

    try:
        res = _bridge_instance.stop_session(session_id)
        status_code = 200 if res.get("success", False) else 400
        return JSONResponse(status_code=status_code, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/settings")
async def save_settings_endpoint(payload: Dict[str, Any] = Body(...)):
    """Update configured backend URL and default execution mode."""
    backend_url = payload.get("backend_url", "")
    mode = payload.get("execution_mode", "hybrid")
    try:
        res = _bridge_instance.save_settings(backend_url=backend_url, execution_mode=mode)
        return JSONResponse(status_code=200, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.get("/windows")
async def list_windows_endpoint():
    """Enumerate active visible desktop application windows."""
    try:
        windows = _bridge_instance.list_windows()
        return JSONResponse(status_code=200, content={"success": True, "total_windows": len(windows), "windows": windows})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/inspect")
async def inspect_ui_endpoint(payload: Dict[str, Any] = Body(default={})):
    """Introspect active or target application window and UI tree."""
    target = payload.get("target") or payload.get("app_name") or payload.get("session_id")
    try:
        res = _bridge_instance.inspect_ui(target=target)
        status_code = 200 if res.get("success", False) else 400
        return JSONResponse(status_code=status_code, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.get("/profiles")
async def list_profiles_endpoint():
    """List all saved App Capability Profiles."""
    try:
        profiles = _bridge_instance.list_profiles()
        return JSONResponse(status_code=200, content={"success": True, "total_profiles": len(profiles), "profiles": profiles})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/resolve-target")
async def resolve_target_endpoint(payload: Dict[str, Any] = Body(default={})):
    """Resolve dropped or pasted file path, shortcut, or directory to target metadata."""
    path = payload.get("path") or payload.get("target") or ""
    try:
        res = _bridge_instance.resolve_target(path)
        status_code = 200 if res.get("success", False) else 400
        return JSONResponse(status_code=status_code, content=res)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.post("/profiles/analyze")
async def profile_application_endpoint(payload: Dict[str, Any] = Body(default={})):
    """Deep reverse-engineer application and generate capability profile."""
    target = payload.get("target") or payload.get("app_name") or ""
    pid = payload.get("pid")
    hwnd = payload.get("hwnd") or payload.get("handle")
    binary_path = payload.get("binary_path")
    if not target and not pid and not hwnd:
        return JSONResponse(status_code=400, content={"success": False, "error": "'target', 'app_name', or 'pid' required."})
    try:
        res = _bridge_instance.profile_app(
            target or "Custom App",
            pid=pid,
            hwnd=hwnd,
            binary_path=binary_path
        )
        status_code = 200 if res.get("success", True) else 400
        return JSONResponse(status_code=status_code, content={"success": True, "profile": res, **res})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@client_router.get("/profiles/{app_name}")
async def get_profile_endpoint(app_name: str):
    """Retrieve capability profile for a specific application."""
    try:
        profile = _bridge_instance.get_profile(app_name)
        if not profile:
            return JSONResponse(status_code=404, content={"success": False, "error": f"Profile for '{app_name}' not found."})
        return JSONResponse(status_code=200, content={"success": True, "profile": profile})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# ==========================================
# LUMO: Image Generation & Vision Suite Endpoints
# ==========================================

@client_router.post("/lumo/generate")
async def lumo_generate_endpoint(payload: Dict[str, Any] = Body(...)):
    """Generate visual asset from prompt."""
    from client.lumo_engine import global_lumo_engine
    prompt = payload.get("prompt", "")
    style = payload.get("style", "modern")
    resolution = payload.get("resolution", "512x512")
    aspect_ratio = payload.get("aspect_ratio", "1:1")
    negative_prompt = payload.get("negative_prompt", "")
    res = global_lumo_engine.generate_image(
        prompt=prompt,
        style=style,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
        negative_prompt=negative_prompt
    )
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)


@client_router.get("/lumo/gallery")
async def lumo_gallery_endpoint():
    """List generated visual assets in Lumo gallery."""
    from client.lumo_engine import global_lumo_engine
    gallery = global_lumo_engine.get_gallery()
    return JSONResponse(status_code=200, content={"success": True, "total": len(gallery), "assets": gallery})


# ==========================================
# ECHO: Audio Core Endpoints
# ==========================================

@client_router.post("/echo/synthesize")
async def echo_synthesize_endpoint(payload: Dict[str, Any] = Body(...)):
    """Synthesize voice speech from text."""
    from client.echo_engine import global_echo_engine
    text = payload.get("text", "")
    voice = payload.get("voice", "nova")
    res = global_echo_engine.synthesize_speech(text=text, voice=voice)
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)


@client_router.post("/echo/transcribe")
async def echo_transcribe_endpoint(payload: Dict[str, Any] = Body(default={})):
    """Transcribe speech audio into clean text."""
    from client.echo_engine import global_echo_engine
    audio_data = payload.get("audio_data")
    simulated_text = payload.get("text")
    res = global_echo_engine.transcribe_audio(audio_file_or_data=audio_data, simulated_text=simulated_text)
    return JSONResponse(status_code=200, content=res)


@client_router.get("/echo/recordings")
async def echo_recordings_endpoint():
    """List synthesized audio and voice recordings."""
    from client.echo_engine import global_echo_engine
    recs = global_echo_engine.get_recordings()
    return JSONResponse(status_code=200, content={"success": True, "total": len(recs), "recordings": recs})


# ==========================================
# FORGE: App Builder & Zero-Vision Control Endpoints
# ==========================================

@client_router.get("/forge/apps")
async def forge_list_apps_endpoint():
    """List all custom applications created with Forge."""
    from client.forge_engine import global_forge_engine
    apps = global_forge_engine.list_apps()
    return JSONResponse(status_code=200, content={"success": True, "total": len(apps), "apps": apps})


@client_router.post("/forge/build")
async def forge_build_app_endpoint(payload: Dict[str, Any] = Body(...)):
    """Build a custom local application with programmatic zero-vision control schema."""
    from client.forge_engine import global_forge_engine
    name = payload.get("name") or payload.get("app_name") or payload.get("title") or ""
    category = payload.get("category", "business")
    description = payload.get("description", "")
    fields = payload.get("fields")
    actions = payload.get("actions")
    initial_data = payload.get("initial_data")
    res = global_forge_engine.build_app(
        name=name,
        category=category,
        description=description,
        fields=fields,
        actions=actions,
        initial_data=initial_data
    )
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)


@client_router.post("/forge/apps/{app_id}/execute")
async def forge_execute_hook_endpoint(app_id: str, payload: Dict[str, Any] = Body(...)):
    """Execute programmatic zero-vision control hook without vision models."""
    from client.forge_engine import global_forge_engine
    action = payload.get("action", "add_record")
    params = payload.get("payload") or payload.get("params") or {}
    res = global_forge_engine.execute_app_hook(app_id=app_id, action=action, payload=params)
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)


# ==========================================
# AUTOPILOT: Autonomous Background Digital Worker Endpoints
# ==========================================

@client_router.get("/autopilot/tasks")
async def autopilot_list_tasks_endpoint():
    """List autonomous background workflow tasks."""
    from client.autopilot_engine import global_autopilot_engine
    tasks = global_autopilot_engine.list_tasks()
    return JSONResponse(status_code=200, content={"success": True, "total": len(tasks), "tasks": tasks})


@client_router.post("/autopilot/enqueue")
async def autopilot_enqueue_endpoint(payload: Dict[str, Any] = Body(...)):
    """Enqueue multi-step autonomous background workflow."""
    from client.autopilot_engine import global_autopilot_engine
    name = payload.get("name", "Automated Workflow")
    steps = payload.get("steps") or [{"action": "default", "description": "Execute task"}]
    target_app = payload.get("target_app")
    schedule_interval = payload.get("schedule_interval_sec")
    res = global_autopilot_engine.enqueue_workflow(
        name=name,
        steps=steps,
        target_app=target_app,
        schedule_interval_sec=schedule_interval
    )
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)


@client_router.post("/autopilot/tasks/{task_id}/cancel")
async def autopilot_cancel_endpoint(task_id: str):
    """Cancel a running autonomous task."""
    from client.autopilot_engine import global_autopilot_engine
    res = global_autopilot_engine.cancel_task(task_id)
    status_code = 200 if res.get("success", False) else 400
    return JSONResponse(status_code=status_code, content=res)




def create_standalone_bridge_app() -> FastAPI:
    """Create a lightweight standalone FastAPI app containing only client routes."""
    app = FastAPI(title="Momento Client Bridge API", version="1.0.0")
    app.include_router(client_router)
    return app


def start_standalone_bridge(host: str = "127.0.0.1", port: int = 8000):
    """Run standalone bridge server."""
    app = create_standalone_bridge_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    port = int(os.environ.get("MOMENTO_BRIDGE_PORT", "8000"))
    start_standalone_bridge(port=port)
