# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec Configuration for Momento Universal AI Agent Workspace.
Bundles FastAPI backend, Jinja2 templates, multi-format file processors,
Google & Telegram integrations, and native desktop window runtime into a
standalone Windows executable.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base directory
BASE_DIR = os.path.abspath(SPECPATH)

# Collect data files and submodules for heavy libraries
datas = [
    (os.path.join(BASE_DIR, 'templates'), 'templates'),
    (os.path.join(BASE_DIR, 'services'), 'services'),
]

# Include optional configuration templates if present
for opt_file in ['.env.example', 'README.md', 'client_secret.json']:
    full_path = os.path.join(BASE_DIR, opt_file)
    if os.path.exists(full_path):
        datas.append((full_path, '.'))

# Hidden imports required by Uvicorn, FastAPI, Telethon, Google SDK, and pywebview
hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.loops.asyncio',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'fastapi',
    'starlette',
    'starlette.routing',
    'starlette.middleware',
    'starlette.middleware.cors',
    'starlette.responses',
    'starlette.templating',
    'jinja2',
    'python_multipart',
    'multipart',
    'docx',
    'openpyxl',
    'pandas',
    'tabulate',
    'google',
    'google.genai',
    'google.auth',
    'google.auth.transport.requests',
    'google.oauth2',
    'google.oauth2.credentials',
    'googleapiclient',
    'googleapiclient.discovery',
    'telethon',
    'telethon.sessions',
    'telethon.sessions.string',
    'webview',
    'clr_loader',
    'pythonnet',
]

# Collect additional submodules dynamically
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('telethon')
hiddenimports += collect_submodules('docx')
hiddenimports += collect_submodules('openpyxl')

# Check if console window should be shown (set MOMENTO_CONSOLE=1 for debugging)
show_console = os.getenv("MOMENTO_CONSOLE", "0").lower() in ("1", "true", "yes")

a = Analysis(
    ['desktop.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=list(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Momento',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=show_console,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Momento',
)
