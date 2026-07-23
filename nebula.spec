# -*- mode: python ; coding: utf-8 -*-
# Single-file build: `pyinstaller nebula.spec` -> dist/Nebula.exe
#
# customtkinter ships its own theme JSON + asset files that PyInstaller's
# static analysis won't pick up on its own - collect_data_files() bundles
# them so the exe doesn't crash at runtime looking for its default theme.
from PyInstaller.utils.hooks import collect_data_files

datas = [("nebula_icon.ico", ".")]
datas += collect_data_files("customtkinter")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Nebula",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["nebula_icon.ico"],
)
