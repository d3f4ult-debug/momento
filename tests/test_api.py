"""
Integration and endpoint tests for Momento FastAPI application.
"""

import io
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient
from docx import Document
import pandas as pd

from main import app

client = TestClient(app)


def test_index_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Momento" in response.text
    assert "Momento Nexus v2.5" in response.text
    assert "Momento Apex v3.1" in response.text
    assert "Momento Omni v3.8" in response.text


@patch("main.execute_gemini_transformation")
def test_process_with_selected_model(mock_gemini):
    mock_gemini.return_value = "Result generated with Pro model."
    data = {
        "prompt": "Deep analysis of strategy",
        "model": "gemini-2.5-pro",
        "custom_api_key": "mock_key"
    }
    response = client.post("/api/process", data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["model"] == "gemini-2.5-pro"
    assert res["model_name"] == "Momento Apex v3.1"
    assert mock_gemini.called
    assert mock_gemini.call_args.kwargs["model_name"] == "gemini-2.5-pro"


@patch("main.execute_gemini_transformation")
def test_process_with_proprietary_model_identifiers(mock_gemini):
    mock_gemini.return_value = "Result from proprietary Omni engine."
    data = {
        "prompt": "Autonomous workflow planning",
        "model": "momento-omni-3.8",
        "custom_api_key": "mock_key"
    }
    response = client.post("/api/process", data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["model"] == "momento-omni-3.8"
    assert res["model_name"] == "Momento Omni v3.8"
    assert mock_gemini.called
    # Verifies mapped to gemini-3.8-flash under the hood
    assert mock_gemini.call_args.kwargs["model_name"] == "gemini-3.8-flash"


def test_session_reset_endpoint():
    response = client.post("/api/session/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["agent"] == "Momento"
    assert "integrations" in data


def test_google_docs_placeholder_export():
    with patch("services.google_workspace.get_google_credentials", return_value=None):
        response = client.post(
            "/api/export/docs",
            data={"title": "Q3 Executive Summary", "content": "Sample parsed text"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Google Docs"
        assert data["status"] == "ready_for_credentials"
        assert "mock_url" in data


def test_google_sheets_placeholder_export():
    with patch("services.google_workspace.get_google_credentials", return_value=None):
        response = client.post(
            "/api/export/sheets",
            data={"title": "Financial Report", "content": "Metric,Value\nRevenue,1000"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Google Sheets"
        assert data["status"] == "ready_for_credentials"


@patch("main.execute_gemini_transformation")
def test_process_txt_file(mock_gemini):
    mock_gemini.return_value = "## Summary\nThis document describes project objectives."

    sample_content = b"Project: Alpha\nObjective: Launch new AI product."
    files = {
        "file": ("project.txt", io.BytesIO(sample_content), "text/plain")
    }
    data = {
        "prompt": "Summarize project objectives",
        "custom_api_key": "test_api_key_mock",
    }

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["file"]["filename"] == "project.txt"
    assert "Summary" in res_data["result"]
    assert mock_gemini.called


@patch("main.execute_gemini_transformation")
def test_process_docx_file(mock_gemini):
    mock_gemini.return_value = "Found 2 action items in the Word document."

    doc = Document()
    doc.add_paragraph("Action Item 1: Prepare staging server.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    files = {
        "file": ("actions.docx", buf, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    }
    data = {
        "prompt": "List all action items",
        "custom_api_key": "test_api_key_mock",
    }

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["file"]["extension"] == ".docx"
    assert "Found 2 action items" in res_data["result"]


@patch("main.execute_gemini_transformation")
def test_process_xlsx_file(mock_gemini):
    mock_gemini.return_value = "Total revenue across all products is $15,000."

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df = pd.DataFrame({"Product": ["A", "B"], "Sales": [10000, 5000]})
        df.to_excel(writer, sheet_name="Sales", index=False)
    buf.seek(0)

    files = {
        "file": ("sales.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    data = {
        "prompt": "Calculate total sales",
        "custom_api_key": "test_api_key_mock",
    }

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["file"]["extension"] == ".xlsx"


@patch("main.execute_gemini_transformation")
def test_process_with_google_docs_intent(mock_gemini):
    mock_gemini.return_value = "Document summary ready for export."

    data = {
        "prompt": "Please summarize this report and export to Google Docs",
        "custom_api_key": "test_api_key_mock"
    }

    response = client.post("/api/process", data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["integrations"]["google_export"] is not None
    assert res_data["integrations"]["google_export"]["service"] == "Google Docs"


def test_missing_api_key_returns_400():
    # When no key is in env and no custom key is provided
    with patch("main.GEMINI_API_KEY_ENV", ""):
        data = {"prompt": "Hello"}
        response = client.post("/api/process", data=data)
        assert response.status_code == 400
        assert "No Gemini API Key provided" in response.json()["detail"]


@patch("main.send_via_userbot")
@patch("main.execute_gemini_transformation")
def test_process_with_userbot_toggle(mock_gemini, mock_userbot):
    mock_gemini.return_value = "Executive briefing for team."
    mock_userbot.return_value = {
        "success": True,
        "recipient_matched": "Animatic",
        "dialog_id": 987654,
        "message": "Successfully sent output to 'Animatic' (1 message parts)."
    }

    data = {
        "prompt": "Create an executive brief",
        "send_telegram": "true",
        "recipient_name": "Animatic",
        "custom_api_key": "mock_key"
    }

    response = client.post("/api/process", data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["integrations"]["telegram"] is not None
    assert res_data["integrations"]["telegram"]["success"] is True
    assert res_data["integrations"]["telegram"]["recipient_matched"] == "Animatic"
    mock_userbot.assert_called_once_with("Animatic", "Executive briefing for team.")


@patch("main.send_via_userbot")
@patch("main.execute_gemini_transformation")
def test_process_with_userbot_prompt_detection(mock_gemini, mock_userbot):
    mock_gemini.return_value = "Parsed data summary."
    mock_userbot.return_value = {
        "success": True,
        "recipient_matched": "Animatic",
        "dialog_id": 987654,
        "message": "Successfully sent output to 'Animatic' (1 message parts)."
    }

    data = {
        "prompt": "Analyze this file and send to Animatic on telegram",
        "custom_api_key": "mock_key"
    }

    response = client.post("/api/process", data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["integrations"]["telegram"] is not None
    assert res_data["integrations"]["telegram"]["success"] is True
    mock_userbot.assert_called_once_with("Animatic", "Parsed data summary.")


@patch("main.check_userbot_status")
def test_telegram_status_endpoint(mock_status):
    mock_status.return_value = {
        "authorized": True,
        "name": "Jane Doe",
        "phone": "15551234567"
    }
    response = client.get("/api/telegram/status")
    assert response.status_code == 200
    data = response.json()
    assert data["authorized"] is True
    assert data["name"] == "Jane Doe"


@patch("main.request_telegram_code")
def test_telegram_send_code_endpoint(mock_req_code):
    mock_req_code.return_value = {
        "success": True,
        "phone": "+15551234567",
        "phone_code_hash": "mock_hash_123"
    }
    response = client.post("/api/telegram/send-code", data={"phone": "+15551234567"})
    assert response.status_code == 200
    assert response.json()["phone_code_hash"] == "mock_hash_123"


@patch("main.complete_telegram_sign_in")
def test_telegram_verify_code_endpoint(mock_sign_in):
    mock_sign_in.return_value = {
        "success": True,
        "user": {"name": "Jane Doe", "phone": "15551234567"}
    }
    response = client.post(
        "/api/telegram/verify-code",
        data={"phone": "+15551234567", "code": "12345"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@patch("main.request_telegram_code")
def test_telegram_send_code_api_id_invalid(mock_req_code):
    mock_req_code.return_value = {
        "success": False,
        "error_type": "ApiIdInvalidError",
        "error": "Telegram API ID/Hash invalid (API_ID_INVALID). Please verify your TELEGRAM_API_ID and TELEGRAM_API_HASH in .env."
    }
    response = client.post("/api/telegram/send-code", data={"phone": "+15551234567"})
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_type"] == "ApiIdInvalidError"
    assert "API_ID_INVALID" in data["error"]


@patch("main.complete_telegram_sign_in")
def test_telegram_verify_code_api_id_invalid(mock_sign_in):
    mock_sign_in.return_value = {
        "success": False,
        "error_type": "ApiIdInvalidError",
        "error": "Telegram API ID/Hash is invalid (API_ID_INVALID). Please verify your TELEGRAM_API_ID and TELEGRAM_API_HASH in .env."
    }
    response = client.post(
        "/api/telegram/verify-code",
        data={"phone": "+15551234567", "code": "12345"}
    )
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_type"] == "ApiIdInvalidError"
    assert "API_ID_INVALID" in data["error"]


def test_telegram_session_string_get_endpoint():
    with patch("main.get_active_session_string", return_value="1ApW_sample_string_1234567890"):
        res = client.get("/api/telegram/session-string")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is True
        assert "1ApW" in data["preview"]


def test_telegram_session_string_post_endpoint_success():
    mock_me = AsyncMock()
    mock_me.id = 777
    mock_me.first_name = "Bob"
    mock_me.last_name = "Ross"
    mock_me.username = "bobross"
    mock_me.phone = "15559876543"

    mock_client = AsyncMock()
    mock_client.is_connected = lambda: True
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_client.get_me = AsyncMock(return_value=mock_me)
    mock_client.disconnect = AsyncMock()

    with patch("main.init_and_connect_telegram_client", return_value=mock_client), \
         patch("main.set_active_session_string") as mock_set:
        res = client.post("/api/telegram/session-string", data={"session_string": "1ApW_valid_test_string=="})
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["user"]["name"] == "Bob Ross"
        mock_set.assert_called_once_with("1ApW_valid_test_string==")


def test_telegram_session_string_post_endpoint_unauthorized():
    mock_client = AsyncMock()
    mock_client.is_connected = lambda: True
    mock_client.is_user_authorized = AsyncMock(return_value=False)
    mock_client.disconnect = AsyncMock()

    with patch("main.init_and_connect_telegram_client", return_value=mock_client):
        res = client.post("/api/telegram/session-string", data={"session_string": "1ApW_expired_string=="})
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False
        assert "not authorized" in data["error"].lower()


def test_telegram_reset_clears_session_string():
    with patch("main.delete_all_session_files", return_value=["dummy.session"]), \
         patch("main.clear_active_session_string") as mock_clear:
        res = client.post("/api/telegram/reset")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["session_string_cleared"] is True
        mock_clear.assert_called_once()


def test_telegram_chats_endpoint_success():
    mock_chats_result = {
        "success": True,
        "authorized": True,
        "count": 2,
        "chats": [
            {"id": 11, "name": "Animatic", "type": "user", "username": "@animatic", "phone": "", "unread_count": 0},
            {"id": -22, "name": "Project Alpha", "type": "group", "username": "", "phone": "", "unread_count": 2}
        ]
    }
    with patch("main.get_telegram_chats", new=AsyncMock(return_value=mock_chats_result)) as mock_fn:
        res = client.get("/api/telegram/chats?limit=25")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["authorized"] is True
        assert data["count"] == 2
        assert len(data["chats"]) == 2
        assert data["chats"][0]["name"] == "Animatic"
        mock_fn.assert_called_once_with(limit=25)


def test_telegram_chats_endpoint_unauthorized():
    mock_chats_result = {
        "success": False,
        "authorized": False,
        "error": "Telegram account not connected.",
        "chats": []
    }
    with patch("main.get_telegram_chats", new=AsyncMock(return_value=mock_chats_result)):
        res = client.get("/api/telegram/chats")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["authorized"] is False
        assert len(data["chats"]) == 0


def test_process_google_workspace_unauthenticated_returns_auth_guard_payload():
    with patch("main.is_google_authenticated", return_value={"authenticated": False}):
        res = client.post("/api/process", data={"prompt": "Check the sheet in my Google account"})
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "auth_required"
        assert data["auth_code"] == "AUTH_REQUIRED_GOOGLE"
        assert data["service"] == "google"
        assert "Google Workspace authentication required" in data["message"]


def test_process_telegram_unauthenticated_returns_auth_guard_payload():
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=False)):
        res = client.post("/api/process", data={"prompt": "Send this summary via Telegram", "recipient_name": "Animatic"})
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "auth_required"
        assert data["auth_code"] == "AUTH_REQUIRED_TELEGRAM"
        assert data["service"] == "telegram"
        assert "Telegram userbot authentication required" in data["message"]


@patch("main.send_via_userbot")
@patch("main.execute_gemini_transformation")
def test_process_telegram_file_dispatch_suppresses_text_dump(mock_gemini, mock_userbot):
    mock_gemini.return_value = "Detailed translated document with hundreds of lines."
    mock_userbot.return_value = {
        "success": True,
        "recipient_matched": "Animatic",
        "dialog_id": 999,
        "dispatched_file": "transformed_sample.docx",
        "message": "Successfully dispatched file 'transformed_sample.docx' to 'Animatic'."
    }

    sample_doc = io.BytesIO(b"Document content for translation")
    files = {"file": ("sample.txt", sample_doc, "text/plain")}
    data = {
        "prompt": "Translate this document and send via Telegram",
        "recipient_name": "Animatic",
        "send_telegram": "true",
        "custom_api_key": "mock_key"
    }

    res = client.post("/api/process", data=data, files=files)
    assert res.status_code == 200
    res_data = res.json()

    assert res_data["suppress_text_dump"] is True
    assert "Document Dispatched via Telegram" in res_data["result"]
    assert "Detailed translated document" not in res_data["result"]
    assert res_data["export_file"] is not None
    assert mock_userbot.called

    # Verify send_via_userbot was passed file_path
    call_kwargs = mock_userbot.call_args.kwargs
    assert "file_path" in call_kwargs
    assert call_kwargs["file_path"].endswith(res_data["export_file"]["filename"])
    assert call_kwargs["recipient_name"] == "Animatic"


def test_detect_telegram_management_intent():
    from main import detect_telegram_management_intent

    # Block
    t1 = detect_telegram_management_intent("Block user @spammer")
    assert t1 is not None
    assert t1["action"] == "block_user"
    assert t1["target_user"] == "@spammer"

    # Unblock
    t2 = detect_telegram_management_intent("Unblock @gooduser")
    assert t2 is not None
    assert t2["action"] == "unblock_user"
    assert t2["target_user"] == "@gooduser"

    # Kick
    t3 = detect_telegram_management_intent("Kick user @troll from Developers Chat")
    assert t3 is not None
    assert t3["action"] == "kick_member"
    assert t3["target_user"] == "@troll"
    assert t3["target_chat"] == "Developers Chat"
    assert t3["ban"] is False

    # Ban
    t4 = detect_telegram_management_intent("Ban @malicious from VIP Group")
    assert t4 is not None
    assert t4["action"] == "ban_member"
    assert t4["target_user"] == "@malicious"
    assert t4["target_chat"] == "VIP Group"
    assert t4["ban"] is True

    # Search dialogs / keyword
    t5 = detect_telegram_management_intent("Search telegram messages for invoice")
    assert t5 is not None
    assert t5["action"] == "search_dialogs"
    assert t5["query"] == "invoice"
    assert t5["unread_only"] is False

    # Unread messages
    t6 = detect_telegram_management_intent("Show unread telegram messages")
    assert t6 is not None
    assert t6["action"] == "search_dialogs"
    assert t6["unread_only"] is True

    # Summarize with chat name
    t7 = detect_telegram_management_intent("Summarize recent messages with Vip Mobile")
    assert t7 is not None
    assert t7["action"] == "summarize_chat"
    assert t7["target_chat"] == "Vip Mobile"

    # Summarize messages from sender
    t8 = detect_telegram_management_intent("Summarize messages from Alice")
    assert t8 is not None
    assert t8["action"] == "summarize_chat"
    assert t8["target_chat"] == "Alice"

    # What did X say about topic
    t9 = detect_telegram_management_intent("What did Vip Mobile say about the invoice?")
    assert t9 is not None
    assert t9["action"] == "summarize_chat"
    assert t9["target_chat"] == "Vip Mobile"
    assert t9["topic"] == "the invoice"

    # Analyze messages in chat
    t10 = detect_telegram_management_intent("Analyze messages in Vip Mobile")
    assert t10 is not None
    assert t10["action"] == "summarize_chat"
    assert t10["target_chat"] == "Vip Mobile"

    # UI Ask AI format
    t11 = detect_telegram_management_intent("Summarize recent messages with Alice and provide key action items:")
    assert t11 is not None
    assert t11["action"] == "summarize_chat"
    assert t11["target_chat"] == "Alice"


def test_process_telegram_management_unauthenticated():
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=False)):
        res = client.post("/api/process", data={"prompt": "Block user @spammer"})
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "auth_required"
        assert data["auth_code"] == "AUTH_REQUIRED_TELEGRAM"
        assert "Telegram userbot authentication required" in data["message"]


def test_process_telegram_management_block_user_execution():
    mock_block = AsyncMock(return_value={
        "success": True,
        "action": "block_user",
        "target": "@spammer",
        "user_id": 12345,
        "display_name": "@spammer",
        "message": "Successfully blocked Telegram user @spammer."
    })
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.block_telegram_user", new=mock_block):
        res = client.post("/api/process", data={"prompt": "Block user @spammer"})
        assert res.status_code == 200
        data = res.json()
        assert "Telegram User Blocked" in data["result"]
        assert "✅ Success" in data["result"]
        assert "@spammer" in data["result"]
        mock_block.assert_called_once_with("@spammer")


def test_process_telegram_management_kick_member_execution():
    mock_kick = AsyncMock(return_value={
        "success": True,
        "action": "kick_member",
        "chat": "Dev Chat",
        "target": "@troll",
        "user_id": 9999,
        "message": "Successfully kicked participant @troll from 'Dev Chat'."
    })
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.kick_chat_member", new=mock_kick):
        res = client.post("/api/process", data={"prompt": "Kick user @troll from Dev Chat"})
        assert res.status_code == 200
        data = res.json()
        assert "Participant Kicked from Group" in data["result"]
        assert "Dev Chat" in data["result"]
        mock_kick.assert_called_once_with("Dev Chat", "@troll", ban=False)


def test_process_telegram_management_search_execution():
    mock_search = AsyncMock(return_value={
        "success": True,
        "authorized": True,
        "query": "invoice",
        "dialog_count": 1,
        "dialogs": [{"name": "Finance Chat", "type": "group", "unread_count": 2, "last_message": "Invoice attached"}],
        "message_count": 1,
        "messages": [{"id": 101, "chat_title": "Finance Chat", "sender": "Alice", "text": "Here is the invoice."}]
    })
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.search_telegram_dialogs", new=mock_search):
        res = client.post("/api/process", data={"prompt": "Search telegram messages for invoice"})
        assert res.status_code == 200
        data = res.json()
        assert "Telegram Dialog & Message Search" in data["result"]
        assert "Finance Chat" in data["result"]
        assert "Invoice attached" in data["result"]
        mock_search.assert_called_once_with(query="invoice", unread_only=False, sender_name=None)


def test_direct_telegram_management_endpoints():
    # 1. Block
    with patch("main.block_telegram_user", new=AsyncMock(return_value={"success": True, "action": "block_user"})):
        res = client.post("/api/telegram/block-user", data={"user_identifier": "@baduser"})
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 2. Unblock
    with patch("main.unblock_telegram_user", new=AsyncMock(return_value={"success": True, "action": "unblock_user"})):
        res = client.post("/api/telegram/unblock-user", data={"user_identifier": "@gooduser"})
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 3. Kick / Ban
    with patch("main.kick_chat_member", new=AsyncMock(return_value={"success": True, "action": "kick_member"})):
        res = client.post("/api/telegram/kick-member", data={"chat_identifier": "MyGroup", "user_identifier": "@troublemaker", "ban": "false"})
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 4. Search
    with patch("main.search_telegram_dialogs", new=AsyncMock(return_value={"success": True, "dialogs": [], "messages": []})):
        res = client.get("/api/telegram/search?query=receipt")
        assert res.status_code == 200
        assert res.json()["success"] is True

    # 5. Chat Messages Fetch
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "123456",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 1, "text": "Hello there", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T10:00:00"},
            {"id": 2, "text": "Here is the summary", "out": True, "sender": "You", "date": "2026-09-27T10:01:00"}
        ],
        "count": 2
    }
    with patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)):
        res = client.get("/api/telegram/chat-messages?chat_id=123456&limit=20")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["messages"]) == 2
        assert data["chat_title"] == "Vip Mobile"

    # 6. Send Message Endpoint
    with patch("main.send_via_userbot", new=AsyncMock(return_value={"success": True, "recipient_matched": "Vip Mobile"})):
        res = client.post("/api/telegram/send-message", data={"recipient": "123456", "message": "Direct message via viewer"})
        assert res.status_code == 200
        assert res.json()["success"] is True


def test_priority_intent_routing_telegram_over_google_workspace():
    """
    Ensure Telegram intents take precedence over Google Workspace tools.
    For example, 'Search telegram messages for sheet' contains 'sheet' (a Google Workspace keyword),
    but must route to search_telegram_dialogs, NOT list_google_drive_files.
    """
    mock_search = AsyncMock(return_value={
        "success": True,
        "authorized": True,
        "query": "sheet",
        "dialog_count": 1,
        "dialogs": [{"name": "Operations Chat", "type": "group", "unread_count": 0, "last_message": "Spreadsheet update"}],
        "message_count": 1,
        "messages": [{"id": 202, "chat_title": "Operations Chat", "sender": "Bob", "text": "Here is the balance sheet."}]
    })
    mock_google = MagicMock()

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.search_telegram_dialogs", new=mock_search), \
         patch("main.list_google_drive_files", new=mock_google):

        res = client.post("/api/process", data={"prompt": "Search telegram messages for sheet"})
        assert res.status_code == 200
        data = res.json()

        # Must execute Telegram tool and return live card directly
        assert "Telegram Dialog & Message Search" in data["result"]
        assert "Operations Chat" in data["result"]
        mock_search.assert_called_once_with(query="sheet", unread_only=False, sender_name=None)
        # Google Workspace tool must NOT be invoked
        mock_google.assert_not_called()


def test_priority_intent_routing_unread_telegram():
    """Ensure 'unread telegram' is intercepted and routes directly to userbot tool."""
    mock_search = AsyncMock(return_value={
        "success": True,
        "authorized": True,
        "query": None,
        "dialog_count": 1,
        "dialogs": [{"name": "Alerts", "type": "channel", "unread_count": 5, "last_message": "System ping"}],
        "message_count": 0,
        "messages": []
    })

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.search_telegram_dialogs", new=mock_search):

        res = client.post("/api/process", data={"prompt": "unread telegram"})
        assert res.status_code == 200
        data = res.json()
        assert "Telegram Dialog & Message Search" in data["result"]
        assert "Alerts" in data["result"]
        mock_search.assert_called_once_with(query=None, unread_only=True, sender_name=None)


def test_priority_intent_routing_block_with_contextual_recipient():
    """Ensure 'block this user' resolves to the active chat recipient_name."""
    mock_block = AsyncMock(return_value={
        "success": True,
        "action": "block_user",
        "target": "@annoying",
        "user_id": 8888,
        "display_name": "@annoying",
        "message": "Blocked user @annoying."
    })

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.block_telegram_user", new=mock_block):

        res = client.post("/api/process", data={"prompt": "block this user", "recipient_name": "@annoying"})
        assert res.status_code == 200
        data = res.json()
        assert "Telegram User Blocked" in data["result"]
        mock_block.assert_called_once_with("@annoying")


def test_direct_telegram_send_message_endpoint():
    """Test POST /api/telegram/send-message with text and with file."""
    mock_send = AsyncMock(return_value={"success": True, "recipient_matched": "Vip Mobile", "dialog_id": 12345})
    with patch("main.send_via_userbot", new=mock_send):
        # 1. Text only
        res = client.post("/api/telegram/send-message", data={"recipient": "12345", "message": "Hello from viewer"})
        assert res.status_code == 200
        assert res.json()["success"] is True
        mock_send.assert_called_with(recipient_name="12345", message_text="Hello from viewer", file_path=None)

        # 2. With file
        res = client.post(
            "/api/telegram/send-message",
            data={"recipient": "12345", "message": "Here is doc"},
            files={"file": ("test.txt", b"Test file content", "text/plain")}
        )
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert mock_send.call_count == 2


def test_process_telegram_management_summarize_chat_execution():
    """Verify local tool execution for chat summarization: fetches messages and calls local agent model."""
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "123456",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 1, "text": "Can we review the budget proposal today?", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T10:00:00"},
            {"id": 2, "text": "Sure, let's lock in the Q4 forecast by 3pm.", "out": True, "sender": "You", "date": "2026-09-27T10:01:00"}
        ],
        "count": 2
    }

    mock_gemini = MagicMock(return_value="### Executive Summary\n- Budget proposal discussed\n- Q4 forecast decision locked for 3pm.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini):

        res = client.post("/api/process", data={"prompt": "Summarize recent messages with Vip Mobile"})
        assert res.status_code == 200
        data = res.json()

        assert "Telegram Chat Analysis: Vip Mobile" in data["result"]
        assert "Budget proposal discussed" in data["result"]
        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        assert data["integrations"]["telegram_management"]["target"] == "Vip Mobile"
        assert data["integrations"]["telegram_management"]["message_count"] == 2

        mock_fetch.assert_called_once_with(chat_id="Vip Mobile", limit=35)
        mock_gemini.assert_called_once()
        # Verify the transcript was passed into the agent prompt
        call_prompt = mock_gemini.call_args[1]["user_prompt"]
        assert "Can we review the budget proposal today?" in call_prompt
        assert "Q4 forecast by 3pm" in call_prompt


def test_priority_intent_routing_summarize_chat_over_google_workspace():
    """Ensure prompts asking to summarize chat with spreadsheet mentions bypass Google Workspace routing."""
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "123456",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 1, "text": "Attached spreadsheet looks great.", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T10:00:00"}
        ],
        "count": 1
    }

    mock_gemini = MagicMock(return_value="Vip Mobile confirmed the spreadsheet is verified.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini), \
         patch("main.list_google_drive_files") as mock_google:

        # Prompt contains 'spreadsheet' and 'sheets' keywords which would normally trigger Google Workspace search
        res = client.post("/api/process", data={"prompt": "Summarize messages from Vip Mobile about the spreadsheet sheets"})
        assert res.status_code == 200
        data = res.json()

        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        mock_fetch.assert_called_once_with(chat_id="Vip Mobile", limit=35)
        # Ensure Google Workspace was completely bypassed
        mock_google.assert_not_called()


def test_hard_intent_override_summarize_last_messages_endpoint_chat():
    """
    Test hard intent override via POST /api/chat:
    'Summarize last messages with Vip Mobile' must bypass Google Workspace completely,
    call get_telegram_chat_messages, and return a structured intelligence card.
    """
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "123456",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 1, "text": "Are we shipping the product today?", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T10:00:00"},
            {"id": 2, "text": "Yes, release build is green.", "out": True, "sender": "You", "date": "2026-09-27T10:05:00"}
        ],
        "count": 2
    }
    mock_gemini = MagicMock(return_value="### Executive Summary\n- Release build is green and confirmed shipping today.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini), \
         patch("main.list_google_drive_files") as mock_google:

        res = client.post("/api/chat", data={"prompt": "Summarize last messages with Vip Mobile"})
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "success"
        assert "Telegram Chat Analysis: Vip Mobile" in data["result"]
        assert "Release build is green and confirmed shipping today." in data["result"]
        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        assert data["integrations"]["telegram_management"]["target"] == "Vip Mobile"
        assert data["integrations"]["telegram_management"]["message_count"] == 2

        mock_fetch.assert_called_once_with(chat_id="Vip Mobile", limit=35)
        mock_gemini.assert_called_once()
        mock_google.assert_not_called()


def test_hard_intent_override_active_telegram_context():
    """
    Test hard intent override when active Telegram context is passed:
    'Summarize last messages' with recipient_name='Vip Mobile'
    must resolve target_chat to 'Vip Mobile' and execute immediately.
    """
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "999888",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 10, "text": "Contract terms are signed.", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T11:00:00"}
        ],
        "count": 1
    }
    mock_gemini = MagicMock(return_value="### Summary\n- Contract is signed.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini), \
         patch("main.list_google_drive_files") as mock_google:

        res = client.post("/api/chat", data={
            "prompt": "Summarize last messages",
            "recipient_name": "Vip Mobile",
            "telegram_chat_id": "999888"
        })
        assert res.status_code == 200
        data = res.json()

        assert "Telegram Chat Analysis: Vip Mobile" in data["result"]
        assert "Contract is signed." in data["result"]
        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        assert data["integrations"]["telegram_management"]["target"] == "Vip Mobile"

        mock_fetch.assert_called_once_with(chat_id="Vip Mobile", limit=35)
        mock_google.assert_not_called()


def test_hard_intent_override_what_did_user_say_query():
    """
    Test hard intent override for 'What did Vip Mobile say about the invoice?'
    """
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "123456",
        "chat_title": "Vip Mobile",
        "messages": [
            {"id": 1, "text": "Invoice #402 has been wired.", "out": False, "sender": "Vip Mobile", "date": "2026-09-27T09:30:00"}
        ],
        "count": 1
    }
    mock_gemini = MagicMock(return_value="Vip Mobile stated that Invoice #402 has been wired.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini):

        res = client.post("/api/process", data={"prompt": "What did Vip Mobile say about the invoice?"})
        assert res.status_code == 200
        data = res.json()

        assert "Telegram Chat Analysis: Vip Mobile" in data["result"]
        assert "Invoice #402 has been wired." in data["result"]
        mock_fetch.assert_called_once_with(chat_id="Vip Mobile", limit=35)
        call_prompt = mock_gemini.call_args[1]["user_prompt"]
        assert "Focus specifically on: 'the invoice'" in call_prompt


def test_hard_intent_override_unauthenticated_returns_401():
    """
    Test hard intent override when userbot is not authorized:
    Must return 401 with AUTH_REQUIRED_TELEGRAM.
    """
    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=False)):
        res = client.post("/api/chat", data={"prompt": "Summarize last messages with Vip Mobile"})
        assert res.status_code == 401
        data = res.json()
        assert data["status"] == "auth_required"
        assert data["auth_code"] == "AUTH_REQUIRED_TELEGRAM"
        assert data["service"] == "telegram"


def test_detect_telegram_summarization_fuzzy_cyrillic_and_slashes():
    """
    Test fuzzy entity extraction with special characters:
    slashes (/), dashes (-), and Cyrillic script.
    """
    from main import detect_telegram_summarization_hard_override

    # Cyrillic chat name with slash
    res1 = detect_telegram_summarization_hard_override("Summarize last messages with Иван/Разработка")
    assert res1 is not None
    assert res1["action"] == "summarize_chat"
    assert res1["target_chat"] == "Иван/Разработка"

    # ASCII entity with slash
    res2 = detect_telegram_summarization_hard_override("Summarize messages in Dev/Ops")
    assert res2 is not None
    assert res2["action"] == "summarize_chat"
    assert res2["target_chat"] == "Dev/Ops"

    # Dash entity with topic
    res3 = detect_telegram_summarization_hard_override("What did Dev-Ops say about the release?")
    assert res3 is not None
    assert res3["action"] == "summarize_chat"
    assert res3["target_chat"] == "Dev-Ops"
    assert res3["topic"] == "the release"

    # Preposition 'for' with trailing prompt instruction
    res4 = detect_telegram_summarization_hard_override("Summarize messages for Tech-Lead/Core and provide action items:")
    assert res4 is not None
    assert res4["action"] == "summarize_chat"
    assert res4["target_chat"] == "Tech-Lead/Core"

    # Preposition 'of' with Cyrillic
    res5 = detect_telegram_summarization_hard_override("Summary of messages of Анна/Дизайн")
    assert res5 is not None
    assert res5["action"] == "summarize_chat"
    assert res5["target_chat"] == "Анна/Дизайн"


def test_summarize_chat_with_cyrillic_slash_entity_execution():
    """
    Execute chat summarization with Cyrillic and slash entity via API.
    Verifies the userbot messages fetcher receives the exact entity and Google Workspace is bypassed.
    """
    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "777666",
        "chat_title": "Иван/Разработка",
        "messages": [
            {"id": 1, "text": "Пулреквест одобрен.", "out": False, "sender": "Иван", "date": "2026-09-27T10:00:00"}
        ],
        "count": 1
    }
    mock_gemini = MagicMock(return_value="Иван подтвердил, что пулреквест одобрен.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini), \
         patch("main.list_google_drive_files") as mock_google:

        res = client.post("/api/chat", data={"prompt": "Summarize last messages with Иван/Разработка"})
        assert res.status_code == 200
        data = res.json()

        assert "Telegram Chat Analysis: Иван/Разработка" in data["result"]
        assert "Иван подтвердил" in data["result"]
        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        assert data["integrations"]["telegram_management"]["target"] == "Иван/Разработка"
        mock_fetch.assert_called_once_with(chat_id="Иван/Разработка", limit=35)
        mock_google.assert_not_called()


def test_summarize_chat_fallback_to_session_active_chat():
    """
    Test that 'Summarize last messages' automatically falls back to
    the currently active Telegram chat in session state.
    """
    from main import set_active_telegram_chat

    set_active_telegram_chat("Active Project Group")

    mock_messages_payload = {
        "success": True,
        "authorized": True,
        "chat_id": "555444",
        "chat_title": "Active Project Group",
        "messages": [
            {"id": 1, "text": "Backend deployment finished.", "out": False, "sender": "Ops", "date": "2026-09-27T10:30:00"}
        ],
        "count": 1
    }
    mock_gemini = MagicMock(return_value="- Deployment completed successfully.")

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_messages_payload)) as mock_fetch, \
         patch("main.execute_gemini_transformation", new=mock_gemini), \
         patch("main.list_google_drive_files") as mock_google:

        res = client.post("/api/chat", data={"prompt": "Summarize last messages"})
        assert res.status_code == 200
        data = res.json()

        assert "Telegram Chat Analysis: Active Project Group" in data["result"]
        assert "- Deployment completed successfully." in data["result"]
        mock_fetch.assert_called_once_with(chat_id="Active Project Group", limit=35)
        mock_google.assert_not_called()


def test_summarize_chat_universal_interception_helpful_prompt_when_no_chat():
    """
    Universal Interception: If a user types 'summarize messages' while Telegram is connected,
    never hit Google Workspace refusal. If no chat is resolvable, return a helpful prompt card.
    """
    from main import set_active_telegram_chat

    set_active_telegram_chat(None)

    with patch("main.is_userbot_authorized", new=AsyncMock(return_value=True)), \
         patch("main.get_telegram_chats", new=AsyncMock(return_value={"success": True, "chats": []})), \
         patch("main.list_google_drive_files") as mock_google:

        res = client.post("/api/chat", data={"prompt": "summarize messages"})
        assert res.status_code == 200
        data = res.json()

        assert data["status"] == "success"
        assert "Please specify which chat you would like to summarize" in data["result"]
        assert data["integrations"]["telegram_management"]["action"] == "summarize_chat"
        mock_google.assert_not_called()


def test_active_chat_tracked_on_chat_messages_endpoint():
    """
    Test that fetching messages for a chat updates the active Telegram chat in session state.
    """
    from main import get_active_telegram_chat

    mock_res = {
        "success": True,
        "authorized": True,
        "chat_title": "Marketing Team",
        "messages": []
    }
    with patch("main.get_telegram_chat_messages", new=AsyncMock(return_value=mock_res)):
        res = client.get("/api/telegram/chat-messages?chat_id=Marketing-Team")
        assert res.status_code == 200
        assert get_active_telegram_chat() == "Marketing-Team"












