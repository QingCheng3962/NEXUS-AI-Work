"""准备内置运行时：便携 Node.js + DSH npm 包。

构建 EXE 前运行一次（build_exe.py 会自动调用）：
    python scripts/prepare_vendor.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
NODE_DIR = VENDOR / "node"
DSH_DIR = VENDOR / "dsh"
DSH_VERSION = "0.2.1-rc.2"
PACKAGE = f"@deepseek-ai/dsh@{DSH_VERSION}"
DSH_BIN = DSH_DIR / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"


def _size_mb(path: Path, limit: int = 20000) -> float:
    total = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
            count += 1
            if count >= limit:
                break
    return total / (1024 * 1024)


def ensure_node() -> None:
    target = NODE_DIR / "node.exe"
    if target.exists():
        print(f"[node] 已存在：{target}")
        return

    source = shutil.which("node")
    if not source:
        raise SystemExit("未找到 Node.js。请先安装 Node.js 22+，或手动放置 node.exe 到 vendor/node/。")

    version = subprocess.run([source, "--version"], capture_output=True, text=True).stdout.strip()
    print(f"[node] 使用 {source} ({version})")
    NODE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"[node] 已复制到 {target}")


def ensure_dsh() -> None:
    if DSH_BIN.exists():
        try:
            version = json.loads((DSH_BIN.parent.parent / "package.json").read_text(encoding="utf-8"))["version"]
        except Exception:  # noqa: BLE001
            version = ""
        if version == DSH_VERSION:
            print(f"[dsh] 已安装 {version}")
            return

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise SystemExit("未找到 npm，无法安装 DSH。")

    print(f"[dsh] 安装 {PACKAGE} …")
    DSH_DIR.mkdir(parents=True, exist_ok=True)
    command = [npm, "install", "--prefix", str(DSH_DIR), "--no-audit", "--no-fund", "--omit=dev", PACKAGE]
    if os.name == "nt":
        command = ["cmd", "/d", "/s", "/c", f'"{subprocess.list2cmdline(command)}"']
    subprocess.run(command, check=True, cwd=str(ROOT))
    if not DSH_BIN.exists():
        raise SystemExit("DSH 安装完成但未找到 bin.js，请检查 npm 输出。")
    print("[dsh] 安装完成")


def main() -> None:
    print("== NEXUS 内置运行时准备 ==")
    ensure_node()
    ensure_dsh()
    print("\n内置运行时已就绪：")
    print(f"  Node : {NODE_DIR / 'node.exe'}")
    print(f"  DSH  : {DSH_BIN}")


if __name__ == "__main__":
    main()
