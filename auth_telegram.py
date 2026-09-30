"""
Momento - Telegram Personal Account Interactive & Headless Login
Run this script in your terminal to log in to your personal Telegram account.
API ID and Hash are built-in automatically — you only provide your phone number and OTP code.
Uses in-memory StringSession: no SQLite database files, no table corruptions, completely portable.
"""

import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import ApiIdInvalidError
from services.telegram_userbot import (
    get_telegram_credentials,
    set_active_session_string,
    get_active_session_string,
    cleanup_session_files,
    SESSION_NAME,
)

load_dotenv()


def main():
    print("=" * 60)
    print(" Momento - Telegram Login (StringSession)")
    print("=" * 60)
    print("Connecting to Telegram...")

    # Clear any stale legacy session files
    cleanup_session_files(SESSION_NAME, force=False)

    load_dotenv()
    api_id = int(os.getenv("TELEGRAM_API_ID") or 2040)
    api_hash = str(os.getenv("TELEGRAM_API_HASH") or "b18441a1ff607e10a989891a5462e627").strip()

    # Initialize client with empty in-memory StringSession
    session = StringSession()
    client = TelegramClient(session, api_id, api_hash)

    try:
        with client:
            # client.start() prompts for phone number, login code, and optional 2FA password
            client.start()

            me = client.get_me()
            full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            session_string = client.session.save()

            # Save session string persistently to .session_string and .env
            set_active_session_string(session_string)

            print("\n" + "=" * 60)
            print(" [✓] Successfully logged in to Telegram!")
            print(f"     Account:         {full_name} (@{me.username or 'No username'})")
            print(f"     Phone:           +{me.phone}")
            print(f"     Session Storage: Saved to .env and .session_string")
            print(f"     Session String:  {session_string[:20]}...{session_string[-10:]}")
            print("=" * 60)
            print("\nMomento can now dispatch outputs directly from your account")
            print("to contacts and chats (e.g. searching 'Animatic') natively!\n")
    except ApiIdInvalidError:
        print("\n[x] Telegram login failed: API_ID_INVALID.")
        print("    Your Telegram API ID / API Hash is invalid.")
        print(f"    Current API_ID: {strict_api_id}")
        cleanup_session_files(SESSION_NAME, force=True)
        sys.exit(1)
    except Exception as e:
        print(f"\n[x] Telegram login failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
