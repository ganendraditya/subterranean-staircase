# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for Subterranean Staircase.

Builds standalone cross-platform GUI bundles:
- macOS: Subterranean Staircase.app bundle (Info.plist + app_icon.icns)
- Windows: Subterranean Staircase.exe (app_icon.ico + console=False)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
project_root = Path.cwd()

# 1. Collect third-party packages with binary/data requirements
datas = []
binaries = []
hiddenimports = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "numpy",
    "cv2",
    "mss",
    "pydantic",
    "ctranslate2",
    "sentencepiece",
    "rapidocr_onnxruntime",
    "onnxruntime",
    "urllib.request",
    "urllib.error",
]

# RapidOCR and ONNXRuntime
d_ocr, b_ocr, h_ocr = collect_all("rapidocr_onnxruntime")
datas += d_ocr
binaries += b_ocr
hiddenimports += h_ocr

# CTranslate2 & SentencePiece
d_ct2, b_ct2, h_ct2 = collect_all("ctranslate2")
datas += d_ct2
binaries += b_ct2
hiddenimports += h_ct2

hiddenimports += collect_submodules("sentencepiece")
hiddenimports += collect_submodules("onnxruntime")

# 2. Add local repository assets
assets_dir = project_root / "ui" / "assets"
if assets_dir.exists():
    for f in assets_dir.glob("*"):
        if f.is_file():
            datas.append((str(f), "ui/assets"))

# 3. Platform-specific imports & configurations
is_darwin = sys.platform == "darwin"
is_windows = sys.platform == "win32"

if is_darwin:
    hiddenimports += [
        "Quartz",
        "AppKit",
        "Foundation",
        "objc",
    ]
elif is_windows:
    hiddenimports += [
        "ctypes",
        "ctypes.wintypes",
    ]

# Deduplicate
hiddenimports = sorted(list(set(hiddenimports)))

a = Analysis(
    ["run.py"],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

app_name = "Subterranean Staircase"
icon_path = str(assets_dir / ("app_icon.icns" if is_darwin else "app_icon.ico"))
if not os.path.exists(icon_path):
    icon_path = None

if is_darwin:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
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
        upx=False,
        upx_exclude=[],
        name=app_name,
    )
    app = BUNDLE(
        coll,
        name=f"{app_name}.app",
        icon=icon_path,
        bundle_identifier="com.subtitle-translator.subtrans",
        info_plist={
            "CFBundleName": app_name,
            "CFBundleDisplayName": app_name,
            "CFBundleIdentifier": "com.subtitle-translator.subtrans",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSUIElement": False,
            "NSScreenCaptureUsageDescription": (
                "Subterranean Staircase requires Screen Recording permission to capture "
                "and translate on-screen subtitles."
            ),
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=app_name,
    )
