"""
Unit tests for Google Workspace integration in services/google_workspace.py.
"""

import pytest
from unittest.mock import patch, MagicMock
from services.google_workspace import (
    parse_text_to_matrix,
    is_google_authenticated,
    create_google_doc,
    create_google_sheet,
    generate_oauth_url,
    ensure_google_client_secrets_file,
)


def test_parse_text_to_matrix_markdown():
    markdown = """
| Metric | Q1 | Q2 |
|---|---|---|
| Revenue | $10,000 | $15,000 |
| Profit | $2,000 | $3,500 |
"""
    matrix = parse_text_to_matrix(markdown)
    assert len(matrix) == 3
    assert matrix[0] == ["Metric", "Q1", "Q2"]
    assert matrix[1] == ["Revenue", "$10,000", "$15,000"]
    assert matrix[2] == ["Profit", "$2,000", "$3,500"]


def test_is_google_authenticated_unlinked():
    with patch("os.path.exists", return_value=False):
        status = is_google_authenticated()
        assert status["authenticated"] is False


def test_create_google_doc_unlinked():
    with patch("services.google_workspace.get_google_credentials", return_value=None):
        res = create_google_doc("Test Doc", "Sample content")
        assert res["success"] is False
        assert res["requires_auth"] is True
        assert "mock_url" in res


def test_create_google_sheet_unlinked():
    with patch("services.google_workspace.get_google_credentials", return_value=None):
        res = create_google_sheet("Test Sheet", raw_text="| Col1 | Col2 |\n|---|---|\n| A | B |")
        assert res["success"] is False
        assert res["requires_auth"] is True
        assert "mock_url" in res


def test_ensure_google_client_secrets_file_when_exists():
    with patch("os.path.exists", return_value=True):
        assert ensure_google_client_secrets_file() is True


def test_ensure_google_client_secrets_file_from_env(tmp_path):
    mock_json = '{"web": {"client_id": "123.apps.googleusercontent.com", "client_secret": "xyz"}}'
    fake_path = str(tmp_path / "client_secret.json")

    with patch("services.google_workspace.CLIENT_SECRETS_FILE", fake_path), \
         patch.dict("os.environ", {"GOOGLE_CLIENT_SECRET_JSON": mock_json}):
        res = ensure_google_client_secrets_file()
        assert res is True
        with open(fake_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "123.apps.googleusercontent.com" in content
            assert "xyz" in content


def test_ensure_google_client_secrets_file_missing_env():
    with patch("os.path.exists", return_value=False), \
         patch.dict("os.environ", {"GOOGLE_CLIENT_SECRET_JSON": "", "GOOGLE_CLIENT_SECRETS_JSON": ""}):
        assert ensure_google_client_secrets_file() is False


def test_generate_oauth_url_missing_secrets():
    with patch("services.google_workspace.ensure_google_client_secrets_file", return_value=False), \
         patch("os.path.exists", return_value=False):
        res = generate_oauth_url("http://localhost:8000/api/google/callback")
        assert res["success"] is False
        assert "not found" in res["error"]


def test_oauth_pkce_caching_and_restoration():
    from services.google_workspace import save_oauth_code, _OAUTH_FLOW_CACHE

    mock_flow_instance = MagicMock()
    mock_flow_instance.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?test=1", "test_state_123")
    mock_flow_instance.code_verifier = "test_pkce_verifier_xyz"

    mock_flow_restore = MagicMock()
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "mock"}'
    mock_flow_restore.credentials = mock_creds

    with patch("google_auth_oauthlib.flow.Flow.from_client_secrets_file", side_effect=[mock_flow_instance, mock_flow_restore]):
        with patch("os.path.exists", return_value=True):
            # 1. Generate URL
            gen_res = generate_oauth_url("http://localhost:8000/api/google/callback")
            assert gen_res["success"] is True
            assert gen_res["state"] == "test_state_123"
            assert "test_state_123" in _OAUTH_FLOW_CACHE
            assert _OAUTH_FLOW_CACHE["test_state_123"]["code_verifier"] == "test_pkce_verifier_xyz"

            # 2. Save code with state
            with patch("builtins.open", MagicMock()):
                save_res = save_oauth_code("auth_code_789", "http://localhost:8000/api/google/callback", state="test_state_123")
                assert save_res["success"] is True
                assert mock_flow_restore.code_verifier == "test_pkce_verifier_xyz"
                assert mock_flow_restore.fetch_token.called
                call_kwargs = mock_flow_restore.fetch_token.call_args.kwargs
                assert call_kwargs.get("code_verifier") == "test_pkce_verifier_xyz"
                assert call_kwargs.get("code") == "auth_code_789"


def test_list_google_drive_files_success():
    from services.google_workspace import list_google_drive_files

    mock_drive = MagicMock()
    mock_drive.files().list().execute.return_value = {
        "files": [
            {
                "id": "sheet_123",
                "name": "Q3 Financials",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "webViewLink": "https://docs.google.com/spreadsheets/d/sheet_123/edit",
                "modifiedTime": "2026-09-25T10:00:00Z"
            }
        ]
    }

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_drive):
            res = list_google_drive_files(file_type="sheet")
            assert res["success"] is True
            assert res["count"] == 1
            assert res["files"][0]["name"] == "Q3 Financials"
            assert res["files"][0]["type"] == "Google Sheet"


def test_list_google_drive_files_unlinked():
    from services.google_workspace import list_google_drive_files

    with patch("services.google_workspace.get_google_credentials", return_value=None):
        res = list_google_drive_files(file_type="sheet")
        assert res["success"] is False
        assert res["requires_auth"] is True


def test_detect_google_workspace_query():
    from main import detect_google_workspace_query

    # Sheets
    q1 = detect_google_workspace_query("what sheets in google do I have")
    assert q1 is not None
    assert q1["file_type"] == "sheet"

    q2 = detect_google_workspace_query("show my spreadsheets")
    assert q2 is not None
    assert q2["file_type"] == "sheet"

    # Docs
    q3 = detect_google_workspace_query("list my google docs")
    assert q3 is not None
    assert q3["file_type"] == "doc"

    # Unrelated
    q4 = detect_google_workspace_query("summarize this word document")
    assert q4 is None


def test_process_google_workspace_query_tool_routing():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    with patch("main.list_google_drive_files") as mock_list:
        mock_list.return_value = {
            "success": True,
            "count": 1,
            "files": [
                {
                    "id": "sheet_abc",
                    "name": "2026 Budget",
                    "type": "Google Sheet",
                    "link": "https://docs.google.com/spreadsheets/d/sheet_abc/edit",
                    "modified_time": "2026-09-25T12:00:00Z"
                }
            ]
        }
        with patch("main.is_google_authenticated", return_value={"authenticated": True}):
            with patch("main.execute_gemini_transformation") as mock_gemini:
                mock_gemini.return_value = (
                    "Here are your connected Google Sheets:\n\n"
                    "- **[2026 Budget](https://docs.google.com/spreadsheets/d/sheet_abc/edit)**\n\n"
                    "Would you like me to analyze or edit this spreadsheet?"
                )

                response = client.post("/api/process", data={"prompt": "what sheets in google do I have"})
                assert response.status_code == 200
                res_data = response.json()
                assert "2026 Budget" in res_data["result"]
                assert mock_list.called
                assert mock_gemini.called
                # Ensure system prompt passed has the required autonomous instructions
                system_inst = mock_gemini.call_args.kwargs["system_instruction"]
                assert "fully autonomous digital employee" in system_inst
                assert "what sheets in google do I have" in system_inst


def test_should_trigger_google_export_explicit_only():
    from main import should_trigger_google_export

    # Explicit creation / export requests MUST trigger
    assert should_trigger_google_export("Please summarize this report and export to Google Docs") == "docs"
    assert should_trigger_google_export("export to google sheets") == "sheets"
    assert should_trigger_google_export("create a google sheet for sales data") == "sheets"
    assert should_trigger_google_export("create new google doc titled 'Notes'") == "docs"
    assert should_trigger_google_export("save as google doc") == "docs"
    assert should_trigger_google_export("save to google sheets") == "sheets"

    # Search, list, view, check queries MUST NEVER trigger file creation
    assert should_trigger_google_export("what sheets in google do I have") is None
    assert should_trigger_google_export("check the sheet in my Google account") is None
    assert should_trigger_google_export("show my google spreadsheets") is None
    assert should_trigger_google_export("what google sheet do I have") is None
    assert should_trigger_google_export("find my google sheet") is None
    assert should_trigger_google_export("list my google docs") is None
    assert should_trigger_google_export("do I have a google sheet?") is None
    assert should_trigger_google_export("can you see my google sheets") is None


def test_list_google_drive_files_removes_momento_sheet_filter_bias():
    from services.google_workspace import list_google_drive_files

    mock_drive = MagicMock()
    mock_drive.files().list().execute.return_value = {
        "files": [
            {
                "id": "real_sheet_1",
                "name": "Q3 Financials Actual",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "webViewLink": "https://docs.google.com/spreadsheets/d/real_sheet_1/edit",
                "modifiedTime": "2026-09-28T10:00:00Z"
            }
        ]
    }

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_drive):
            # Passing 'Momento Sheet' or 'template' must be stripped to prevent locking onto template files
            res = list_google_drive_files(file_type="sheet", query="Momento Sheet")
            assert res["success"] is True
            # Verify the API query sent to drive does NOT filter strictly for 'Momento Sheet'
            list_call_args = mock_drive.files().list.call_args.kwargs
            query_sent = list_call_args.get("q", "")
            assert "name contains 'Momento Sheet'" not in query_sent
            assert "name contains 'momento sheet'" not in query_sent.lower()
            assert "application/vnd.google-apps.spreadsheet" in query_sent


def test_no_sheet_created_on_workspace_search_query():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    with patch("main.list_google_drive_files") as mock_list, \
         patch("main.create_google_sheet") as mock_create_sheet, \
         patch("main.create_google_doc") as mock_create_doc, \
         patch("main.is_google_authenticated", return_value={"authenticated": True}), \
         patch("main.execute_gemini_transformation", return_value="Here are your files"):

        mock_list.return_value = {
            "success": True,
            "count": 1,
            "files": [{"id": "s1", "name": "Actual Sales", "type": "Google Sheet", "link": "http://sheet"}]
        }

        # Query that asks about Google Sheets must search Drive and NEVER create a new sheet or doc
        response = client.post("/api/process", data={"prompt": "check my google sheet"})
        assert response.status_code == 200
        assert mock_list.called
        mock_create_sheet.assert_not_called()
        mock_create_doc.assert_not_called()


def test_list_google_drive_files_broad_fallback_when_filtered_empty():
    from services.google_workspace import list_google_drive_files

    mock_drive = MagicMock()
    # First call (specific mimeType filter) returns empty
    # Second call (broad fallback trashed = false) returns real files
    mock_drive.files().list().execute.side_effect = [
        {"files": []},
        {
            "files": [
                {
                    "id": "broad_sheet_99",
                    "name": "Company Budget.xlsx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "webViewLink": "https://docs.google.com/spreadsheets/d/broad_sheet_99/edit",
                    "modifiedTime": "2026-09-30T10:00:00Z"
                }
            ]
        }
    ]

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_drive):
            res = list_google_drive_files(file_type="sheet")
            assert res["success"] is True
            assert res["count"] == 1
            assert res["files"][0]["name"] == "Company Budget.xlsx"
            assert res["files"][0]["type"] == "Google Sheet"


def test_should_trigger_google_export_natural_creation_and_title():
    from main import should_trigger_google_export, extract_custom_title

    prompt = "create new one name it iphone prices and search google for current prices"
    assert should_trigger_google_export(prompt) == "sheets"
    assert extract_custom_title(prompt) == "iphone prices"

    prompt_doc = "create a new doc titled 'Meeting Minutes' and search web"
    assert should_trigger_google_export(prompt_doc) == "docs"
    assert extract_custom_title(prompt_doc) == "Meeting Minutes"


def test_execute_gemini_transformation_handles_web_search_cleanly():
    from main import execute_gemini_transformation

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "| Model | Price |\n|---|---|\n| iPhone 16 | $799 |"
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        res = execute_gemini_transformation(
            api_key="test_key",
            model_name="gemini-2.5-flash",
            system_instruction="System prompt",
            user_prompt="create new one name it iphone prices and search google for current prices"
        )
        assert "| iPhone 16 | $799 |" in res
        # Verify tools was passed with google_search
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs.get("config")
        assert config is not None
        assert config.tools is not None

