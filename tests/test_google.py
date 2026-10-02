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


def test_detect_google_workspace_counting_and_informational_queries():
    from main import detect_google_workspace_query, should_trigger_google_export

    q1 = "how many google sheet folders do i have"
    res1 = detect_google_workspace_query(q1)
    assert res1 is not None
    assert res1["action"] == "count_files"
    assert res1["file_type"] == "folder"
    assert res1["is_count"] is True
    assert should_trigger_google_export(q1) is None

    q2 = "what sheets do I have"
    res2 = detect_google_workspace_query(q2)
    assert res2 is not None
    assert res2["action"] == "list_files"
    assert res2["file_type"] == "sheet"
    assert res2["is_count"] is False
    assert should_trigger_google_export(q2) is None

    q3 = "how many sheets do i have"
    res3 = detect_google_workspace_query(q3)
    assert res3 is not None
    assert res3["action"] == "count_files"
    assert res3["file_type"] == "sheet"
    assert res3["is_count"] is True

    q4 = "how many google docs do i have"
    res4 = detect_google_workspace_query(q4)
    assert res4 is not None
    assert res4["action"] == "count_files"
    assert res4["file_type"] == "doc"
    assert res4["is_count"] is True


def test_informational_query_returns_clean_natural_response_not_table():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    with patch("main.is_google_authenticated", return_value={"authenticated": True}):
        # 1. Counting query
        with patch("main.list_google_drive_files") as mock_list, \
             patch("main.execute_gemini_transformation", return_value="You have 3 folders in your connected Google Drive account."):
            mock_list.return_value = {
                "success": True,
                "count": 3,
                "files": [
                    {"name": "Folder A", "type": "Folder", "link": "http://fa", "modified_time": "2026-09-01"},
                    {"name": "Folder B", "type": "Folder", "link": "http://fb", "modified_time": "2026-09-02"},
                    {"name": "Folder C", "type": "Folder", "link": "http://fc", "modified_time": "2026-09-03"}
                ]
            }
            res = client.post("/api/process", data={"prompt": "how many google sheet folders do i have"})
            assert res.status_code == 200
            data = res.json()
            assert "3" in data["result"]
            assert "Generated research data and compiled documentation" not in data["result"]
            assert "| Item | Description |" not in data["result"]

        # 2. Listing query
        with patch("main.list_google_drive_files") as mock_list, \
             patch("main.execute_gemini_transformation", return_value="Here are your Google Sheets:\n- [Sales](http://s1)"):
            mock_list.return_value = {
                "success": True,
                "count": 1,
                "files": [
                    {"name": "Sales", "type": "Google Sheet", "link": "http://s1", "modified_time": "2026-09-01"}
                ]
            }
            res2 = client.post("/api/process", data={"prompt": "what sheets do I have"})
            assert res2.status_code == 200
            data2 = res2.json()
            assert "Sales" in data2["result"]
            assert "Generated research data and compiled documentation" not in data2["result"]
            assert "| Item | Description |" not in data2["result"]


def test_multi_turn_followup_confirmation_and_title_resolution():
    from main import should_trigger_google_export, extract_custom_title, is_followup_confirmation

    # Assert helper detects affirmatives and confirmations
    assert is_followup_confirmation("yes create that") is True
    assert is_followup_confirmation("do it") is True
    assert is_followup_confirmation("sure go ahead") is True
    assert is_followup_confirmation("proceed") is True
    assert is_followup_confirmation("check my google sheet") is False

    history_sheet = [
        {"role": "user", "content": "can u create a sheet with iphone specs"},
        {"role": "assistant", "content": "I can create a Google Sheet for iPhone specs. Would you like me to proceed?"}
    ]

    # Turn 2: "yes create that"
    assert should_trigger_google_export("yes create that", history_sheet) == "sheets"
    title1 = extract_custom_title("yes create that", history_sheet)
    assert title1 is not None
    assert "iphone specs" in title1.lower()

    # Turn 2: "do it"
    assert should_trigger_google_export("do it", history_sheet) == "sheets"

    # Turn 2: Providing custom title
    assert should_trigger_google_export("name it iPhone 16 Specs", history_sheet) == "sheets"
    assert extract_custom_title("name it iPhone 16 Specs", history_sheet) == "iPhone 16 Specs"

    # Turn 2: Document confirmation
    history_doc = [
        {"role": "user", "content": "can you create a doc summarizing AI trends"},
        {"role": "assistant", "content": "I can create a Google Doc summarizing AI trends. Should I generate it now?"}
    ]
    assert should_trigger_google_export("yes please", history_doc) == "docs"
    title_doc = extract_custom_title("yes please", history_doc)
    assert title_doc is not None
    assert "ai trends" in title_doc.lower()


def test_multi_turn_creation_endpoint_executes_tool_without_questionnaire_loop():
    import json
    from fastapi.testclient import TestClient
    from main import app, clear_session_chat_history
    client = TestClient(app)

    clear_session_chat_history()

    sample_table = (
        "| Model | Display | Processor | Price |\n"
        "|---|---|---|---|\n"
        "| iPhone 16 Pro | 6.3 OLED | A18 Pro | $999 |\n"
        "| iPhone 16 Pro Max | 6.9 OLED | A18 Pro | $1199 |"
    )

    with patch("main.is_google_authenticated", return_value={"authenticated": True}), \
         patch("main.create_google_sheet") as mock_create_sheet, \
         patch("main.execute_gemini_transformation", return_value=sample_table) as mock_gemini:

        mock_create_sheet.return_value = {
            "success": True,
            "spreadsheet_id": "test-sheet-id",
            "url": "https://docs.google.com/spreadsheets/d/test-sheet-id/edit",
            "title": "iPhone Specs - Spreadsheet",
            "rows_written": 2
        }

        # Follow-up confirmation with client-provided chat history
        chat_hist = [
            {"role": "user", "content": "can u create a sheet with iphone specs"},
            {"role": "assistant", "content": "I can create a Google Sheet for iPhone specs. Would you like me to proceed?"}
        ]

        response = client.post("/api/process", data={
            "prompt": "yes create that",
            "chat_history": json.dumps(chat_hist)
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # Tool execution must have occurred immediately
        assert mock_create_sheet.called
        # Verify creation banner and link are rendered
        assert "Google Sheet Created" in data["result"]
        assert "https://docs.google.com/spreadsheets/d/test-sheet-id/edit" in data["result"]
        # Verify no questionnaire questions
        assert "what kind of file" not in data["result"].lower()
        # Verify gemini was called with creation directives and conversation history
        call_kwargs = mock_gemini.call_args[1]
        assert call_kwargs.get("creation_export_type") == "sheets"
        assert call_kwargs.get("chat_history") is not None


def test_parse_text_to_matrix_normalization_and_formatting():
    from services.google_workspace import parse_text_to_matrix, clean_cell_text

    # Test clean_cell_text
    assert clean_cell_text("**Bold Text**") == "Bold Text"
    assert clean_cell_text("[Apple Link](https://apple.com)") == "Apple Link"
    assert clean_cell_text("`code_snippet`") == "code_snippet"

    # Test uneven row normalization and escaped pipe handling
    raw_markdown = """
| **Device Model** | **Display** | **Price** |
|---|---|---|
| iPhone 16 Pro | 6.3\" \\| Super Retina OLED | $999 |
| iPhone 16 | 6.1\" OLED |
"""
    matrix = parse_text_to_matrix(raw_markdown)
    assert len(matrix) == 3
    # Check headers cleaned of bold markers
    assert matrix[0] == ["Device Model", "Display", "Price"]
    # Check escaped pipe handled
    assert matrix[1] == ["iPhone 16 Pro", '6.3" | Super Retina OLED', "$999"]
    # Check uneven row padded to max_cols (3 columns)
    assert matrix[2] == ["iPhone 16", '6.1" OLED', ""]
    assert len(matrix[0]) == len(matrix[1]) == len(matrix[2]) == 3


def test_parse_text_to_matrix_csv_quoted_commas():
    from services.google_workspace import parse_text_to_matrix

    csv_data = """Name,Company,Valuation\nTim Cook,"Apple, Inc.",$3 Trillion\nSatya Nadella,"Microsoft, Corp.",$3 Trillion"""
    matrix = parse_text_to_matrix(csv_data)
    assert len(matrix) == 3
    assert matrix[0] == ["Name", "Company", "Valuation"]
    assert matrix[1] == ["Tim Cook", "Apple, Inc.", "$3 Trillion"]
    assert matrix[2] == ["Satya Nadella", "Microsoft, Corp.", "$3 Trillion"]


def test_create_google_sheet_enterprise_formatting_and_batch_update():
    from services.google_workspace import create_google_sheet

    mock_sheets_service = MagicMock()
    mock_create_exec = MagicMock()
    mock_create_exec.execute.return_value = {
        "spreadsheetId": "test_sheet_999",
        "sheets": [{"properties": {"sheetId": 42}}]
    }
    mock_sheets_service.spreadsheets().create.return_value = mock_create_exec

    mock_update_exec = MagicMock()
    mock_sheets_service.spreadsheets().values().update.return_value = mock_update_exec

    mock_batch_exec = MagicMock()
    mock_sheets_service.spreadsheets().batchUpdate.return_value = mock_batch_exec

    markdown_input = (
        "| **Metric** | **Q1** | **Q2** |\n"
        "|---|---|---|\n"
        "| Revenue | $10,000 | $15,000 |\n"
        "| Operating Profit | $2,000 | $3,500 |\n"
    )

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_sheets_service):
            res = create_google_sheet("Q1-Q2 Financials", raw_text=markdown_input)

            assert res["success"] is True
            assert res["spreadsheet_id"] == "test_sheet_999"
            assert res["rows_written"] == 3

            # Verify values.update was called with normalized matrix
            update_call_kwargs = mock_sheets_service.spreadsheets().values().update.call_args[1]
            written_values = update_call_kwargs["body"]["values"]
            assert written_values[0] == ["Metric", "Q1", "Q2"]
            assert written_values[1] == ["Revenue", "$10,000", "$15,000"]
            assert written_values[2] == ["Operating Profit", "$2,000", "$3,500"]

            # Verify batchUpdate was called with enterprise styling requests
            assert mock_sheets_service.spreadsheets().batchUpdate.called
            batch_kwargs = mock_sheets_service.spreadsheets().batchUpdate.call_args[1]
            assert batch_kwargs["spreadsheetId"] == "test_sheet_999"
            requests = batch_kwargs["body"]["requests"]

            # Verify freeze header row request
            freeze_req = next((r for r in requests if "updateSheetProperties" in r), None)
            assert freeze_req is not None
            assert freeze_req["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] == 1
            assert freeze_req["updateSheetProperties"]["properties"]["sheetId"] == 42

            # Verify header styling request (Navy #1E293B, White bold text, text wrapping)
            repeat_cell_reqs = [r for r in requests if "repeatCell" in r]
            assert len(repeat_cell_reqs) >= 2
            header_repeat = repeat_cell_reqs[0]["repeatCell"]
            assert header_repeat["range"]["startRowIndex"] == 0
            assert header_repeat["range"]["endRowIndex"] == 1
            assert header_repeat["cell"]["userEnteredFormat"]["backgroundColor"]["red"] == 0.12
            assert header_repeat["cell"]["userEnteredFormat"]["textFormat"]["bold"] is True
            assert header_repeat["cell"]["userEnteredFormat"]["wrapStrategy"] == "WRAP"

            # Verify data row formatting request (wrapStrategy: WRAP)
            data_repeat = repeat_cell_reqs[1]["repeatCell"]
            assert data_repeat["range"]["startRowIndex"] == 1
            assert data_repeat["range"]["endRowIndex"] == 3
            assert data_repeat["cell"]["userEnteredFormat"]["wrapStrategy"] == "WRAP"

            # Verify alternating row banding (zebra striping)
            banding_req = next((r for r in requests if "addBanding" in r), None)
            assert banding_req is not None
            assert banding_req["addBanding"]["bandedRange"]["range"]["sheetId"] == 42

            # Verify auto-resize columns
            resize_req = next((r for r in requests if "autoResizeDimensions" in r), None)
            assert resize_req is not None
            assert resize_req["autoResizeDimensions"]["dimensions"]["dimension"] == "COLUMNS"
            assert resize_req["autoResizeDimensions"]["dimensions"]["startIndex"] == 0
            assert resize_req["autoResizeDimensions"]["dimensions"]["endIndex"] == 3


def test_create_google_sheet_formatting_error_does_not_break_creation():
    from services.google_workspace import create_google_sheet

    mock_sheets_service = MagicMock()
    mock_create_exec = MagicMock()
    mock_create_exec.execute.return_value = {
        "spreadsheetId": "test_sheet_fail_fmt",
        "sheets": [{"properties": {"sheetId": 0}}]
    }
    mock_sheets_service.spreadsheets().create.return_value = mock_create_exec

    # batchUpdate raises error, but sheet creation should still succeed
    mock_sheets_service.spreadsheets().batchUpdate.side_effect = Exception("Google API formatting rate limit")

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_sheets_service):
            res = create_google_sheet("Resilient Sheet", raw_text="| Col1 | Col2 |\n|---|---|\n| 1 | 2 |")

            assert res["success"] is True
            assert res["spreadsheet_id"] == "test_sheet_fail_fmt"
            assert "url" in res


def test_find_google_drive_file():
    from services.google_workspace import find_google_drive_file

    mock_files = [
        {"id": "sheet_1", "name": "iPhone Specs", "type": "Google Sheet", "link": "https://sheet1"},
        {"id": "sheet_2", "name": "Q4 Financials", "type": "Google Sheet", "link": "https://sheet2"},
        {"id": "doc_1", "name": "Project Roadmap", "type": "Google Doc", "link": "https://doc1"}
    ]

    with patch("services.google_workspace.list_google_drive_files", return_value={"success": True, "files": mock_files}):
        # Exact match
        f1 = find_google_drive_file("Q4 Financials")
        assert f1 is not None
        assert f1["id"] == "sheet_2"

        # Case-insensitive + filler strip: "my iPhone specs sheet"
        f2 = find_google_drive_file("my iPhone specs sheet")
        assert f2 is not None
        assert f2["id"] == "sheet_1"

        # Substring / token overlap: "Project Roadmap doc"
        f3 = find_google_drive_file("Project Roadmap doc", file_type="doc")
        assert f3 is not None
        assert f3["id"] == "doc_1"

        # Non-matching
        f4 = find_google_drive_file("Nonexistent File 12345")
        assert f4 is None


def test_append_to_google_sheet_preserves_layout_and_omits_duplicate_headers():
    from services.google_workspace import append_to_google_sheet

    mock_sheets = MagicMock()

    # Mock metadata: sheet has title "Specs"
    mock_sheets.spreadsheets().get().execute.return_value = {
        "properties": {"title": "iPhone Specs"},
        "sheets": [{"properties": {"title": "Specs"}}]
    }

    # Mock existing rows: headers are ["Model", "Storage", "Price"]
    mock_sheets.spreadsheets().values().get().execute.return_value = {
        "values": [
            ["Model", "Storage", "Price"],
            ["iPhone 15", "128GB", "$799"]
        ]
    }

    # Mock append execution
    mock_sheets.spreadsheets().values().append().execute.return_value = {
        "spreadsheetId": "test_sheet_id",
        "updates": {"updatedRows": 1, "updatedRange": "Specs!A3:C3"}
    }

    raw_new_data = """
| Model | Storage | Price |
|---|---|---|
| iPhone 16 | 128GB | $899 |
"""

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_sheets):
            res = append_to_google_sheet("test_sheet_id", raw_text=raw_new_data)

            assert res["success"] is True
            assert res["rows_appended"] == 1
            assert "https://docs.google.com/spreadsheets/d/test_sheet_id/edit" in res["url"]

            # Verify that the repeated header row ["Model", "Storage", "Price"] was omitted,
            # and only the new data row was appended
            append_call_args = mock_sheets.spreadsheets().values().append.call_args[1]
            body_values = append_call_args["body"]["values"]
            assert len(body_values) == 1
            assert body_values[0] == ["iPhone 16", "128GB", "$899"]
            assert append_call_args["insertDataOption"] == "INSERT_ROWS"


def test_update_google_sheet_range():
    from services.google_workspace import update_google_sheet

    mock_sheets = MagicMock()
    mock_sheets.spreadsheets().values().update().execute.return_value = {
        "updatedRows": 1,
        "updatedCells": 1
    }

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_sheets):
            res = update_google_sheet("sheet_xyz", range_name="Sheet1!C2", values=[["$1,200,000"]])
            assert res["success"] is True
            assert res["updated_cells"] == 1
            assert res["range"] == "Sheet1!C2"


def test_append_to_google_doc():
    from services.google_workspace import append_to_google_doc

    mock_docs = MagicMock()
    mock_docs.documents().get().execute.return_value = {
        "title": "Meeting Notes",
        "body": {
            "content": [
                {"endIndex": 120}
            ]
        }
    }
    mock_docs.documents().batchUpdate().execute.return_value = {}

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_docs):
            res = append_to_google_doc("doc_xyz", content="Next Steps: Launch Phase 2")
            assert res["success"] is True
            assert res["title"] == "Meeting Notes"

            # Verify batchUpdate was called with insertText at endIndex - 1 (119)
            batch_kwargs = mock_docs.documents().batchUpdate.call_args[1]
            requests = batch_kwargs["body"]["requests"]
            assert len(requests) == 1
            assert "insertText" in requests[0]
            assert requests[0]["insertText"]["location"]["index"] == 119
            assert "Next Steps: Launch Phase 2" in requests[0]["insertText"]["text"]


def test_update_google_doc_text_replacement():
    from services.google_workspace import update_google_doc

    mock_docs = MagicMock()
    mock_docs.documents().batchUpdate().execute.return_value = {}

    with patch("services.google_workspace.get_google_credentials", return_value=MagicMock()):
        with patch("googleapiclient.discovery.build", return_value=mock_docs):
            res = update_google_doc("doc_xyz", replace_map={"[DRAFT]": "[FINAL]"})
            assert res["success"] is True

            batch_kwargs = mock_docs.documents().batchUpdate.call_args[1]
            requests = batch_kwargs["body"]["requests"]
            assert len(requests) == 1
            assert "replaceAllText" in requests[0]
            assert requests[0]["replaceAllText"]["containsText"]["text"] == "[DRAFT]"
            assert requests[0]["replaceAllText"]["replaceText"] == "[FINAL]"


def test_detect_google_workspace_edit_intent():
    from main import detect_google_workspace_edit_intent

    # 1. Sheets append
    q1 = detect_google_workspace_edit_intent("add a row for iPhone 16 to my iPhone specs sheet")
    assert q1 is not None
    assert q1["action"] == "append"
    assert q1["target_file_name"] == "iPhone specs"
    assert q1["file_type"] == "sheet"

    # 2. Update existing sheet
    q2 = detect_google_workspace_edit_intent("update the budget in Q4 Financials")
    assert q2 is not None
    assert q2["action"] == "update"
    assert q2["target_file_name"] == "Q4 Financials"

    # 3. Docs append
    q3 = detect_google_workspace_edit_intent("append meeting notes to Project Roadmap doc")
    assert q3 is not None
    assert q3["action"] == "append"
    assert q3["target_file_name"] == "Project Roadmap"
    assert q3["file_type"] == "doc"

    # 4. Multi-turn confirmation
    chat_hist = [
        {"role": "user", "content": "add a row for iPhone 16 to my iPhone specs sheet"},
        {"role": "assistant", "content": "Found your sheet 'iPhone Specs'. Shall I append the row?"}
    ]
    q4 = detect_google_workspace_edit_intent("yes update that", chat_history=chat_hist)
    assert q4 is not None
    assert q4["target_file_name"] == "iPhone specs"

    # 5. Informational query should NOT trigger edit intent
    q5 = detect_google_workspace_edit_intent("what sheets do I have")
    assert q5 is None

    # 6. Direct creation prompt should NOT trigger edit intent
    q6 = detect_google_workspace_edit_intent("create a new sheet with iPhone specs")
    assert q6 is None


def test_process_google_workspace_edit_routing_and_execution():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    mock_sheet_file = {
        "id": "sheet_iphone_123",
        "name": "iPhone Specs",
        "type": "Google Sheet",
        "link": "https://docs.google.com/spreadsheets/d/sheet_iphone_123/edit"
    }

    with patch("main.is_google_authenticated", return_value={"authenticated": True}), \
         patch("main.find_google_drive_file", return_value=mock_sheet_file), \
         patch("main.read_google_sheet", return_value={"headers": ["Model", "Display", "Price"], "values": [["Model", "Display", "Price"]]}), \
         patch("main.execute_gemini_transformation", return_value="| iPhone 16 | 6.1 OLED | $799 |"), \
         patch("main.append_to_google_sheet", return_value={"success": True, "rows_appended": 1, "url": "https://docs.google.com/spreadsheets/d/sheet_iphone_123/edit"}) as mock_append:

        response = client.post("/api/process", data={
            "prompt": "add a row for iPhone 16 to my iPhone specs sheet"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert mock_append.called
        assert "Google Sheet Updated: [iPhone Specs]" in data["result"]
        assert "https://docs.google.com/spreadsheets/d/sheet_iphone_123/edit" in data["result"]
        assert data["integrations"]["google_edit"] is not None
        assert data["integrations"]["google_edit"]["success"] is True


def test_google_sheets_append_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    with patch("main.append_to_google_sheet") as mock_append:
        mock_append.return_value = {
            "success": True,
            "spreadsheet_id": "sheet_abc",
            "rows_appended": 1,
            "url": "https://docs.google.com/spreadsheets/d/sheet_abc/edit"
        }

        response = client.post("/api/google/sheets/append", data={
            "file_id": "sheet_abc",
            "content": "| A | B |\n| 1 | 2 |"
        })

        assert response.status_code == 200
        res = response.json()
        assert res["success"] is True
        assert res["rows_appended"] == 1


def test_google_docs_append_endpoint():
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    with patch("main.append_to_google_doc") as mock_append:
        mock_append.return_value = {
            "success": True,
            "document_id": "doc_abc",
            "url": "https://docs.google.com/document/d/doc_abc/edit"
        }

        response = client.post("/api/google/docs/append", data={
            "file_id": "doc_abc",
            "content": "Added project summary section."
        })

        assert response.status_code == 200
        res = response.json()
        assert res["success"] is True
        assert res["document_id"] == "doc_abc"



