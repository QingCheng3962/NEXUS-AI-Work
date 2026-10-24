"""系统状态快照与路径信息。"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

import psutil

from . import settings


def snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(settings.ROOT))
    return {
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "memory": round(memory.percent, 1),
        "memory_used": round(memory.used / (1024**3), 1),
        "memory_total": round(memory.total / (1024**3), 1),
        "disk": round(disk.percent, 1),
        "disk_used": round(disk.used / (1024**3), 1),
        "disk_total": round(disk.total / (1024**3), 1),
        "platform": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "cores": psutil.cpu_count(logical=True) or 0,
    }


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def pick_directory(initial: str = "") -> str:
    """打开系统文件夹选择框；失败时返回空字符串，调用方可退回手工输入。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass
        root.update_idletasks()
        selected = filedialog.askdirectory(
            title="选择 AI 工作区",
            initialdir=initial or str(settings.WORKSPACE_DIR),
            mustexist=True,
        )
        root.destroy()
        return str(selected or "")
    except Exception:  # noqa: BLE001 - 没有图形环境时由调用方处理
        return ""


def folder_size(path: Path, limit: int = 5000) -> int:
    total = 0
    count = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
                count += 1
                if count >= limit:
                    break
    except OSError:
        pass
    return total
