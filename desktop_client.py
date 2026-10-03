"""
Momento Standalone Desktop Application
======================================
Native Windows desktop application wrapper running pywebview with local
application discovery, natural-language execution routing, and real-time monitoring.
"""

import argparse
import os
import sys
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from client.config import DEFAULT_BACKEND_URL, get_backend_url
from client.desktop_bridge import DesktopAppBridge


def get_gui_html_path() -> str:
    """Resolve absolute path to client/gui/index.html."""
    possible_paths = [
        os.path.join(PROJECT_ROOT, "client", "gui", "index.html"),
        os.path.join(PROJECT_ROOT, "gui", "index.html"),
        os.path.join(os.path.dirname(__file__), "client", "gui", "index.html")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return possible_paths[0]


def run_desktop_app(
    backend_url: Optional[str] = None,
    width: int = 1120,
    height: int = 740,
    debug: bool = False
) -> int:
    """Launch the native pywebview desktop window."""
    target_url = backend_url or get_backend_url()
    bridge = DesktopAppBridge(backend_url=target_url)

    html_file = get_gui_html_path()
    if not os.path.exists(html_file):
        print(f"[!] Error: GUI template not found at {html_file}", file=sys.stderr)
        return 1

    try:
        import webview
    except ImportError:
        print("[!] pywebview is not installed. Run: pip install pywebview", file=sys.stderr)
        return 1

    # Configure window
    window = webview.create_window(
        title="Momento — Universal Desktop Workspace",
        url=html_file,
        js_api=bridge,
        width=width,
        height=height,
        min_size=(850, 580),
        background_color="#0a0f1d"
    )

    try:
        webview.start(debug=debug)
        return 0
    except Exception as e:
        print(f"[!] Failed to initialize desktop window: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description="Momento Native Windows Desktop App")
    parser.add_argument("--url", default=None, help=f"Momento VPS Backend URL (default: {DEFAULT_BACKEND_URL})")
    parser.add_argument("--width", type=int, default=1120, help="Window width (default: 1120)")
    parser.add_argument("--height", type=int, default=740, help="Window height (default: 740)")
    parser.add_argument("--debug", action="store_true", help="Enable developer tools and debug logging")
    parser.add_argument("--headless-check", action="store_true", help="Verify bridge initialization without showing GUI")

    args = parser.parse_args()

    if args.headless_check:
        bridge = DesktopAppBridge(backend_url=args.url)
        state = bridge.get_initial_state()
        print(f"[*] Desktop bridge initialized successfully. Backend: {state['backend_url']}")
        return 0

    return run_desktop_app(
        backend_url=args.url,
        width=args.width,
        height=args.height,
        debug=args.debug
    )


if __name__ == "__main__":
    sys.exit(main())
