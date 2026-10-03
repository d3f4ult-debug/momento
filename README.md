# ⚡ Momento — Universal AI Agent Workspace & Standalone Desktop App

Momento is an intelligent, high-performance universal AI agent workspace built with **FastAPI**, **pywebview**, **Google GenAI SDK**, and a modern Linear/Vercel-inspired glassmorphic dashboard.

It processes Microsoft Word documents (`.docx`), Excel spreadsheets (`.xlsx`/`.xls`), and plain text notes using native Python parsers, transforms content via proprietary Momento AI engines, and provides native file dispatch to Telegram and Google Workspace.

---

## 🚀 Key Features

- **Proprietary Momento AI Model Family**:
  - **Momento Nexus v2.5**: Core engine optimized for fast document handling and everyday utility.
  - **Momento Apex v3.1**: Advanced reasoning model for complex logic and structured parsing.
  - **Momento Omni v3.8**: Flagship autonomous intelligence built for multi-step agent operations.
- **Standalone Native Desktop App (`Momento.exe`)**:
  - Native Windows desktop application window powered by `pywebview` and a background Uvicorn daemon.
  - Packaged via PyInstaller into a standalone executable (`dist/Momento/Momento.exe`) with zero local configuration required.
  - Launchable via `python desktop.py` or double-clicking `Momento.exe`.
- **Fully Functional "New Chat" Reset**:
  - Top navigation `+` button completely resets the active workspace session, cleans files, clears inputs, and restores the landing command center.
  - **Word (`.docx`)**: Extracts structural paragraphs, headings, and tabular data formatted into Markdown.
  - **Excel (`.xlsx`, `.xls`)**: Extracts multi-sheet structures, dimensions, column names, and Markdown table previews.
  - **Plaintext (`.txt`, `.md`, `.csv`, `.json`, `.tsv`)**: Resilient multi-encoding decoders (`utf-8`, `utf-8-sig`, `latin-1`, `cp1252`).
- **AI Engine**:
  - Integrated with **Google GenAI SDK** (`google-genai`) leveraging `gemini-2.5-flash`.
  - Supports configurable system prompts, temperature controls, and context injection.
  - API key can be supplied via `.env` or set directly on the web interface.
- **Conditional Integrations**:
  - **Telegram Userbot Dispatch**: Sends outputs natively from your personal Telegram account to contacts or chats by searching display names (e.g., *"Animatic"*) via Telethon. Triggered via UI toggle or natural prompt commands (e.g., *"send this to Animatic on telegram"*).
  - **Google Docs & Sheets**: Structured integration hooks ready for Google Cloud Service Account OAuth credentials.
- **Modern Dashboard UI**:
  - Dark-mode interface designed with Tailwind CSS, Lucide icons, and Marked.js.
  - Interactive drag-and-drop file upload with format badges and size indicators.
  - One-click copy, markdown file download, and real-time latency diagnostics.

---

## 📂 Project Architecture

```
momento/
├── main.py                     # FastAPI server, parsers, Gemini SDK engine & routes
├── auth_telegram.py            # One-time interactive userbot authentication script
├── requirements.txt            # Python dependencies (telethon, fastapi, etc.)
├── .env.example                # Sample environment configuration
├── .gitignore                  # Python & session exclusions
├── services/
│   └── telegram_userbot.py     # Telethon client session & chat search dispatcher
├── templates/
│   └── index.html              # Dark single-page web dashboard UI
├── tests/
│   ├── __init__.py
│   ├── test_parsers.py         # Unit tests for .docx, .xlsx, and .txt extractors
│   ├── test_api.py             # FastAPI API endpoint & flow tests
│   └── test_userbot.py         # Telethon userbot unit tests
├── deployment/
│   ├── momento.service         # Systemd service unit for Ubuntu Linux
│   └── nginx.conf              # Nginx reverse proxy configuration
└── README.md                   # Documentation and deployment manual
```

---

## 🛠️ Quickstart (Local Run)

### 1. Clone & Set Up Virtual Environment

```bash
git clone <your-repo-url> momento
cd momento

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```ini
GEMINI_API_KEY=AIzaSy...your-gemini-key
GEMINI_MODEL=gemini-2.5-flash

# Optional: Telegram Userbot credentials (from https://my.telegram.org/apps)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef0123456789abcdef0123456789
```

### 3. One-Time Telegram Userbot Login (Interactive)

If you plan to use Telegram dispatch from your personal account:
```bash
python auth_telegram.py
```
This prompts for your phone number, Telegram OTP code, and 2FA password (if enabled), creating the authorized session file `momento_user_session.session`. Once completed, Momento can dispatch messages to any contact or group by display name (e.g., "Animatic").

### 3. Start the Server

```bash
python main.py
# Or with uvicorn directly:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at **http://localhost:8000**.

---

## 🐧 Deploying to an Ubuntu Linux VPS

Here is the complete guide to deploy Momento as a production background service on Ubuntu 22.04 or 24.04 LTS:

### Step 1: Install System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx git
```

### Step 2: Set Up Directory & Application

```bash
sudo mkdir -p /var/www/momento
sudo chown -R $USER:$USER /var/www/momento
cd /var/www/momento

# Clone or copy project files here
git clone <your-repo> .

# Create virtual environment and install packages
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env
```

### Step 3: Configure Systemd Background Service

```bash
sudo cp deployment/momento.service /etc/systemd/system/momento.service
sudo systemctl daemon-reload
sudo systemctl start momento
sudo systemctl enable momento
sudo systemctl status momento
```

### Step 4: Configure Nginx Reverse Proxy

```bash
sudo cp deployment/nginx.conf /etc/nginx/sites-available/momento
# Edit server_name in the file:
sudo nano /etc/nginx/sites-available/momento

# Enable site
sudo ln -s /etc/nginx/sites-available/momento /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Step 5: Secure with SSL (Let's Encrypt / Certbot)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Your Momento agent is now live and running securely over HTTPS!

---

## 🖥️ Desktop Application & Installer

Momento can be packaged and distributed as a native desktop application with a single-file installer wizard.

### Single-File Installer Setup (`Momento-Setup.exe`)
Momento includes an automated builder that compiles the desktop application into a standalone setup executable:

```bash
# Build the single-file setup wizard (dist/Momento-Setup.exe)
python build_installer.py
```

#### Features of `Momento-Setup.exe`:
- **Single Executable:** Bundles the complete runtime, webview, backend, and dependencies in one portable `.exe` (~78 MB).
- **Zero-Friction Installation:** Installs by default to `%LOCALAPPDATA%\Programs\Momento` without requiring administrator privileges or triggering UAC prompts.
- **Automatic Shortcuts:** Automatically places clean shortcuts on the user's Desktop and Windows Start Menu.
- **Windows Add/Remove Programs Integration:** Registers an uninstaller in Windows Settings / Control Panel and generates `uninstall.bat`.
- **Silent Deployment Support:** Supports headless or enterprise scripted deployments:
  ```powershell
  # Silent install without GUI to default location
  .\dist\Momento-Setup.exe /S

  # Silent install to custom directory without desktop shortcut
  .\dist\Momento-Setup.exe /S /D="C:\Custom\Momento" /no-desktop
  ```

### NSIS Installer Script
For automated enterprise pipelines or users with NSIS (`makensis`), a complete NSIS script is included:
```bash
makensis installer.nsi
```

### Standalone Executable Build (`Momento.exe`)
To compile the raw folder-based desktop executable without the installer wrapper:
```bash
python build_desktop.py
```
This produces `dist/Momento/Momento.exe` and `dist/Momento/_internal/`.

---

## 🧪 Testing

Run the automated test suite using pytest:

```bash
pytest -v
```

This verifies:
1. `.docx` parser extraction (headings, paragraphs, and multi-cell tables).
2. `.xlsx` parser extraction (multi-sheet sheets, dimension stats, and table schemas).
3. Plaintext parser with multi-encoding fallbacks.
4. FastAPI endpoints (`/`, `/api/health`, `/api/process`, session reset, auth guards).
5. Telegram userbot session strings and chat dialog queries.
6. Desktop server lifecycle, dynamic port binding, and health checks.
7. Installer extraction, shortcut generation, uninstaller creation, and CLI argument parsing.

---

## 🖥️ Self-Hosted Local Office Engine (Headless LibreOffice)

Momento operates as a 100% self-hosted document and spreadsheet generation engine on Ubuntu VPS, eliminating dependencies on external Google Workspace cloud APIs.

### Supported Local Formats
- **Documents**: `.docx` (Microsoft Word via python-docx), `.pdf` (Portable Document Format via headless LibreOffice), `.html`, `.txt`.
- **Spreadsheets**: `.xlsx` (Excel via openpyxl with enterprise styling and auto column widths), `.ods` (OpenDocument Spreadsheet via headless LibreOffice), `.csv` (Excel-compatible UTF-8 BOM).

### Ubuntu / Contabo VPS System Dependencies
Run the automated installer script:
```bash
sudo bash deployment/setup_local_office.sh
```

Or install dependencies manually via `apt` and `pip`:
```bash
# 1. System packages & typography fonts
sudo apt update
sudo apt install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    default-jre-headless

# 2. Python packages in your virtual environment
pip install python-docx openpyxl pandas

# 3. Ensure exports storage directory exists with proper permissions
sudo mkdir -p /var/www/momento/exports
sudo chown -R www-data:www-data /var/www/momento/exports
sudo chmod -R 775 /var/www/momento/exports
```

---

## 📡 API Reference

### Local Office Status
`GET /api/local/status`
Returns LibreOffice installation status, binary command path, detected version, and supported document/spreadsheet formats.
### Local Document Export
`POST /api/local/export/doc`
- Form fields: `title` (string), `content` (Markdown or plaintext), `format` (`docx` or `pdf`).
- Returns: JSON with file metadata and direct `/api/download/{filename}` download link.
### Local Spreadsheet Export
`POST /api/local/export/sheet`
- Form fields: `title` (string), `content` (Markdown table or CSV string), `format` (`xlsx`, `ods`, or `csv`).
- Returns: JSON with file metadata, rows parsed, and direct download link.
### Direct PDF Conversion
`POST /api/local/export/pdf`
- Form fields: `title` (string), `content` (Markdown or plaintext).
### Health Check
`GET /api/health`
```json
{
"status": "healthy",
"agent": "Momento",
"model": "gemini-2.5-flash",
"integrations": {
"gemini_api_key_configured": true,
"telegram_bot_configured": true,
"google_docs_placeholder": true,
"google_sheets_placeholder": true
}
}
```
### Process Document & Instruction
`POST /api/process`
- Form fields:
- `prompt`: Natural language instructions (e.g. *"Summarize and extract action items"*).
- `file`: (Optional) Uploaded document (`.docx`, `.xlsx`, `.txt`, `.csv`, etc.).
- `selected_model`: (Optional) Proprietary model (`momento-nexus-2.5`, `momento-apex-3.1`, `momento-omni-3.8`).
- `custom_api_key`: (Optional) Overrides server API key.
- `send_telegram`: (Optional) `true` / `false`.
- `telegram_chat_id`: (Optional) Target Telegram user or channel ID.

