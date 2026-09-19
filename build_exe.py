#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键打包成单文件 exe。"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def run(cmd):
    print("$ " + " ".join(cmd))
    r = subprocess.run(cmd)
    return r.returncode


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 pyinstaller，正在安装...")
        if run([sys.executable, "-m", "pip", "install", "pyinstaller"]) != 0:
            return 1

    if run([sys.executable, "-m", "PyInstaller", "build.spec", "--noconfirm", "--clean"]) != 0:
        print("打包失败")
        return 1

    exe = os.path.join(HERE, "dist", "ai-gateway-checkin.exe")
    if not os.path.exists(exe):
        print("未找到产物，打包可能失败")
        return 1

    size = os.path.getsize(exe) / 1024 / 1024
    print()
    print("=" * 56)
    print("打包完成: %s" % exe)
    print("文件大小: %.1f MB" % size)
    print("=" * 56)
    print()
    print("自检命令: dist\\ai-gateway-checkin.exe --selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())