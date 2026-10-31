"""Anvil · AI 个人工作站

启动：
    python app.py
    python app.py --no-browser --port 8080
"""

from __future__ import annotations

import argparse
import os
import sys

from nicegui import app, ui

from core import db, reminders, runtime, settings, snapshots
from core.approval import broker as approval_broker
from core.approval import install_route
from core.dsh_agent import dsh_agent

# 导入页面模块即完成路由注册
from ui.pages import chat, notes, settings_page, tasks  # noqa: F401

APP_TITLE = "Anvil · AI 个人工作站"

install_route(app)


@app.on_startup
def _startup() -> None:
    settings.load()
    db.init_db()
    try:
        snapshots.prune(days=7)
    except OSError:
        pass
    reminders.start()


@app.on_shutdown
def _shutdown() -> None:
    reminders.stop()
    try:
        dsh_agent.cancel()
    except Exception:  # noqa: BLE001 - 退出阶段不再抛错
        pass


def main() -> None:
    _ensure_streams()
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--host", default=None, help="监听地址（默认读取设置）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认读取设置）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--native", action="store_true", help="以桌面窗口运行（pywebview）")
    parser.add_argument("--web", action="store_true", help="强制使用浏览器模式")
    parser.add_argument("--reload", action="store_true", help="开发模式：代码变更自动重载")
    args, _ = parser.parse_known_args()

    cfg = settings.load()
    db.init_db()

    use_native = not args.web and (args.native or runtime.IS_FROZEN)
    port = args.port or int(cfg["app"].get("port", 8080))
    host = args.host or cfg["app"].get("host", "127.0.0.1")

    if use_native:
        from nicegui import native

        port = args.port or native.find_open_port()
        host = "127.0.0.1"

    approval_broker.port = port
    icon = runtime.app_dir() / "assets" / "anvil.png"
    favicon = str(icon) if icon.exists() else "🚀"

    ui.run(
        host=host,
        port=port,
        title=APP_TITLE,
        favicon=favicon,
        dark=None,
        show=not args.no_browser and not use_native,
        native=use_native,
        window_size=(1440, 900) if use_native else None,
        reload=args.reload and not use_native and not runtime.IS_FROZEN,
        storage_secret=os.environ.get("ANVIL_STORAGE_SECRET", "anvil-local-workstation-2026"),
        uvicorn_logging_level="warning",
        language="zh-CN",
    )


def _ensure_streams() -> None:
    """windowed EXE 没有控制台，把 stdout/stderr 重定向到日志文件。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        log_path = runtime.support_dir() / "anvil.log"
        handle = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def _entry() -> None:
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        import traceback

        log_path = runtime.support_dir() / "crash.log"
        try:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
        if os.name == "nt" and runtime.IS_FROZEN:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Anvil 启动失败，请把日志发给开发者：\n{log_path}",
                "Anvil",
                0x10,
            )
        else:
            raise


if __name__ in {"__main__", "__mp_main__"}:
    import multiprocessing

    multiprocessing.freeze_support()
    _entry()
