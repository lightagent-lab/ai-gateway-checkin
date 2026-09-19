# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置：生成单文件 exe，双击即用。

字体处理：
  若存在 assets/PingFangSC-Semibold.otf，则一并打包进 exe。
  注意苹方(PingFang SC)是 Apple 专有字体，仅限本机自用，
  请勿将打包后的含字体版本再分发。仓库已通过 .gitignore 排除该文件。
  未打包字体时，程序会自动使用系统已安装的同类字体。
"""
import os
import sys

block_cipher = None

# spec 执行时没有 __file__，用 sys.path[0] 或当前目录兜底
try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = os.path.abspath(os.getcwd())

FONT = os.path.join(HERE, "assets", "PingFangSC-Semibold.otf")

datas = []
if os.path.exists(FONT):
    datas.append((FONT, "assets"))
    print("[build.spec] 打包字体: %s (%.1f MB)" % (FONT, os.path.getsize(FONT) / 1024 / 1024))
else:
    print("[build.spec] 未找到 assets/PingFangSC-Semibold.otf，将使用系统字体")

a = Analysis(
    ["gui_app.py"],
    pathex=[HERE],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "uc", "uc.sites", "uc.client", "uc.runner", "uc.store",
        "uc.crypto_util", "uc.selftest", "uc.fonts",
        "cryptography",
        "cryptography.hazmat.primitives.asymmetric.padding",
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
        "setuptools", "pip", "wheel", "fontTools",
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
    name="ai-gateway-checkin",
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
    icon=None,
)