"""
Momento Local Office Service.
Self-hosted document and spreadsheet generation engine powered by:
- Python Native: python-docx, openpyxl, pandas, csv
- Headless LibreOffice CLI: libreoffice / soffice --headless for PDF, DOCX, ODS conversion
Runs on Ubuntu VPS without external Google Workspace cloud API dependencies.
"""

import os
import re
import csv
import io
import time
import shutil
import logging
import subprocess
from typing import Dict, Any, List, Optional, Union

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from services.file_exporter import (
    compile_docx,
    compile_xlsx,
    compile_csv,
    compile_text,
    parse_text_to_matrix,
    parse_markdown_tables,
    format_bytes_human,
)

logger = logging.getLogger("momento.local_office")

# Dedicated storage directory for local exports (/var/www/momento/exports on VPS)
EXPORTS_DIR = os.getenv(
    "MOMENTO_EXPORTS_DIR",
    os.getenv("EXPORTS_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "exports")))
)


def ensure_exports_dir() -> str:
    """Ensure exports directory exists and return absolute path."""
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    return EXPORTS_DIR


def get_libreoffice_command() -> Optional[str]:
    """
    Locate the headless LibreOffice / soffice binary across platforms:
    1. Custom environment variable LIBREOFFICE_PATH
    2. System PATH (libreoffice, soffice)
    3. Common Linux paths (/usr/bin/libreoffice, /usr/bin/soffice)
    4. Common Windows paths (C:\\Program Files\\LibreOffice\\program\\soffice.exe)
    """
    env_path = os.getenv("LIBREOFFICE_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path

    # Check PATH
    for cmd in ["libreoffice", "soffice"]:
        found = shutil.which(cmd)
        if found:
            return found

    # Check standard Linux binary paths
    linux_paths = [
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/usr/local/bin/libreoffice",
        "/snap/bin/libreoffice",
    ]
    for p in linux_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    # Check standard Windows paths
    windows_paths = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for p in windows_paths:
        if os.path.isfile(p):
            return p

    return None


def is_libreoffice_available() -> bool:
    """Return True if headless LibreOffice is installed and executable."""
    return get_libreoffice_command() is not None


def get_libreoffice_version() -> Optional[str]:
    """Retrieve installed LibreOffice version string."""
    cmd = get_libreoffice_command()
    if not cmd:
        return None
    try:
        proc = subprocess.run(
            [cmd, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=True
        )
        return proc.stdout.strip()
    except Exception as e:
        logger.warning("Failed to determine LibreOffice version: %s", e)
        return "LibreOffice (version unknown)"


def convert_with_libreoffice(
    input_path: str,
    target_format: str,
    output_dir: Optional[str] = None,
    timeout: int = 45
) -> Dict[str, Any]:
    """
    Convert a document or spreadsheet using headless LibreOffice.
    Example formats: 'pdf', 'docx', 'ods', 'xlsx', 'html', 'txt'.
    """
    cmd = get_libreoffice_command()
    if not cmd:
        return {
            "success": False,
            "error": "Headless LibreOffice is not installed on this system. Please install libreoffice via apt."
        }

    if not os.path.isfile(input_path):
        return {
            "success": False,
            "error": f"Input file not found: {input_path}"
        }

    target_dir = output_dir or os.path.dirname(input_path) or ensure_exports_dir()
    os.makedirs(target_dir, exist_ok=True)

    input_filename = os.path.basename(input_path)
    base_name, _ = os.path.splitext(input_filename)
    expected_output = os.path.join(target_dir, f"{base_name}.{target_format.lower()}")

    # Command arguments for robust headless conversion without GUI/user prompts
    run_args = [
        cmd,
        "--headless",
        "--invisible",
        "--nodefault",
        "--nofirststartwizard",
        "--nolockcheck",
        "--nologo",
        "--convert-to",
        target_format.lower(),
        input_path,
        "--outdir",
        target_dir
    ]

    try:
        logger.info("Executing headless LibreOffice conversion: %s -> %s", input_path, target_format)
        proc = subprocess.run(
            run_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )

        if proc.returncode != 0:
            err_msg = proc.stderr.strip() or proc.stdout.strip() or f"Exited with code {proc.returncode}"
            logger.error("LibreOffice conversion failed: %s", err_msg)
            return {
                "success": False,
                "error": f"LibreOffice conversion error: {err_msg}"
            }

        if not os.path.exists(expected_output):
            # Check if LibreOffice generated with slightly different name
            matches = [f for f in os.listdir(target_dir) if f.startswith(base_name) and f.endswith(f".{target_format.lower()}")]
            if matches:
                expected_output = os.path.join(target_dir, matches[0])
            else:
                return {
                    "success": False,
                    "error": f"Conversion completed, but output file '{expected_output}' was not generated."
                }

        file_size = os.path.getsize(expected_output)
        return {
            "success": True,
            "output_path": expected_output,
            "filename": os.path.basename(expected_output),
            "format": target_format.lower(),
            "size_bytes": file_size,
            "size_human": format_bytes_human(file_size)
        }
    except subprocess.TimeoutExpired:
        logger.error("LibreOffice conversion timed out after %ds for %s", timeout, input_path)
        return {"success": False, "error": f"LibreOffice conversion timed out after {timeout} seconds."}
    except Exception as e:
        logger.exception("Unexpected error during LibreOffice conversion: %s", e)
        return {"success": False, "error": f"LibreOffice execution failed: {str(e)}"}


def markdown_to_html(markdown_text: str, title: Optional[str] = None) -> str:
    """
    Convert Markdown content to clean, beautifully styled HTML document.
    Suitable for direct viewing or conversion to PDF/DOCX via headless LibreOffice.
    """
    doc_title = title or "Momento Document"
    lines = markdown_text.split("\n")
    html_body_lines = []

    in_table = False
    table_lines = []

    def flush_table():
        nonlocal table_lines
        if not table_lines:
            return
        matrix = []
        for tl in table_lines:
            cells = [c.strip() for c in tl.split("|")[1:-1]]
            matrix.append(cells)
        if matrix:
            tbl_html = ['<table class="data-table">']
            for r_idx, row in enumerate(matrix):
                tbl_html.append("  <tr>")
                for cell in row:
                    tag = "th" if r_idx == 0 else "td"
                    # clean markdown bold
                    clean_cell = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", cell)
                    tbl_html.append(f"    <{tag}>{clean_cell}</{tag}>")
                tbl_html.append("  </tr>")
            tbl_html.append("</table>")
            html_body_lines.append("\n".join(tbl_html))
        table_lines = []

    for line in lines:
        stripped = line.strip()

        # Markdown Table Detection
        if stripped.startswith("|") and stripped.endswith("|"):
            stripped_mid = stripped.replace("|", "").replace("-", "").replace(":", "").strip()
            if not stripped_mid:
                continue
            in_table = True
            table_lines.append(stripped)
            continue
        elif in_table:
            in_table = False
            flush_table()

        if not stripped:
            html_body_lines.append("<p>&nbsp;</p>")
            continue

        # Headings
        if stripped.startswith("### "):
            html_body_lines.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            html_body_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            html_body_lines.append(f"<h1>{stripped[2:]}</h1>")
        # Bullet list items
        elif stripped.startswith("- ") or stripped.startswith("* "):
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", stripped[2:])
            html_body_lines.append(f"<ul><li>{content}</li></ul>")
        # Numbered list items
        elif re.match(r"^\d+\.\s", stripped):
            text_part = re.sub(r"^\d+\.\s", "", stripped)
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text_part)
            html_body_lines.append(f"<ol><li>{content}</li></ol>")
        # Blockquote
        elif stripped.startswith("> "):
            content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", stripped[2:])
            html_body_lines.append(f"<blockquote>{content}</blockquote>")
        else:
            # Inline bold/italic conversion
            clean_p = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", stripped)
            clean_p = re.sub(r"\*(.*?)\*", r"<em>\1</em>", clean_p)
            html_body_lines.append(f"<p>{clean_p}</p>")

    if in_table:
        flush_table()

    body_html = "\n".join(html_body_lines)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{doc_title}</title>
<style>
  @page {{
    margin: 1in;
    size: letter;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    line-height: 1.6;
    margin: 40px auto;
    max-width: 850px;
    padding: 0 20px;
  }}
  h1 {{
    color: #1e3a8a;
    font-size: 26px;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    margin-top: 24px;
  }}
  h2 {{
    color: #1e3a8a;
    font-size: 20px;
    margin-top: 20px;
  }}
  h3 {{
    color: #334155;
    font-size: 16px;
    margin-top: 16px;
  }}
  p {{
    margin: 8px 0;
  }}
  .meta-tag {{
    color: #64748b;
    font-size: 12px;
    font-style: italic;
    margin-bottom: 20px;
  }}
  table.data-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    font-size: 13px;
  }}
  table.data-table th {{
    background-color: #1e3a8a;
    color: #ffffff;
    font-weight: 600;
    text-align: left;
    padding: 10px 12px;
    border: 1px solid #cbd5e1;
  }}
  table.data-table td {{
    padding: 8px 12px;
    border: 1px solid #e2e8f0;
  }}
  table.data-table tr:nth-child(even) {{
    background-color: #f8fafc;
  }}
  blockquote {{
    border-left: 4px solid #6366f1;
    margin: 16px 0;
    padding: 8px 16px;
    background-color: #f1f5f9;
    color: #475569;
  }}
  ul, ol {{
    padding-left: 24px;
    margin: 8px 0;
  }}
  li {{
    margin-bottom: 4px;
  }}
</style>
</head>
<body>
  <div class="meta-tag">Generated by Momento AI Local Engine • {time.strftime('%B %d, %Y')}</div>
  {body_html}
</body>
</html>
"""
    return full_html


def generate_local_doc(
    content: str,
    title: Optional[str] = None,
    format: str = "docx",
    output_filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a formatted document locally on the server (.docx or .pdf).
    1. If format is 'docx', generates cleanly using python-docx.
    2. If format is 'pdf', generates .docx or .html and converts to .pdf via headless LibreOffice.
    """
    exports_dir = ensure_exports_dir()
    safe_title = (title or "").strip() or f"Document - {time.strftime('%Y-%m-%d')}"
    target_format = format.lower().strip() if format else "docx"

    # Sanitize base filename
    slug = re.sub(r"[^\w\s-]", "", safe_title).strip().replace(" ", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = output_filename or f"{slug}_{timestamp}"
    if base_name.endswith(f".{target_format}"):
        base_name = base_name[:-len(f".{target_format}")]

    docx_path = os.path.join(exports_dir, f"{base_name}.docx")

    try:
        # Compile clean docx first
        compile_docx(content=content or "", output_path=docx_path, title=safe_title)

        if target_format == "pdf":
            # Convert docx to pdf via LibreOffice
            if is_libreoffice_available():
                conv_res = convert_with_libreoffice(docx_path, "pdf", output_dir=exports_dir)
                if conv_res.get("success"):
                    pdf_path = conv_res["output_path"]
                    pdf_size = os.path.getsize(pdf_path)
                    pdf_filename = os.path.basename(pdf_path)
                    return {
                        "success": True,
                        "service": "Local Office",
                        "engine": "LibreOffice Headless",
                        "file_id": pdf_filename,
                        "filename": pdf_filename,
                        "format": "PDF",
                        "media_type": "application/pdf",
                        "filepath": pdf_path,
                        "url": f"/api/download/{pdf_filename}",
                        "download_url": f"/api/download/{pdf_filename}",
                        "size_bytes": pdf_size,
                        "size_human": format_bytes_human(pdf_size),
                        "title": safe_title,
                        "message": f"Successfully generated local PDF: '{safe_title}'"
                    }
                else:
                    logger.warning("LibreOffice PDF conversion failed; falling back to DOCX: %s", conv_res.get("error"))

            # If LibreOffice is not installed, return docx with graceful informative notice
            docx_size = os.path.getsize(docx_path)
            docx_filename = os.path.basename(docx_path)
            return {
                "success": True,
                "service": "Local Office",
                "engine": "python-docx",
                "file_id": docx_filename,
                "filename": docx_filename,
                "format": "DOCX",
                "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "filepath": docx_path,
                "url": f"/api/download/{docx_filename}",
                "download_url": f"/api/download/{docx_filename}",
                "size_bytes": docx_size,
                "size_human": format_bytes_human(docx_size),
                "title": safe_title,
                "message": f"Generated DOCX document '{safe_title}' (Install LibreOffice on VPS for automatic PDF conversion)."
            }

        # Default DOCX
        docx_size = os.path.getsize(docx_path)
        docx_filename = os.path.basename(docx_path)
        return {
            "success": True,
            "service": "Local Office",
            "engine": "python-docx",
            "file_id": docx_filename,
            "filename": docx_filename,
            "format": "DOCX",
            "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "filepath": docx_path,
            "url": f"/api/download/{docx_filename}",
            "download_url": f"/api/download/{docx_filename}",
            "size_bytes": docx_size,
            "size_human": format_bytes_human(docx_size),
            "title": safe_title,
            "message": f"Successfully created local Word document: '{safe_title}'"
        }
    except Exception as e:
        logger.exception("Failed to generate local document: %s", e)
        return {
            "success": False,
            "service": "Local Office",
            "error": f"Failed to generate local document: {str(e)}",
            "message": f"Failed to generate local document: {str(e)}"
        }


def generate_local_spreadsheet(
    content_or_matrix: Union[str, List[List[Any]]],
    title: Optional[str] = None,
    format: str = "xlsx",
    output_filename: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a formatted spreadsheet locally on the server (.xlsx, .ods, or .csv).
    1. If format is 'xlsx', generates enterprise styled Excel workbook via openpyxl.
    2. If format is 'ods', generates .xlsx first and converts to .ods via headless LibreOffice (or openpyxl).
    3. If format is 'csv', outputs UTF-8 BOM CSV.
    """
    exports_dir = ensure_exports_dir()
    safe_title = (title or "").strip() or f"Spreadsheet - {time.strftime('%Y-%m-%d')}"
    target_format = format.lower().strip() if format else "xlsx"

    slug = re.sub(r"[^\w\s-]", "", safe_title).strip().replace(" ", "_")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    base_name = output_filename or f"{slug}_{timestamp}"
    if base_name.endswith(f".{target_format}"):
        base_name = base_name[:-len(f".{target_format}")]

    # Parse data into matrix
    if isinstance(content_or_matrix, list):
        matrix = content_or_matrix
    else:
        matrix = parse_text_to_matrix(str(content_or_matrix or ""))

    if not matrix:
        matrix = [["Data", "Output"], ["1", "Empty spreadsheet"]]

    try:
        if target_format == "csv":
            csv_path = os.path.join(exports_dir, f"{base_name}.csv")
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                for row in matrix:
                    writer.writerow(row)
            file_size = os.path.getsize(csv_path)
            csv_filename = os.path.basename(csv_path)
            return {
                "success": True,
                "service": "Local Office",
                "engine": "python-csv",
                "file_id": csv_filename,
                "filename": csv_filename,
                "format": "CSV",
                "media_type": "text/csv",
                "filepath": csv_path,
                "url": f"/api/download/{csv_filename}",
                "download_url": f"/api/download/{csv_filename}",
                "size_bytes": file_size,
                "size_human": format_bytes_human(file_size),
                "title": safe_title,
                "rows_written": len(matrix),
                "message": f"Successfully created local CSV: '{safe_title}'"
            }

        # Build styled XLSX
        xlsx_path = os.path.join(exports_dir, f"{base_name}.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = safe_title[:31]

        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        data_font = Font(name="Calibri", size=10)
        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )
        align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)

        for row_idx, row in enumerate(matrix, start=1):
            for col_idx, cell_value in enumerate(row, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=cell_value)
                cell.border = thin_border
                cell.alignment = align_left

                if row_idx == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                else:
                    cell.font = data_font
                    if row_idx % 2 == 0:
                        cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)

        # Freeze top header row
        ws.freeze_panes = "A2"
        wb.save(xlsx_path)

        if target_format == "ods":
            # Convert XLSX to ODS via headless LibreOffice
            if is_libreoffice_available():
                conv_res = convert_with_libreoffice(xlsx_path, "ods", output_dir=exports_dir)
                if conv_res.get("success"):
                    ods_path = conv_res["output_path"]
                    ods_size = os.path.getsize(ods_path)
                    ods_filename = os.path.basename(ods_path)
                    return {
                        "success": True,
                        "service": "Local Office",
                        "engine": "LibreOffice Headless",
                        "file_id": ods_filename,
                        "filename": ods_filename,
                        "format": "ODS",
                        "media_type": "application/vnd.oasis.opendocument.spreadsheet",
                        "filepath": ods_path,
                        "url": f"/api/download/{ods_filename}",
                        "download_url": f"/api/download/{ods_filename}",
                        "size_bytes": ods_size,
                        "size_human": format_bytes_human(ods_size),
                        "title": safe_title,
                        "rows_written": len(matrix),
                        "message": f"Successfully created local ODS spreadsheet: '{safe_title}'"
                    }
                else:
                    logger.warning("LibreOffice ODS conversion failed; falling back to XLSX: %s", conv_res.get("error"))

            # Fallback to XLSX if LibreOffice is not installed
            xlsx_size = os.path.getsize(xlsx_path)
            xlsx_filename = os.path.basename(xlsx_path)
            return {
                "success": True,
                "service": "Local Office",
                "engine": "openpyxl",
                "file_id": xlsx_filename,
                "filename": xlsx_filename,
                "format": "XLSX",
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "filepath": xlsx_path,
                "url": f"/api/download/{xlsx_filename}",
                "download_url": f"/api/download/{xlsx_filename}",
                "size_bytes": xlsx_size,
                "size_human": format_bytes_human(xlsx_size),
                "title": safe_title,
                "rows_written": len(matrix),
                "message": f"Generated XLSX spreadsheet '{safe_title}' (Install LibreOffice on VPS for native ODS format)."
            }

        # Default XLSX
        xlsx_size = os.path.getsize(xlsx_path)
        xlsx_filename = os.path.basename(xlsx_path)
        return {
            "success": True,
            "service": "Local Office",
            "engine": "openpyxl",
            "file_id": xlsx_filename,
            "filename": xlsx_filename,
            "format": "XLSX",
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "filepath": xlsx_path,
            "url": f"/api/download/{xlsx_filename}",
            "download_url": f"/api/download/{xlsx_filename}",
            "size_bytes": xlsx_size,
            "size_human": format_bytes_human(xlsx_size),
            "title": safe_title,
            "rows_written": len(matrix),
            "message": f"Successfully created local spreadsheet: '{safe_title}'"
        }
    except Exception as e:
        logger.exception("Failed to generate local spreadsheet: %s", e)
        return {
            "success": False,
            "service": "Local Office",
            "error": f"Failed to generate local spreadsheet: {str(e)}",
            "message": f"Failed to generate local spreadsheet: {str(e)}"
        }


def get_local_office_status() -> Dict[str, Any]:
    """Inspect local office engine availability, LibreOffice version, and storage health."""
    lo_cmd = get_libreoffice_command()
    lo_avail = lo_cmd is not None
    lo_ver = get_libreoffice_version() if lo_avail else None
    exports_dir = ensure_exports_dir()

    return {
        "status": "ready",
        "engine": "Momento Self-Hosted Office Engine",
        "libreoffice_installed": lo_avail,
        "libreoffice_command": lo_cmd,
        "libreoffice_version": lo_ver,
        "supported_document_formats": ["docx", "pdf", "html", "txt"] if lo_avail else ["docx", "html", "txt"],
        "supported_spreadsheet_formats": ["xlsx", "ods", "csv"] if lo_avail else ["xlsx", "csv"],
        "exports_directory": exports_dir,
        "mode": "self_hosted_vps"
    }
