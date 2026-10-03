"""
Momento Onboarding & Permission Wizard
======================================
Interactive first-run onboarding prompt that requests system access/permissions,
configures backend connection, and executes local application discovery.
"""

import os
import sys
from typing import Optional

from client.config import (
    DEFAULT_BACKEND_URL,
    is_setup_completed,
    load_config,
    save_config,
    set_permissions
)
from client.scanner import AppScanner

BANNER = r"""
  __  __                         _        
 |  \/  |                       | |       
 | \  / | ___  _ __ ___   ___ _ __ | |_ ___  
 | |\/| |/ _ \| '_ ` _ \ / _ \ '_ \| __/ _ \ 
 | |  | | (_) | | | | | |  __/ | | | || (_) |
 |_|  |_|\___/|_| |_| |_|\___|_| |_|\__\___/ 
                                              
   Universal Host Runtime & Isolated Sandbox
"""


def prompt_user_confirmation(prompt_text: str, default_yes: bool = True) -> bool:
    """Prompt user for confirmation (y/n) with default value."""
    hint = "[Y/n]" if default_yes else "[y/N]"
    try:
        choice = input(f"{prompt_text} {hint}: ").strip().lower()
        if not choice:
            return default_yes
        return choice in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run_onboarding(
    force: bool = False,
    non_interactive: bool = False,
    backend_url: Optional[str] = None
) -> bool:
    """
    Run the initial setup and permission request flow.
    Returns True if setup was completed successfully.
    """
    if not force and is_setup_completed():
        return True

    print(BANNER)
    print("=" * 60)
    print("Welcome to Momento Local Client Onboarding!")
    print("=" * 60)
    print("Momento bridges your local workflow with our high-performance")
    print("isolated VPS Sandbox backend to run, inspect, and automate apps.\n")

    # 1. Permission Requests
    print("[1/3] System Permission Requests:")
    print("  To enable seamless local operation, Momento requires:")
    print("  * [1] File System Indexing: Read common app directories & PATH.")
    print("  * [2] App Discovery: Catalog installed software in local registry.")
    print("  * [3] Execution Rights: Dispatch launch & inspect commands to Momento VPS.\n")

    if non_interactive:
        granted = True
    else:
        granted = prompt_user_confirmation("Grant system permissions to Momento?")

    if not granted:
        print("\n[!] Setup cancelled. Permissions are required to run Momento locally.")
        return False

    # 2. Backend Link Configuration
    print("\n[2/3] Backend Core Link:")
    chosen_url = backend_url or DEFAULT_BACKEND_URL
    if not non_interactive:
        try:
            user_input = input(
                f"Enter Momento VPS Backend URL [default: {DEFAULT_BACKEND_URL}]: "
            ).strip()
            if user_input:
                chosen_url = user_input.rstrip("/")
        except (EOFError, KeyboardInterrupt):
            print()
            chosen_url = DEFAULT_BACKEND_URL

    print(f"[*] Configured Backend: {chosen_url}")

    # 3. Environment Scan & App Discovery
    print("\n[3/3] Performing Local Environment Scan...")
    scanner = AppScanner()
    try:
        registry = scanner.scan_environment()
        total_apps = registry.get("total_apps", 0)
        print(f"[+] Successfully cataloged {total_apps} applications into:")
        print(f"    {scanner.registry_file}\n")
    except Exception as e:
        print(f"[!] Warning during app scan: {e}")
        registry = {"total_apps": 0}

    # Save configuration & permissions
    cfg = load_config()
    cfg["backend_url"] = chosen_url
    cfg["permissions"] = {
        "filesystem_indexing": True,
        "app_discovery": True,
        "execution_rights": True
    }
    cfg["setup_completed"] = True
    save_config(cfg)

    print("=" * 60)
    print("[+] Setup Complete! Momento is ready to use.")
    print("    Try running:")
    print("      momento \"open notepad\"")
    print("      momento \"run calc\"")
    print("      momento shell")
    print("=" * 60 + "\n")
    return True
