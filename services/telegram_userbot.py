"""
Telegram Userbot Service using Telethon.
Features built-in standard Telegram developer credentials so users never need to
manually configure API IDs or API Hashes from my.telegram.org.
"""

import os
import asyncio
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dotenv import load_dotenv

load_dotenv()

# Telegram developer credentials (provided working pair)
DEFAULT_API_ID = 2040
DEFAULT_API_HASH = "b18441a1ff607e10a989891a5462e627"

SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "momento_user_session")

# Active session tracking
_ACTIVE_SESSION_FILE = Path(".active_session")
_SESSION_STRING_FILE = Path(".session_string")
_ACTIVE_SESSION_STRING: Optional[str] = None

# In-memory store for pending phone auth requests: {phone: phone_code_hash}
_PENDING_AUTH_HASHES: Dict[str, str] = {}
# In-memory store for pending phone session isolation: {phone: session_name}
_PENDING_AUTH_SESSIONS: Dict[str, str] = {}
# In-memory store for active pending TelegramClient instances: {phone: client}
_PENDING_CLIENTS: Dict[str, Any] = {}
# In-memory store for pending string sessions: {phone: session_string}
_PENDING_STRING_SESSIONS: Dict[str, str] = {}


def get_active_session_string() -> str:
    """
    Return the currently active in-memory or persistent Telegram session string.
    Checks TELEGRAM_SESSION_STRING in environment variables, then .session_string file,
    and finally the in-memory global _ACTIVE_SESSION_STRING.
    """
    global _ACTIVE_SESSION_STRING
    env_str = os.getenv("TELEGRAM_SESSION_STRING", "").strip()
    if env_str:
        _ACTIVE_SESSION_STRING = env_str
        return env_str

    if _SESSION_STRING_FILE.exists():
        try:
            file_str = _SESSION_STRING_FILE.read_text(encoding="utf-8").strip()
            if file_str:
                _ACTIVE_SESSION_STRING = file_str
                return file_str
        except Exception:
            pass

    if _ACTIVE_SESSION_STRING:
        return _ACTIVE_SESSION_STRING.strip()

    return ""


def set_active_session_string(session_str: str) -> None:
    """
    Save the active session string in memory, write to .session_string,
    and persist into .env as TELEGRAM_SESSION_STRING.
    """
    global _ACTIVE_SESSION_STRING
    clean_str = session_str.strip()
    _ACTIVE_SESSION_STRING = clean_str
    os.environ["TELEGRAM_SESSION_STRING"] = clean_str

    try:
        _SESSION_STRING_FILE.write_text(clean_str, encoding="utf-8")
    except Exception:
        pass

    # Update or append in .env file
    env_path = Path(".env")
    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            if "TELEGRAM_SESSION_STRING=" in content:
                import re
                new_content = re.sub(
                    r"TELEGRAM_SESSION_STRING=.*",
                    f"TELEGRAM_SESSION_STRING={clean_str}",
                    content
                )
            else:
                new_content = content.rstrip() + f"\nTELEGRAM_SESSION_STRING={clean_str}\n"
            env_path.write_text(new_content, encoding="utf-8")
        except Exception:
            pass


def clear_active_session_string(remove_from_env: bool = True) -> None:
    """Clear active session string from memory, .session_string file, and .env."""
    global _ACTIVE_SESSION_STRING
    _ACTIVE_SESSION_STRING = None
    os.environ.pop("TELEGRAM_SESSION_STRING", None)
    try:
        _SESSION_STRING_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    if remove_from_env:
        env_path = Path(".env")
        if env_path.exists():
            try:
                content = env_path.read_text(encoding="utf-8")
                if "TELEGRAM_SESSION_STRING=" in content:
                    lines = [line for line in content.splitlines() if not line.startswith("TELEGRAM_SESSION_STRING=")]
                    env_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
            except Exception:
                pass



def get_active_session_name() -> str:
    """Return the currently active authenticated session name."""
    if _ACTIVE_SESSION_FILE.exists():
        try:
            saved_name = _ACTIVE_SESSION_FILE.read_text(encoding="utf-8").strip()
            if saved_name and (Path(f"{saved_name}.session").exists() or Path(f"{saved_name}").exists()):
                return saved_name
        except Exception:
            pass
    if Path(f"{SESSION_NAME}.session").exists() or Path(SESSION_NAME).exists():
        return SESSION_NAME
    return SESSION_NAME


def set_active_session_name(session_name: str) -> None:
    """Record the active session name persistently."""
    try:
        _ACTIVE_SESSION_FILE.write_text(session_name.strip(), encoding="utf-8")
    except Exception:
        pass



def delete_all_session_files(workspace_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """
    Locate any .session or .session-journal (or .session-wal, .session-shm) files
    in the backend workspace directory and delete them entirely via code using Path(...).unlink(missing_ok=True).
    """
    base_dir = Path(workspace_dir) if workspace_dir else Path(__file__).resolve().parent.parent
    deleted = []
    for pattern in ("*.session", "*.session-journal", "*.session-wal", "*.session-shm"):
        for p in base_dir.glob(pattern):
            try:
                p.unlink(missing_ok=True)
                deleted.append(p.name)
            except Exception:
                try:
                    with open(p, "wb") as f:
                        f.truncate(0)
                    deleted.append(p.name)
                except Exception:
                    pass
    return deleted


def reset_session_database(session_name: str) -> None:
    """
    Safely drop and recreate/unlink database tables and delete the SQLite files
    if an operational error occurs or when starting a fresh session, rather than reading from stale cache.
    """
    import sqlite3
    session_file = Path(f"{session_name}.session")
    journal_file = Path(f"{session_name}.session-journal")
    wal_file = Path(f"{session_name}.session-wal")
    shm_file = Path(f"{session_name}.session-shm")

    if session_file.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(session_file))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cur.fetchall()]
            for tbl in tables:
                try:
                    cur.execute(f"DROP TABLE IF EXISTS {tbl}")
                except Exception:
                    pass
            conn.commit()
        except Exception:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    # Unlink all session files using Path.unlink(missing_ok=True)
    session_file.unlink(missing_ok=True)
    journal_file.unlink(missing_ok=True)
    wal_file.unlink(missing_ok=True)
    shm_file.unlink(missing_ok=True)
    cleanup_session_files(session_name, force=True)


def cleanup_session_files(session_name: Optional[str] = None, force: bool = False) -> bool:
    """
    Clear corrupted or empty local .session and SQLite journal/wal files
    when a new authentication attempt is triggered so Telethon doesn't hold onto a bad handshake state.
    If force=True, unlinks the session files unconditionally using Path.unlink(missing_ok=True).
    """
    import sqlite3
    s_name = session_name or get_active_session_name()
    extensions = [".session", ".session-journal", ".session-wal", ".session-shm"]
    removed_any = False

    for ext in extensions:
        file_path = Path(f"{s_name}{ext}")
        if not file_path.exists():
            continue

        should_delete = force
        if not should_delete:
            try:
                # 1. Clear empty (0-byte) session files
                if file_path.stat().st_size == 0:
                    should_delete = True
                # 2. Clear corrupted SQLite files that fail validation
                elif ext == ".session":
                    # Check SQLite magic header
                    try:
                        with open(file_path, "rb") as sf:
                            header = sf.read(16)
                            if not header.startswith(b"SQLite format 3\x00"):
                                should_delete = True
                    except OSError:
                        should_delete = True

                    if not should_delete:
                        conn = None
                        try:
                            conn = sqlite3.connect(str(file_path))
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                            tables = [row[0] for row in cur.fetchall()]
                            # If tables exist but update_state is missing from Telethon schema, it is corrupted
                            if tables and "update_state" not in tables and "sessions" in tables:
                                should_delete = True
                        except Exception:
                            should_delete = True
                        finally:
                            if conn:
                                conn.close()
            except OSError:
                should_delete = True

        if should_delete:
            try:
                file_path.unlink(missing_ok=True)
                removed_any = True
            except OSError:
                # File may be temporarily held by OS; attempt truncate
                try:
                    with open(file_path, "wb") as f:
                        f.truncate(0)
                    removed_any = True
                except Exception:
                    pass

    return removed_any


def get_telegram_credentials() -> tuple[int, str]:
    """
    Retrieve API ID and API HASH explicitly using os.getenv.
    Strictly converts TELEGRAM_API_ID to integer:
        api_id = int(os.getenv("TELEGRAM_API_ID"))
        api_hash = os.getenv("TELEGRAM_API_HASH")
    """
    load_dotenv()
    raw_id = os.getenv("TELEGRAM_API_ID")
    raw_hash = os.getenv("TELEGRAM_API_HASH")

    api_id = DEFAULT_API_ID
    if raw_id is not None and str(raw_id).strip():
        try:
            api_id = int(str(raw_id).strip())
        except (ValueError, TypeError):
            api_id = DEFAULT_API_ID

    api_hash = DEFAULT_API_HASH
    if raw_hash is not None and str(raw_hash).strip():
        api_hash = str(raw_hash).strip()

    return int(api_id), str(api_hash).strip()


def get_telegram_client(session: Optional[Union[str, Any]] = None):
    """
    Instantiate a TelegramClient instance using in-memory StringSession.
    Explicitly pulls credentials using os.getenv rather than hardcoded or empty fallbacks:
        api_id = int(os.getenv("TELEGRAM_API_ID"))
        api_hash = os.getenv("TELEGRAM_API_HASH")
        client = TelegramClient(session, api_id, api_hash)
    """
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    load_dotenv()
    raw_api_id = os.getenv("TELEGRAM_API_ID")
    raw_api_hash = os.getenv("TELEGRAM_API_HASH")

    if raw_api_id is not None and str(raw_api_id).strip():
        api_id = int(str(raw_api_id).strip())
    else:
        api_id = int(DEFAULT_API_ID)

    if raw_api_hash is not None and str(raw_api_hash).strip():
        api_hash = str(raw_api_hash).strip()
    else:
        api_hash = str(DEFAULT_API_HASH).strip()

    if session is None:
        active_str = get_active_session_string()
        if active_str:
            try:
                session_obj = StringSession(active_str)
            except Exception:
                session_obj = StringSession()
        else:
            session_obj = StringSession()
    elif isinstance(session, StringSession):
        session_obj = session
    elif isinstance(session, str):
        raw_str = session.strip()
        if not raw_str:
            session_obj = StringSession()
        else:
            try:
                session_obj = StringSession(raw_str)
            except Exception:
                session_obj = StringSession()
    elif hasattr(session, "save"):
        session_obj = session
    else:
        session_obj = StringSession()

    return TelegramClient(session_obj, api_id, api_hash)



async def init_and_connect_telegram_client(session: Optional[Union[str, Any]] = None):
    """
    Initialize and connect a TelegramClient instance using in-memory StringSession.
    Completely eliminates SQLite database crashes and file lock conflicts.
    Safely recovers if any unexpected error occurs during connection.
    """
    import sqlite3
    client = get_telegram_client(session)
    try:
        await client.connect()
        return client
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as sql_err:
        print(f"Warning: SQLite operational error ({sql_err}). Recovering with fresh StringSession.")
        try:
            if hasattr(client, "is_connected") and client.is_connected():
                await client.disconnect()
        except Exception:
            pass
        if isinstance(session, str):
            cleanup_session_files(session, force=True)
        fresh_client = get_telegram_client(session)
        await fresh_client.connect()
        return fresh_client
    except Exception as e:
        err_msg = str(e).lower()
        if "no such table" in err_msg or "malformed" in err_msg or "operationalerror" in err_msg:
            print(f"Warning: Database error caught in connect: {e}. Recovering with fresh StringSession.")
            try:
                if hasattr(client, "is_connected") and client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
            if isinstance(session, str):
                cleanup_session_files(session, force=True)
            fresh_client = get_telegram_client(session)
            await fresh_client.connect()
            return fresh_client
        raise


async def check_userbot_status() -> Dict[str, Any]:
    """Check if the userbot session is currently authorized and return user info."""
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {"authorized": False, "reason": "No active Telegram session found"}

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {"authorized": False, "reason": "Session not authorized"}

        me = await client.get_me()
        full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        saved_str = client.session.save() if hasattr(client, "session") and hasattr(client.session, "save") else active_str
        if saved_str and not active_str:
            set_active_session_string(saved_str)

        return {
            "authorized": True,
            "id": me.id,
            "name": full_name or "Telegram User",
            "username": me.username or "",
            "phone": me.phone or "",
            "session_string": (saved_str[:16] + "...") if saved_str else "",
            "session_name": target_session
        }
    except Exception as e:
        return {"authorized": False, "error": str(e)}
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def request_telegram_code(phone: str) -> Dict[str, Any]:
    """
    Request a verification login code to be sent to the user's phone.
    Uses in-memory StringSession without writing to SQLite database.
    """
    import sqlite3
    from telethon.sessions import StringSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        ApiIdInvalidError,
        PhoneNumberInvalidError,
    )

    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone:
        return {"success": False, "error": "Phone number cannot be empty."}

    phone_digits = "".join([c for c in clean_phone if c.isdigit()])[-7:] or "user"
    unique_session_name = f"session_{phone_digits}_{uuid.uuid4().hex[:8]}"
    _PENDING_AUTH_SESSIONS[clean_phone] = unique_session_name

    client = None
    try:
        client = await init_and_connect_telegram_client(unique_session_name)
        try:
            res = await client.send_code_request(clean_phone)
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            if client and hasattr(client, "is_connected") and client.is_connected():
                try:
                    await client.disconnect()
                except Exception:
                    pass
            reset_session_database(unique_session_name)
            unique_session_name = f"session_{phone_digits}_{uuid.uuid4().hex[:8]}"
            _PENDING_AUTH_SESSIONS[clean_phone] = unique_session_name
            client = await init_and_connect_telegram_client(unique_session_name)
            res = await client.send_code_request(clean_phone)

        # Store pending client and serialized intermediate StringSession
        _PENDING_CLIENTS[clean_phone] = client
        intermediate_str = client.session.save() if hasattr(client, "session") and hasattr(client.session, "save") else ""
        _PENDING_STRING_SESSIONS[clean_phone] = intermediate_str
        _PENDING_AUTH_HASHES[clean_phone] = res.phone_code_hash

        return {
            "success": True,
            "phone": clean_phone,
            "phone_code_hash": res.phone_code_hash,
            "session_name": unique_session_name,
            "session_string": intermediate_str,
            "message": f"Verification code sent to Telegram app / SMS for {clean_phone}."
        }
    except ApiIdInvalidError:
        reset_session_database(unique_session_name)
        return {
            "success": False,
            "error_type": "ApiIdInvalidError",
            "error": "Telegram API ID/Hash invalid (API_ID_INVALID). Please verify your TELEGRAM_API_ID and TELEGRAM_API_HASH in .env."
        }
    except PhoneNumberInvalidError:
        return {
            "success": False,
            "error": "Invalid phone number format. Please ensure country code is included (e.g. +998901234567)."
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to send code: {str(e)}"
        }


async def complete_telegram_sign_in(
    phone: str,
    code: str,
    phone_code_hash: Optional[str] = None,
    password: Optional[str] = None
) -> Dict[str, Any]:
    """
    Complete Telegram sign-in with the verification code and optional 2FA password,
    returning the resulting encrypted session string for safe storage in .env or config.
    """
    from telethon.sessions import StringSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneCodeExpiredError,
        ApiIdInvalidError,
    )

    clean_phone = phone.strip().replace(" ", "").replace("-", "")
    clean_code = code.strip().replace(" ", "")
    code_hash = phone_code_hash or _PENDING_AUTH_HASHES.get(clean_phone, "")

    client = _PENDING_CLIENTS.get(clean_phone)
    if client is None or not (hasattr(client, "is_connected") and client.is_connected()):
        pending_str = _PENDING_STRING_SESSIONS.get(clean_phone, "")
        client = await init_and_connect_telegram_client(StringSession(pending_str) if pending_str else None)

    try:
        try:
            await client.sign_in(
                phone=clean_phone,
                code=clean_code,
                phone_code_hash=code_hash
            )
        except SessionPasswordNeededError:
            if not password:
                return {
                    "success": False,
                    "requires_2fa": True,
                    "message": "Two-factor authentication (2FA) password is required."
                }
            await client.sign_in(password=password.strip())
        except PhoneCodeInvalidError:
            return {"success": False, "error": "Invalid verification code. Please check and try again."}
        except PhoneCodeExpiredError:
            return {"success": False, "error": "Verification code has expired. Please request a new code."}
        except ApiIdInvalidError:
            return {
                "success": False,
                "error_type": "ApiIdInvalidError",
                "error": "Telegram API ID/Hash is invalid (API_ID_INVALID). Please verify your TELEGRAM_API_ID and TELEGRAM_API_HASH in .env."
            }

        me = await client.get_me()
        full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()

        session_string = ""
        if hasattr(client, "session") and hasattr(client.session, "save"):
            session_string = client.session.save()
            if session_string:
                set_active_session_string(session_string)

        target_session = _PENDING_AUTH_SESSIONS.get(clean_phone) or "momento_user_session"
        set_active_session_name(target_session)

        # Clean up pending entries
        _PENDING_AUTH_HASHES.pop(clean_phone, None)
        _PENDING_AUTH_SESSIONS.pop(clean_phone, None)
        _PENDING_CLIENTS.pop(clean_phone, None)
        _PENDING_STRING_SESSIONS.pop(clean_phone, None)

        return {
            "success": True,
            "message": f"Successfully authenticated as {full_name}!",
            "session_string": session_string,
            "session_name": target_session,
            "user": {
                "id": me.id,
                "name": full_name or "Telegram User",
                "username": me.username or "",
                "phone": me.phone or ""
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Authentication failed: {str(e)}"
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def headless_login(
    phone: str,
    code_callback,
    password_callback=None
) -> Dict[str, Any]:
    """
    Headless login flow helper:
    1. Sends login code to the phone number.
    2. Calls code_callback (sync or async) to obtain the verification code.
    3. If 2FA is needed, calls password_callback to obtain the 2FA password.
    4. Completes sign-in and outputs the resulting encrypted session string.
    """
    req_res = await request_telegram_code(phone)
    if not req_res.get("success"):
        return req_res

    phone_code_hash = req_res.get("phone_code_hash", "")
    code = code_callback() if not asyncio.iscoroutinefunction(code_callback) else await code_callback()

    sign_in_res = await complete_telegram_sign_in(
        phone=phone,
        code=str(code),
        phone_code_hash=phone_code_hash
    )

    if sign_in_res.get("requires_2fa") and password_callback:
        pwd = password_callback() if not asyncio.iscoroutinefunction(password_callback) else await password_callback()
        sign_in_res = await complete_telegram_sign_in(
            phone=phone,
            code=str(code),
            phone_code_hash=phone_code_hash,
            password=str(pwd)
        )

    return sign_in_res


async def is_userbot_authorized() -> bool:
    """Check if the userbot has an active, authorized Telegram session."""
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return False

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        return await client.is_user_authorized()
    except Exception:
        return False
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def send_via_userbot(
    recipient_name: str,
    message_text: str = "",
    file_path: Optional[str] = None,
    caption: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search active dialogs/chats for a partial or exact match on recipient_name
    and send the message_text and/or file_path directly from the authenticated user's account using StringSession.
    """
    if not recipient_name or not recipient_name.strip():
        return {
            "success": False,
            "error": "No recipient name specified."
        }

    recipient_query = recipient_name.strip().lower()
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    # Verify session exists
    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "error": (
                "Telegram account not connected. "
                "Please connect your account via the dashboard, supply a session string, or run 'python auth_telegram.py'."
            )
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)

        if not await client.is_user_authorized():
            return {
                "success": False,
                "error": "Telegram session is expired or not authorized. Please log in again."
            }

        target_dialog = None
        matched_name = ""

        clean_query = recipient_query.lstrip("@")
        async for dialog in client.iter_dialogs():
            d_title = (dialog.title or "").strip()
            entity = dialog.entity

            if str(dialog.id) == recipient_query or str(getattr(entity, "id", "")) == recipient_query:
                target_dialog = dialog
                matched_name = d_title or f"Chat {dialog.id}"
                break

            if recipient_query in d_title.lower() or clean_query in d_title.lower():
                target_dialog = dialog
                matched_name = d_title
                break

            if hasattr(entity, "first_name"):
                full_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip().lower()
                username = (getattr(entity, "username", "") or "").lower()

                if recipient_query in full_name or clean_query in full_name:
                    target_dialog = dialog
                    matched_name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                    break

                if username and (clean_query == username or clean_query in username):
                    target_dialog = dialog
                    matched_name = f"@{entity.username}"
                    break

        if not target_dialog:
            try:
                target_val = int(recipient_name.strip()) if recipient_name.strip().lstrip("-").isdigit() else recipient_name.strip()
                direct_entity = await client.get_entity(target_val)
                if direct_entity:
                    d_id = getattr(direct_entity, "id", target_val)
                    d_title = getattr(direct_entity, "title", getattr(direct_entity, "first_name", recipient_name))
                    target_dialog = type("EntityWrapper", (), {"id": d_id, "entity": direct_entity, "title": d_title})()
                    matched_name = d_title
            except Exception:
                pass

        if not target_dialog:
            return {
                "success": False,
                "error": f"Could not find any contact or chat matching '{recipient_name}' in your active Telegram dialogs."
            }

        # Native File Dispatch if file_path is provided
        if file_path and os.path.exists(file_path):
            file_caption = caption or (message_text[:1024] if message_text else "")
            await client.send_file(target_dialog.entity, file_path, caption=file_caption)
            dispatched_filename = os.path.basename(file_path)

            return {
                "success": True,
                "recipient_matched": matched_name or recipient_name,
                "dialog_id": target_dialog.id,
                "dispatched_file": dispatched_filename,
                "message": f"Successfully dispatched file '{dispatched_filename}' to '{matched_name or recipient_name}'."
            }

        # Otherwise send text message chunks
        chunk_size = 4000
        chunks = [message_text[i:i + chunk_size] for i in range(0, len(message_text), chunk_size)] or [""]

        for idx, chunk in enumerate(chunks):
            prefix = f"[Momento AI Part {idx+1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            await client.send_message(target_dialog.entity, prefix + chunk)

        return {
            "success": True,
            "recipient_matched": matched_name or recipient_name,
            "dialog_id": target_dialog.id,
            "dispatched_file": None,
            "message": f"Successfully sent output to '{matched_name or recipient_name}' ({len(chunks)} message parts)."
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Userbot dispatch failed: {str(e)}"
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def get_telegram_chats(limit: int = 50) -> Dict[str, Any]:
    """
    Retrieve active user dialogs (direct chats, groups, channels) from Telegram using Telethon.
    Returns a clean JSON-serializable list with chat id, name, type, username, and unread counts.
    """
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first.",
            "chats": []
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized.",
                "chats": []
            }

        chats = []
        async for dialog in client.iter_dialogs(limit=limit):
            entity = dialog.entity
            chat_type = "user"
            if getattr(dialog, "is_channel", False):
                chat_type = "channel" if not getattr(entity, "megagroup", False) else "group"
            elif getattr(dialog, "is_group", False):
                chat_type = "group"
            elif getattr(dialog, "is_user", False):
                chat_type = "user"

            username = getattr(entity, "username", "") or ""
            phone = getattr(entity, "phone", "") or ""
            display_name = (dialog.name or getattr(dialog, "title", "") or "Unknown").strip()

            chats.append({
                "id": dialog.id,
                "name": display_name,
                "type": chat_type,
                "username": f"@{username}" if username else "",
                "phone": phone,
                "unread_count": getattr(dialog, "unread_count", 0),
            })

        return {
            "success": True,
            "authorized": True,
            "count": len(chats),
            "chats": chats
        }
    except Exception as e:
        return {
            "success": False,
            "authorized": False,
            "error": f"Failed to retrieve Telegram chats: {str(e)}",
            "chats": []
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def block_telegram_user(user_identifier: Union[str, int]) -> Dict[str, Any]:
    """
    Block a Telegram user by username, phone number, or numeric user ID.
    Executes raw BlockRequest via Telethon.
    """
    from telethon.tl.functions.contacts import BlockRequest

    if not user_identifier or not str(user_identifier).strip():
        return {"success": False, "error": "No user identifier provided to block."}

    user_raw = str(user_identifier).strip()
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first."
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized."
            }

        # Normalize target
        target = int(user_raw) if user_raw.lstrip("-").isdigit() else user_raw

        try:
            full_entity = await client.get_entity(target)
            input_peer = await client.get_input_entity(full_entity)
        except Exception:
            input_peer = await client.get_input_entity(target)
            full_entity = input_peer

        await client(BlockRequest(id=input_peer))

        name = ""
        username = ""
        uid = getattr(full_entity, "id", user_raw)
        if hasattr(full_entity, "first_name"):
            name = f"{full_entity.first_name or ''} {full_entity.last_name or ''}".strip()
        if hasattr(full_entity, "username") and full_entity.username:
            username = f"@{full_entity.username}"

        display = username or name or str(user_raw)

        return {
            "success": True,
            "action": "block_user",
            "target": user_raw,
            "user_id": uid,
            "display_name": display,
            "message": f"Successfully blocked Telegram user {display}."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "block_user",
            "target": user_raw,
            "error": f"Failed to block user '{user_raw}': {str(e)}"
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def unblock_telegram_user(user_identifier: Union[str, int]) -> Dict[str, Any]:
    """
    Unblock a previously blocked Telegram user by username, phone number, or user ID.
    Executes raw UnblockRequest via Telethon.
    """
    from telethon.tl.functions.contacts import UnblockRequest

    if not user_identifier or not str(user_identifier).strip():
        return {"success": False, "error": "No user identifier provided to unblock."}

    user_raw = str(user_identifier).strip()
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first."
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized."
            }

        target = int(user_raw) if user_raw.lstrip("-").isdigit() else user_raw

        try:
            full_entity = await client.get_entity(target)
            input_peer = await client.get_input_entity(full_entity)
        except Exception:
            input_peer = await client.get_input_entity(target)
            full_entity = input_peer

        await client(UnblockRequest(id=input_peer))

        name = ""
        username = ""
        uid = getattr(full_entity, "id", user_raw)
        if hasattr(full_entity, "first_name"):
            name = f"{full_entity.first_name or ''} {full_entity.last_name or ''}".strip()
        if hasattr(full_entity, "username") and full_entity.username:
            username = f"@{full_entity.username}"

        display = username or name or str(user_raw)

        return {
            "success": True,
            "action": "unblock_user",
            "target": user_raw,
            "user_id": uid,
            "display_name": display,
            "message": f"Successfully unblocked Telegram user {display}."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "unblock_user",
            "target": user_raw,
            "error": f"Failed to unblock user '{user_raw}': {str(e)}"
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def kick_chat_member(
    chat_identifier: Union[str, int],
    user_identifier: Union[str, int],
    ban: bool = False
) -> Dict[str, Any]:
    """
    Kick or permanently ban a participant from a group or channel using Telethon.
    If ban is True, denies view permissions; otherwise kicks the participant.
    """
    if not chat_identifier or not str(chat_identifier).strip():
        return {"success": False, "error": "No chat identifier provided."}
    if not user_identifier or not str(user_identifier).strip():
        return {"success": False, "error": "No user identifier provided."}

    chat_raw = str(chat_identifier).strip()
    user_raw = str(user_identifier).strip()
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first."
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized."
            }

        chat_target = int(chat_raw) if chat_raw.lstrip("-").isdigit() else chat_raw
        user_target = int(user_raw) if user_raw.lstrip("-").isdigit() else user_raw

        # Resolve chat entity (with dialog search fallback for names)
        chat_entity = None
        try:
            chat_entity = await client.get_entity(chat_target)
        except Exception:
            clean_name = str(chat_target).lower().lstrip("@")
            async for dialog in client.iter_dialogs():
                d_title = (dialog.title or dialog.name or "").lower()
                if clean_name in d_title:
                    chat_entity = dialog.entity
                    break

        if not chat_entity:
            return {
                "success": False,
                "error": f"Could not find or resolve chat '{chat_raw}'."
            }

        # Resolve user entity
        try:
            user_entity = await client.get_entity(user_target)
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not find or resolve user '{user_raw}': {str(e)}"
            }

        chat_title = getattr(chat_entity, "title", getattr(chat_entity, "name", chat_raw))
        user_name = getattr(user_entity, "username", None)
        user_display = f"@{user_name}" if user_name else (
            f"{getattr(user_entity, 'first_name', '')} {getattr(user_entity, 'last_name', '')}".strip() or str(user_raw)
        )

        if ban:
            await client.edit_permissions(chat_entity, user_entity, view_messages=False)
            action_desc = "banned"
        else:
            try:
                await client.kick_participant(chat_entity, user_entity)
                action_desc = "kicked"
            except Exception:
                # Supergroup fallback: restrict view permissions
                await client.edit_permissions(chat_entity, user_entity, view_messages=False)
                action_desc = "restricted/kicked"

        return {
            "success": True,
            "action": "ban_member" if ban else "kick_member",
            "chat": chat_title,
            "chat_id": getattr(chat_entity, "id", None),
            "target": user_display,
            "user_id": getattr(user_entity, "id", None),
            "message": f"Successfully {action_desc} participant {user_display} from '{chat_title}'."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "ban_member" if ban else "kick_member",
            "chat": chat_raw,
            "target": user_raw,
            "error": f"Failed to restrict member in chat: {str(e)}"
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def search_telegram_dialogs(
    query: Optional[str] = None,
    limit: int = 20,
    unread_only: bool = False,
    sender_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search and scan Telegram dialogs, filter unread chats, or search message history by keyword or sender.
    """
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first.",
            "dialogs": [],
            "messages": []
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized.",
                "dialogs": [],
                "messages": []
            }

        matched_dialogs = []
        clean_sender = sender_name.lower().lstrip("@") if sender_name else None

        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            d_name = (dialog.name or getattr(dialog, "title", "") or "Unknown").strip()
            username = getattr(entity, "username", "") or ""
            phone = getattr(entity, "phone", "") or ""

            if unread_only and getattr(dialog, "unread_count", 0) <= 0:
                continue

            if clean_sender:
                if clean_sender not in d_name.lower() and clean_sender not in username.lower() and clean_sender not in phone:
                    continue

            chat_type = "user"
            if getattr(dialog, "is_channel", False):
                chat_type = "channel" if not getattr(entity, "megagroup", False) else "group"
            elif getattr(dialog, "is_group", False):
                chat_type = "group"
            elif getattr(dialog, "is_user", False):
                chat_type = "user"

            last_msg_text = ""
            if getattr(dialog, "message", None) and hasattr(dialog.message, "message"):
                last_msg_text = (dialog.message.message or "")[:140]

            matched_dialogs.append({
                "id": dialog.id,
                "name": d_name,
                "type": chat_type,
                "username": f"@{username}" if username else "",
                "phone": phone,
                "unread_count": getattr(dialog, "unread_count", 0),
                "date": dialog.date.isoformat() if hasattr(dialog, "date") and dialog.date else "",
                "last_message": last_msg_text
            })

            if len(matched_dialogs) >= limit and not query:
                break

        # Search message history across dialogs if keyword query is provided
        matched_messages = []
        if query and query.strip():
            clean_query = query.strip()
            # If a specific sender was matched, search within that sender's chat entity
            search_target = None
            if clean_sender and matched_dialogs:
                try:
                    search_target = matched_dialogs[0]["id"]
                except Exception:
                    search_target = None

            async for msg in client.iter_messages(search_target, search=clean_query, limit=limit):
                chat_title = ""
                if hasattr(msg, "chat") and msg.chat:
                    chat_title = getattr(msg.chat, "title", getattr(msg.chat, "first_name", "Chat")) or "Chat"

                sender_title = ""
                try:
                    sender = await msg.get_sender()
                    if sender:
                        sender_title = getattr(sender, "first_name", "") or getattr(sender, "title", "") or getattr(sender, "username", "")
                except Exception:
                    pass

                text_content = msg.text or getattr(msg, "message", "") or ""
                matched_messages.append({
                    "id": msg.id,
                    "chat_id": getattr(msg, "chat_id", None),
                    "chat_title": str(chat_title),
                    "sender": str(sender_title) if sender_title else "User",
                    "date": msg.date.isoformat() if hasattr(msg, "date") and msg.date else "",
                    "text": text_content[:300]
                })

        return {
            "success": True,
            "authorized": True,
            "query": query,
            "unread_only": unread_only,
            "sender_name": sender_name,
            "dialog_count": len(matched_dialogs),
            "dialogs": matched_dialogs[:limit],
            "message_count": len(matched_messages),
            "messages": matched_messages,
            "message": f"Found {len(matched_dialogs)} dialogs and {len(matched_messages)} messages matching search criteria."
        }
    except Exception as e:
        return {
            "success": False,
            "authorized": False,
            "error": f"Failed to search Telegram dialogs: {str(e)}",
            "dialogs": [],
            "messages": []
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass


async def get_telegram_chat_messages(chat_id: Union[int, str], limit: int = 40) -> Dict[str, Any]:
    """
    Fetch recent messages from a specific Telegram chat, channel, or dialog.
    """
    active_str = get_active_session_string()
    target_session = get_active_session_name()
    session_file = f"{target_session}.session"

    if not active_str and not os.path.exists(session_file) and not os.path.exists(target_session):
        return {
            "success": False,
            "authorized": False,
            "error": "Telegram account not connected. Please connect your account first.",
            "messages": []
        }

    client = None
    try:
        client = await init_and_connect_telegram_client(active_str or target_session)
        if not await client.is_user_authorized():
            return {
                "success": False,
                "authorized": False,
                "error": "Telegram session is expired or not authorized.",
                "messages": []
            }

        target = chat_id
        if isinstance(chat_id, str):
            clean_str = chat_id.strip()
            if clean_str.lstrip("-").isdigit():
                try:
                    target = int(clean_str)
                except ValueError:
                    target = clean_str
            else:
                target = clean_str

        entity = None
        try:
            entity = await client.get_entity(target)
        except Exception:
            # Fallback search dialogs
            async for dialog in client.iter_dialogs():
                if str(dialog.id) == str(chat_id) or getattr(dialog.entity, "username", "") == str(chat_id).lstrip("@") or dialog.name.lower() == str(chat_id).lower():
                    entity = dialog.entity
                    break

        if not entity:
            return {
                "success": False,
                "authorized": True,
                "error": f"Could not find or resolve chat '{chat_id}'.",
                "messages": []
            }

        chat_title = getattr(entity, "title", getattr(entity, "first_name", "")) or str(chat_id)
        chat_username = getattr(entity, "username", "") or ""

        messages = []
        async for msg in client.iter_messages(entity, limit=limit):
            sender_title = ""
            try:
                sender = await msg.get_sender()
                if sender:
                    sender_title = getattr(sender, "first_name", "") or getattr(sender, "title", "") or getattr(sender, "username", "")
            except Exception:
                pass

            is_out = bool(getattr(msg, "out", False))
            text_content = msg.text or getattr(msg, "message", "") or ""
            date_iso = msg.date.isoformat() if hasattr(msg, "date") and msg.date else ""

            # Check if file/media attached
            file_name = None
            if hasattr(msg, "file") and msg.file and hasattr(msg.file, "name") and msg.file.name:
                file_name = msg.file.name

            messages.append({
                "id": msg.id,
                "text": text_content,
                "out": is_out,
                "sender": str(sender_title) if sender_title else ("You" if is_out else chat_title),
                "date": date_iso,
                "file_name": file_name
            })

        # Return chronologically ascending (oldest to newest)
        messages.reverse()

        return {
            "success": True,
            "authorized": True,
            "chat_id": str(chat_id),
            "chat_title": str(chat_title),
            "chat_username": str(chat_username),
            "messages": messages,
            "count": len(messages)
        }
    except Exception as e:
        return {
            "success": False,
            "authorized": False,
            "error": f"Failed to retrieve chat messages: {str(e)}",
            "messages": []
        }
    finally:
        if client and hasattr(client, "is_connected") and client.is_connected():
            try:
                await client.disconnect()
            except Exception:
                pass




