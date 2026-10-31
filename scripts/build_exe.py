"""构建 Windows 桌面 EXE（PyInstaller onedir）。

    python scripts/build_exe.py
    python scripts/build_exe.py --onefile   # 单文件（启动较慢，不推荐）

产物：dist/Anvil/Anvil.exe
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Anvil"


def main() -> None:
    onefile = "--onefile" in sys.argv
    if os.name != "nt":
        raise SystemExit("当前构建脚本面向 Windows。")

    # 1. 内置运行时
    subprocess.run([sys.executable, str(ROOT / "scripts" / "prepare_vendor.py")], check=True, cwd=str(ROOT))

    # 2. 图标
    icon = ROOT / "assets" / "anvil.ico"
    if not icon.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_icon.py")], check=True, cwd=str(ROOT))

    # 3. 直接用 PyInstaller（nicegui-pack 不支持额外的隐藏导入）
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "Anvil",
        "--windowed",
        "--onedir" if not onefile else "--onefile",
        "--clean",
        "--noconfirm",
        "--icon",
        str(icon),
        "--add-data",
        f"{ROOT / 'vendor'}{os.pathsep}vendor",
        "--collect-all",
        "nicegui",
        "--collect-all",
        "webview",
        "--collect-all",
        "docx",
        "--collect-all",
        "openpyxl",
        "--collect-all",
        "pypdf",
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "webview.platforms.winforms",
        "--hidden-import",
        "nicegui.native",
        "--hidden-import",
        "tkinter",
        "--hidden-import",
        "tkinter.filedialog",
        "--hidden-import",
        "engineio.async_drivers.threading",
        str(ROOT / "app.py"),
    ]

    print("\n== 构建 EXE ==")
    print(" ".join(command))
    subprocess.run(command, check=True, cwd=str(ROOT))

    target = DIST / "Anvil.exe"
    if not target.exists():
        raise SystemExit(f"构建结束但未找到 {target}")

    # 附带说明文件
    for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, DIST / name)
    if (ROOT / "assets").exists():
        shutil.copytree(ROOT / "assets", DIST / "assets", dirs_exist_ok=True)

    print("\n构建完成：")
    print(f"  {target}")
    print(f"  运行时目录：{DIST / '_internal'}")
    print("  分发时请压缩整个 dist/Anvil 目录。")


if __name__ == "__main__":
    main()
