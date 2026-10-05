"""
Momento Desktop GUI Automation & Interaction Engine
===================================================
Coordinates safe UI automation, keyboard typing, window focusing, and keypress
interactions across desktop applications (Notepad, Calculator, custom tools).
"""

import logging
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

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
