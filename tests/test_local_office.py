import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from services.local_office import (
    generate_local_doc,
    generate_local_spreadsheet,
    get_local_office_status,
    is_libreoffice_available,
    markdown_to_html,
    convert_with_libreoffice,
    ensure_exports_dir,
    EXPORTS_DIR
)

client = TestClient(app)


def test_local_office_status():
    status = get_local_office_status()
    assert status["status"] == "ready"
    assert "Self-Hosted" in status["engine"]
    assert "docx" in status["supported_document_formats"]
    assert "xlsx" in status["supported_spreadsheet_formats"]
    assert os.path.exists(status["exports_directory"])


def test_local_office_status_endpoint():
    res = client.get("/api/local/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "engine" in data
    assert "exports_directory" in data


def test_markdown_to_html_rendering():
    md = (
        "# Title\n\n"
        "## Subtitle\n\n"
        "This is **bold** and *italic* text.\n\n"
        "- Bullet 1\n"
        "- Bullet 2\n\n"
        "| Col A | Col B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
    )
    html = markdown_to_html(md, title="Test Render")
    assert "<title>Test Render</title>" in html
    assert "<h1>Title</h1>" in html
    assert "<h2>Subtitle</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert '<table class="data-table">' in html
    assert "<th>Col A</th>" in html
    assert "<td>1</td>" in html


def test_generate_local_doc_docx():
    content = "## Project Plan\n\n- Task 1: Initialize server\n- Task 2: Configure LibreOffice"
    res = generate_local_doc(content, title="VPS Deployment Plan", format="docx")
    assert res["success"] is True
    assert res["format"] == "DOCX"
    assert os.path.exists(res["filepath"])
    assert res["download_url"].startswith("/api/download/")
    assert res["size_bytes"] > 0

    # Cleanup
    if os.path.exists(res["filepath"]):
        os.remove(res["filepath"])


def test_generate_local_doc_pdf_mocked():
    mock_conv = {
        "success": True,
        "output_path": os.path.join(EXPORTS_DIR, "Mock_Doc.pdf"),
        "filename": "Mock_Doc.pdf",
        "format": "pdf",
        "size_bytes": 1024,
        "size_human": "1.0 KB"
    }
    # Touch mock file
    with open(mock_conv["output_path"], "wb") as f:
        f.write(b"%PDF-1.4 mock pdf content")

    with patch("services.local_office.is_libreoffice_available", return_value=True), \
         patch("services.local_office.convert_with_libreoffice", return_value=mock_conv):
        res = generate_local_doc("Test PDF content", title="Mock Doc", format="pdf")
        assert res["success"] is True
        assert res["format"] == "PDF"
        assert res["download_url"] == "/api/download/Mock_Doc.pdf"

    if os.path.exists(mock_conv["output_path"]):
        os.remove(mock_conv["output_path"])


def test_generate_local_spreadsheet_xlsx():
    markdown_table = (
        "| Item | Quantity | Price |\n"
        "|---|---|---|\n"
        "| Server RAM 64GB | 2 | $300 |\n"
        "| NVMe SSD 1TB | 4 | $400 |\n"
    )
    res = generate_local_spreadsheet(markdown_table, title="Hardware Budget", format="xlsx")
    assert res["success"] is True
    assert res["format"] == "XLSX"
    assert res["rows_written"] == 3
    assert os.path.exists(res["filepath"])
    assert res["download_url"].startswith("/api/download/")

    if os.path.exists(res["filepath"]):
        os.remove(res["filepath"])


def test_generate_local_spreadsheet_csv():
    matrix = [["A", "B", "C"], ["1", "2", "3"]]
    res = generate_local_spreadsheet(matrix, title="Matrix Export", format="csv")
    assert res["success"] is True
    assert res["format"] == "CSV"
    assert res["rows_written"] == 2
    assert os.path.exists(res["filepath"])

    if os.path.exists(res["filepath"]):
        os.remove(res["filepath"])


def test_local_export_doc_endpoint():
    res = client.post("/api/local/export/doc", data={
        "title": "API Test Doc",
        "content": "This is generated via the local export endpoint."
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["format"] == "DOCX"
    assert "download_url" in data
    assert os.path.exists(data["filepath"])

    if os.path.exists(data["filepath"]):
        os.remove(data["filepath"])


def test_local_export_sheet_endpoint():
    res = client.post("/api/local/export/sheet", data={
        "title": "API Test Sheet",
        "content": "| Header 1 | Header 2 |\n| Val 1 | Val 2 |"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["format"] == "XLSX"
    assert "download_url" in data
    assert os.path.exists(data["filepath"])

    if os.path.exists(data["filepath"]):
        os.remove(data["filepath"])


def test_local_download_endpoint_and_traversal_protection():
    # 1. Create a dummy file in exports
    ensure_exports_dir()
    dummy_name = "test_traversal_check.txt"
    dummy_path = os.path.join(EXPORTS_DIR, dummy_name)
    with open(dummy_path, "w", encoding="utf-8") as f:
        f.write("Safe export content")

    try:
        # Download via /api/download/{filename}
        res = client.get(f"/api/download/{dummy_name}")
        assert res.status_code == 200
        assert res.text == "Safe export content"

        # Download via /api/local/export/download/{filename}
        res2 = client.get(f"/api/local/export/download/{dummy_name}")
        assert res2.status_code == 200
        assert res2.text == "Safe export content"

        # Directory traversal blocked
        bad_res = client.get("/api/download/../../etc/passwd")
        assert bad_res.status_code in (404, 422)
    finally:
        if os.path.exists(dummy_path):
            os.remove(dummy_path)


def test_process_chat_query_local_document_creation():
    with patch("main.is_google_authenticated", return_value={"authenticated": False}), \
         patch("main.execute_gemini_transformation", return_value="## Lesson Notes\n1. Photosynthesis\n2. Respiration"):

        res = client.post("/api/process", data={
            "prompt": "create a document for biology lesson notes",
            "custom_api_key": "test_key"
        })

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["export_file"] is not None
        assert data["export_file"]["format"] in ("DOCX", "PDF")
        assert "download_url" in data["export_file"]
        assert "Local Document Created" in data["result"]
        assert "Download Document" in data["result"]

        # Clean generated file
        if data["export_file"].get("filepath") and os.path.exists(data["export_file"]["filepath"]):
            os.remove(data["export_file"]["filepath"])


def test_process_chat_query_local_spreadsheet_creation():
    sample_table = "| Model | RAM | Storage |\n|---|---|---|\n| Dell XPS | 32GB | 1TB |"
    with patch("main.is_google_authenticated", return_value={"authenticated": False}), \
         patch("main.execute_gemini_transformation", return_value=sample_table):

        res = client.post("/api/process", data={
            "prompt": "create spreadsheet for laptop specs",
            "custom_api_key": "test_key"
        })

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["export_file"] is not None
        assert data["export_file"]["format"] in ("XLSX", "ODS", "CSV")
        assert "download_url" in data["export_file"]
        assert "Local Spreadsheet Created" in data["result"]
        assert "Download Spreadsheet" in data["result"]

        if data["export_file"].get("filepath") and os.path.exists(data["export_file"]["filepath"]):
            os.remove(data["export_file"]["filepath"])


def test_system_instruction_empowers_local_office_engine():
    from main import get_local_office_tools
    with patch("main.is_google_authenticated", return_value={"authenticated": False}), \
         patch("main.execute_gemini_transformation") as mock_gemini:
        mock_gemini.return_value = "### Document\nSample content"

        res = client.post("/api/process", data={
            "prompt": "create a document for quarterly planning",
            "custom_api_key": "test_key"
        })
        assert res.status_code == 200
        assert mock_gemini.called
        system_inst = mock_gemini.call_args.kwargs["system_instruction"]

        # Ensure local office engine instructions are present
        assert "self-hosted local office generation engine" in system_inst
        assert "POST /api/local/export/doc" in system_inst
        assert "POST /api/local/export/sheet" in system_inst
        assert "POST /api/local/export/pdf" in system_inst
        assert "NEVER say you cannot create files locally" in system_inst
        assert "Always prefer self-hosted local office generation" in system_inst


def test_get_local_office_tools_declarations():
    from main import get_local_office_tools
    tools = get_local_office_tools()
    assert len(tools) == 1
    func_decls = tools[0].function_declarations
    assert len(func_decls) == 3
    names = [f.name for f in func_decls]
    assert "export_local_doc" in names
    assert "export_local_sheet" in names
    assert "export_local_pdf" in names


def test_process_chat_query_creates_local_pdf():
    with patch("main.is_google_authenticated", return_value={"authenticated": False}), \
         patch("main.execute_gemini_transformation", return_value="# Executive Report\n\nQ3 Financial Summary"):

        res = client.post("/api/process", data={
            "prompt": "create a pdf for executive summary",
            "custom_api_key": "test_key"
        })

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["export_file"] is not None
        assert "download_url" in data["export_file"]
        # When PDF format is requested, local engine processes doc or pdf
        assert data["export_file"]["format"] in ("PDF", "DOCX")
        assert "Local PDF Created" in data["result"] or "Local Document Created" in data["result"]

        if data["export_file"].get("filepath") and os.path.exists(data["export_file"]["filepath"]):
            os.remove(data["export_file"]["filepath"])

