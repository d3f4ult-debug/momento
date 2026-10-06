"""
Momento Application Semantic Profiler & Reverse-Engineering Engine
==================================================================
Performs deep UI control tree traversal, semantic role classification,
and capability workflow discovery for desktop applications using pywinauto / Windows UIA.
Builds and persists structured App Capability Profiles in ~/.momento/profiles/<app>.json.
"""

import datetime
import json
import logging
import os
import re
import shutil
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from client.config import PROFILES_DIR, ensure_profiles_dir
from client.scanner import resolve_app_binary

logger = logging.getLogger("momento.app_profiler")

# Safe PyWinAuto import
PYWINAUTO_AVAILABLE = False
try:
    import pywinauto
    from pywinauto import Application, Desktop
    PYWINAUTO_AVAILABLE = True
except Exception as e:
    logger.warning(f"pywinauto not available for App Profiler: {e}")
    PYWINAUTO_AVAILABLE = False


def slugify_app_name(name: str) -> str:
    """Convert an application name into a clean filesystem slug."""
    clean = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", clean) or "app"


def get_profile_path(app_name: str) -> str:
    """Get absolute file path for an application's capability profile."""
    profiles_dir = ensure_profiles_dir()
    slug = slugify_app_name(app_name)
    return os.path.join(profiles_dir, f"{slug}.json")


def load_profile(app_name: str) -> Optional[Dict[str, Any]]:
    """Load an application's capability profile from disk if it exists."""
    path = get_profile_path(app_name)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read profile at {path}: {e}")
    return None


def save_profile(profile: Dict[str, Any]) -> str:
    """Save an application capability profile to disk."""
    ensure_profiles_dir()
    app_name = profile.get("app_name") or profile.get("app_id") or "app"
    path = get_profile_path(app_name)
    profile["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    return path


def list_profiles() -> List[Dict[str, Any]]:
    """List all saved application capability profiles."""
    profiles_dir = ensure_profiles_dir()
    results: List[Dict[str, Any]] = []
    if not os.path.exists(profiles_dir):
        return results

    for fname in os.listdir(profiles_dir):
        if fname.endswith(".json"):
            fpath = os.path.join(profiles_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append({
                        "app_id": data.get("app_id", ""),
                        "app_name": data.get("app_name", ""),
                        "binary_path": data.get("binary_path", ""),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "controls_count": len(data.get("controls", [])),
                        "workflows_count": len(data.get("available_workflows", [])),
                        "semantic_tags": data.get("semantic_tags", []),
                        "stats": data.get("stats", {}),
                        "interactive_controls": data.get("stats", {}).get("interactive_controls", 0),
                        "profile_path": fpath
                    })
            except Exception:
                pass
    return sorted(results, key=lambda x: x.get("app_name", ""))


def delete_profile(app_name: str) -> bool:
    """Delete a profile from disk."""
    path = get_profile_path(app_name)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except Exception:
            return False
    return False


def classify_control_semantics(
    name: Any,
    control_type: Optional[str] = None,
    class_name: Optional[str] = None,
    automation_id: Optional[str] = None
) -> Tuple[str, List[str]]:
    """
    Classify semantic role and supported interaction actions for a UI control.
    Supports either passing a control dict as first argument, or positional parameters.
    Returns (semantic_role, list_of_supported_actions).
    """
    if isinstance(name, dict):
        d = name
        c_name = d.get("name", "") or ""
        c_type = d.get("control_type", "") or ""
        c_class = d.get("class_name", "") or ""
        c_auto = d.get("automation_id", "") or ""
    else:
        c_name = name or ""
        c_type = control_type or ""
        c_class = class_name or ""
        c_auto = automation_id or ""

    text_corpus = f"{c_name} {c_auto} {c_class}".lower()
    ct = c_type.lower()
    cn_lower = c_class.lower()

    # Default action
    actions = ["click"]

    # 1. Inputs (Edit, Document, TextBox)
    if any(k in ct for k in ("edit", "document", "textbox", "rich")) or "edit" in cn_lower:
        actions = ["type", "clear", "click"]
        if any(w in text_corpus for w in ("user", "login", "email", "account", "matricule", "uname")):
            return ("username_input", actions)
        if any(w in text_corpus for w in ("pass", "pwd", "secret", "pin", "token")):
            return ("password_input", actions)
        if any(w in text_corpus for w in ("search", "find", "query", "filter")):
            return ("search_input", actions)
        if "document" in ct or "rich" in text_corpus:
            return ("text_editor", actions)
        return ("text_input", actions)

    # 2. Buttons
    if "button" in ct or "btn" in class_name.lower():
        actions = ["click"]
        if any(w in text_corpus for w in ("login", "sign in", "signin", "authenticate", "connect")):
            return ("login_button", actions)
        if any(w in text_corpus for w in ("submit", "confirm", "ok", "apply", "enter")):
            return ("submit_button", actions)
        if any(w in text_corpus for w in ("save", "write", "commit")):
            return ("save_button", actions)
        if any(w in text_corpus for w in ("cancel", "abort", "close", "dismiss", "exit")):
            return ("cancel_button", actions)
        if any(w in text_corpus for w in ("search", "find", "lookup")):
            return ("search_button", actions)
        if any(w in text_corpus for w in ("add", "create", "new")):
            return ("create_button", actions)
        if any(w in text_corpus for w in ("delete", "remove", "trash")):
            return ("delete_button", actions)
        return ("action_button", actions)

    # 3. Tabs & Navigation
    if "tab" in ct:
        return ("navigation_tab", ["select", "click"])

    # 4. Menus & Toolbars
    if "menu" in ct or "menuitem" in ct:
        return ("menu_action", ["click"])

    # 5. Dropdown / ComboBox
    if "combo" in ct or "dropdown" in ct:
        return ("dropdown_select", ["select", "click"])

    # 6. CheckBox & RadioButton
    if "check" in ct or "radio" in ct:
        return ("toggle_option", ["toggle", "click"])

    # 7. Grids & Lists
    if any(k in ct for k in ("grid", "table", "list", "tree", "datagrid")):
        return ("data_grid", ["inspect_rows", "select_row", "click"])

    # 8. Hyperlinks
    if "hyperlink" in ct or "link" in ct:
        return ("hyperlink", ["click"])

    # 9. Generic Container
    if any(k in ct for k in ("pane", "window", "group", "custom")):
        return ("container_pane", [])

    return ("generic_control", ["click"])


def infer_workflows_and_tags(controls: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Infer high-level capability tags and workflow templates based on discovered controls.
    """
    tags: Set[str] = set()
    workflows: List[Dict[str, Any]] = []

    roles = {c.get("semantic_role") for c in controls}

    # Authentication workflow
    has_login_btn = any(r in roles for r in ("login_button", "submit_button"))
    has_user_input = "username_input" in roles
    has_pass_input = "password_input" in roles

    if has_login_btn and (has_user_input or has_pass_input):
        tags.add("authentication")
        suggested_steps = []
        req_inputs = []
        if has_user_input:
            suggested_steps.append({"action": "type", "target": "username_input", "description": "Enter username"})
            req_inputs.append("username")
        if has_pass_input:
            suggested_steps.append({"action": "type", "target": "password_input", "description": "Enter password"})
            req_inputs.append("password")
        suggested_steps.append({"action": "click", "target": "login_button" if "login_button" in roles else "submit_button", "description": "Submit login"})
        workflows.append({
            "name": "login",
            "description": "Authenticate user into application",
            "required_inputs": req_inputs,
            "steps": suggested_steps
        })

    # Search workflow
    if "search_input" in roles or "search_button" in roles:
        tags.add("search")
        workflows.append({
            "name": "search",
            "description": "Perform query search in application",
            "required_inputs": ["query"],
            "steps": [
                {"action": "type", "target": "search_input", "description": "Enter search query"},
                {"action": "press", "key": "enter", "description": "Execute search"}
            ]
        })

    # Document editing / word processing
    if "text_editor" in roles or "save_button" in roles:
        tags.add("document_editing")
        workflows.append({
            "name": "edit_and_save",
            "description": "Enter text content and save document",
            "required_inputs": ["text"],
            "steps": [
                {"action": "type", "target": "text_editor", "description": "Enter document text"},
                {"action": "click", "target": "save_button", "description": "Save file"}
            ]
        })

    # Data grid / records
    if "data_grid" in roles:
        tags.add("data_management")

    # Navigation
    if "navigation_tab" in roles or "menu_action" in roles:
        tags.add("navigation")

    # Form submission
    if "submit_button" in roles and "text_input" in roles:
        tags.add("form_submission")

    if not tags:
        tags.add("utility")

    return (sorted(list(tags)), workflows)


def profile_application(
    app_name_or_path: str,
    session_id: Optional[str] = None,
    pid: Optional[int] = None,
    hwnd: Optional[int] = None,
    binary_path: Optional[str] = None,
    timeout: float = 8.0,
    max_depth: int = 8,
    max_controls: int = 150,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Launch (or attach to) target application, deeply introspect its UI control tree,
    classify semantic roles, and persist an App Capability Profile in ~/.momento/profiles/<app>.json.
    Supports targeting an exact PID or HWND directly from the visual target picker.
    """
    def _log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    _log(f"[*] Initializing Deep Semantic Profiler for '{app_name_or_path}'...")

    target_clean = (app_name_or_path or "").strip()
    is_active_intent = not target_clean or target_clean.lower() in (
        "active", "current", "screen", "foreground", "this app", "this",
        "window", "the app", "active app", "active window", "active session",
        "the screen", "foreground window", "current window", "current app", "active process"
    )

    from client.gui_automation import get_foreground_window_info, inspect_window_ui, list_active_windows

    # 1. Resolve application
    app_record = None if is_active_intent else resolve_app_binary(target_clean)
    resolved_bin = binary_path or (app_record["binary_path"] if app_record else target_clean)
    binary_path = resolved_bin
    app_name = app_record["name"] if app_record else (
        "Active Application" if is_active_intent else os.path.splitext(os.path.basename(target_clean))[0].title()
    )
    app_working_dir = app_record.get("working_dir") if app_record else None
    app_id = app_record["id"] if app_record else slugify_app_name(app_name)

    # 2. Check if the app is already running on the desktop or if targeting active window or direct PID/HWND
    running_win_found: Optional[Dict[str, Any]] = None
    all_active_windows = list_active_windows()

    if pid or hwnd:
        _log(f"[*] Direct visual target selected (PID: {pid}, HWND: {hwnd}). Attaching directly...")
        for w in all_active_windows:
            if (pid and w.get("pid") == pid) or (hwnd and w.get("handle") == hwnd):
                running_win_found = w
                if w.get("title") and (not app_name or app_name in ("Active Application", "Custom App")):
                    app_name = w["title"]
                break
        if not running_win_found:
            running_win_found = {"pid": pid, "handle": hwnd, "title": app_name}
    elif is_active_intent:
        _log("[*] Targeting active foreground window directly...")
        running_win_found = get_foreground_window_info()
    else:
        # Check if already running on the desktop
        tgt_lower = target_clean.lower()
        app_lower = app_name.lower()
        for w in all_active_windows:
            w_title = w.get("title", "").lower()
            w_proc = w.get("process_name", "").lower()
            if (tgt_lower in w_title) or (app_lower in w_title) or (tgt_lower == w_proc) or (app_lower == w_proc):
                running_win_found = w
                _log(f"[+] Found already running window for '{app_name}': '{w.get('title')}' (PID: {w.get('pid')}). Attaching directly...")
                break

    # 3. Attach or launch controlled session
    from client.execution_engine import global_execution_engine
    active_session = None

    if session_id:
        active_session = global_execution_engine.get_session(session_id)
    else:
        # Check if already running in an engine session
        with global_execution_engine._lock:
            for s in reversed(list(global_execution_engine._sessions.values())):
                if (s.app_name.lower() == app_name.lower() or s.binary_path == binary_path) and s.process and s.process.poll() is None:
                    active_session = s
                    break

    launched_here = False
    # Only attempt launch if not already running on desktop and not active intent
    if not running_win_found and not active_session and not is_active_intent:
        can_spawn = False
        if binary_path and os.path.exists(binary_path):
            if os.path.isdir(binary_path):
                _log(f"[-] Target path '{binary_path}' is a directory/folder and cannot be executed directly.")
            elif binary_path.lower().endswith(".lnk"):
                _log(f"[-] Target path '{binary_path}' is a shortcut (.lnk) that cannot be directly spawned.")
            elif os.path.isfile(binary_path):
                can_spawn = True
        elif binary_path and shutil.which(binary_path):
            can_spawn = True

        if can_spawn:
            _log(f"[*] Launching '{app_name}' in controlled reverse-engineering session...")
            launch_res = global_execution_engine.launch(
                binary_path=binary_path,
                app_name=app_name,
                working_dir=app_working_dir
            )
            if launch_res.get("success"):
                session_id = launch_res["session_id"]
                active_session = global_execution_engine.get_session(session_id)
                launched_here = True
                _log(f"[+] Controlled session spawned (PID: {launch_res.get('pid')}, Session: {session_id}).")
                time.sleep(2.0)  # Wait for UI elements to render
            else:
                _log(f"[-] Could not launch binary natively: {launch_res.get('error')}. Falling back to active foreground window...")
        else:
            _log(f"[*] Target '{target_clean}' resolves to a shortcut/folder or unspawnable path. Falling back to active foreground window...")

    # 4. Locate target window
    _log(f"[*] Attaching to window for '{app_name}'...")
    target_pid = active_session.process.pid if (active_session and active_session.process) else (
        running_win_found.get("pid") if running_win_found else None
    )

    if running_win_found:
        window_meta = inspect_window_ui(hwnd=running_win_found.get("handle"), pid=running_win_found.get("pid"), max_controls=max_controls)
        if not window_meta.get("title") and running_win_found.get("title"):
            window_meta.update(running_win_found)
    else:
        window_meta = inspect_window_ui(target=app_name, pid=target_pid, max_controls=max_controls)

    # 5. Robust Fallback: if no window found or missing handle/pid, attach to GetForegroundWindow
    if not window_meta.get("title") and not window_meta.get("pid") and not window_meta.get("handle"):
        _log(f"[-] Could not locate window matching '{app_name}'. Falling back to active foreground window (GetForegroundWindow)...")
        fg = get_foreground_window_info()
        if fg and fg.get("title") and fg.get("title") not in ("Program Manager", "Task Switching", "Taskbar"):
            window_meta = inspect_window_ui(hwnd=fg.get("handle"), pid=fg.get("pid"), max_controls=max_controls)
            if not window_meta.get("title"):
                window_meta.update(fg)
            _log(f"[+] Fallback attached to active window: '{fg.get('title')}' (PID: {fg.get('pid')}, Process: {fg.get('process_name')}).")
        elif all_active_windows:
            for w in all_active_windows:
                if w.get("class_name") not in ("Shell_TrayWnd", "Progman", "WorkerW") and w.get("title"):
                    window_meta = w
                    _log(f"[+] Fallback attached to open window: '{w.get('title')}' (PID: {w.get('pid')}).")
                    break

    w_title = window_meta.get("title") or app_name
    w_pid = window_meta.get("pid") or target_pid or 0
    w_class = window_meta.get("class_name") or "StandardWindow"
    w_rect = window_meta.get("rect") or {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}
    w_proc = window_meta.get("process_name") or (os.path.basename(binary_path) if binary_path else "unknown")

    # If active intent or fallback adopted a real window title, update profile metadata
    if is_active_intent or (app_name in ("Active Application", "Application") and w_title):
        app_name = w_title
        app_id = slugify_app_name(w_title)
    if (not binary_path or os.path.isdir(binary_path) or binary_path.lower().endswith(".lnk")) and window_meta.get("process_path"):
        binary_path = window_meta["process_path"]

    _log(f"[+] Attached to window: '{w_title}' (PID: {w_pid}, Class: {w_class}).")

    # 4. Deep Control Tree Traversal via pywinauto
    discovered_controls: List[Dict[str, Any]] = []
    seen_elements: Set[str] = set()

    if PYWINAUTO_AVAILABLE and (w_pid or window_meta.get("handle")):
        _log("[*] Performing deep UI control tree traversal via Windows UIA...")
        for backend in ("uia", "win32"):
            try:
                d = Desktop(backend=backend)
                wrapper = None
                if window_meta.get("handle"):
                    try:
                        wrapper = d.window(handle=window_meta["handle"])
                        if not wrapper.exists():
                            wrapper = None
                    except Exception:
                        wrapper = None
                if not wrapper and w_pid:
                    try:
                        matches = [w for w in d.windows() if w.process_id() == w_pid]
                        if matches:
                            wrapper = matches[0]
                    except Exception:
                        pass

                if wrapper:
                    descendants = []
                    try:
                        descendants = wrapper.descendants()
                    except Exception:
                        pass

                    _log(f"[+] Found {len(descendants)} elements in UI hierarchy. Classifying semantic roles...")

                    for idx, c in enumerate(descendants[:max_controls]):
                        try:
                            c_title = c.window_text().strip()
                            c_class = c.class_name()
                            c_type = str(getattr(c.element_info, "control_type", None) or c_class or "Control")
                            c_auto_id = getattr(c.element_info, "automation_id", "")
                            
                            c_rect_dict = None
                            try:
                                cr = c.rectangle()
                                c_rect_dict = {
                                    "left": cr.left, "top": cr.top, "right": cr.right, "bottom": cr.bottom,
                                    "width": cr.width(), "height": cr.height()
                                }
                            except Exception:
                                pass

                            # Signature for deduplication
                            sig = f"{c_type}:{c_auto_id}:{c_title}:{c_class}"
                            if sig in seen_elements:
                                continue
                            seen_elements.add(sig)

                            # Classify semantics
                            role, actions = classify_control_semantics(
                                name=c_title,
                                control_type=c_type,
                                class_name=c_class,
                                automation_id=c_auto_id
                            )

                            # Deterministic identifier
                            clean_tag = slugify_app_name(c_auto_id or c_title or f"{c_type}_{idx}")
                            ctrl_id = f"{c_type.lower()}_{clean_tag}"[:40]

                            discovered_controls.append({
                                "id": ctrl_id,
                                "name": c_title,
                                "control_type": c_type,
                                "class_name": c_class,
                                "automation_id": c_auto_id,
                                "rect": c_rect_dict,
                                "semantic_role": role,
                                "actions": actions,
                                "is_interactive": bool(actions and role != "container_pane")
                            })
                        except Exception:
                            pass
                    break  # Success
            except Exception as e:
                logger.debug(f"pywinauto tree traversal attempt error ({backend}): {e}")

    # Fallback to window_meta controls if pywinauto produced nothing
    if not discovered_controls and window_meta.get("controls"):
        for idx, c in enumerate(window_meta["controls"]):
            c_name = c.get("text", "")
            c_type = c.get("control_type", "Control")
            role, actions = classify_control_semantics(
                name=c_name,
                control_type=c_type,
                class_name=c.get("class_name", ""),
                automation_id=c.get("automation_id", "")
            )
            ctrl_id = f"{c_type.lower()}_{slugify_app_name(c_name or str(idx))}"[:40]
            discovered_controls.append({
                "id": ctrl_id,
                "name": c_name,
                "control_type": c_type,
                "class_name": c.get("class_name", ""),
                "automation_id": c.get("automation_id", ""),
                "rect": c.get("rect"),
                "semantic_role": role,
                "actions": actions,
                "is_interactive": bool(actions and role != "container_pane")
            })

    # 5. Infer tags and workflows
    tags, workflows = infer_workflows_and_tags(discovered_controls)
    interactive_count = sum(1 for c in discovered_controls if c.get("is_interactive"))

    _log(f"[+] Mapped {len(discovered_controls)} controls ({interactive_count} interactive triggers).")
    _log(f"[+] Identified {len(workflows)} capability workflow(s): {', '.join(w['name'] for w in workflows) if workflows else 'standard interactions'}.")

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    profile: Dict[str, Any] = {
        "app_id": app_id,
        "app_name": app_name,
        "binary_path": binary_path,
        "working_dir": app_working_dir,
        "created_at": now,
        "updated_at": now,
        "window": {
            "title": w_title,
            "class_name": w_class,
            "rect": w_rect,
            "pid": w_pid,
            "process_name": w_proc
        },
        "stats": {
            "total_controls": len(discovered_controls),
            "interactive_controls": interactive_count,
            "tags_count": len(tags),
            "workflows_count": len(workflows)
        },
        "session_id": active_session.session_id if active_session else None,
        "success": True,
        "semantic_tags": tags,
        "controls": discovered_controls,
        "available_workflows": workflows,
        "recorded_workflows": {}
    }

    # 6. Save Profile
    saved_path = save_profile(profile)
    _log(f"[+] Saved App Capability Profile to: {saved_path}")

    # Build summary
    summary_lines = [
        f"Momento Reverse-Engineering Profile for '{app_name}':",
        f"  [+] Binary:        {binary_path}",
        f"  [+] Window Title:  '{w_title}' (PID: {w_pid})",
        f"  [+] Discovered:    {len(discovered_controls)} controls ({interactive_count} interactive)",
        f"  [+] Semantic Tags: {', '.join(tags)}"
    ]
    if workflows:
        summary_lines.append(f"  [+] Workflows:     {', '.join(w['name'] for w in workflows)}")
    
    # Highlights of interactive controls
    interactive_sample = [f"{c['name']} ({c['semantic_role']})" for c in discovered_controls if c.get("is_interactive") and c.get("name")][:6]
    if interactive_sample:
        summary_lines.append(f"  [+] Sample Triggers: {', '.join(interactive_sample)}")

    profile["summary"] = "\n".join(summary_lines)
    _log("[+] Application reverse-engineering completed successfully.")

    return profile


def resolve_control_from_profile(profile: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
    """
    Find best matching control in an App Capability Profile given natural language descriptor.
    Matches by id, name, automation_id, or semantic_role.
    """
    controls = profile.get("controls", [])
    if not controls:
        return None

    clean_query = query.strip().lower()
    
    # 1. Exact match on ID or name
    for c in controls:
        if c.get("id", "").lower() == clean_query or c.get("name", "").lower() == clean_query:
            return c

    # 2. Match on semantic role
    role_mapping = {
        "login button": ("login_button", "submit_button"),
        "submit button": ("submit_button", "login_button"),
        "username": ("username_input", "text_input"),
        "user": ("username_input", "text_input"),
        "password": ("password_input", "text_input"),
        "search": ("search_input", "search_button"),
        "save": ("save_button", "action_button"),
        "editor": ("text_editor", "text_input")
    }

    for key, target_roles in role_mapping.items():
        if key in clean_query:
            for c in controls:
                if c.get("semantic_role") in target_roles:
                    return c

    # 3. Substring match on name or automation_id
    for c in controls:
        c_name = c.get("name", "").lower()
        c_auto = c.get("automation_id", "").lower()
        if (c_name and c_name in clean_query) or (c_auto and c_auto in clean_query):
            return c

    return None


def execute_profile_semantic_action(
    app_name: str,
    action_type: str,
    target_descriptor: str,
    param_value: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Execute a high-level action mapped against an application's capability profile.
    e.g. click 'login button', or type 'admin' in 'username'.
    """
    def _log(msg: str):
        logger.info(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    profile = load_profile(app_name)
    if not profile:
        return {
            "success": False,
            "error": f"No capability profile found for '{app_name}'. Run 'reverse engineer {app_name}' first."
        }

    _log(f"[*] Resolving semantic target '{target_descriptor}' in profile for '{app_name}'...")
    control = resolve_control_from_profile(profile, target_descriptor)
    if not control:
        _log(f"[-] Could not find matching control for '{target_descriptor}' in profile schema.")
        return {
            "success": False,
            "error": f"Control '{target_descriptor}' not found in profile for '{app_name}'."
        }

    c_name = control.get("name") or control.get("id")
    c_role = control.get("semantic_role")
    rect = control.get("rect")
    _log(f"[+] Mapped to control: [{c_role}] '{c_name}' (ID: {control.get('id')}).")

    from client.gui_automation import focus_window_by_title, press_key, type_text
    focus_window_by_title(profile.get("window", {}).get("title") or app_name)
    time.sleep(0.3)

    if action_type in ("click", "press_button"):
        if rect and rect.get("left") is not None:
            # Click coordinates
            center_x = rect["left"] + (rect.get("width", 20) // 2)
            center_y = rect["top"] + (rect.get("height", 20) // 2)
            _log(f"[*] Clicking control at screen coords ({center_x}, {center_y})...")
            try:
                import pyautogui
                pyautogui.click(center_x, center_y)
                _log(f"[+] Clicked [{c_role}] '{c_name}'.")
                return {"success": True, "control": control, "action": "click"}
            except Exception as e:
                _log(f"[-] PyAutoGUI click error: {e}")

        # Fallback to keypress enter
        press_key("enter")
        return {"success": True, "control": control, "action": "click_fallback"}

    elif action_type in ("type", "enter", "write", "fill"):
        val = param_value or ""
        if rect and rect.get("left") is not None:
            center_x = rect["left"] + (rect.get("width", 20) // 2)
            center_y = rect["top"] + (rect.get("height", 20) // 2)
            _log(f"[*] Focusing input field at ({center_x}, {center_y})...")
            try:
                import pyautogui
                pyautogui.click(center_x, center_y)
                time.sleep(0.1)
            except Exception:
                pass

        _log(f"[*] Entering value into [{c_role}] '{c_name}'...")
        success = type_text(val)
        return {"success": success, "control": control, "action": "type", "value": val}

    return {"success": False, "error": f"Unsupported action type: {action_type}"}
