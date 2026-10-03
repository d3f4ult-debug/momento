# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec Configuration for Momento Native Desktop Client.
Bundles the native pywebview graphical user interface, local application scanner,
natural-language intent router, and process execution engine into a standalone Windows executable.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

BASE_DIR = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(BASE_DIR, 'client', 'gui'), 'client/gui'),
    (os.path.join(BASE_DIR, 'config.json'), '.'),
]

for opt_file in ['.env.example', 'README.md']:
    full_path = os.path.join(BASE_DIR, opt_file)
    if os.path.exists(full_path):
        datas.append((full_path, '.'))

hiddenimports = [
    'webview',
    'clr_loader',
    'pythonnet',
    'client',
    'client.config',
    'client.scanner',
    'client.onboarding',
    'client.nlp_router',
    'client.shell',
    'client.execution_engine',
    'client.desktop_bridge',
]

hiddenimports += collect_submodules('webview')
hiddenimports += collect_submodules('client')

show_console = os.getenv("MOMENTO_CONSOLE", "0").lower() in ("1", "true", "yes")

a = Analysis(
    ['desktop_client.py'],
    pathex=[BASE_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=list(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy'],
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
    name='Momento-Client',
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
    name='Momento-Client',
)
