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
