"""
Momento Desktop GUI Automation & Interaction Engine
===================================================
Coordinates safe UI automation, keyboard typing, window focusing, and keypress
interactions across desktop applications (Notepad, Calculator, custom tools).
"""

import logging
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("momento.gui_automation")

# Safe PyAutoGUI initialization
PYAUTOGUI_AVAILABLE = False
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except Exception as e:
    logger.warning(f"PyAutoGUI not available: {e}")

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except Exception:
    PYPERCLIP_AVAILABLE = False

try:
    import pygetwindow
    PYGETWINDOW_AVAILABLE = True
except Exception:
    PYGETWINDOW_AVAILABLE = False

try:
    import pywinauto
    from pywinauto import Desktop, Application
    PYWINAUTO_AVAILABLE = True
except Exception as e:
    logger.warning(f"pywinauto not available: {e}")
    PYWINAUTO_AVAILABLE = False


def focus_window_by_title(title_pattern: str, timeout: float = 3.0) -> bool:
    """
    Attempt to bring target application window into focus by title substring.
    """
    if not PYGETWINDOW_AVAILABLE:
        # Fallback for Windows using ctypes
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowWithText if hasattr(user32, 'FindWindowWithText') else None
                # Basic sleep to allow window focus
                time.sleep(0.5)
                return True
            except Exception:
                pass
        return False

    deadline = time.time() + timeout
    pattern_lower = title_pattern.lower()

    while time.time() < deadline:
        try:
            windows = pygetwindow.getAllWindows()
            for win in windows:
                if win.title and pattern_lower in win.title.lower():
                    if not win.isActive:
                        win.activate()
                    time.sleep(0.2)
                    return True
        except Exception:
            pass
        time.sleep(0.3)

    return False


def type_text(text: str, delay: float = 0.02) -> bool:
    """
    Type text into currently focused application window.
    Uses clipboard paste for multiline/unicode reliability, or pyautogui write.
    """
    if not PYAUTOGUI_AVAILABLE:
        return False

    try:
        # For multiline or unicode text, clipboard paste is fast and deterministic
        if "\n" in text or any(ord(c) > 127 for c in text):
            if PYPERCLIP_AVAILABLE:
                old_clip = ""
                try:
                    old_clip = pyperclip.paste()
                except Exception:
                    pass

                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.05)
                return True

        # Standard keyboard typing
        pyautogui.write(text, interval=delay)
        return True
    except Exception as e:
        logger.warning(f"Error typing text: {e}")
        return False


def press_key(key: str) -> bool:
    """Press a single key (e.g. 'enter', 'tab', 'esc', 'space')."""
    if not PYAUTOGUI_AVAILABLE:
        return False
    try:
        pyautogui.press(key.lower())
        return True
    except Exception as e:
        logger.warning(f"Error pressing key '{key}': {e}")
        return False


def execute_steps(
    steps: List[Dict[str, Any]],
    log_callback: Optional[Callable[[str], None]] = None
) -> List[str]:
    """
    Execute a sequence of GUI automation steps, reporting progress via log_callback.
    """
    logs: List[str] = []

    def _log(msg: str):
        logs.append(msg)
        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

    for step in steps:
        action = step.get("action", "")

        if action == "wait":
            secs = float(step.get("seconds", 1.0))
            _log(f"[*] Waiting {secs:.1f}s for application interface to settle...")
            time.sleep(secs)

        elif action == "focus":
            title = step.get("title", "")
            _log(f"[*] Focusing application window matching '{title}'...")
            focused = focus_window_by_title(title, timeout=step.get("timeout", 3.0))
            if focused:
                _log(f"[+] Application window '{title}' focused successfully.")
            else:
                _log(f"[-] Could not find distinct window for '{title}', proceeding with active window.")

        elif action == "type":
            content = step.get("text", "")
            preview = content[:30] + "..." if len(content) > 30 else content
            _log(f"[*] Typing input: \"{preview}\" ({len(content)} chars)...")
            success = type_text(content, delay=step.get("delay", 0.02))
            if success:
                _log(f"[+] Automated text entry completed.")
            else:
                _log(f"[-] Text entry skipped or failed (display/PyAutoGUI unavailable).")

        elif action == "press":
            key = step.get("key", "enter")
            _log(f"[*] Pressing key: [{key.upper()}]...")
            press_key(key)
            _log(f"[+] Key [{key.upper()}] sent.")

        elif action == "hotkey":
            keys = step.get("keys", [])
            _log(f"[*] Triggering shortcut: [{'+'.join(keys).upper()}]...")
            if PYAUTOGUI_AVAILABLE and keys:
                pyautogui.hotkey(*keys)
                _log(f"[+] Shortcut [{'+'.join(keys).upper()}] executed.")

    return logs


def parse_compound_instruction(text: str) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Parse natural language commands like:
      - "open notepad and type Hello World"
      - "run notepad and write This is a test"
      - "launch notepad and enter Some text"
      - "open calc and type 123"
    Returns (target_app, steps) or None.
    """
    import re

    clean = text.strip()
    # Strip prefixes
    clean = re.sub(r"^(momento\s*[,:]?\s*|hey momento\s*[,:]?\s*|please\s+)", "", clean, flags=re.IGNORECASE).strip()

    # Pattern: (open|run|launch|start)\s+(<app>)\s+(?:and|,?\s*then)\s+(?:type|write|enter|paste|input)\s+(.+)
    pattern = r"^(?:open|run|launch|start)\s+(.+?)\s+(?:and|,?\s*then)\s+(?:type|write|enter|paste|input)\s+(.+)$"
    m = re.match(pattern, clean, flags=re.IGNORECASE)
    if m:
        target_app = m.group(1).strip()
        payload = m.group(2).strip()

        # Remove surrounding quotes if present
        if (payload.startswith('"') and payload.endswith('"')) or (payload.startswith("'") and payload.endswith("'")):
            payload = payload[1:-1]

        steps: List[Dict[str, Any]] = [
            {"action": "wait", "seconds": 1.2},
            {"action": "focus", "title": target_app, "timeout": 2.5},
            {"action": "type", "text": payload, "delay": 0.02}
        ]

        # Check if ending with "and press enter"
        m_enter = re.search(r"\s+(?:and|,?\s*then)\s+press\s+(?:enter|return)$", payload, flags=re.IGNORECASE)
        if m_enter:
            clean_payload = payload[:m_enter.start()].strip()
            steps[2]["text"] = clean_payload
            steps.append({"action": "press", "key": "enter"})

        return (target_app, steps)

    return None


def get_process_info_by_pid(pid: int) -> Dict[str, Any]:
    """Retrieve process executable name and full image path by PID using Win32 API."""
    info = {"pid": pid, "name": "unknown", "path": ""}
    if sys.platform != "win32" or not pid:
        return info
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        h_proc = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h_proc:
            try:
                buf = (ctypes.c_wchar * 1024)()
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    full_path = buf.value
                    info["path"] = full_path
                    info["name"] = os.path.basename(full_path)
            finally:
                kernel32.CloseHandle(h_proc)
    except Exception:
        pass
    return info


def list_active_windows() -> List[Dict[str, Any]]:
    """
    Enumerate active visible top-level application windows on the desktop.
    Returns structured list of dictionaries with title, pid, process_name, handle, rect, class_name.
    """
    windows_found: List[Dict[str, Any]] = []
    seen_handles: Set[int] = set()

    if sys.platform == "win32":
        # 1. Inspect using pywinauto UIA Desktop if available
        if PYWINAUTO_AVAILABLE:
            try:
                d = Desktop(backend="uia")
                for w in d.windows():
                    try:
                        title = w.window_text().strip()
                        if not title:
                            continue
                        hwnd = getattr(w, "handle", 0)
                        if hwnd and hwnd in seen_handles:
                            continue
                        if hwnd:
                            seen_handles.add(hwnd)

                        pid = w.process_id()
                        proc_info = get_process_info_by_pid(pid)
                        r = w.rectangle()
                        width = r.width()
                        height = r.height()
                        # Ignore 0-sized hidden helper windows or root desktop
                        if width <= 1 and height <= 1:
                            continue
                        rect_dict = {
                            "left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
                            "width": width, "height": height
                        }
                        windows_found.append({
                            "title": title,
                            "pid": pid,
                            "process_name": proc_info["name"],
                            "process_path": proc_info["path"],
                            "handle": hwnd,
                            "rect": rect_dict,
                            "class_name": w.class_name()
                        })
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"pywinauto window enumeration error: {e}")

        # 2. Fallback to pygetwindow if needed
        if not windows_found and PYGETWINDOW_AVAILABLE:
            try:
                for w in pygetwindow.getAllWindows():
                    if w.title and w.title.strip():
                        hwnd = getattr(w, "_hWnd", 0)
                        if hwnd and hwnd in seen_handles:
                            continue
                        if hwnd:
                            seen_handles.add(hwnd)
                        if w.width <= 1 and w.height <= 1:
                            continue
                        rect_dict = {
                            "left": w.left, "top": w.top, "right": w.right, "bottom": w.bottom,
                            "width": w.width, "height": w.height
                        }
                        pid = 0
                        proc_info = {"name": "unknown", "path": ""}
                        if hwnd:
                            import ctypes
                            from ctypes import wintypes
                            pid_val = wintypes.DWORD()
                            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                            pid = pid_val.value
                            proc_info = get_process_info_by_pid(pid)
                        windows_found.append({
                            "title": w.title.strip(),
                            "pid": pid,
                            "process_name": proc_info["name"],
                            "process_path": proc_info["path"],
                            "handle": hwnd,
                            "rect": rect_dict,
                            "class_name": ""
                        })
            except Exception as e:
                logger.debug(f"pygetwindow enumeration error: {e}")

    return windows_found


def get_foreground_window_info() -> Optional[Dict[str, Any]]:
    """Retrieve title, PID, process name, class, and bounds for the active foreground window."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # Title
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

        # PID
        pid_val = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
        pid = pid_val.value
        proc_info = get_process_info_by_pid(pid)

        # Class
        class_buff = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buff, 256)
        class_name = class_buff.value

        # Rect
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        rect_dict = {
            "left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom,
            "width": rect.right - rect.left, "height": rect.bottom - rect.top
        }

        return {
            "title": title,
            "pid": pid,
            "process_name": proc_info["name"],
            "process_path": proc_info["path"],
            "handle": hwnd,
            "rect": rect_dict,
            "class_name": class_name
        }
    except Exception as e:
        logger.debug(f"GetForegroundWindow error: {e}")
        return None


def inspect_window_ui(
    target: Optional[str] = None,
    pid: Optional[int] = None,
    hwnd: Optional[int] = None,
    max_controls: int = 50
) -> Dict[str, Any]:
    """
    Introspect active application window, extracting title, process details,
    geometry, control hierarchy, and textual elements via pywinauto / Windows UI Automation.
    Returns structured inspection dictionary and live formatted log lines.
    """
    active_windows = list_active_windows()
    selected_win: Optional[Dict[str, Any]] = None

    # 1. Match by handle if explicitly provided
    if hwnd:
        for w in active_windows:
            if w.get("handle") == hwnd:
                selected_win = w
                break

    # 2. Match by PID if explicitly provided
    if not selected_win and pid:
        for w in active_windows:
            if w.get("pid") == pid:
                selected_win = w
                break

    # 3. Match by target name / substring (e.g. "notepad", "calculator", "chrome")
    if not selected_win and target and target.lower() not in ("active", "current", "screen", "window", "the app", "app"):
        target_lower = target.lower()
        for w in active_windows:
            title_lower = w.get("title", "").lower()
            proc_lower = w.get("process_name", "").lower()
            if target_lower in title_lower or target_lower in proc_lower:
                selected_win = w
                break

    # 4. Fallback: Check foreground window
    if not selected_win:
        fg = get_foreground_window_info()
        if fg and fg.get("title") and fg.get("title") not in ("Program Manager", "Task Switching", "Taskbar"):
            selected_win = fg

    # 5. Fallback: Select first visible application window from list
    if not selected_win and active_windows:
        for w in active_windows:
            # Skip typical background desktop components
            if w.get("class_name") not in ("Shell_TrayWnd", "Progman", "WorkerW"):
                selected_win = w
                break

    if not selected_win:
        return {
            "success": False,
            "target": target,
            "title": None,
            "pid": None,
            "process_name": None,
            "rect": None,
            "controls_count": 0,
            "controls": [],
            "visible_texts": [],
            "error": "No active application window found on screen to inspect.",
            "summary": "Momento UI Introspection: No active application window found on screen.",
            "log_lines": [
                "[*] Contextual Window Inspection Initiated...",
                "[-] No active application window detected on desktop.",
                "[*] Launch an application or bring an existing window into focus."
            ]
        }

    title = selected_win.get("title", "Unknown Window")
    w_pid = selected_win.get("pid") or pid or 0
    proc_name = selected_win.get("process_name", "unknown")
    w_hwnd = selected_win.get("handle") or hwnd or 0
    w_rect = selected_win.get("rect") or {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}
    class_name = selected_win.get("class_name", "")

    controls: List[Dict[str, Any]] = []
    visible_texts: List[str] = []
    seen_texts: Set[str] = set()

    # Query UI tree using pywinauto
    if PYWINAUTO_AVAILABLE and (w_hwnd or w_pid):
        for backend in ("uia", "win32"):
            try:
                d = Desktop(backend=backend)
                wrapper = None
                if w_hwnd:
                    try:
                        wrapper = d.window(handle=w_hwnd)
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
                    if not class_name:
                        try:
                            class_name = wrapper.class_name()
                        except Exception:
                            pass

                    descendants = []
                    try:
                        descendants = wrapper.descendants()
                    except Exception:
                        pass

                    for c in descendants[:max_controls]:
                        try:
                            c_title = c.window_text().strip()
                            c_class = c.class_name()
                            c_type = getattr(c.element_info, "control_type", None) or c_class or "Control"
                            c_auto_id = getattr(c.element_info, "automation_id", "")
                            
                            c_rect = None
                            try:
                                cr = c.rectangle()
                                c_rect = {
                                    "left": cr.left, "top": cr.top, "right": cr.right, "bottom": cr.bottom,
                                    "width": cr.width(), "height": cr.height()
                                }
                            except Exception:
                                pass

                            controls.append({
                                "class_name": c_class,
                                "control_type": str(c_type),
                                "text": c_title,
                                "automation_id": c_auto_id,
                                "rect": c_rect
                            })

                            if c_title and c_title not in seen_texts and len(c_title) < 200:
                                seen_texts.add(c_title)
                                visible_texts.append(c_title)
                        except Exception:
                            pass
                    break  # Introspection succeeded on current backend
            except Exception as e:
                logger.debug(f"pywinauto introspection attempt error ({backend}): {e}")

    # Build control element breakdown
    types_count: Dict[str, int] = {}
    for c in controls:
        ct = c.get("control_type") or "Control"
        types_count[ct] = types_count.get(ct, 0) + 1

    # Format live terminal log lines
    w_width = w_rect.get("width", 0)
    w_height = w_rect.get("height", 0)
    w_left = w_rect.get("left", 0)
    w_top = w_rect.get("top", 0)

    log_lines: List[str] = [
        "[*] Contextual Window Inspection Initiated...",
        f"[+] Active Window: '{title}'",
        f"[+] Process: {proc_name} (PID: {w_pid})",
        f"[+] Window Class: {class_name or 'Standard Window'} | Geometry: {w_width}x{w_height} at ({w_left}, {w_top})",
        f"[+] UI Control Tree: {len(controls)} element(s) introspected"
    ]

    if types_count:
        breakdown_str = ", ".join(f"{k}: {v}" for k, v in sorted(types_count.items()))
        log_lines.append(f"[+] Elements Breakdown: {breakdown_str}")

    if visible_texts:
        log_lines.append(f"[+] Screen Text Elements ({len(visible_texts)} found):")
        for t in visible_texts[:10]:
            log_lines.append(f"    - \"{t}\"")
        if len(visible_texts) > 10:
            log_lines.append(f"    ... [{len(visible_texts) - 10} additional elements]")

    log_lines.append("[+] Introspection completed successfully.")

    # Format readable summary
    summary = (
        f"Momento UI Introspection Report:\n"
        f"  [+] Window Title: '{title}'\n"
        f"  [+] Process:      {proc_name} (PID: {w_pid})\n"
        f"  [+] Geometry:     {w_width}x{w_height} at ({w_left}, {w_top})\n"
        f"  [+] UI Elements:  {len(controls)} controls introspected\n"
    )
    if types_count:
        top_types = ", ".join(f"{k}({v})" for k, v in list(sorted(types_count.items(), key=lambda x: -x[1]))[:6])
        summary += f"  [+] Breakdown:    {top_types}\n"
    if visible_texts:
        preview_texts = '", "'.join(visible_texts[:6])
        summary += f'  [+] Screen Text:  ["{preview_texts}"]\n'

    return {
        "success": True,
        "target": target,
        "title": title,
        "pid": w_pid,
        "process_name": proc_name,
        "rect": w_rect,
        "class_name": class_name,
        "controls_count": len(controls),
        "controls": controls,
        "visible_texts": visible_texts,
        "summary": summary.rstrip(),
        "log_lines": log_lines
    }

