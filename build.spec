# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成单文件 exe，双击即用。"""
import os

block_cipher = None

a = Analysis(
    ["gui_app.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "uc", "uc.sites", "uc.client", "uc.runner", "uc.store", "uc.crypto_util",
        "uc.selftest",
        "cryptography", "cryptography.hazmat.primitives.asymmetric.padding",
        "cryptography.hazmat.primitives.asymmetric.rsa",
        "cryptography.hazmat.primitives.ciphers.aead",
        "cryptography.hazmat.primitives.serialization",
        "cryptography.hazmat.primitives.hashes",
        "cryptography.hazmat.backends.openssl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "PIL", "PyQt5", "PyQt6",
        "PySide2", "PySide6", "notebook", "IPython", "jupyter", "pytest",
        "setuptools", "pip", "wheel",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AI签到助手",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
