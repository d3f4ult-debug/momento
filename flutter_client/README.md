# Momento Desktop — Native Windows Flutter Application

Native, consumer-grade Windows desktop client for **Momento Universal AI Workspace**, built with **Flutter 3 / Dart 3** and powered by the deterministic Python host execution engine.

---

## 🏛️ Architecture Overview

The application follows a modular decoupled architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Momento Native Flutter Desktop App                   │
│                                                                        │
│   ┌─────────────────────┐    ┌─────────────────────────────────────┐   │
│   │   Sidebar           │    │   Main Chat Dashboard               │   │
│   │  - App Discovery    │    │  - Conversational Input             │   │
│   │  - Search Filter    │    │  - Quick Prompt Chips               │   │
│   │  - Active Sessions  │    │  - Real-Time Execution Cards        │   │
│   │  - Mode Switcher    │    │  - Live Stdout/Stderr Terminal Box  │   │
│   └─────────────────────┘    └─────────────────────────────────────┘   │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ HTTP REST API / Background Process
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Python Backend Core Engine                           │
│                                                                        │
│  - Bridge Server & REST API (/api/client/...)                          │
│  - Local App Scanner & Registry (%USERPROFILE%\.momento\registry.json) │
│  - Natural Language Router (NLP intent parser & fuzzy resolver)        │
│  - Native Process Execution Engine (real-time stdout/stderr capture)   │
│  - VPS Sandbox Execution Core (isolated Wine64 container on Contabo)   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

1. **Sleek Modern Dark Dashboard**:
   - Tailored specifically for Windows desktop with dark slate aesthetic, glowing status indicators, and responsive flex layout.
2. **First-Run Graphical Permission Wizard**:
   - Displays an onboarding dialog requesting permissions for *File System Indexing*, *App Discovery*, and *Execution Management*.
   - Automatically executes the Python app scanner on first run to index installed applications into `%USERPROFILE%\.momento\registry.json`.
3. **Execution Target Toggle**:
   - **Hybrid Auto** *(Default)*: Launches applications natively on the local Windows laptop if available; falls back to the Contabo VPS sandbox container for isolated execution.
   - **Local Host**: Forces native direct subprocess execution on the user's laptop.
   - **VPS Sandbox**: Routes all execution headlessly to the Contabo VPS sandbox backend (`http://161.97.64.38:8000`).
4. **Natural Language Chat Interface**:
   - Plain human language commands (e.g., *"Momento, open Notepad"*, *"run Calculator"*, *"open Chrome with args --incognito"*).
   - Fuzzy name matching against all discovered applications.
5. **Interactive Inline Execution Cards**:
   - Displays process PID, session ID (`sbx_local_...` or `sbx_...`), runtime mode (`Local Host` / `Contabo VPS Wine64`).
   - Embedded expandable live terminal box streaming stdout/stderr outputs in real time.
   - One-click **Stop Process** button to terminate processes instantly.

---

## 🛠️ Development & Running

### Prerequisites
- Windows 10/11 x64
- [Flutter SDK 3.x](https://flutter.dev) with desktop development enabled
- Python 3.10+ (active virtual environment with dependencies)

### Run in Debug Mode
```powershell
cd flutter_client
flutter run -d windows
```

### Run Tests
```powershell
cd flutter_client
flutter test
```

### Build Release Windows Executable (.exe)
```powershell
cd flutter_client
flutter build windows --release
```

The compiled standalone release application and runtime dependencies will be generated at:
```
flutter_client/build/windows/x64/runner/Release/momento_desktop.exe
```

---

## 🔌 API Bridge Endpoints

The Flutter desktop client communicates with the Python core via the following endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/api/client/state` | `GET` | Fetches setup status, permissions, indexed apps, and active sessions |
| `/api/client/permissions` | `POST` | Records granted permissions and runs initial environment scan |
| `/api/client/scan` | `POST` | Triggers a fresh application discovery scan |
| `/api/client/chat` | `POST` | Dispatches natural language conversational command |
| `/api/client/logs/{session_id}` | `GET` | Streams live process stdout/stderr log output |
| `/api/client/stop` | `POST` | Terminates an active process session |
| `/api/client/settings` | `POST` | Updates backend URL and default execution target mode |
