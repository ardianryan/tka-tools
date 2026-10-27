# -*- mode: python ; coding: utf-8 -*-
import sys
import os

block_cipher = None

datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('settings.example.json', '.'),
]

# Note: settings.json containing credentials is NEVER bundled!
# Only settings.example.json is distributed. settings.json is created dynamically at runtime.

if sys.platform.startswith('win'):
    if os.path.exists('wia_scan.ps1'):
        datas.append(('wia_scan.ps1', '.'))

# Determine Icon
if sys.platform.startswith('win'):
    icon_file = 'static/favicon.ico' if os.path.exists('static/favicon.ico') else None
else:
    icon_file = 'static/app_icon.png' if os.path.exists('static/app_icon.png') else None

hidden_imports = [
    'flask',
    'flask_cors',
    'requests',
    'PIL',
    'webview',
    'pytesseract',
    'packaging',
    'packaging.version',
]

if sys.platform.startswith('win'):
    hidden_imports.append('winocr')

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['DokumenTKA'],
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
    name='SmartTKAScanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SmartTKAScanner',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='SmartTKAScanner.app',
        icon=icon_file,
        bundle_identifier='id.go.kemendikdasmen.tka.scanner',
        info_plist={
            'CFBundleName': 'Smart TKA Scanner',
            'CFBundleDisplayName': 'Smart TKA Scanner',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
        }
    )
