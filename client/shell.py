"""
Momento Interactive Conversational Shell
========================================
Interactive terminal experience for executing conversational app commands,
managing sandbox processes, and querying live telemetry.
"""

import os
import sys
from typing import Optional

from client.config import get_backend_url, is_setup_completed, load_config
from client.nlp_router import NLPRouter
from client.onboarding import run_onboarding


def start_interactive_shell(backend_url: Optional[str] = None) -> int:
    """Launch the interactive conversational Momento shell."""
    # Ensure onboarding is completed first
    if not is_setup_completed():
        print("[!] Setup not detected. Starting onboarding wizard...")
        success = run_onboarding(backend_url=backend_url)
        if not success:
            print("[!] Onboarding incomplete. Exiting.")
            return 1

    active_url = backend_url or get_backend_url()
    router = NLPRouter(backend_url=active_url)

    print("\n" + "=" * 55)
    print("  Momento Conversational Shell")
    print(f"  Connected to VPS Backend: {active_url}")
    print("  Type 'help' for examples or 'exit' to quit.")
    print("=" * 55 + "\n")

    while True:
        try:
            line = input("momento> ").strip()
            if not line:
                continue

            if line.lower() in ("exit", "quit", "q", ":q"):
                print("Goodbye!")
                return 0

            if line.lower() in ("config", "status"):
                cfg = load_config()
                print(f"[*] Momento Client Status:")
                print(f"    Backend URL:     {cfg.get('backend_url')}")
                print(f"    Setup Complete:  {cfg.get('setup_completed')}")
                print(f"    Registry Path:   {cfg.get('registry_path')}")
                continue

            result = router.execute(line)
            message = result.get("message", "")
            if message:
                print(message)
            print()

        except (KeyboardInterrupt, EOFError):
            print("\nExiting Momento shell.")
            return 0
        except Exception as e:
            print(f"[!] Error: {e}\n")
