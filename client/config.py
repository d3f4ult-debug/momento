"""
Momento Client Configuration
============================
Manages local client configuration, permissions, and connection settings
to the remote Momento VPS Sandbox backend.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Default Contabo VPS backend API
DEFAULT_BACKEND_URL = os.environ.get("MOMENTO_API_URL", "http://161.97.64.38:8000")

# Local storage paths in user home directory
MOMENTO_DIR = os.path.expanduser("~/.momento")
CONFIG_PATH = os.path.join(MOMENTO_DIR, "config.json")
REGISTRY_PATH = os.path.join(MOMENTO_DIR, "registry.json")

# Fallback root configuration file
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FALLBACK_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "backend_url": DEFAULT_BACKEND_URL,
    "setup_completed": False,
    "permissions": {
        "filesystem_indexing": False,
        "app_discovery": False,
        "execution_rights": False
    },
    "registry_path": REGISTRY_PATH,
    "last_scan_time": None,
    "timeout_seconds": 300,
    "version": "1.0.0"
}


def ensure_momento_dir() -> str:
    """Ensure ~/.momento directory exists."""
    os.makedirs(MOMENTO_DIR, exist_ok=True)
    return MOMENTO_DIR


def get_config_file_path() -> str:
    """Resolve active config file path."""
    if os.path.exists(CONFIG_PATH):
        return CONFIG_PATH
    if os.path.exists(FALLBACK_CONFIG_PATH):
        return FALLBACK_CONFIG_PATH
    return CONFIG_PATH


def load_config() -> Dict[str, Any]:
    """Load configuration from disk with defaults fallback."""
    config_file = get_config_file_path()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                merged.update(data)
                # Environment override always takes precedence if set
                if os.environ.get("MOMENTO_API_URL"):
                    merged["backend_url"] = os.environ["MOMENTO_API_URL"]
                return merged
        except Exception:
            pass

    cfg = DEFAULT_CONFIG.copy()
    if os.environ.get("MOMENTO_API_URL"):
        cfg["backend_url"] = os.environ["MOMENTO_API_URL"]
    return cfg


def save_config(config_data: Dict[str, Any]) -> str:
    """Save configuration dictionary to ~/.momento/config.json."""
    ensure_momento_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    return CONFIG_PATH


def is_setup_completed() -> bool:
    """Check whether local onboarding and permission setup has been completed."""
    cfg = load_config()
    perms = cfg.get("permissions", {})
    return bool(
        cfg.get("setup_completed", False)
        and perms.get("filesystem_indexing")
        and perms.get("app_discovery")
        and perms.get("execution_rights")
    )


def get_backend_url() -> str:
    """Get active backend API URL (with environment variable override support)."""
    env_url = os.environ.get("MOMENTO_API_URL")
    if env_url:
        return env_url.rstrip("/")
    cfg = load_config()
    return cfg.get("backend_url", DEFAULT_BACKEND_URL).rstrip("/")


def set_backend_url(url: str) -> None:
    """Update configured backend URL."""
    cfg = load_config()
    cfg["backend_url"] = url.rstrip("/")
    save_config(cfg)


def set_permissions(filesystem: bool = True, discovery: bool = True, execution: bool = True) -> None:
    """Record granted permissions and mark setup complete."""
    cfg = load_config()
    cfg["permissions"] = {
        "filesystem_indexing": filesystem,
        "app_discovery": discovery,
        "execution_rights": execution
    }
    cfg["setup_completed"] = bool(filesystem and discovery and execution)
    save_config(cfg)
