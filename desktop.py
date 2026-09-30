"""
Momento Desktop Application Wrapper
Launches the FastAPI backend in a background thread and presents
a native desktop application window via pywebview.
"""

import sys
import os
import time
import socket
import argparse
import threading
import urllib.request
import webbrowser

# Ensure current directory is in sys.path
BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import uvicorn
from main import app


class DesktopApi:
    """JS API bridge exposed to pywebview window as window.pywebview.api."""

    def open_external_url(self, url: str) -> bool:
        """Safely launch an external URL in the default browser without navigating the desktop window."""
        clean_url = (url or "").strip()
        if clean_url and (clean_url.startswith("http://") or clean_url.startswith("https://")):
            webbrowser.open(clean_url)
            return True
        return False


def is_port_available(host: str, port: int) -> bool:
    """Check if a local port is available for binding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(host: str = "127.0.0.1", start_port: int = 8000, max_attempts: int = 50) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(host, port):
            return port
    # Fallback to dynamic port assigned by OS
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


class UvicornServerThread(threading.Thread):
    """Runs Uvicorn ASGI server in a dedicated background daemon thread."""

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True, name="Momento-UvicornServer")
        self.host = host
        self.port = port
        self.config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
            workers=1,
            loop="asyncio"
        )
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


def wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """Wait until the backend server responds to /api/health."""
    start = time.time()
    health_url = f"{url.rstrip('/')}/api/health"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def main():
    parser = argparse.ArgumentParser(description="Momento — Universal AI Agent Workspace")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Port to bind (default: auto-detected from 8000)")
    parser.add_argument("--browser", action="store_true", help="Launch in default web browser instead of desktop window")
    parser.add_argument("--headless", action="store_true", help="Run server only without opening UI")
    args = parser.parse_args()

    host = args.host
    port = args.port or find_free_port(host, start_port=8000)
    app_url = f"http://{host}:{port}"

    print(f"==================================================")
    print(f"  Momento — Universal AI Agent Workspace")
    print(f"  Starting local server at: {app_url}")
    print(f"==================================================")

    # Start server in background thread
    server_thread = UvicornServerThread(host, port)
    server_thread.start()

    # Wait for readiness
    server_ready = wait_for_server(app_url, timeout=12.0)
    if not server_ready:
        print("Warning: Server took longer than expected to report healthy.")

    if args.headless:
        print(f"Momento is running in headless mode on {app_url}. Press Ctrl+C to stop.")
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Momento...")
            server_thread.stop()
        return

    if args.browser:
        print(f"Opening browser at {app_url}...")
        webbrowser.open(app_url)
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Momento...")
            server_thread.stop()
        return

    # Native Desktop Window via pywebview
    try:
        import webview

        print("Launching native desktop window...")
        desktop_api = DesktopApi()
        window = webview.create_window(
            title="Momento — Universal AI Agent Workspace",
            url=app_url,
            width=1280,
            height=860,
            min_size=(920, 600),
            background_color="#0e1117",
            text_select=True,
            zoomable=True,
            confirm_close=False,
            js_api=desktop_api,
        )
        
        # Start webview GUI event loop (blocks until user closes window)
        webview.start()
        print("Desktop window closed. Exiting Momento...")
        server_thread.stop()

    except Exception as e:
        print(f"Desktop GUI initialization failed: {e}")
        print("Falling back to default web browser...")
        webbrowser.open(app_url)
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            server_thread.stop()


if __name__ == "__main__":
    main()
