# -*- mode: python ; coding: utf-8 -*-
"""Single-file Windows build for CC Installer - TSR Community Manager.

Double-click CCInstaller.exe - no _internal folder required.
Uses system Edge WebView2 (no Chromium bundle).
"""

from pathlib import Path

ROOT = Path(SPECPATH)
SRC = ROOT / "src"

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[
        (str(SRC / "templates"), "templates"),
        (str(SRC / "static"), "static"),
        (str(ROOT / "LICENSE"), "."),
    ],
    hiddenimports=[
        "webview",
        "webview.platforms.winforms",
        "clr_loader",
        "pythonnet",
        "flask",
        "jinja2",
        "werkzeug",
        "requests",
        "certifi",
        "charset_normalizer",
        "idna",
        "urllib3",
        "clipboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "PySide6",
        "PyQt5",
        "PyQt6",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "IPython",
        "notebook",
        "pytest",
        "unittest",
        "test",
        "tests",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CCInstaller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(SRC / "static" / "STCM.ico"),
)
