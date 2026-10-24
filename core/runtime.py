"""运行时路径解析：兼容源码运行与 PyInstaller 打包后的 EXE。

- 资源（内置 DSH / Node）从 PyInstaller 的 `_MEIPASS` 读取
- 用户数据优先放在 exe 同级的 `data/`，不可写时退回 %LOCALAPPDATA%\\NEXUS
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_FROZEN = bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """exe 所在目录（源码运行时为项目根目录）。"""
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """打包资源目录（PyInstaller 解包目录）。"""
    return Path(getattr(sys, "_MEIPASS", app_dir()))


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def support_dir() -> Path:
    """可写的数据目录。"""
    portable = app_dir() / "data"
    if _writable(portable):
        return portable
    fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "NEXUS" / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def default_workspace() -> Path:
    """DSH Agent 的默认工作区：独立的用户目录，避免误改程序源码。"""
    path = Path.home() / "NEXUS-Workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_node() -> Path | None:
    candidate = resource_dir() / "vendor" / "node" / "node.exe"
    return candidate if candidate.exists() else None


def bundled_dsh_bin() -> Path | None:
    candidate = (
        resource_dir()
        / "vendor"
        / "dsh"
        / "node_modules"
        / "@deepseek-ai"
        / "dsh"
        / "lib"
        / "bin.js"
    )
    return candidate if candidate.exists() else None


def dsh_is_bundled() -> bool:
    return bundled_node() is not None and bundled_dsh_bin() is not None


def app_version() -> str:
    return "1.1.0"
