"""
Momento App Discovery & Scanner
===============================
Performs local environment scans to discover installed applications and binaries
across Windows and Linux hosts, building a queryable local app registry.
"""

import datetime
import difflib
import json
import os
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

from client.config import MOMENTO_DIR, REGISTRY_PATH, ensure_momento_dir


# Common well-known Windows binaries and utility aliases
KNOWN_WINDOWS_APPS = [
    {
        "id": "notepad",
        "name": "Notepad",
        "binary_name": "notepad.exe",
        "relative_paths": ["notepad.exe", r"C:\Windows\System32\notepad.exe", r"C:\Windows\notepad.exe"],
        "aliases": ["notepad", "text editor", "notes", "note"],
        "category": "utility"
    },
    {
        "id": "calculator",
        "name": "Calculator",
        "binary_name": "calc.exe",
        "relative_paths": ["calc.exe", r"C:\Windows\System32\calc.exe"],
        "aliases": ["calc", "calculator", "math"],
        "category": "utility"
    },
    {
        "id": "paint",
        "name": "Paint",
        "binary_name": "mspaint.exe",
        "relative_paths": ["mspaint.exe", r"C:\Windows\System32\mspaint.exe"],
        "aliases": ["mspaint", "paint", "drawing"],
        "category": "graphics"
    },
    {
        "id": "powershell",
        "name": "PowerShell",
        "binary_name": "powershell.exe",
        "relative_paths": ["powershell.exe", r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
        "aliases": ["powershell", "posh", "pwsh", "shell"],
        "category": "system"
    },
    {
        "id": "cmd",
        "name": "Command Prompt",
        "binary_name": "cmd.exe",
        "relative_paths": ["cmd.exe", r"C:\Windows\System32\cmd.exe"],
        "aliases": ["cmd", "command prompt", "terminal", "dos"],
        "category": "system"
    },
    {
        "id": "taskmgr",
        "name": "Task Manager",
        "binary_name": "taskmgr.exe",
        "relative_paths": ["taskmgr.exe", r"C:\Windows\System32\taskmgr.exe"],
        "aliases": ["task manager", "taskmgr", "tasks"],
        "category": "system"
    },
    {
        "id": "regedit",
        "name": "Registry Editor",
        "binary_name": "regedit.exe",
        "relative_paths": [r"C:\Windows\regedit.exe"],
        "aliases": ["regedit", "registry", "registry editor"],
        "category": "system"
    },
    {
        "id": "chrome",
        "name": "Google Chrome",
        "binary_name": "chrome.exe",
        "relative_paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ],
        "aliases": ["chrome", "google chrome", "browser", "web browser"],
        "category": "internet"
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "binary_name": "msedge.exe",
        "relative_paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ],
        "aliases": ["edge", "msedge", "microsoft edge"],
        "category": "internet"
    },
    {
        "id": "vscode",
        "name": "Visual Studio Code",
        "binary_name": "Code.exe",
        "relative_paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe"
        ],
        "aliases": ["code", "vscode", "visual studio code", "editor"],
        "category": "development"
    }
]

# Common well-known Linux binaries
KNOWN_LINUX_APPS = [
    {
        "id": "calculator",
        "name": "Calculator",
        "binary_name": "gnome-calculator",
        "relative_paths": ["/usr/bin/gnome-calculator", "/usr/bin/kcalc", "/usr/bin/bc"],
        "aliases": ["calc", "calculator", "kcalc"],
        "category": "utility"
    },
    {
        "id": "text-editor",
        "name": "Text Editor",
        "binary_name": "gedit",
        "relative_paths": ["/usr/bin/gedit", "/usr/bin/kate", "/usr/bin/nano", "/usr/bin/vim"],
        "aliases": ["editor", "text editor", "gedit", "nano"],
        "category": "utility"
    },
    {
        "id": "terminal",
        "name": "Terminal",
        "binary_name": "gnome-terminal",
        "relative_paths": ["/usr/bin/gnome-terminal", "/usr/bin/xterm", "/usr/bin/konsole", "/usr/bin/bash"],
        "aliases": ["terminal", "bash", "shell", "console"],
        "category": "system"
    },
    {
        "id": "browser",
        "name": "Web Browser",
        "binary_name": "firefox",
        "relative_paths": ["/usr/bin/firefox", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"],
        "aliases": ["firefox", "browser", "chrome", "chromium"],
        "category": "internet"
    }
]


class AppScanner:
    """Discovers and catalogs installed software and system tools."""

    def __init__(self, registry_file: Optional[str] = None):
        self.registry_file = registry_file or REGISTRY_PATH

    def scan_environment(self) -> Dict[str, Any]:
        """Perform a comprehensive local scan for applications."""
        ensure_momento_dir()
        discovered: Dict[str, Dict[str, Any]] = {}

        # 1. Scan well-known system apps
        known_list = KNOWN_WINDOWS_APPS if sys.platform == "win32" else KNOWN_LINUX_APPS
        for app in known_list:
            found_path = None
            for p in app["relative_paths"]:
                if os.path.isabs(p) and os.path.exists(p):
                    found_path = p
                    break
                elif not os.path.isabs(p):
                    which = shutil.which(p)
                    if which:
                        found_path = which
                        break

            if found_path:
                discovered[app["id"]] = {
                    "id": app["id"],
                    "name": app["name"],
                    "binary_path": os.path.normpath(found_path),
                    "aliases": app["aliases"],
                    "category": app.get("category", "utility"),
                    "source": "system_catalog"
                }

        # 2. Scan PATH executables
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for pdir in path_dirs:
            if not pdir or not os.path.isdir(pdir):
                continue
            try:
                for fname in os.listdir(pdir):
                    fpath = os.path.join(pdir, fname)
                    if not os.path.isfile(fpath):
                        continue

                    lower_name = fname.lower()
                    if sys.platform == "win32":
                        if not lower_name.endswith(".exe"):
                            continue
                        app_id = lower_name[:-4]
                    else:
                        if not os.access(fpath, os.X_OK):
                            continue
                        app_id = lower_name

                    if app_id not in discovered and len(app_id) > 1:
                        clean_name = app_id.replace("-", " ").replace("_", " ").title()
                        discovered[app_id] = {
                            "id": app_id,
                            "name": clean_name,
                            "binary_path": os.path.normpath(fpath),
                            "aliases": [app_id, clean_name.lower()],
                            "category": "cli",
                            "source": "path"
                        }
            except (PermissionError, OSError):
                continue

        # 3. Linux Desktop file scanning
        if sys.platform != "win32":
            desktop_dirs = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
            for ddir in desktop_dirs:
                if os.path.isdir(ddir):
                    for dfile in os.listdir(ddir):
                        if dfile.endswith(".desktop"):
                            app_info = self._parse_desktop_file(os.path.join(ddir, dfile))
                            if app_info and app_info["id"] not in discovered:
                                discovered[app_info["id"]] = app_info

        # Preserve any previously registered custom apps
        custom_apps: Dict[str, Dict[str, Any]] = {}
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    old_reg = json.load(f)
                    for k, v in old_reg.get("apps", {}).items():
                        if v.get("custom") is True or v.get("source") == "manual_registration":
                            custom_apps[k] = v
            except Exception:
                pass

        discovered.update(custom_apps)

        # Compile registry payload
        registry_payload = {
            "version": "1.0",
            "scanned_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "platform": sys.platform,
            "total_apps": len(discovered),
            "apps": discovered
        }

        # Save to registry file
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(registry_payload, f, indent=2)

        return registry_payload

    def register_custom_app(
        self,
        name: str,
        binary_path: str,
        aliases: Optional[List[str]] = None,
        category: str = "custom"
    ) -> Dict[str, Any]:
        """Manually register a custom application into local registry."""
        ensure_momento_dir()
        clean_name = name.strip()
        clean_path = binary_path.strip()

        if not os.path.isabs(clean_path):
            which_path = shutil.which(clean_path)
            if which_path:
                clean_path = which_path

        clean_path = os.path.normpath(clean_path)
        app_id = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")
        if not app_id:
            app_id = f"custom-app-{int(datetime.datetime.now().timestamp())}"

        alias_set = {app_id, clean_name.lower()}
        if aliases:
            for a in aliases:
                a_str = a.strip().lower()
                if a_str:
                    alias_set.add(a_str)

        record = {
            "id": app_id,
            "name": clean_name,
            "binary_path": clean_path,
            "aliases": sorted(list(alias_set)),
            "category": category or "custom",
            "source": "manual_registration",
            "custom": True,
            "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        registry = self.load_registry()
        apps = registry.get("apps", {})
        apps[app_id] = record
        registry["apps"] = apps
        registry["total_apps"] = len(apps)
        registry["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)

        return record

    def _parse_desktop_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse Linux .desktop file to extract binary name and display name."""
        try:
            name, exec_bin = None, None
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Name=") and not name:
                        name = line.split("=", 1)[1]
                    elif line.startswith("Exec=") and not exec_bin:
                        exec_raw = line.split("=", 1)[1]
                        exec_bin = exec_raw.split()[0]  # Strip arguments like %u
            if name and exec_bin:
                bin_path = shutil.which(exec_bin) or exec_bin
                app_id = os.path.basename(file_path).replace(".desktop", "").lower()
                return {
                    "id": app_id,
                    "name": name,
                    "binary_path": bin_path,
                    "aliases": [app_id, name.lower()],
                    "category": "application",
                    "source": "desktop_entry"
                }
        except Exception:
            pass
        return None

    def load_registry(self) -> Dict[str, Any]:
        """Load stored app registry, or run scan if absent."""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self.scan_environment()

    def get_registered_apps(self) -> List[Dict[str, Any]]:
        """Return list of all registered applications in catalog."""
        reg = self.load_registry()
        return list(reg.get("apps", {}).values())



def resolve_app_binary(query: str, registry_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Resolve an application query string to a registered application record.
    Supports exact ID match, name match, alias lookup, substring, and fuzzy matching.
    """
    clean_query = query.strip().lower()
    if not clean_query:
        return None

    scanner = AppScanner(registry_file=registry_file)
    registry = scanner.load_registry()
    apps: Dict[str, Dict[str, Any]] = registry.get("apps", {})

    # 1. Exact ID match
    if clean_query in apps:
        return apps[clean_query]

    # 2. Check alias or direct name match
    for app in apps.values():
        if app.get("name", "").lower() == clean_query:
            return app
        aliases = [a.lower() for a in app.get("aliases", [])]
        if clean_query in aliases:
            return app

    # 3. Strip common prefixes/suffixes: "open ", "run ", ".exe"
    stripped = clean_query
    for prefix in ("open ", "run ", "launch ", "start "):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].strip()
            break
    if stripped.endswith(".exe"):
        stripped = stripped[:-4].strip()

    if stripped in apps:
        return apps[stripped]

    for app in apps.values():
        if app.get("name", "").lower() == stripped:
            return app
        if stripped in [a.lower() for a in app.get("aliases", [])]:
            return app

    # 4. Substring match
    for app in apps.values():
        app_name = app.get("name", "").lower()
        if stripped in app_name or app.get("id", "").lower() in stripped:
            return app

    # 5. Fuzzy match on app names and IDs
    candidates = {}
    for app_id, app in apps.items():
        candidates[app_id] = app
        candidates[app.get("name", "").lower()] = app
        for alias in app.get("aliases", []):
            candidates[alias.lower()] = app

    matches = difflib.get_close_matches(stripped, candidates.keys(), n=1, cutoff=0.6)
    if matches:
        return candidates[matches[0]]

    # 6. Fallback to host PATH
    which_path = shutil.which(stripped) or shutil.which(query)
    if which_path:
        return {
            "id": stripped,
            "name": stripped.title(),
            "binary_path": os.path.normpath(which_path),
            "aliases": [stripped],
            "category": "cli",
            "source": "direct_path"
        }

    return None


def register_custom_app(
    name: str,
    binary_path: str,
    aliases: Optional[List[str]] = None,
    category: str = "custom",
    registry_file: Optional[str] = None
) -> Dict[str, Any]:
    """Register custom application using AppScanner."""
    scanner = AppScanner(registry_file=registry_file)
    return scanner.register_custom_app(name=name, binary_path=binary_path, aliases=aliases, category=category)
