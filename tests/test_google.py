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
    generate_oauth_url
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


def test_generate_oauth_url_missing_secrets():
    with patch("os.path.exists", return_value=False):
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

