"""
Unit tests for Telethon userbot service in services/telegram_userbot.py.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from services.telegram_userbot import (
    send_via_userbot,
    get_telegram_credentials,
    get_telegram_client,
    request_telegram_code,
    check_userbot_status,
    DEFAULT_API_ID,
    DEFAULT_API_HASH
)


def test_built_in_credentials_fallback():
    with patch.dict("os.environ", {"TELEGRAM_API_ID": "", "TELEGRAM_API_HASH": ""}):
        api_id, api_hash = get_telegram_credentials()
        assert api_id == DEFAULT_API_ID
        assert api_hash == DEFAULT_API_HASH


@pytest.mark.anyio
async def test_send_via_userbot_empty_recipient():
    res = await send_via_userbot("", "Hello")
    assert res["success"] is False
    assert "No recipient name specified" in res["error"]


@pytest.mark.anyio
async def test_send_via_userbot_missing_session():
    with patch("os.path.exists", return_value=False), \
         patch("services.telegram_userbot.get_active_session_string", return_value=""):
        res = await send_via_userbot("Animatic", "Hello")
        assert res["success"] is False
        assert "not connected" in res["error"].lower()
        assert "auth_telegram.py" in res["error"]



@pytest.mark.anyio
async def test_request_telegram_code_empty_phone():
    res = await request_telegram_code("")
    assert res["success"] is False
    assert "Phone number cannot be empty" in res["error"]


@pytest.mark.anyio
async def test_check_userbot_status_unauthorized():
    with patch("os.path.exists", return_value=False):
        res = await check_userbot_status()
        assert res["authorized"] is False


@pytest.mark.anyio
async def test_strict_integer_casting_for_api_id(tmp_path):
    with patch.dict("os.environ", {"TELEGRAM_API_ID": " 2040 ", "TELEGRAM_API_HASH": " test_hash "}):
        api_id, api_hash = get_telegram_credentials()
        assert isinstance(api_id, int)
        assert api_id == 2040
        assert api_hash == "test_hash"

        # Verify client constructor receives integer
        session_path = str(tmp_path / "test_strict_int_session")
        client = get_telegram_client(session_path)
        assert isinstance(client.api_id, int)
        assert client.api_id == 2040




def test_cleanup_session_files_empty_and_corrupted(tmp_path):
    from services.telegram_userbot import cleanup_session_files

    test_session_base = str(tmp_path / "temp_session")
    session_file = f"{test_session_base}.session"

    # 1. Test 0-byte file removal
    with open(session_file, "wb") as f:
        pass
    assert os.path.exists(session_file)
    removed = cleanup_session_files(session_name=test_session_base, force=False)
    assert removed is True
    assert not os.path.exists(session_file)

    # 2. Test corrupted non-sqlite file removal
    with open(session_file, "w") as f:
        f.write("corrupted non sqlite bytes content")
    assert os.path.exists(session_file)
    removed = cleanup_session_files(session_name=test_session_base, force=False)
    assert removed is True
    assert not os.path.exists(session_file)


@pytest.mark.anyio
async def test_request_telegram_code_api_id_invalid_caught():
    from telethon.errors import ApiIdInvalidError

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()
    mock_client.send_code_request = AsyncMock(side_effect=ApiIdInvalidError(request=None))

    with patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client), \
         patch("services.telegram_userbot.reset_session_database") as mock_reset:
        res = await request_telegram_code("+998901234567")
        assert res["success"] is False
        assert res["error_type"] == "ApiIdInvalidError"
        assert "API_ID_INVALID" in res["error"]
        assert mock_reset.called


@pytest.mark.anyio
async def test_init_and_connect_telegram_client_sqlite_error_auto_recovery():
    import sqlite3
    from services.telegram_userbot import init_and_connect_telegram_client

    mock_client_bad = AsyncMock()
    mock_client_bad.connect = AsyncMock(side_effect=sqlite3.OperationalError("no such table: update_state"))
    mock_client_bad.is_connected = lambda: True
    mock_client_bad.disconnect = AsyncMock()

    mock_client_good = AsyncMock()
    mock_client_good.connect = AsyncMock()
    mock_client_good.is_connected = lambda: True

    with patch("services.telegram_userbot.get_telegram_client", side_effect=[mock_client_bad, mock_client_good]) as mock_get_client, \
         patch("services.telegram_userbot.cleanup_session_files") as mock_cleanup:
        client = await init_and_connect_telegram_client("test_sqlite_error_session")
        assert client == mock_client_good
        assert mock_cleanup.called
        assert mock_client_bad.connect.called
        assert mock_client_good.connect.called


@pytest.mark.anyio
async def test_request_telegram_code_recovers_from_sqlite_update_state_error():
    import sqlite3

    mock_client_bad = AsyncMock()
    mock_client_bad.connect = AsyncMock()
    mock_client_bad.is_connected = lambda: True
    mock_client_bad.disconnect = AsyncMock()
    mock_client_bad.send_code_request = AsyncMock(side_effect=sqlite3.OperationalError("no such table: update_state"))

    mock_res = AsyncMock()
    mock_res.phone_code_hash = "auto_recovered_hash_999"
    mock_client_good = AsyncMock()
    mock_client_good.connect = AsyncMock()
    mock_client_good.is_connected = lambda: True
    mock_client_good.send_code_request = AsyncMock(return_value=mock_res)

    with patch("services.telegram_userbot.init_and_connect_telegram_client", side_effect=[mock_client_bad, mock_client_good]), \
         patch("services.telegram_userbot.reset_session_database") as mock_reset, \
         patch("os.path.exists", return_value=False):
        res = await request_telegram_code("+998901234567")
        assert res["success"] is True
        assert res["phone_code_hash"] == "auto_recovered_hash_999"
        assert mock_reset.called


def test_delete_all_session_files(tmp_path):
    from pathlib import Path
    from services.telegram_userbot import delete_all_session_files

    # Create dummy session files in tmp_path
    f1 = tmp_path / "dummy_1.session"
    f2 = tmp_path / "dummy_1.session-journal"
    f3 = tmp_path / "dummy_2.session"
    f4 = tmp_path / "not_a_session.txt"
    for f in (f1, f2, f3, f4):
        f.write_text("sample")

    deleted = delete_all_session_files(workspace_dir=tmp_path)
    assert len(deleted) == 3
    assert not f1.exists()
    assert not f2.exists()
    assert not f3.exists()
    assert f4.exists()


def test_reset_session_database(tmp_path):
    import sqlite3
    from pathlib import Path
    from services.telegram_userbot import reset_session_database

    sess_base = str(tmp_path / "reset_target")
    db_file = Path(f"{sess_base}.session")
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE dummy_tbl (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO dummy_tbl VALUES (1)")
    conn.commit()
    conn.close()
    assert db_file.exists()

    reset_session_database(sess_base)
    assert not db_file.exists()


@pytest.mark.anyio
async def test_request_telegram_code_generates_isolated_session_path():
    mock_res = AsyncMock()
    mock_res.phone_code_hash = "isolated_hash_777"
    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.is_connected = lambda: True
    mock_client.send_code_request = AsyncMock(return_value=mock_res)

    with patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client) as mock_init:
        res = await request_telegram_code("+998901234567")
        assert res["success"] is True
        assert "session_name" in res
        assert res["session_name"].startswith("session_1234567_")
        mock_init.assert_called_once_with(res["session_name"])


@pytest.mark.anyio
async def test_string_session_client_instantiation():
    from telethon.sessions import StringSession
    from services.telegram_userbot import get_telegram_client

    client = get_telegram_client()
    assert isinstance(client.session, StringSession)
    # Also verify non-base64 string falls back gracefully to in-memory StringSession
    client_legacy = get_telegram_client("legacy_session_name")
    assert isinstance(client_legacy.session, StringSession)



def test_session_string_persistence(tmp_path):
    from pathlib import Path
    from services.telegram_userbot import (
        get_active_session_string,
        set_active_session_string,
        clear_active_session_string,
    )

    test_str = "1ApW_test_session_string_data_xyz123=="
    fake_file = tmp_path / ".session_string"
    fake_env = tmp_path / ".env"
    fake_env.write_text("SOME_VAR=1\n", encoding="utf-8")

    with patch("services.telegram_userbot._SESSION_STRING_FILE", fake_file), \
         patch("services.telegram_userbot.Path", side_effect=lambda p: fake_env if p == ".env" else Path(p)), \
         patch.dict("os.environ", {}, clear=False):
        set_active_session_string(test_str)
        assert get_active_session_string() == test_str

        clear_active_session_string(remove_from_env=True)
        assert get_active_session_string() == ""



@pytest.mark.anyio
async def test_complete_telegram_sign_in_returns_session_string():
    from services.telegram_userbot import complete_telegram_sign_in

    mock_me = AsyncMock()
    mock_me.id = 123456
    mock_me.first_name = "Alice"
    mock_me.last_name = "Wonderland"
    mock_me.username = "alicew"
    mock_me.phone = "+15551234567"

    mock_client = AsyncMock()
    mock_client.connect = AsyncMock()
    mock_client.is_connected = lambda: True
    mock_client.sign_in = AsyncMock()
    mock_client.get_me = AsyncMock(return_value=mock_me)
    mock_client.disconnect = AsyncMock()

    mock_session = AsyncMock()
    mock_session.save = lambda: "1ApW_mock_encrypted_session_string=="
    mock_client.session = mock_session

    with patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client), \
         patch("services.telegram_userbot.set_active_session_string") as mock_set_active:
        res = await complete_telegram_sign_in("+15551234567", "12345", phone_code_hash="mock_hash")
        assert res["success"] is True
        assert res["session_string"] == "1ApW_mock_encrypted_session_string=="
        assert res["user"]["name"] == "Alice Wonderland"
        mock_set_active.assert_called_once_with("1ApW_mock_encrypted_session_string==")


@pytest.mark.anyio
async def test_headless_login_flow():
    from services.telegram_userbot import headless_login

    mock_req_res = {
        "success": True,
        "phone": "+15551234567",
        "phone_code_hash": "headless_hash_123"
    }
    mock_sign_in_res = {
        "success": True,
        "session_string": "1ApW_headless_session_string==",
        "user": {"name": "Alice"}
    }

    with patch("services.telegram_userbot.request_telegram_code", return_value=mock_req_res), \
         patch("services.telegram_userbot.complete_telegram_sign_in", return_value=mock_sign_in_res):
        res = await headless_login("+15551234567", code_callback=lambda: "54321")
        assert res["success"] is True
        assert res["session_string"] == "1ApW_headless_session_string=="


@pytest.mark.anyio
async def test_get_telegram_chats_unconnected():
    from services.telegram_userbot import get_telegram_chats

    with patch("services.telegram_userbot.get_active_session_string", return_value=""), \
         patch("services.telegram_userbot.get_active_session_name", return_value="nonexistent_sess"), \
         patch("os.path.exists", return_value=False):
        res = await get_telegram_chats()
        assert res["success"] is False
        assert res["authorized"] is False
        assert "not connected" in res["error"].lower()
        assert res["chats"] == []


@pytest.mark.anyio
async def test_get_telegram_chats_unauthorized():
    from services.telegram_userbot import get_telegram_chats

    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=False)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_string"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await get_telegram_chats()
        assert res["success"] is False
        assert res["authorized"] is False
        assert "not authorized" in res["error"].lower()
        assert res["chats"] == []
        mock_client.disconnect.assert_called_once()


@pytest.mark.anyio
async def test_get_telegram_chats_success_with_dialog_types():
    from services.telegram_userbot import get_telegram_chats
    from unittest.mock import MagicMock

    # 1. User Dialog
    user_entity = MagicMock()
    user_entity.username = "animatic_bot"
    user_entity.phone = "15550001"
    user_dialog = MagicMock()
    user_dialog.id = 101
    user_dialog.name = "Animatic"
    user_dialog.is_user = True
    user_dialog.is_group = False
    user_dialog.is_channel = False
    user_dialog.unread_count = 3
    user_dialog.entity = user_entity

    # 2. Group Dialog
    group_entity = MagicMock()
    group_entity.username = "project_momento"
    group_entity.phone = None
    group_dialog = MagicMock()
    group_dialog.id = -202
    group_dialog.name = "Momento Devs"
    group_dialog.is_user = False
    group_dialog.is_group = True
    group_dialog.is_channel = False
    group_dialog.unread_count = 0
    group_dialog.entity = group_entity

    # 3. Channel Dialog
    chan_entity = MagicMock()
    chan_entity.username = "momento_news"
    chan_entity.phone = None
    chan_entity.megagroup = False
    chan_dialog = MagicMock()
    chan_dialog.id = -100303
    chan_dialog.name = "Momento Announcements"
    chan_dialog.is_user = False
    chan_dialog.is_group = False
    chan_dialog.is_channel = True
    chan_dialog.unread_count = 5
    chan_dialog.entity = chan_entity

    dialog_list = [user_dialog, group_dialog, chan_dialog]

    async def mock_iter_dialogs(limit=50):
        for d in dialog_list:
            yield d

    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()
    mock_client.iter_dialogs = mock_iter_dialogs

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_string"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await get_telegram_chats(limit=10)
        assert res["success"] is True
        assert res["authorized"] is True
        assert res["count"] == 3
        chats = res["chats"]
        assert len(chats) == 3

        # User check
        assert chats[0]["id"] == 101
        assert chats[0]["name"] == "Animatic"
        assert chats[0]["type"] == "user"
        assert chats[0]["username"] == "@animatic_bot"
        assert chats[0]["phone"] == "15550001"
        assert chats[0]["unread_count"] == 3

        # Group check
        assert chats[1]["id"] == -202
        assert chats[1]["name"] == "Momento Devs"
        assert chats[1]["type"] == "group"
        assert chats[1]["username"] == "@project_momento"

        # Channel check
        assert chats[2]["id"] == -100303
        assert chats[2]["name"] == "Momento Announcements"
        assert chats[2]["type"] == "channel"
        assert chats[2]["username"] == "@momento_news"
        assert chats[2]["unread_count"] == 5

        mock_client.disconnect.assert_called_once()


@pytest.mark.anyio
async def test_send_via_userbot_with_file_path(tmp_path):
    from services.telegram_userbot import send_via_userbot
    from unittest.mock import MagicMock

    test_file = tmp_path / "test_doc.docx"
    test_file.write_bytes(b"PK000fake_docx_data")

    mock_dialog = MagicMock()
    mock_dialog.id = 555
    mock_dialog.title = "Animatic"
    mock_dialog.entity = MagicMock()

    async def mock_iter_dialogs():
        yield mock_dialog

    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()
    mock_client.iter_dialogs = mock_iter_dialogs
    mock_client.send_file = AsyncMock()

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_string"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await send_via_userbot(
            recipient_name="Animatic",
            file_path=str(test_file),
            caption="Momento Test Caption"
        )
        assert res["success"] is True
        assert res["recipient_matched"] == "Animatic"
        assert res["dispatched_file"] == "test_doc.docx"
        mock_client.send_file.assert_called_once_with(
            mock_dialog.entity,
            str(test_file),
            caption="Momento Test Caption"
        )


@pytest.mark.anyio
async def test_is_userbot_authorized_states():
    from services.telegram_userbot import is_userbot_authorized

    # 1. No session
    with patch("services.telegram_userbot.get_active_session_string", return_value=""), \
         patch("services.telegram_userbot.get_active_session_name", return_value="nonexistent_sess"), \
         patch("os.path.exists", return_value=False):
        assert await is_userbot_authorized() is False

    # 2. Authorized client
    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_string"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        assert await is_userbot_authorized() is True


@pytest.mark.anyio
async def test_block_telegram_user():
    from services.telegram_userbot import block_telegram_user
    from unittest.mock import MagicMock

    # Empty user identifier
    res_empty = await block_telegram_user("")
    assert res_empty["success"] is False
    assert "No user identifier" in res_empty["error"]

    # Successful block
    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    mock_entity = MagicMock()
    mock_entity.id = 98765
    mock_entity.first_name = "Bad"
    mock_entity.last_name = "Actor"
    mock_entity.username = "badactor"
    mock_client.get_entity = AsyncMock(return_value=mock_entity)
    mock_client.get_input_entity = AsyncMock(return_value=MagicMock())
    mock_client.__call__ = AsyncMock()

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_str"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await block_telegram_user("@badactor")
        assert res["success"] is True
        assert res["action"] == "block_user"
        assert res["user_id"] == 98765
        assert "@badactor" in res["display_name"]
        mock_client.assert_awaited_once()


@pytest.mark.anyio
async def test_unblock_telegram_user():
    from services.telegram_userbot import unblock_telegram_user
    from unittest.mock import MagicMock

    # Empty identifier
    res_empty = await unblock_telegram_user("")
    assert res_empty["success"] is False

    # Successful unblock
    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    mock_entity = MagicMock()
    mock_entity.id = 54321
    mock_entity.first_name = "Good"
    mock_entity.last_name = "User"
    mock_entity.username = "gooduser"
    mock_client.get_entity = AsyncMock(return_value=mock_entity)
    mock_client.get_input_entity = AsyncMock(return_value=MagicMock())

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_str"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await unblock_telegram_user("@gooduser")
        assert res["success"] is True
        assert res["action"] == "unblock_user"
        assert res["user_id"] == 54321
        mock_client.assert_awaited_once()


@pytest.mark.anyio
async def test_kick_chat_member():
    from services.telegram_userbot import kick_chat_member
    from unittest.mock import MagicMock

    # Empty inputs
    res_err1 = await kick_chat_member("", "@spammer")
    assert res_err1["success"] is False
    res_err2 = await kick_chat_member("MyGroup", "")
    assert res_err2["success"] is False

    # Mock client setup
    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    mock_chat = MagicMock()
    mock_chat.id = -100123
    mock_chat.title = "Developers Community"

    mock_user = MagicMock()
    mock_user.id = 9999
    mock_user.username = "troll"
    mock_user.first_name = "Troll"

    mock_client.get_entity = AsyncMock(side_effect=[mock_chat, mock_user, mock_chat, mock_user])
    mock_client.kick_participant = AsyncMock()
    mock_client.edit_permissions = AsyncMock()

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_str"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        # Kick mode
        res_kick = await kick_chat_member("Developers Community", "@troll", ban=False)
        assert res_kick["success"] is True
        assert res_kick["action"] == "kick_member"
        assert "Developers Community" in res_kick["message"]
        mock_client.kick_participant.assert_called_once()

        # Ban mode
        res_ban = await kick_chat_member("Developers Community", "@troll", ban=True)
        assert res_ban["success"] is True
        assert res_ban["action"] == "ban_member"
        assert "Developers Community" in res_ban["message"]
        mock_client.edit_permissions.assert_called_once()


@pytest.mark.anyio
async def test_search_telegram_dialogs():
    from services.telegram_userbot import search_telegram_dialogs
    from unittest.mock import MagicMock

    mock_client = AsyncMock()
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.is_connected = lambda: True
    mock_client.disconnect = AsyncMock()

    # Create mock dialogs
    mock_d1 = MagicMock()
    mock_d1.id = 111
    mock_d1.name = "Work Chat"
    mock_d1.is_channel = False
    mock_d1.is_group = True
    mock_d1.is_user = False
    mock_d1.unread_count = 3
    mock_d1.entity = MagicMock(username="workchat", phone="")
    mock_d1.date = None
    mock_d1.message = MagicMock(message="Please check the invoice")

    mock_d2 = MagicMock()
    mock_d2.id = 222
    mock_d2.name = "News Channel"
    mock_d2.is_channel = True
    mock_d2.is_group = False
    mock_d2.is_user = False
    mock_d2.unread_count = 0
    mock_d2.entity = MagicMock(username="news", phone="", megagroup=False)
    mock_d2.date = None
    mock_d2.message = MagicMock(message="Latest updates")

    async def mock_iter_dialogs(limit=None):
        for d in [mock_d1, mock_d2]:
            yield d

    mock_client.iter_dialogs = mock_iter_dialogs

    # Create mock message
    mock_msg = MagicMock()
    mock_msg.id = 555
    mock_msg.chat_id = 111
    mock_msg.chat = MagicMock(title="Work Chat")
    mock_msg.text = "Here is the invoice for project Alpha"
    mock_msg.message = "Here is the invoice for project Alpha"
    mock_msg.date = None
    mock_msg.get_sender = AsyncMock(return_value=MagicMock(first_name="Bob", title="", username="bob"))

    async def mock_iter_messages(entity=None, search=None, limit=None):
        yield mock_msg

    mock_client.iter_messages = mock_iter_messages

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_str"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        # Test unread only + query
        res = await search_telegram_dialogs(query="invoice", unread_only=True)
        assert res["success"] is True
        assert res["unread_only"] is True
        # Only mock_d1 had unread_count > 0
        assert res["dialog_count"] == 1
        assert res["dialogs"][0]["name"] == "Work Chat"
        # Message matched
        assert res["message_count"] == 1
        assert "invoice" in res["messages"][0]["text"]


@pytest.mark.anyio
async def test_get_telegram_chat_messages():
    from services.telegram_userbot import get_telegram_chat_messages

    # Unauthenticated state
    with patch("services.telegram_userbot.get_active_session_string", return_value=""), \
         patch("services.telegram_userbot.get_active_session_name", return_value="nonexistent_sess_123"):
        res = await get_telegram_chat_messages("12345")
        assert res["success"] is False
        assert res["authorized"] is False

    # Authenticated state with message stream
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.disconnect = AsyncMock()

    mock_entity = MagicMock()
    mock_entity.id = 9999
    mock_entity.title = "Vip Mobile"
    mock_entity.username = "vip_mobile"
    mock_client.get_entity = AsyncMock(return_value=mock_entity)

    msg1 = MagicMock()
    msg1.id = 1
    msg1.out = False
    msg1.text = "Hello from customer"
    msg1.date = None
    msg1.file = None
    msg1.get_sender = AsyncMock(return_value=MagicMock(first_name="Customer", title="", username="cust"))

    msg2 = MagicMock()
    msg2.id = 2
    msg2.out = True
    msg2.text = "Here is your document"
    msg2.date = None
    msg2.file = MagicMock()
    msg2.file.name = "report.docx"
    msg2.get_sender = AsyncMock(return_value=MagicMock(first_name="Me", title="", username="me"))

    async def mock_iter_msgs(entity, limit=None):
        for m in [msg2, msg1]:  # telethon returns newest first
            yield m

    mock_client.iter_messages = mock_iter_msgs

    with patch("services.telegram_userbot.get_active_session_string", return_value="fake_str"), \
         patch("services.telegram_userbot.init_and_connect_telegram_client", return_value=mock_client):
        res = await get_telegram_chat_messages("9999", limit=10)
        assert res["success"] is True
        assert res["chat_title"] == "Vip Mobile"
        assert res["count"] == 2
        # After reverse (chronological ascending): msg1 then msg2
        assert res["messages"][0]["id"] == 1
        assert res["messages"][0]["out"] is False
        assert res["messages"][1]["id"] == 2
        assert res["messages"][1]["out"] is True
        assert res["messages"][1]["file_name"] == "report.docx"







