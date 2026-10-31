"""设置页：模型服务、DSH 运行时、外观与数据维护。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from urllib.parse import urlparse

from nicegui import ui

from core import ai_providers, db, llm, settings, system
from core.dsh_agent import dsh_agent
from ui.ai_settings import AISettingsDialog
from ui.theme import page_shell, panel

EFFORT_LABELS = {"": "默认", "off": "关闭", "low": "低", "high": "高", "max": "最高"}


@ui.page("/settings", title="设置 · Anvil")
def settings_page() -> None:
    content = page_shell("设置", "配置模型、DSH Agent 与本地数据", "settings")
    cfg = settings.load()
    provider_state: dict = {"id": None}
    provider_delete_state: dict = {"provider": None}

    with content:
        with ui.element("div").classes("toolbar"):
            ui.label("配置保存在 data/config.json，仅存放于本机").classes("muted").style("font-size:11.5px")
            ui.space()
            save_status = ui.label("").classes("dim").style("font-size:11px")
            ui.button("保存设置", icon="save", on_click=lambda: save_fields()).props(
                "unelevated no-caps"
            ).classes("gradient-btn")

        # ---------------------------------------------------------------- #
        # AI 服务商节点：SQLite 存储，可动态增删改
        # ---------------------------------------------------------------- #
        with ui.element("div").style("margin-bottom:16px"):
            @ui.refreshable
            def providers_panel() -> None:
                providers = db.list_ai_providers()
                active_id = ai_providers.active_provider_id()
                with panel(
                    "AI 服务商管理",
                    "hub",
                    "保存多个 API 节点，在 AI 工作窗口下拉切换",
                ):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label(
                            f"{len(providers)} 个节点 · API Key 仅保存在本机 SQLite"
                        ).classes("dim").style("font-size:10.5px")
                        ui.button(
                            "添加服务商",
                            icon="add",
                            on_click=lambda: open_provider(None),
                        ).props("flat no-caps").classes("soft-btn")
                    if not providers:
                        ui.label(
                            "还没有服务商节点。添加后，AI 工作窗口会出现可切换的模型下拉框。"
                        ).classes("muted").style("font-size:11.5px;margin-top:10px")
                    else:
                        with ui.element("div").classes("provider-list"):
                            for provider in providers:
                                with ui.element("div").classes(
                                    "provider-row"
                                    + (" active" if str(provider["id"]) == active_id else "")
                                ):
                                    with ui.element("div").classes("provider-main"):
                                        with ui.row().classes("items-center gap-2"):
                                            ui.label(provider["name"]).classes("provider-name")
                                            if str(provider["id"]) == active_id:
                                                ui.label("当前").classes("pill on")
                                        ui.label(provider["model"] or "未填写模型").classes(
                                            "provider-model"
                                        )
                                        ui.label(provider["base_url"] or "未填写 Base URL").classes(
                                            "provider-url"
                                        )
                                    with ui.row().classes("items-center gap-1 no-wrap"):
                                        ui.label(
                                            "Key 已配置" if provider.get("api_key") else "无 Key"
                                        ).classes("provider-key")
                                        ui.button(
                                            icon="edit",
                                            on_click=lambda p=provider: open_provider(p),
                                        ).props("flat round dense size=sm").classes("icon-btn").tooltip(
                                            "编辑服务商"
                                        )
                                        ui.button(
                                            icon="delete_outline",
                                            on_click=lambda p=provider: ask_delete_provider(p),
                                        ).props("flat round dense size=sm").classes("icon-btn").tooltip(
                                            "删除服务商"
                                        )

            providers_panel()

        with ui.element("div").classes("settings-grid"):
            # ------------------------------------------------------------ #
            # 左侧：模型 + DSH
            # ------------------------------------------------------------ #
            with ui.element("div").classes("dash-col"):
                with panel("AI 连接", "smart_toy", "DSH API · 模型 · 工作区"):
                    @ui.refreshable
                    def ai_summary() -> None:
                        cfg_dsh = settings.load()["dsh"]
                        key = (cfg_dsh.get("api_key") or "").strip() or (
                            llm.active_profile().get("api_key") or ""
                        ).strip()
                        stored = bool(cfg_dsh.get("use_stored_credentials")) and dsh_agent.has_stored_credentials()
                        connected = bool(key) or stored
                        effort = EFFORT_LABELS.get(
                            (cfg_dsh.get("reasoning_effort") or "").strip(), "默认"
                        )
                        with ui.element("div").classes("setting-row"):
                            with ui.element("div").classes("min-w-0"):
                                ui.label(
                                    cfg_dsh.get("model") or "未选择（自动检测）"
                                ).classes("setting-label")
                                ui.label(
                                    cfg_dsh.get("workspace", str(settings.WORKSPACE_DIR))
                                ).classes("setting-desc").style("word-break:break-all")
                            ui.label("已连接" if connected else "待配置").classes(
                                "pill on" if connected else "pill warn"
                            )

                        with ui.element("div").classes("hint-box").style("margin-top:10px"):
                            ui.html(
                                f"凭据：{'已配置' if key else ('DSH 已保存' if stored else '<b>未配置</b>')} · "
                                f"模型：<code>{cfg_dsh.get('model') or '自动检测'}</code> · "
                                f"推理：<code>{effort}</code>"
                            )

                    ai_summary()
                    ai_dialog = AISettingsDialog(on_saved=lambda: ai_summary.refresh())

                    with ui.element("div").classes("settings-actions"):
                        ui.button("打开 AI 设置", icon="settings", on_click=lambda: ai_dialog.open()).props(
                            "unelevated no-caps"
                        ).classes("gradient-btn")
                        ui.button("打开 AI 工作", icon="open_in_new", on_click=lambda: ui.navigate.to("/")).props(
                            "flat no-caps"
                        ).classes("soft-btn")

                with panel("DSH 运行时", "terminal", "DeepSeek Harness 本地运行时 · 无需浏览器"):
                    env = dsh_agent.check_environment()
                    for label, value in [
                        ("Node.js", env["node"]),
                        ("DSH 版本", env["dsh"]),
                        ("内置运行时", "是" if env["bundled"] else "否"),
                        ("已保存凭据", "检测到" if env["credentials"] else "未检测到"),
                    ]:
                        with ui.element("div").classes("setting-row"):
                            ui.label(label).classes("setting-label")
                            ui.label(str(value)).classes("dim").style(
                                "font-size:10.5px;max-width:60%;text-align:right;word-break:break-all"
                            )

                    with ui.element("div").classes("settings-actions"):
                        ui.button("检查环境", icon="fact_check", on_click=lambda: check_env()).props(
                            "flat no-caps"
                        ).classes("soft-btn")
                        ui.button("打开工作区", icon="folder_open", on_click=lambda: open_workspace()).props(
                            "flat no-caps"
                        ).classes("soft-btn")

                    with ui.element("div").classes("hint-box").style("margin-top:12px"):
                        ui.html(
                            "DSH 以 <code>headless --json</code> 模式在应用内直接运行，不启动 Web 服务。"
                            "会话记录保存在 <code>~/.dsh/sessions</code>，与 DSH 桌面版共享。"
                            "权限模式在 AI 工作窗口顶部切换，并随每段对话保存。",
                            sanitize=False,
                        )

            # ------------------------------------------------------------ #
            # 右侧：外观 + 数据 + 关于
            # ------------------------------------------------------------ #
            with ui.element("div").classes("dash-col"):
                with panel("外观与启动", "palette", "个性化你的工作站"):
                    with ui.element("div").classes("form-grid"):
                        user_name = ui.input(
                            label="称呼", value=cfg["app"].get("user_name", "HI")
                        ).props("outlined dense").classes("w-full")
                        theme = ui.select(
                            {"dark": "深色 · 星云", "light": "浅色 · 晨雾"},
                            value=cfg["app"].get("theme", "dark"),
                        ).props("outlined dense options-dense").classes("w-full")
                        app_port = ui.number(
                            label="工作站端口", value=int(cfg["app"].get("port", 8080)), min=1024, max=65535, format="%d"
                        ).props("outlined dense").classes("w-full")
                        app_host = ui.input(
                            label="监听地址", value=cfg["app"].get("host", "127.0.0.1")
                        ).props("outlined dense").classes("w-full")
                    with ui.element("div").classes("hint-box").style("margin-top:10px"):
                        ui.html(
                            "主题保存后立即生效；<b>端口与监听地址</b>需要重启 <code>python app.py</code> 才会生效。"
                            "默认只监听本机，不要在不信任的网络中暴露服务。",
                            sanitize=False,
                        )

                with panel("数据与维护", "storage", "本地优先，数据只属于你"):
                    data_size = system.folder_size(settings.DATA_DIR)
                    for label, value in [
                        ("数据库", str(db.DB_FILE)),
                        ("配置文件", str(settings.CONFIG_FILE)),
                        ("数据目录大小", system.human_size(data_size)),
                    ]:
                        with ui.element("div").classes("setting-row"):
                            ui.label(label).classes("setting-label")
                            ui.label(value).classes("dim").style(
                                "font-size:10.5px;max-width:62%;text-align:right;word-break:break-all"
                            )
                    with ui.element("div").classes("settings-actions"):
                        ui.button("打开数据目录", icon="folder_open", on_click=lambda: open_data_dir()).props(
                            "flat no-caps"
                        ).classes("soft-btn")
                        ui.button("重置配置", icon="restart_alt", on_click=lambda: reset_dialog.open()).props(
                            "flat no-caps"
                        ).style("color:#fb7185")

                    with ui.element("div").classes("hint-box").style("margin-top:12px"):
                        ui.html(
                            "API Key 以明文形式保存在本地 <code>config.json</code> 中；"
                            "请勿把 <code>data/</code> 目录提交到 Git 或分享给他人。",
                            sanitize=False,
                        )

                with panel("关于 Anvil", "info", "AI 个人工作站"):
                    with ui.element("div").classes("dsh-meta").style("flex-direction:column;gap:6px"):
                        ui.html("<span>界面 <code>NiceGUI 3.x</code> · 逻辑 <code>Python 3.10+</code></span>", sanitize=False)
                        ui.html("<span>Agent 运行时 <code>DeepSeek Harness · dsh</code></span>", sanitize=False)
                        ui.html("<span>数据 <code>SQLite + JSON</code>，全部本地存储</span>", sanitize=False)
                    with ui.element("div").classes("settings-actions").style("margin-top:12px"):
                        ui.link("DSH 官方仓库", "https://github.com/deepseek-ai/deepseek-harness", new_tab=True).classes(
                            "panel-link"
                        ).style("font-size:11.5px")
                        ui.link("NiceGUI 文档", "https://nicegui.io/documentation", new_tab=True).classes(
                            "panel-link"
                        ).style("font-size:11.5px")

    # -------------------------------------------------------------------- #
    # AI 服务商编辑 / 删除
    # -------------------------------------------------------------------- #
    with ui.dialog() as provider_dialog, ui.card().classes("glass provider-dialog"):
        provider_dialog_title = ui.label("添加 AI 服务商").style(
            "font-size:16px;font-weight:750"
        )
        ui.label(
            "字段保存到 SQLite。Base URL 应与 DSH 使用 Anthropic Messages 兼容端点。"
        ).classes("dialog-sub")

        with ui.element("div").classes("provider-form"):
            provider_name = ui.input(label="服务商名称").props("outlined dense").classes(
                "w-full"
            )
            provider_base = ui.input(
                label="Base URL", placeholder="https://api.example.com/anthropic"
            ).props("outlined dense").classes("w-full")
            provider_key = ui.input(
                label="API Key",
                password=True,
                password_toggle_button=True,
            ).props("outlined dense").classes("w-full")
            provider_model = ui.input(
                label="Model Name", placeholder="例如 deepseek-chat"
            ).props("outlined dense").classes("w-full")

        def save_provider() -> None:
            name = (provider_name.value or "").strip()
            base = (provider_base.value or "").strip()
            model = (provider_model.value or "").strip()
            key = (provider_key.value or "").strip()
            if not name or not base or not model:
                ui.notify("服务商名称、Base URL 和 Model Name 不能为空", type="warning")
                return
            parsed = urlparse(base)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                ui.notify("Base URL 必须是完整的 http(s) 地址", type="negative")
                return
            provider_id = provider_state.get("id")
            if provider_id:
                db.update_ai_provider(int(provider_id), name, base, key, model)
                if str(provider_id) == ai_providers.active_provider_id():
                    ai_providers.activate(int(provider_id))
            else:
                new_id = db.create_ai_provider(name, base, key, model)
                if not ai_providers.active_provider_id():
                    ai_providers.activate(new_id)
            provider_dialog.close()
            providers_panel.refresh()
            ai_summary.refresh()
            ui.notify("AI 服务商已保存", type="positive")

        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("取消", on_click=provider_dialog.close).props("flat no-caps")
            ui.button("保存服务商", icon="save", on_click=save_provider).props(
                "unelevated no-caps"
            ).classes("gradient-btn")

    with ui.dialog() as provider_delete_dialog, ui.card().classes("glass").style(
        "padding:20px 22px;min-width:340px"
    ):
        provider_delete_title = ui.label("").style("font-size:14px;font-weight:700")
        ui.label("删除后不会删除工作区文件，但当前节点会从下拉框中移除。").classes(
            "muted"
        ).style("font-size:11.5px;margin-top:5px")

        def confirm_delete_provider() -> None:
            provider = provider_delete_state.get("provider")
            if provider:
                was_active = str(provider["id"]) == ai_providers.active_provider_id()
                db.delete_ai_provider(int(provider["id"]))
                if was_active:
                    remaining = db.list_ai_providers()
                    if remaining:
                        ai_providers.activate(int(remaining[0]["id"]))
                    else:
                        settings.update(
                            {"dsh": {"active_provider_id": "", "model": ""}}
                        )
            provider_delete_state["provider"] = None
            provider_delete_dialog.close()
            providers_panel.refresh()
            ai_summary.refresh()
            ui.notify("AI 服务商已删除", type="positive")

        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("取消", on_click=provider_delete_dialog.close).props("flat no-caps")
            ui.button("确认删除", on_click=confirm_delete_provider).props(
                "unelevated no-caps"
            ).style("background:#e11d48;color:#fff")

    def open_provider(provider: dict | None = None) -> None:
        provider_state["id"] = provider["id"] if provider else None
        provider_dialog_title.set_text("编辑 AI 服务商" if provider else "添加 AI 服务商")
        provider_name.value = provider["name"] if provider else ""
        provider_base.value = provider["base_url"] if provider else ""
        provider_key.value = provider["api_key"] if provider else ""
        provider_model.value = provider["model"] if provider else ""
        provider_dialog.open()

    def ask_delete_provider(provider: dict) -> None:
        provider_delete_state["provider"] = provider
        provider_delete_title.set_text(f"删除服务商「{provider['name']}」？")
        provider_delete_dialog.open()

    # -------------------------------------------------------------------- #
    # 确认重置
    # -------------------------------------------------------------------- #
    with ui.dialog() as reset_dialog, ui.card().classes("glass").style("padding:20px 22px;min-width:340px"):
        ui.label("重置所有配置？").style("font-size:15px;font-weight:700")
        ui.label("模型密钥、DSH 设置等会恢复默认值，笔记与对话不会被删除。").classes("muted").style(
            "font-size:11.5px;margin-top:4px"
        )

        def do_reset() -> None:
            settings.reset()
            reset_dialog.close()
            ui.notify("配置已重置，正在刷新…", type="positive")
            ui.timer(0.6, lambda: ui.navigate.reload(), once=True)

        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("取消", on_click=reset_dialog.close).props("flat no-caps")
            ui.button("确认重置", on_click=do_reset).props("unelevated no-caps").style(
                "background:#e11d48;color:#fff"
            )

    # -------------------------------------------------------------------- #
    # 行为
    # -------------------------------------------------------------------- #
    def save_fields(silent: bool = False) -> None:
        settings.update(
            {
                "app": {
                    "user_name": (user_name.value or "HI").strip() or "HI",
                    "theme": theme.value or "dark",
                    "port": int(app_port.value or 8080),
                    "host": (app_host.value or "127.0.0.1").strip(),
                }
            }
        )
        # 主题立即应用
        ui.dark_mode((theme.value or "dark") == "dark")
        save_status.set_text("已保存")
        ui.timer(2.0, lambda: save_status.set_text(""), once=True)
        if not silent:
            ui.notify("设置已保存", type="positive")

    async def check_env() -> None:
        ui.notify("正在检查 DSH 运行环境…", type="info")
        result = await asyncio.to_thread(dsh_agent.check_environment)
        with ui.dialog() as dialog, ui.card().classes("glass").style("padding:22px 24px;min-width:420px"):
            ui.label("DSH 环境检查").style("font-size:15px;font-weight:700")
            with ui.element("div").classes("divider"):
                pass
            for label, value in [
                ("Node.js", result["node"]),
                ("DSH 版本", result["dsh"]),
                ("内置运行时", "是" if result["bundled"] else "否（使用 npx）"),
                ("DSH 已保存凭据", "检测到" if result["credentials"] else "未检测到"),
            ]:
                with ui.row().classes("w-full justify-between items-center").style("padding:5px 0"):
                    ui.label(label).classes("muted").style("font-size:12px")
                    ui.label(str(value)).style("font-size:12px;font-family:Consolas,monospace")
            with ui.row().classes("w-full justify-end").style("margin-top:12px"):
                ui.button("关闭", on_click=dialog.close).props("flat no-caps")
        dialog.open()

    def open_workspace() -> None:
        try:
            path = dsh_agent.workspace()
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"无法打开工作区：{exc}", type="negative")

    def open_data_dir() -> None:
        try:
            if os.name == "nt":
                os.startfile(settings.DATA_DIR)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(settings.DATA_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(settings.DATA_DIR)])
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"无法打开目录：{exc}", type="negative")
