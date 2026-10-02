"""
Google Workspace Integration Service (Google Docs v1 & Google Sheets v4).
Allows Momento to authenticate via OAuth2 and export generated outputs
directly to new Google Documents and Google Spreadsheets.
"""

import os
import re
import json
import time
import csv
import io
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("momento.google_workspace")

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file"
]

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOKEN_FILE = os.path.abspath(os.getenv("GOOGLE_TOKEN_FILE", os.path.join(BASE_DIR, "google_token.json")))
CLIENT_SECRETS_FILE = os.path.abspath(os.getenv("GOOGLE_CLIENT_SECRETS_FILE", os.path.join(BASE_DIR, "client_secret.json")))


def ensure_google_client_secrets_file() -> bool:
    """
    Ensure client_secret.json exists on disk.
    If client_secret.json doesn't exist locally, dynamically create it from
    the GOOGLE_CLIENT_SECRET_JSON environment variable (essential for cloud platforms like Render).
    """
    if os.path.exists(CLIENT_SECRETS_FILE):
        return True

    env_json = os.getenv("GOOGLE_CLIENT_SECRET_JSON") or os.getenv("GOOGLE_CLIENT_SECRETS_JSON")
    if env_json and env_json.strip():
        try:
            content = env_json.strip()
            # Strip outer wrapping quotes if added by shell or env managers
            if (content.startswith("'") and content.endswith("'")) or (content.startswith('"') and content.endswith('"') and not content.startswith('{"')):
                content = content[1:-1].strip()

            try:
                parsed = json.loads(content)
                content = json.dumps(parsed, indent=2)
            except Exception:
                pass

            target_dir = os.path.dirname(CLIENT_SECRETS_FILE)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

            with open(CLIENT_SECRETS_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception:
            return False
    return False


# Auto-create if environment variable is present on import
ensure_google_client_secrets_file()


def get_google_credentials():
    """Retrieve valid user Google credentials from token file or refresh if needed."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        creds = None
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE)
            except Exception:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        if creds and creds.valid:
            return creds
        return None
    except Exception:
        return None


def is_google_authenticated() -> Dict[str, Any]:
    """Check if the user has an active Google Workspace OAuth session."""
    ensure_google_client_secrets_file()
    creds = get_google_credentials()
    if creds:
        return {
            "authenticated": True,
            "has_token_file": True,
            "message": "Google Workspace account is connected."
        }
    return {
        "authenticated": False,
        "has_token_file": os.path.exists(TOKEN_FILE),
        "has_secrets_file": os.path.exists(CLIENT_SECRETS_FILE),
        "message": "Google Workspace not connected."
    }


def clean_cell_text(cell: Any) -> str:
    """Strip markdown formatting, links, backticks, and extra spaces from cell contents."""
    if not isinstance(cell, str):
        return cell if cell is not None else ""
    text = cell.strip()
    if not text:
        return ""
    # Convert markdown links [Label](url) -> Label
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Strip bold and italics: **text**, __text__, `text`
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    # Strip single asterisks/underscores wrapping text
    text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)
    return text.strip()


def parse_text_to_matrix(text: str) -> List[List[str]]:
    """Convert Markdown tables, CSV text, or lines into a normalized 2D matrix for Google Sheets."""
    if not text:
        return [["Data", ""]]

    lines = [l.strip() for l in text.strip().split("\n")]
    table_rows = []

    # 1. First pass: look for markdown table rows
    for line in lines:
        if not line:
            continue
        # Temporarily mask escaped pipes \|
        masked = line.replace(r"\|", "__ESCAPED_PIPE__")

        # Check if line looks like a markdown table row (has pipe)
        if "|" in masked:
            stripped_pipes = masked.replace("|", "").strip()
            # Skip separator rows like |---|---| or :---:|:---
            if stripped_pipes and set(stripped_pipes).issubset({"-", ":", " ", "="}):
                continue

            parts = masked.split("|")
            # If line started with |, first part is empty
            if parts and parts[0].strip() == "":
                parts = parts[1:]
            # If line ended with |, last part is empty
            if parts and parts[-1].strip() == "":
                parts = parts[:-1]

            if parts:
                cells = [clean_cell_text(p.replace("__ESCAPED_PIPE__", "|")) for p in parts]
                table_rows.append(cells)

    if table_rows:
        # Normalize rectangular matrix: pad any uneven rows so columns align perfectly
        max_cols = max(len(r) for r in table_rows)
        normalized_table = []
        for row in table_rows:
            if len(row) < max_cols:
                row = row + [""] * (max_cols - len(row))
            normalized_table.append(row)
        return normalized_table

    # 2. Check for CSV format if comma exists across lines
    csv_candidates = [l for l in lines if l]
    if any("," in l for l in csv_candidates):
        try:
            reader = csv.reader(io.StringIO(text.strip()))
            csv_rows = []
            for row in reader:
                if row:
                    csv_rows.append([clean_cell_text(c) for c in row])
            if csv_rows and max(len(r) for r in csv_rows) > 1:
                max_cols = max(len(r) for r in csv_rows)
                return [r + [""] * (max_cols - len(r)) for r in csv_rows]
        except Exception:
            pass

    # 3. Fallback: check tab-delimited, key-value pairs, or split into rows
    for line_str in lines:
        if not line_str:
            continue
        if "\t" in line_str:
            table_rows.append([clean_cell_text(c) for c in line_str.split("\t")])
        elif ":" in line_str and not line_str.lower().startswith(("http://", "https://", "###", "##", "#")):
            clean_kv = line_str.lstrip("-*• ").strip()
            if ":" in clean_kv:
                parts = [clean_cell_text(p) for p in clean_kv.split(":", 1)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    table_rows.append(parts)
                    continue
            table_rows.append([clean_cell_text(line_str)])
        else:
            table_rows.append([clean_cell_text(line_str)])

    if table_rows:
        max_cols = max(len(r) for r in table_rows)
        return [r + [""] * (max_cols - len(r)) for r in table_rows]

    return [["Data", text[:500]]]


def create_google_doc(title: str, content: str) -> Dict[str, Any]:
    """Create a new Google Document and populate it with content."""
    creds = get_google_credentials()
    if not creds:
        # Return graceful mock placeholder with clear instructions
        return {
            "success": False,
            "status": "ready_for_credentials",
            "requires_auth": True,
            "service": "Google Docs",
            "title": title,
            "message": "Google Account not linked. Please connect your Google account in settings.",
            "mock_url": f"https://docs.google.com/document/d/mock-doc-{int(time.time())}/edit"
        }

    try:
        from googleapiclient.discovery import build
        docs_service = build("docs", "v1", credentials=creds)

        # 1. Create blank document
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")

        # 2. Insert text content
        clean_content = content.replace("\r\n", "\n")
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": clean_content
                }
            }
        ]
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return {
            "success": True,
            "service": "Google Docs",
            "document_id": doc_id,
            "url": doc_url,
            "title": title,
            "message": f"Successfully created Google Doc: '{title}'"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create Google Doc: {str(e)}"
        }


def create_google_sheet(title: str, data_matrix: Optional[List[List[Any]]] = None, raw_text: Optional[str] = None) -> Dict[str, Any]:
    """Create a new Google Spreadsheet and populate it with a 2D data matrix, applying professional enterprise formatting."""
    creds = get_google_credentials()
    if not creds:
        return {
            "success": False,
            "status": "ready_for_credentials",
            "requires_auth": True,
            "service": "Google Sheets",
            "title": title,
            "message": "Google Account not linked. Please connect your Google account in settings.",
            "mock_url": f"https://docs.google.com/spreadsheets/d/mock-sheet-{int(time.time())}/edit"
        }

    try:
        from googleapiclient.discovery import build
        sheets_service = build("sheets", "v4", credentials=creds)

        # 1. Create spreadsheet
        spreadsheet = sheets_service.spreadsheets().create(
            body={"properties": {"title": title}}
        ).execute()
        spreadsheet_id = spreadsheet.get("spreadsheetId")

        # Extract first sheet ID (defaults to 0 if not explicitly returned)
        sheet_id = 0
        sheets = spreadsheet.get("sheets", [])
        if sheets and isinstance(sheets, list):
            sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)

        # 2. Determine matrix
        matrix = data_matrix
        if not matrix and raw_text:
            matrix = parse_text_to_matrix(raw_text)

        if not matrix:
            matrix = [["Data"], ["No tabular data found"]]

        # Clean cells and normalize matrix dimensions so all rows have uniform column count
        max_cols = max((len(r) for r in matrix), default=1)
        normalized_matrix = []
        for r in matrix:
            cleaned_row = [clean_cell_text(c) if isinstance(c, str) else c for c in r]
            if len(cleaned_row) < max_cols:
                cleaned_row.extend([""] * (max_cols - len(cleaned_row)))
            normalized_matrix.append(cleaned_row)
        matrix = normalized_matrix

        # 3. Write data to Sheet1
        value_range_body = {
            "values": matrix
        }
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="USER_ENTERED",
            body=value_range_body
        ).execute()

        # 4. Enterprise-Grade Formatting & Auto-Fit Column Layout
        num_rows = len(matrix)
        num_cols = max_cols

        format_requests = [
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {
                            "frozenRowCount": 1
                        }
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            },
            # Style header row (Dark Slate #1E293B, Bold White Text, Wrap, Left/Middle Align)
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {
                                "red": 0.12,
                                "green": 0.16,
                                "blue": 0.23
                            },
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {
                                "foregroundColor": {
                                    "red": 1.0,
                                    "green": 1.0,
                                    "blue": 1.0
                                },
                                "fontSize": 11,
                                "bold": True
                            },
                            "wrapStrategy": "WRAP"
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)"
                }
            }
        ]

        if num_rows > 1:
            # Data rows formatting: Text wrap (no clipped text), vertical middle alignment, clean 10pt font
            format_requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": num_rows,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                            "textFormat": {
                                "fontSize": 10
                            }
                        }
                    },
                    "fields": "userEnteredFormat(verticalAlignment,wrapStrategy,textFormat.fontSize)"
                }
            })
            # Alternating subtle row banding (Zebra striping)
            format_requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": num_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "rowProperties": {
                            "headerColor": {
                                "red": 0.12,
                                "green": 0.16,
                                "blue": 0.23
                            },
                            "firstBandColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0
                            },
                            "secondBandColor": {
                                "red": 0.96,
                                "green": 0.97,
                                "blue": 0.98
                            }
                        }
                    }
                }
            })

        # Auto-resize column widths across all columns so text isn't cramped or cut off
        format_requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": num_cols
                }
            }
        })

        try:
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": format_requests}
            ).execute()
        except Exception as fmt_err:
            logger.warning("Could not apply enterprise formatting to sheet %s: %s", spreadsheet_id, fmt_err)

        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        return {
            "success": True,
            "service": "Google Sheets",
            "spreadsheet_id": spreadsheet_id,
            "url": sheet_url,
            "title": title,
            "rows_written": len(matrix),
            "message": f"Successfully created Google Sheet: '{title}'"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create Google Sheet: {str(e)}"
        }



def list_google_drive_files(
    file_type: Optional[str] = None,
    query: Optional[str] = None,
    page_size: int = 50
) -> Dict[str, Any]:
    """Search and list Google Drive files (Google Sheets, Google Docs, etc.)."""
    creds = get_google_credentials()
    if not creds:
        return {
            "success": False,
            "requires_auth": True,
            "message": "Google Workspace is not connected. Please connect your Google account in settings."
        }

    try:
        from googleapiclient.discovery import build
        drive_service = build("drive", "v3", credentials=creds)

        query_parts = ["trashed = false"]

        type_lower = (file_type or "").lower().strip()
        if type_lower in ["sheet", "sheets", "spreadsheet", "spreadsheets"]:
            query_parts.append("(mimeType = 'application/vnd.google-apps.spreadsheet' or mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or mimeType = 'application/vnd.ms-excel' or mimeType = 'text/csv')")
        elif type_lower in ["doc", "docs", "document", "documents"]:
            query_parts.append("(mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or mimeType = 'application/pdf' or mimeType = 'text/plain')")
        elif type_lower in ["folder", "folders"]:
            query_parts.append("mimeType = 'application/vnd.google-apps.folder'")

        if query and query.strip():
            safe_q = query.strip()
            # Strip out any strict or biased filters for 'Momento Sheet' or default templates
            # so the user's real files are always retrieved dynamically.
            clean_search = re.sub(r"\b(?:momento\s*(?:sheet|doc|export)?|template|default)\b", "", safe_q, flags=re.IGNORECASE).strip()
            if clean_search:
                escaped_q = clean_search.replace("'", "\\'")
                query_parts.append(f"name contains '{escaped_q}'")

        q_str = " and ".join(query_parts)

        # Primary listing attempt with formatted filters
        results = drive_service.files().list(
            q=q_str,
            pageSize=page_size,
            fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
            orderBy="modifiedTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        raw_files = results.get("files", [])

        # Broad listing fallback: if specific filter or mimeType yields 0 files,
        # query broadly for all non-trashed files so existing user files are always retrieved
        if not raw_files and (type_lower or (query and query.strip())):
            try:
                fallback_res = drive_service.files().list(
                    q="trashed = false",
                    pageSize=page_size,
                    fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
                    orderBy="modifiedTime desc",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                fallback_files = fallback_res.get("files", [])
                if fallback_files:
                    if type_lower in ["sheet", "sheets", "spreadsheet", "spreadsheets"]:
                        matching = [
                            f for f in fallback_files
                            if "spreadsheet" in f.get("mimeType", "").lower()
                            or "sheet" in f.get("mimeType", "").lower()
                            or f.get("name", "").lower().endswith((".xlsx", ".xls", ".csv"))
                        ]
                        raw_files = matching if matching else fallback_files
                    elif type_lower in ["doc", "docs", "document", "documents"]:
                        matching = [
                            f for f in fallback_files
                            if "document" in f.get("mimeType", "").lower()
                            or "word" in f.get("mimeType", "").lower()
                            or f.get("name", "").lower().endswith((".docx", ".doc", ".pdf", ".txt"))
                        ]
                        raw_files = matching if matching else fallback_files
                    elif type_lower in ["folder", "folders"]:
                        matching = [
                            f for f in fallback_files
                            if f.get("mimeType") == "application/vnd.google-apps.folder" or "folder" in f.get("mimeType", "").lower()
                        ]
                        raw_files = matching if matching else fallback_files
                    else:
                        raw_files = fallback_files
            except Exception:
                pass

        formatted_files = []
        for f in raw_files:
            mime = f.get("mimeType", "").lower()
            fname = f.get("name", "").lower()
            if mime == "application/vnd.google-apps.folder" or "folder" in mime:
                type_label = "Folder"
                default_link = f"https://drive.google.com/drive/folders/{f.get('id')}"
            elif "spreadsheet" in mime or "sheet" in mime or fname.endswith((".xlsx", ".xls", ".csv")):
                type_label = "Google Sheet"
                default_link = f"https://docs.google.com/spreadsheets/d/{f.get('id')}/edit"
            elif "document" in mime or "word" in mime or fname.endswith((".docx", ".doc", ".pdf", ".txt")):
                type_label = "Google Doc"
                default_link = f"https://docs.google.com/document/d/{f.get('id')}/edit"
            else:
                type_label = f.get("mimeType", "File")
                default_link = f.get("webViewLink", "")

            formatted_files.append({
                "id": f.get("id"),
                "name": f.get("name"),
                "type": type_label,
                "link": f.get("webViewLink") or default_link,
                "modified_time": f.get("modifiedTime")
            })

        return {
            "success": True,
            "count": len(formatted_files),
            "files": formatted_files
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to list Google Drive files: {str(e)}"
        }


def read_google_sheet(spreadsheet_id: str, range_name: str = "A1:Z50") -> Dict[str, Any]:
    """Read cell values from a Google Spreadsheet."""
    creds = get_google_credentials()
    if not creds:
        return {"success": False, "requires_auth": True, "message": "Google Workspace not connected."}

    try:
        from googleapiclient.discovery import build
        sheets_service = build("sheets", "v4", credentials=creds)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get("values", [])
        return {
            "success": True,
            "spreadsheet_id": spreadsheet_id,
            "range": range_name,
            "values": values,
            "row_count": len(values)
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to read Google Sheet: {str(e)}"}



# Server-side cache for pending OAuth flows: state -> { "code_verifier": ..., "created_at": ... }
_OAUTH_FLOW_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_OAUTH_DATA: Dict[str, Any] = {}


def generate_oauth_url(redirect_uri: str) -> Dict[str, Any]:
    """Generate Google OAuth consent URL for user linking, caching PKCE code_verifier."""
    ensure_google_client_secrets_file()
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {
            "success": False,
            "error": f"'{CLIENT_SECRETS_FILE}' not found.",
            "instructions": (
                "To enable real Google OAuth linking: "
                "1. Go to Google Cloud Console (console.cloud.google.com). "
                "2. Create an OAuth 2.0 Client ID (Web Application). "
                "3. Set Authorized Redirect URI to http://localhost:8000/api/google/callback. "
                "4. Download JSON and save as 'client_secret.json' in the project directory."
            )
        }

    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        code_verifier = getattr(flow, "code_verifier", None)

        oauth_data = {
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "created_at": time.time()
        }
        if state:
            _OAUTH_FLOW_CACHE[state] = oauth_data
        _LAST_OAUTH_DATA.clear()
        _LAST_OAUTH_DATA.update(oauth_data)

        # Evict old cached states older than 15 minutes
        cutoff = time.time() - 900
        expired = [s for s, d in _OAUTH_FLOW_CACHE.items() if d.get("created_at", 0) < cutoff]
        for s in expired:
            _OAUTH_FLOW_CACHE.pop(s, None)

        return {
            "success": True,
            "auth_url": auth_url,
            "state": state
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to generate OAuth URL: {str(e)}"
        }


def save_oauth_code(code: str, redirect_uri: str, state: Optional[str] = None) -> Dict[str, Any]:
    """
    Exchange authorization code for tokens, restoring exact state and PKCE code_verifier
    onto the Flow instance before calling fetch_token.
    """
    ensure_google_client_secrets_file()
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return {"success": False, "error": f"'{CLIENT_SECRETS_FILE}' not found."}

    try:
        from google_auth_oauthlib.flow import Flow

        stored_data = None
        if state and state in _OAUTH_FLOW_CACHE:
            stored_data = _OAUTH_FLOW_CACHE.pop(state)
        elif _LAST_OAUTH_DATA:
            stored_data = _LAST_OAUTH_DATA

        code_verifier = stored_data.get("code_verifier") if stored_data else None
        cached_state = stored_data.get("state") if stored_data else None
        effective_state = state or cached_state
        effective_redirect = (stored_data.get("redirect_uri") if stored_data else None) or redirect_uri

        flow_kwargs: Dict[str, Any] = {
            "scopes": SCOPES,
            "redirect_uri": effective_redirect
        }
        if effective_state:
            flow_kwargs["state"] = effective_state

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            **flow_kwargs
        )
        if code_verifier:
            flow.code_verifier = code_verifier

        fetch_kwargs: Dict[str, Any] = {"code": code}
        if code_verifier:
            fetch_kwargs["code_verifier"] = code_verifier

        flow.fetch_token(**fetch_kwargs)
        creds = flow.credentials

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        return {
            "success": True,
            "message": "Google Workspace connected successfully!"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Token exchange failed: {str(e)}"
        }
