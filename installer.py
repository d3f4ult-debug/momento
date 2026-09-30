"""
Momento Desktop App Installer
Installs Momento to the user's local application directory,
creates Desktop and Start Menu shortcuts, registers an uninstaller,
and optionally launches Momento immediately.
"""

import sys
import os
import zipfile
import subprocess
import tempfile
import argparse
import threading
import shutil
try:
    import winreg
except ImportError:
    winreg = None

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    tk = None


APP_NAME = "Momento"
APP_DISPLAY_NAME = "Momento Universal AI Agent Workspace"
APP_VERSION = "1.1.0"
APP_PUBLISHER = "Momento AI"
DEFAULT_INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Programs",
    "Momento"
)


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def make_shortcut(target_path: str, link_path: str, description: str = ""):
    """Create a Windows .lnk shortcut using standard WScript.Shell without extra dependencies."""
    os.makedirs(os.path.dirname(link_path), exist_ok=True)
    working_dir = os.path.dirname(target_path)

    vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{link_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target_path}"
oLink.WorkingDirectory = "{working_dir}"
oLink.Description = "{description}"
oLink.Save
'''
    with tempfile.NamedTemporaryFile('w', suffix='.vbs', delete=False) as f:
        f.write(vbs_content)
        vbs_path = f.name

    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(['cscript', '//nologo', vbs_path], check=True, creationflags=flags)
    finally:
        if os.path.exists(vbs_path):
            os.remove(vbs_path)


def create_uninstaller(install_dir: str, desktop_link: str, start_menu_link: str):
    """Create a clean uninstaller batch script and register with Windows."""
    uninstall_bat = os.path.join(install_dir, "uninstall.bat")
    
    bat_content = f'''@echo off
title Uninstall {APP_DISPLAY_NAME}
echo ===================================================
echo   Uninstalling {APP_DISPLAY_NAME}
echo ===================================================
echo.

:: Remove shortcuts
if exist "{desktop_link}" del /f /q "{desktop_link}"
if exist "{start_menu_link}" del /f /q "{start_menu_link}"

:: Remove registry entry
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" /f >nul 2>&1

echo Shortcuts and registry entries removed.
echo Removing application directory...

:: Self-deleting batch command to clean directory
cd /d "%TEMP%"
rmdir /s /q "{install_dir}" >nul 2>&1

echo.
echo {APP_NAME} has been completely uninstalled.
timeout /t 3 >nul
'''
    with open(uninstall_bat, "w", encoding="utf-8") as f:
        f.write(bat_content)

    # Register in Windows Add / Remove Programs if winreg is available
    if winreg:
        try:
            key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, os.path.join(install_dir, "Momento.exe"))
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstall_bat}"')
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        except Exception as e:
            print(f"Notice: Could not write uninstall registry entry: {e}")


def perform_installation(install_dir: str, create_desktop: bool, create_start: bool, progress_callback=None):
    """Extract embedded payload and configure shortcuts and registry."""
    payload_zip = get_resource_path("installer_payload.zip")

    if not os.path.exists(payload_zip):
        # Fallback to local dist/Momento directory if zip not bundled
        local_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "Momento")
        if not os.path.exists(local_dist):
            raise FileNotFoundError("Installation payload (installer_payload.zip or dist/Momento) not found.")

    os.makedirs(install_dir, exist_ok=True)

    if os.path.exists(payload_zip):
        with zipfile.ZipFile(payload_zip, 'r') as zip_ref:
            total_files = len(zip_ref.infolist())
            for idx, item in enumerate(zip_ref.infolist(), 1):
                zip_ref.extract(item, install_dir)
                if progress_callback:
                    pct = int((idx / total_files) * 85)
                    progress_callback(pct, f"Extracting {os.path.basename(item.filename)}...")
    else:
        local_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "Momento")
        files = []
        for root, _, filenames in os.walk(local_dist):
            for fn in filenames:
                files.append(os.path.join(root, fn))
        total_files = len(files)
        for idx, src_file in enumerate(files, 1):
            rel_path = os.path.relpath(src_file, local_dist)
            dst_file = os.path.join(install_dir, rel_path)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)
            if progress_callback:
                pct = int((idx / total_files) * 85)
                progress_callback(pct, f"Copying {os.path.basename(src_file)}...")

    if progress_callback:
        progress_callback(90, "Creating application shortcuts...")

    main_exe = os.path.join(install_dir, "Momento.exe")
    desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    start_menu_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "Microsoft", "Windows", "Start Menu", "Programs"
    )

    desktop_link = os.path.join(desktop_dir, f"{APP_NAME}.lnk")
    start_menu_link = os.path.join(start_menu_dir, f"{APP_NAME}.lnk")

    if create_desktop:
        make_shortcut(main_exe, desktop_link, APP_DISPLAY_NAME)

    if create_start:
        make_shortcut(main_exe, start_menu_link, APP_DISPLAY_NAME)

    if progress_callback:
        progress_callback(95, "Registering uninstaller...")

    create_uninstaller(install_dir, desktop_link, start_menu_link)

    if progress_callback:
        progress_callback(100, "Installation complete!")

    return main_exe


class InstallerGUI:
    """Tkinter-based sleek installer wizard for Windows."""

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("540x440")
        self.root.resizable(False, False)

        # Style configuration
        self.bg_color = "#0e1117"
        self.card_bg = "#1b202e"
        self.text_color = "#f8fafc"
        self.subtext_color = "#94a3b8"
        self.accent_color = "#6366f1"

        self.root.configure(bg=self.bg_color)

        self.install_dir_var = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        self.start_shortcut_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=True)

        self.installed_exe = None
        self._build_ui()

    def _build_ui(self):
        # Header Banner
        header_frame = tk.Frame(self.root, bg="#131722", padx=20, pady=16)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(
            header_frame,
            text=f"⚡ {APP_NAME} Setup",
            font=("Segoe UI", 16, "bold"),
            fg="#ffffff",
            bg="#131722"
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame,
            text="Universal AI Agent Workspace — Installation Wizard",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#131722"
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Main Body Frame
        body_frame = tk.Frame(self.root, bg=self.bg_color, padx=24, pady=16)
        body_frame.pack(fill="both", expand=True)

        # Destination Folder
        dest_lbl = tk.Label(
            body_frame,
            text="Destination Directory:",
            font=("Segoe UI", 9, "bold"),
            fg=self.text_color,
            bg=self.bg_color
        )
        dest_lbl.pack(anchor="w", pady=(0, 4))

        dest_box = tk.Frame(body_frame, bg=self.bg_color)
        dest_box.pack(fill="x", pady=(0, 14))

        self.dest_entry = tk.Entry(
            dest_box,
            textvariable=self.install_dir_var,
            font=("Segoe UI", 9),
            bg="#1b202e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            bd=5
        )
        self.dest_entry.pack(side="left", fill="x", expand=True, ipady=3)

        browse_btn = tk.Button(
            dest_box,
            text="Browse...",
            font=("Segoe UI", 9),
            bg="#283044",
            fg="#ffffff",
            activebackground="#3b445c",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            command=self._browse_dir
        )
        browse_btn.pack(side="right", padx=(8, 0))

        # Options Card
        opts_card = tk.Frame(body_frame, bg="#131722", padx=16, pady=12, relief="flat")
        opts_card.pack(fill="x", pady=(0, 14))

        opts_lbl = tk.Label(
            opts_card,
            text="Installation Options:",
            font=("Segoe UI", 9, "bold"),
            fg=self.text_color,
            bg="#131722"
        )
        opts_lbl.pack(anchor="w", pady=(0, 6))

        dt_chk = tk.Checkbutton(
            opts_card,
            text="Create Desktop Shortcut",
            variable=self.desktop_shortcut_var,
            font=("Segoe UI", 9),
            bg="#131722",
            fg=self.text_color,
            selectcolor="#1b202e",
            activebackground="#131722",
            activeforeground=self.text_color
        )
        dt_chk.pack(anchor="w", pady=2)

        sm_chk = tk.Checkbutton(
            opts_card,
            text="Create Start Menu Shortcut",
            variable=self.start_shortcut_var,
            font=("Segoe UI", 9),
            bg="#131722",
            fg=self.text_color,
            selectcolor="#1b202e",
            activebackground="#131722",
            activeforeground=self.text_color
        )
        sm_chk.pack(anchor="w", pady=2)

        ln_chk = tk.Checkbutton(
            opts_card,
            text="Launch Momento immediately after install",
            variable=self.launch_after_var,
            font=("Segoe UI", 9),
            bg="#131722",
            fg=self.text_color,
            selectcolor="#1b202e",
            activebackground="#131722",
            activeforeground=self.text_color
        )
        ln_chk.pack(anchor="w", pady=2)

        # Progress Area
        self.progress_bar = ttk.Progressbar(body_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 4))

        self.status_lbl = tk.Label(
            body_frame,
            text="Ready to install.",
            font=("Segoe UI", 8),
            fg=self.subtext_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.status_lbl.pack(fill="x")

        # Footer Frame
        footer_frame = tk.Frame(self.root, bg="#131722", padx=20, pady=12)
        footer_frame.pack(fill="x", side="bottom")

        self.cancel_btn = tk.Button(
            footer_frame,
            text="Cancel",
            font=("Segoe UI", 9),
            bg="#283044",
            fg="#ffffff",
            activebackground="#3b445c",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=4,
            command=self.root.quit
        )
        self.cancel_btn.pack(side="right", padx=(8, 0))

        self.install_btn = tk.Button(
            footer_frame,
            text="Install",
            font=("Segoe UI", 9, "bold"),
            bg=self.accent_color,
            fg="#ffffff",
            activebackground="#4f46e5",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=4,
            command=self._start_install
        )
        self.install_btn.pack(side="right")

    def _browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.install_dir_var.get())
        if chosen:
            self.install_dir_var.set(os.path.normpath(chosen))

    def _update_progress(self, percent: int, message: str):
        def _update():
            self.progress_bar['value'] = percent
            self.status_lbl.config(text=message)
        self.root.after(0, _update)

    def _start_install(self):
        target_dir = self.install_dir_var.get().strip()
        if not target_dir:
            messagebox.showerror("Error", "Please specify a valid installation directory.")
            return

        self.install_btn.config(state="disabled")
        self.dest_entry.config(state="disabled")
        self.cancel_btn.config(state="disabled")

        def _worker():
            try:
                main_exe = perform_installation(
                    install_dir=target_dir,
                    create_desktop=self.desktop_shortcut_var.get(),
                    create_start=self.start_shortcut_var.get(),
                    progress_callback=self._update_progress
                )
                self.installed_exe = main_exe
                self.root.after(0, self._on_success)
            except Exception as e:
                self.root.after(0, lambda: self._on_failure(str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_success(self):
        self.status_lbl.config(text="✓ Installation successfully completed!", fg="#4ade80")
        self.progress_bar['value'] = 100
        self.install_btn.config(text="Finish", state="normal", bg="#10b981", activebackground="#059669", command=self._finish)
        self.cancel_btn.pack_forget()

    def _on_failure(self, error_msg: str):
        messagebox.showerror("Installation Failed", f"An error occurred during installation:\n\n{error_msg}")
        self.status_lbl.config(text="Installation failed.", fg="#f87171")
        self.install_btn.config(state="normal", text="Retry")
        self.dest_entry.config(state="normal")
        self.cancel_btn.config(state="normal")

    def _finish(self):
        if self.launch_after_var.get() and self.installed_exe and os.path.exists(self.installed_exe):
            try:
                subprocess.Popen([self.installed_exe], cwd=os.path.dirname(self.installed_exe))
            except Exception as e:
                print(f"Notice: Failed to launch installed app: {e}")
        self.root.quit()


def parse_installer_args(argv=None):
    if argv is None:
        raw_args = sys.argv[1:]
    else:
        raw_args = list(argv)

    # Normalize Windows-style flags (/S, /SILENT, /D)
    normalized = []
    for a in raw_args:
        if a.upper() in ("/S", "/SILENT"):
            normalized.append("--silent")
        elif a.upper() in ("/NO-DESKTOP",):
            normalized.append("--no-desktop")
        elif a.upper() in ("/NO-START",):
            normalized.append("--no-start")
        elif a.upper() in ("/LAUNCH",):
            normalized.append("--launch")
        elif a.upper().startswith("/D="):
            normalized.append("--dir")
            normalized.append(a[3:])
        else:
            normalized.append(a)

    parser = argparse.ArgumentParser(description=f"{APP_NAME} Installer")
    parser.add_argument("-s", "--silent", action="store_true", help="Silent installation without GUI")
    parser.add_argument("--dir", default=DEFAULT_INSTALL_DIR, help="Target installation directory")
    parser.add_argument("--no-desktop", action="store_true", help="Do not create desktop shortcut")
    parser.add_argument("--no-start", action="store_true", help="Do not create Start Menu shortcut")
    parser.add_argument("--launch", action="store_true", help="Launch Momento after installation")
    return parser.parse_args(normalized)


def main():
    args = parse_installer_args()

    if args.silent or tk is None:
        print(f"Installing {APP_DISPLAY_NAME} to: {args.dir}...")
        try:
            main_exe = perform_installation(
                install_dir=args.dir,
                create_desktop=not args.no_desktop,
                create_start=not args.no_start,
                progress_callback=lambda pct, msg: print(f"[{pct}%] {msg}")
            )
            print(f"Installation complete: {main_exe}")
            if args.launch and os.path.exists(main_exe):
                subprocess.Popen([main_exe], cwd=os.path.dirname(main_exe))
        except Exception as e:
            print(f"Installation error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Interactive GUI Mode
    root = tk.Tk()
    app = InstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
