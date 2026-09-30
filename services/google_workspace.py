"""
Google Workspace Integration Service (Google Docs v1 & Google Sheets v4).
Allows Momento to authenticate via OAuth2 and export generated outputs
directly to new Google Documents and Google Spreadsheets.
"""

import os
import re
import json
import time
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

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


def parse_text_to_matrix(text: str) -> List[List[str]]:
    """Convert Markdown tables, CSV text, or lines into a 2D matrix for Google Sheets."""
    lines = text.strip().split("\n")
    table_rows = []

    # Check for markdown table syntax
    for line in lines:
        line_str = line.strip()
        if line_str.startswith("|") and line_str.endswith("|"):
            # Skip separator line like |---|---|
            if set(line_str.replace("|", "").strip()).issubset({"-", ":", " "}):
                continue
            cells = [c.strip() for c in line_str.split("|")[1:-1]]
            table_rows.append(cells)

    if table_rows:
        return table_rows

    # Fallback: check CSV format or split into rows
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        if "," in line_str:
            table_rows.append([c.strip() for c in line_str.split(",")])
        elif "\t" in line_str:
            table_rows.append([c.strip() for c in line_str.split("\t")])
        else:
            table_rows.append([line_str])

    return table_rows if table_rows else [["Momento Output", text[:500]]]


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
    """Create a new Google Spreadsheet and populate it with a 2D data matrix."""
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

        # 2. Determine matrix
        matrix = data_matrix
        if not matrix and raw_text:
            matrix = parse_text_to_matrix(raw_text)

        if not matrix:
            matrix = [["Momento Output"], ["No tabular data found"]]

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
    page_size: int = 25
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
            query_parts.append("mimeType = 'application/vnd.google-apps.spreadsheet'")
        elif type_lower in ["doc", "docs", "document", "documents"]:
            query_parts.append("mimeType = 'application/vnd.google-apps.document'")

        if query and query.strip():
            safe_q = query.strip().replace("'", "\\'")
            query_parts.append(f"name contains '{safe_q}'")

        q_str = " and ".join(query_parts)

        results = drive_service.files().list(
            q=q_str,
            pageSize=page_size,
            fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
            orderBy="modifiedTime desc"
        ).execute()

        raw_files = results.get("files", [])
        formatted_files = []
        for f in raw_files:
            mime = f.get("mimeType", "")
            if "spreadsheet" in mime:
                type_label = "Google Sheet"
                default_link = f"https://docs.google.com/spreadsheets/d/{f.get('id')}/edit"
            elif "document" in mime:
                type_label = "Google Doc"
                default_link = f"https://docs.google.com/document/d/{f.get('id')}/edit"
            else:
                type_label = mime
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
