"""
Momento Local Client Package
============================
Local client application connecting to the remote Momento VPS Sandbox backend.
"""

from client.config import (
    load_config,
    save_config,
    get_backend_url,
    is_setup_completed,
    MOMENTO_DIR,
    CONFIG_PATH
)
from client.scanner import AppScanner, resolve_app_binary
from client.onboarding import run_onboarding
from client.nlp_router import NLPRouter
from client.shell import start_interactive_shell

__all__ = [
    "load_config",
    "save_config",
    "get_backend_url",
    "is_setup_completed",
    "MOMENTO_DIR",
    "CONFIG_PATH",
    "AppScanner",
    "resolve_app_binary",
    "run_onboarding",
    "NLPRouter",
    "start_interactive_shell"
]
