"""任务 / 笔记提醒：时间解析与 NiceGUI 全局异步检查器。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from . import db

CHECK_INTERVAL = 15.0
_task: asyncio.Task | None = None


def normalize_remind_at(value: str | None) -> str:
    """把 datetime-local / 常见日期格式统一成可排序的本地时间字符串。"""
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise ValueError("提醒时间格式不正确，请使用日期和时间选择器。")


def input_value(remind_at: str | None) -> str:
    """把数据库时间转成 <input type=datetime-local> 需要的格式。"""
    text = str(remind_at or "").strip()
    if len(text) >= 16:
        return text[:16].replace(" ", "T")
    return text


def display_value(remind_at: str | None) -> str:
    text = str(remind_at or "").strip()
    return text[5:16] if len(text) >= 16 else text


def _message(item: dict[str, Any]) -> str:
    title = " ".join(str(item.get("title") or "未命名").split())[:80]
    if item.get("kind") == "task":
        return f"任务提醒 · {title}"
    return f"笔记提醒 · {title}"


async def check_due() -> int:
    """向所有已连接页面推送到点提醒；成功投递后再标记已发送。"""
    from nicegui import app, ui

    clients = [client for client in app.clients() if not client.is_deleted]
    if not clients:
        return 0

    items = db.due_reminders()
    delivered = 0
    for item in items:
        for client in clients:
            try:
                # 后台任务没有页面槽上下文，进入 client 后再调用 ui.notify。
                with client:
                    ui.notify(
                        _message(item),
                        position="top-right",
                        type="warning" if item.get("kind") == "task" else "info",
                        icon="alarm",
                        timeout=9000,
                        multi_line=True,
                        close_button="知道了",
                    )
                delivered += 1
            except Exception:  # noqa: BLE001 - 单个页面断开不应影响其他页面
                continue
    if delivered:
        db.mark_reminders_sent(items)
    return delivered


async def _loop() -> None:
    while True:
        try:
            await check_due()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 后台检查器必须持续运行
            pass
        await asyncio.sleep(CHECK_INTERVAL)


def start() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _task = loop.create_task(_loop(), name="anvil-reminders")


def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
