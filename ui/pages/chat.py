"""AI 工作：对话与 Agent 执行合并在同一个窗口。"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from nicegui import ui

from core import (
    approval,
    db,
    llm,
    model_catalog,
    model_router,
    security,
    settings,
    snapshots,
    system,
)
from core.dsh_agent import dsh_agent
from ui.ai_settings import AISettingsDialog
from ui.theme import page_shell

PERMISSION_ORDER = ["read-only", "read-write", "full"]
PERMISSIONS = {
    "read-only": {
        "label": "只读",
        "icon": "visibility",
        "desc": "AI 可以读取工作区，但不能修改文件；高风险命令会被拒绝。",
        "dsh": "read-only",
    },
    "read-write": {
        "label": "读写",
        "note": "命令需确认",
        "icon": "edit_note",
        "desc": "AI 可以修改工作区文件；需要提升权限的命令会先请求你确认。",
        "dsh": "workspace-write",
    },
    "full": {
        "label": "完全控制",
        "note": "高风险",
        "icon": "gpp_maybe",
        "desc": "AI 可以修改任意文件并执行任意命令。仅用于可信项目。",
        "dsh": "danger-full-access",
    },
}


def permission_info(value: str) -> dict:
    return PERMISSIONS.get(value, PERMISSIONS["read-only"])


def permission_text(value: str) -> str:
    info = permission_info(value)
    return f"{info['label']}（{info['note']}）" if info.get("note") else info["label"]


def workspace_name(path: str | Path) -> str:
    value = str(path)
    name = Path(value).name
    return name or value


@ui.page("/", title="AI 工作 · Anvil")
@ui.page("/chat", title="AI 工作 · Anvil")
@ui.page("/dsh", title="AI 工作 · Anvil")
def chat_page() -> None:
    shell = page_shell("", "", "chat", header=False, flush=True)

    request = ui.context.client.request
    params = request.query_params
    conversation_id = params.get("agent") or ""
    legacy_id = params.get("session") or ""
    if not conversation_id and legacy_id:
        candidate = f"legacy-{legacy_id}"
        if db.get_dsh_conversation(candidate):
            conversation_id = candidate
    conversation = db.get_dsh_conversation(conversation_id) if conversation_id else None

    default_workspace = str(dsh_agent.workspace())
    default_permission = settings.get("dsh.permission", "read-only")
    if default_permission not in PERMISSIONS:
        default_permission = "read-only"

    default_mode = str(settings.get("dsh.router.mode", "direct") or "direct")
    if default_mode not in ("direct", "router"):
        default_mode = "direct"

    state: dict = {
        "cid": conversation["id"] if conversation else None,
        "dsh_session": (conversation.get("dsh_session_id") or "") if conversation else "",
        "workspace": (conversation.get("workspace") or default_workspace) if conversation else default_workspace,
        "permission": (conversation.get("permission") or default_permission) if conversation else default_permission,
        "mode": default_mode,
        "busy": False,
        "cancel": False,
        "pending": "",
    }
    if state["permission"] not in PERMISSIONS:
        state["permission"] = "read-only"

    client = ui.context.client

    def page_alive() -> bool:
        return not getattr(client, "is_deleted", True)

    def has_credentials() -> bool:
        cfg = settings.load()
        if (cfg["dsh"].get("api_key") or "").strip():
            return True
        if (os.environ.get("DEEPSEEK_API_KEY") or "").strip():
            return True
        if (llm.active_profile().get("api_key") or "").strip():
            return True
        return bool(cfg["dsh"].get("use_stored_credentials")) and dsh_agent.has_stored_credentials()

    def open_folder(path: str | Path) -> None:
        try:
            target = str(path)
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:  # noqa: BLE001
            ui.notify(f"无法打开目录：{exc}", type="negative")

    # ------------------------------------------------------------------ #
    # 主界面
    # ------------------------------------------------------------------ #
    with shell:
        with ui.element("div").classes("work-page"):
            with ui.element("div").classes("work-head"):
                with ui.element("div").classes("work-head-left"):
                    work_title = ui.label("AI 工作").classes("work-title")
                    work_title.mark("work-title")
                    work_sub = ui.label("").classes("work-sub")
                with ui.element("div").classes("work-actions"):
                    @ui.refreshable
                    def mode_control() -> None:
                        ui.toggle(
                            {"direct": "简易", "router": "调度"},
                            value=state["mode"],
                            on_change=lambda e: choose_mode(str(e.value or "direct")),
                        ).props("unelevated dense no-caps").classes("mode-toggle").tooltip(
                            "简易：始终使用当前模型；调度：按任务自动选择轻量/强模型，并可主备降级"
                        )

                    @ui.refreshable
                    def model_control() -> None:
                        if state["mode"] == "router":
                            cfg = settings.load().get("dsh", {}).get("router", {}) or {}
                            summary = (
                                f"轻量 {cfg.get('cheap_model') or '未配置'} · "
                                f"强模型 {cfg.get('strong_model') or '未配置'} · "
                                f"备用 {cfg.get('fallback_model') or '无'}"
                            )
                            with ui.element("div").classes("work-model-empty").on(
                                "click", lambda: ai_dialog.open()
                            ).tooltip(summary):
                                ui.icon("alt_route")
                                ui.label("自动调度").classes("work-model-empty-label")
                            return

                        current = (settings.get("dsh.model", "") or "").strip()
                        options = model_catalog.select_options()
                        if current and current not in options:
                            options[current] = f"{current} · 未检测"
                        if not options:
                            with ui.element("div").classes("work-model-empty").on(
                                "click", lambda: ai_dialog.open()
                            ).tooltip("打开 AI 设置，自动检测当前 API 的模型"):
                                ui.icon("travel_explore")
                                ui.label("检测模型").classes("work-model-empty-label")
                            return
                        ui.select(
                            options,
                            value=current or None,
                            on_change=lambda e: settings.set_value(
                                "dsh.model", str(e.value or "")
                            ),
                        ).props("outlined dense options-dense").classes(
                            "work-model"
                        ).tooltip("当前 API 自动检测到的模型")

                    mode_control()
                    model_control()
                    stop_btn = ui.button(icon="stop_circle", on_click=lambda: stop()).props(
                        "flat round dense"
                    ).classes("icon-btn").tooltip("停止当前执行")
                    stop_btn.disable()
                    ui.button("新对话", icon="add", on_click=lambda: new_chat()).props(
                        "unelevated no-caps"
                    ).classes("new-chat-top")
                    ui.button(
                        icon="delete_sweep", on_click=lambda: clear_dialog.open()
                    ).props("flat round dense").classes("icon-btn").tooltip("删除当前对话")
                    ui.button(
                        icon="settings", on_click=lambda: ai_dialog.open()
                    ).props("flat round dense").classes("icon-btn").tooltip("AI 设置")

            with ui.element("div").classes("work-toolbar"):
                @ui.refreshable
                def workspace_control() -> None:
                    with ui.element("div").classes("work-chip").on(
                        "click", lambda: workspace_dialog.open()
                    ).tooltip(str(state["workspace"])):
                        ui.icon("folder_open")
                        ui.label(workspace_name(state["workspace"])).classes("work-chip-label")
                        ui.icon("expand_more").classes("work-chip-caret")

                @ui.refreshable
                def permission_control() -> None:
                    with ui.element("div").classes("permission-switch"):
                        for key in PERMISSION_ORDER:
                            info = PERMISSIONS[key]
                            active = state["permission"] == key
                            classes = "perm-btn"
                            if active:
                                classes += " active"
                            if key == "full":
                                classes += " danger"
                            button = ui.element("div").classes(classes).on(
                                "click", lambda k=key: choose_permission(k)
                            )
                            button.mark(f"permission-{key}")
                            with button:
                                ui.icon(info["icon"])
                                ui.label(info["label"]).classes("perm-name")
                                if info.get("note"):
                                    ui.label(info["note"]).classes("perm-note")
                                ui.tooltip(info["desc"])

                workspace_control()
                ui.element("div").classes("work-toolbar-sep")
                ui.label("权限").classes("work-toolbar-label")
                permission_control()

            scroll = ui.scroll_area().classes("work-scroll")
            with scroll:
                message_box = ui.column().classes("w-full gap-0")

            with ui.element("div").classes("composer work-composer"):
                with ui.element("div").classes("composer-box"):
                    box = ui.textarea(
                        placeholder="描述你想完成的事。Enter 发送，Shift + Enter 换行…"
                    ).props("borderless dense autogrow id=work-composer").classes(
                        "composer-input"
                    ).style("flex:1")
                    box.mark("chat-input")
                    ui.button(icon="settings", on_click=lambda: ai_dialog.open()).props(
                        "flat round dense"
                    ).classes("icon-btn ai-gear").tooltip("AI 设置")
                    send_btn = ui.button(
                        icon="arrow_upward", on_click=lambda: send(box.value or "")
                    ).props("unelevated round id=work-send data-work-send=1").classes(
                        "gradient-btn work-send"
                    ).style("width:38px;height:38px;min-width:38px")
                    send_btn.mark("chat-send")
                composer_hint = ui.label("").classes("composer-hint")

    def after_ai_saved() -> None:
        configured = str(dsh_agent.workspace())
        if configured != state["workspace"]:
            if state["busy"]:
                ui.notify("工作区设置已保存，将在新对话中生效", type="info")
                return
            apply_workspace(configured)
            return
        mode_control.refresh()
        model_control.refresh()
        workspace_control.refresh()
        update_header()

    ai_dialog = AISettingsDialog(on_saved=after_ai_saved)

    # ------------------------------------------------------------------ #
    # 弹窗
    # ------------------------------------------------------------------ #
    with ui.dialog() as workspace_dialog, ui.card().classes("glass work-dialog"):
        ui.label("选择工作区").classes("dialog-title")
        ui.label("AI 只在这个目录内读写。切换工作区会开始一段新对话。").classes(
            "dialog-sub"
        )
        workspace_input = ui.input(
            label="目录", value=state["workspace"]
        ).props("outlined dense").classes("w-full").style("margin-top:14px")

        async def browse_workspace() -> None:
            selected = await asyncio.to_thread(
                system.pick_directory, workspace_input.value or state["workspace"]
            )
            if selected:
                workspace_input.value = selected
            elif not selected:
                ui.notify("没有选择目录，可直接输入路径", type="info")

        with ui.row().classes("w-full items-center justify-between").style("margin-top:12px"):
            with ui.row().classes("items-center gap-2"):
                ui.button("浏览…", icon="folder_open", on_click=browse_workspace).props(
                    "flat dense no-caps"
                ).classes("soft-btn")
                ui.button(
                    "打开", icon="open_in_new",
                    on_click=lambda: open_folder(workspace_input.value or state["workspace"]),
                ).props("flat dense no-caps").classes("soft-btn")
            with ui.row().classes("items-center gap-2"):
                ui.button("取消", on_click=workspace_dialog.close).props("flat no-caps")
                ui.button(
                    "使用此目录", icon="check", on_click=lambda: save_workspace()
                ).props("unelevated no-caps").classes("gradient-btn")

    with ui.dialog() as run_confirm_dialog, ui.card().classes("glass work-dialog"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("terminal").style("color:#fbbf24;font-size:22px")
            with ui.element("div"):
                ui.label("允许执行这次任务？").classes("dialog-title")
                ui.label("当前权限：读写（命令需确认）").classes("dialog-sub")
        confirm_preview = ui.label("").classes("confirm-preview")
        ui.label(
            "AI 可能修改工作区文件。需要提升权限的命令会在执行前弹出授权窗口；"
            "当前确认只代表你允许启动这次任务。"
        ).classes("muted").style("font-size:11.5px;margin-top:10px;line-height:1.65")
        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("取消", on_click=run_confirm_dialog.close).props("flat no-caps")
            ui.button(
                "允许并运行", icon="play_arrow", on_click=lambda: confirm_run()
            ).props("unelevated no-caps").classes("gradient-btn")

    with ui.dialog() as risk_dialog, ui.card().classes("glass work-dialog risk-dialog"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("gpp_maybe").style("color:#fb7185;font-size:20px")
            ui.label("确认启用完全控制？").classes("risk-title")
        ui.label(
            "开启后，AI 将减少确认步骤，可以直接修改文件、执行命令或访问网络。"
            "仅在你信任当前任务时使用。"
        ).classes("risk-desc")
        risk_ack = ui.checkbox("我已了解风险，并愿意继续").props("dense").classes(
            "risk-ack"
        )
        with ui.row().classes("w-full justify-end gap-2").style("margin-top:14px"):
            ui.button("取消", on_click=risk_dialog.close).props("flat no-caps")
            risk_btn = ui.button(
                "启用完全控制", icon="lock_open", on_click=lambda: confirm_full_control()
            ).props("unelevated no-caps").classes("risk-btn")
            risk_btn.disable()

        risk_ack.on_value_change(
            lambda e: risk_btn.enable() if e.value else risk_btn.disable()
        )

    approval_state: dict[str, object] = {"future": None}

    with ui.dialog() as approval_dialog, ui.card().classes("glass work-dialog approval-dialog"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("verified_user").style("color:#fbbf24;font-size:24px")
            with ui.element("div"):
                ui.label("需要你的授权").classes("dialog-title")
                ui.label("AI 请求执行一个需要提升权限的操作").classes("dialog-sub")
        approval_tool = ui.label("").classes("approval-tool")
        approval_reason = ui.label("").classes("approval-reason")
        ui.label(
            "这次授权只对当前操作有效，不会自动放宽后续操作。"
        ).classes("muted").style("font-size:10.5px;margin-top:10px")
        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("拒绝", on_click=lambda: finish_approval(False)).props("flat no-caps")
            ui.button(
                "允许一次", icon="check", on_click=lambda: finish_approval(True)
            ).props("unelevated no-caps").classes("gradient-btn")

    with ui.dialog() as clear_dialog, ui.card().classes("glass work-dialog"):
        ui.label("删除当前对话？").style("font-size:14px;font-weight:700")
        ui.label("这段 AI 工作记录会从本地数据库中删除，且无法恢复。").classes(
            "muted"
        ).style("font-size:11.5px;margin-top:4px")
        with ui.row().classes("w-full justify-end gap-2").style("margin-top:14px"):
            ui.button("取消", on_click=clear_dialog.close).props("flat no-caps")
            ui.button("删除", on_click=lambda: (clear_dialog.close(), delete_current())).props(
                "unelevated no-caps"
            ).style("background:#e11d48;color:#fff")

    # ------------------------------------------------------------------ #
    # 文件修改对比
    # ------------------------------------------------------------------ #
    diff_state: dict = {"id": "", "changes": []}

    def _diff_html(change: snapshots.FileDiff) -> str:
        if change.binary:
            return (
                '<div class="diff-binary">二进制文件已修改，无法显示行级差异。'
                "可以撤销全部修改，或接受当前结果。</div>"
            )
        rows: list[str] = []
        for line in (change.diff or "").splitlines():
            if line.startswith("+++") or line.startswith("---"):
                css = "meta"
            elif line.startswith("+"):
                css = "add"
            elif line.startswith("-"):
                css = "del"
            elif line.startswith("@@"):
                css = "hunk"
            else:
                css = "ctx"
            rows.append(
                f'<span class="diff-line {css}">{html_lib.escape(line) or " "}</span>'
            )
        if not rows:
            return '<div class="diff-binary">没有可显示的行级差异。</div>'
        return '<pre class="diff-pre">' + "\n".join(rows) + "</pre>"

    with ui.dialog() as diff_dialog, ui.card().classes("glass diff-dialog"):
        with ui.row().classes("w-full items-center justify-between"):
            with ui.element("div"):
                ui.label("AI 修改了工作区文件").classes("dialog-title")
                diff_summary = ui.label("").classes("dialog-sub")
            ui.icon("difference").style("color:var(--ws-amber);font-size:22px")
        diff_select = ui.select(
            {}, value=None, on_change=lambda e: _render_selected_diff(str(e.value or ""))
        ).props("outlined dense options-dense").classes("w-full").style("margin-top:12px")
        diff_view = ui.html("", sanitize=False).classes("diff-view")
        with ui.row().classes("w-full justify-end gap-2").style("margin-top:14px"):
            undo_btn = ui.button(
                "撤销全部", icon="undo", on_click=lambda: _undo_diff()
            ).props("flat no-caps").style("color:#fb7185")
            accept_btn = ui.button(
                "接受修改", icon="check", on_click=lambda: _accept_diff()
            ).props("unelevated no-caps").classes("gradient-btn")

    def _render_selected_diff(path: str) -> None:
        changes = diff_state.get("changes") or []
        change = next((item for item in changes if item.path == path), None)
        diff_view.set_content(_diff_html(change) if change else "")

    def show_diff(snapshot_id: str, changes: list[snapshots.FileDiff]) -> None:
        diff_state["id"] = snapshot_id
        diff_state["changes"] = changes
        # 上一次撤销会禁用按钮；新任务开始时重新启用。
        accept_btn.enable()
        undo_btn.enable()
        additions = sum(item.additions for item in changes)
        deletions = sum(item.deletions for item in changes)
        diff_summary.set_text(
            f"{len(changes)} 个文件 · +{additions} 行 / -{deletions} 行"
        )
        options = {
            item.path: (
                ("新增 · " if item.kind == "added" else "删除 · " if item.kind == "deleted" else "修改 · ")
                + item.path
            )
            for item in changes
        }
        diff_select.options = options
        diff_select.update()
        first = changes[0].path
        diff_select.value = first
        _render_selected_diff(first)
        diff_dialog.open()

    def _accept_diff() -> None:
        snapshot_id = str(diff_state.get("id") or "")
        if snapshot_id:
            snapshots.discard(snapshot_id)
        diff_state["id"] = ""
        diff_state["changes"] = []
        diff_dialog.close()
        ui.notify("已接受本次文件修改", type="positive")

    async def _undo_diff() -> None:
        snapshot_id = str(diff_state.get("id") or "")
        if not snapshot_id:
            diff_dialog.close()
            return
        accept_btn.disable()
        undo_btn.disable()
        try:
            ok, message = await asyncio.to_thread(snapshots.restore, snapshot_id)
        except Exception as exc:  # noqa: BLE001
            ok, message = False, f"撤销失败：{exc}"
        diff_state["id"] = ""
        diff_state["changes"] = []
        diff_dialog.close()
        ui.notify(message, type="positive" if ok else "negative")
        update_header()

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def render_user(text: str) -> None:
        with ui.element("div").classes("msg-row user"):
            with ui.element("div").classes("msg-bubble"):
                ui.label(text)

    def render_static_trace(events: list[dict]) -> None:
        if not events:
            return
        tools = sum(1 for event in events if event.get("type") == "tool_call")
        title = f"执行轨迹 · {tools} 次工具调用" if tools else "执行轨迹"
        with ui.expansion(title, icon="account_tree").classes("agent-trace"):
            with ui.element("div").classes("agent-trace-body"):
                call_map: dict[str, tuple[ui.label, ui.element]] = {}
                for event in events:
                    kind = event.get("type")
                    if kind == "thinking" and event.get("text"):
                        ui.markdown(event["text"]).classes("ws-markdown agent-thinking")
                    elif kind == "tool_call":
                        status, body = _tool_card(
                            event.get("tool") or "tool",
                            event.get("input"),
                            event.get("callId", ""),
                        )
                        call_map[event.get("callId", "")] = (status, body)
                    elif kind == "tool_result":
                        pair = call_map.get(event.get("callId", ""))
                        if pair:
                            _fill_tool_result(
                                pair[0], pair[1], event.get("status", ""), event.get("result", "")
                            )
                    elif kind == "stderr" and event.get("text"):
                        with ui.expansion("诊断输出", icon="bug_report").classes("agent-trace"):
                            ui.code(event["text"][-4000:], language="text").classes("w-full")

    def render_assistant_message(message: dict) -> None:
        try:
            events = json.loads(message.get("events_json") or "[]")
        except json.JSONDecodeError:
            events = []
        tools = sum(1 for event in events if event.get("type") == "tool_call")
        route = next(
            (event.get("text", "") for event in events if event.get("type") == "route"),
            "",
        )
        with ui.element("div").classes("msg-row assistant"):
            with ui.element("div").classes("msg-bubble work-bubble"):
                with ui.element("div").classes("work-msg-head"):
                    ui.icon("auto_awesome")
                    ui.label("AI").classes("work-msg-name")
                    if route:
                        ui.label(
                            f"{route} · {tools} 次工具调用" if tools else route
                        ).classes("work-msg-meta")
                    elif tools:
                        ui.label(f"{tools} 次工具调用").classes("work-msg-meta")
                if message.get("content"):
                    ui.markdown(message["content"]).classes("ws-markdown")
                render_static_trace(events)

    def render_empty() -> None:
        with ui.element("div").classes("work-empty"):
            with ui.element("div").classes("work-empty-icon"):
                ui.icon("auto_awesome")
            ui.label("开始工作").classes("work-empty-title")
            ui.label(
                "直接描述目标。AI 会读取当前工作区，并在你选择的权限内修改文件或执行命令。"
            ).classes("work-empty-sub")
            with ui.element("div").classes("work-empty-meta"):
                with ui.element("div").classes("empty-chip"):
                    ui.icon("folder_open")
                    ui.label(workspace_name(state["workspace"]))
                with ui.element("div").classes("empty-chip"):
                    ui.icon(permission_info(state["permission"])["icon"])
                    ui.label(permission_text(state["permission"]))

    def render_thread() -> None:
        message_box.clear()
        rows = db.list_dsh_messages(state["cid"]) if state["cid"] else []
        with message_box:
            if not rows:
                render_empty()
            else:
                for message in rows:
                    if message["role"] == "user":
                        render_user(message["content"])
                    else:
                        render_assistant_message(message)
        scroll.scroll_to(percent=1.0)

    def update_header() -> None:
        conv = db.get_dsh_conversation(state["cid"]) if state["cid"] else None
        work_title.set_text(conv["title"] if conv else "AI 工作")
        work_sub.set_text(
            f"{model_router.mode_label(state['mode'])} · "
            f"{workspace_name(state['workspace'])} · {permission_text(state['permission'])}"
        )

    def update_composer() -> None:
        hint = "Enter 发送 · Shift + Enter 换行"
        if state["mode"] == "router":
            hint += " · 调度模式：自动选择模型"
        if state["permission"] == "read-write":
            hint += " · 修改前自动快照 · 高风险命令会请求授权"
        elif state["permission"] == "full":
            hint += " · 修改前自动快照 · 完全控制已开启，请谨慎操作"
        composer_hint.set_text(hint)
        composer_hint.style(
            "color:#fbbf24" if state["permission"] == "full" else "color:var(--ws-dim)"
        )

    # ------------------------------------------------------------------ #
    # 操作
    # ------------------------------------------------------------------ #
    def set_url() -> None:
        target = f"/?agent={quote(state['cid'])}" if state["cid"] else "/"
        ui.run_javascript(
            f"window.history.replaceState(null, '', {json.dumps(target)})"
        )

    def choose_mode(value: str) -> None:
        mode = value if value in ("direct", "router") else "direct"
        if mode == state["mode"]:
            return
        state["mode"] = mode
        settings.set_value("dsh.router.mode", mode)
        if mode == "router":
            model_router.bootstrap_router_models()
            cfg = settings.load().get("dsh", {}).get("router", {}) or {}
            if not (cfg.get("cheap_model") or cfg.get("strong_model")):
                ui.notify("调度模型还没有配置，请先在 AI 设置中检测模型", type="warning")
        model_control.refresh()
        update_header()
        update_composer()

    def refresh_controls() -> None:
        mode_control.refresh()
        workspace_control.refresh()
        permission_control.refresh()
        update_header()
        update_composer()

    def reset_thread() -> None:
        state["cid"] = None
        state["dsh_session"] = ""
        state["pending"] = ""

    def new_chat(notice: str = "") -> None:
        if state["busy"]:
            ui.notify("请先停止当前执行", type="warning")
            return
        reset_thread()
        state["workspace"] = str(dsh_agent.workspace())
        state["permission"] = settings.get("dsh.permission", "read-only")
        if state["permission"] not in PERMISSIONS:
            state["permission"] = "read-only"
        refresh_controls()
        render_thread()
        set_url()
        shell.set_active_session(None)
        shell.refresh_history()
        box.run_method("focus")
        if notice:
            ui.notify(notice, type="info")

    def apply_workspace(path_text: str) -> None:
        if state["busy"]:
            ui.notify("请先停止当前执行", type="warning")
            return
        try:
            path = security.workspace_root((path_text or "").strip())
        except (OSError, security.SecurityError) as exc:
            ui.notify(f"无法使用这个工作区：{exc}", type="negative")
            return
        had_thread = bool(state["cid"] and db.list_dsh_messages(state["cid"]))
        settings.set_value("dsh.workspace", str(path))
        state["workspace"] = str(path)
        workspace_dialog.close()
        if had_thread:
            new_chat(notice="工作区已切换，已开始新对话")
        else:
            refresh_controls()
            render_thread()

    def save_workspace() -> None:
        apply_workspace(workspace_input.value or "")

    def choose_permission(value: str) -> None:
        if state["busy"]:
            ui.notify("请先停止当前执行", type="warning")
            return
        if value == state["permission"]:
            return
        if value == "full":
            risk_ack.value = False
            risk_btn.disable()
            risk_dialog.open()
            return
        apply_permission(value)

    def apply_permission(value: str) -> None:
        if value not in PERMISSIONS or value == state["permission"]:
            return
        had_thread = bool(state["cid"] and db.list_dsh_messages(state["cid"]))
        state["permission"] = value
        settings.set_value("dsh.permission", value)
        permission_control.refresh()
        update_header()
        update_composer()
        if had_thread:
            new_chat(notice=f"权限已切换为「{permission_text(value)}」，已开始新对话")
        else:
            render_thread()

    def confirm_full_control() -> None:
        risk_dialog.close()
        apply_permission("full")

    def delete_current() -> None:
        if state["busy"]:
            ui.notify("请先停止当前执行", type="warning")
            return
        if state["cid"]:
            db.delete_dsh_conversation(state["cid"])
        reset_thread()
        refresh_controls()
        render_thread()
        set_url()
        shell.set_active_session(None)
        shell.refresh_history()
        ui.notify("对话已删除", type="positive")

    def stop() -> None:
        state["cancel"] = True
        finish_approval(False)
        dsh_agent.cancel()
        stop_btn.disable()

    def finish_approval(allow: bool) -> None:
        future = approval_state.get("future")
        if future is not None and not future.done():  # type: ignore[union-attr]
            future.set_result(allow)  # type: ignore[union-attr]
        approval_state["future"] = None
        approval_dialog.close()

    async def on_approval_request(payload: dict) -> bool:
        if not page_alive():
            return False
        future = asyncio.get_running_loop().create_future()
        approval_state["future"] = future
        tool = str(payload.get("toolName") or "工具")
        reason = str(payload.get("reason") or "这个操作需要你的确认。")
        approval_tool.set_text(tool)
        approval_reason.set_text(reason)
        approval_dialog.open()
        try:
            return await asyncio.wait_for(future, timeout=300)
        except asyncio.TimeoutError:
            return False
        finally:
            if approval_state.get("future") is future:
                approval_state["future"] = None
            approval_dialog.close()

    async def send(text: str | None = None) -> None:
        if state["busy"]:
            ui.notify("正在执行，请稍候…", type="warning")
            return
        message = (text if isinstance(text, str) else (box.value or "")).strip()
        if not message:
            return
        state["pending"] = message
        if state["permission"] == "read-write":
            confirm_preview.set_text(message)
            run_confirm_dialog.open()
            return
        await run_message(message)

    async def confirm_run() -> None:
        run_confirm_dialog.close()
        message = state["pending"]
        state["pending"] = ""
        if message:
            await run_message(message)

    async def run_message(message: str) -> None:
        if state["busy"]:
            return
        if not dsh_agent.available():
            ui.notify("DSH 运行时不可用，请检查安装包或 Node.js", type="negative")
            return
        if state["mode"] == "router":
            model_router.bootstrap_router_models()
        decision = model_router.choose(message, mode=state["mode"])
        if not decision.model:
            ui.notify("请先在 AI 设置中检测并选择模型", type="warning")
            ai_dialog.open()
            return
        if not has_credentials():
            ui.notify("请先在 AI 设置中配置 API Key 或 DSH 凭据", type="warning")
            ai_dialog.open()
            return

        state["busy"] = True
        state["cancel"] = False
        send_btn.disable()
        stop_btn.enable()
        box.value = ""
        finish_approval(False)
        approval.broker.handler = on_approval_request

        cid = state["cid"]
        if not cid:
            cid = db.create_dsh_conversation(
                title=message[:28],
                workspace=state["workspace"],
                permission=state["permission"],
            )
            state["cid"] = cid
            set_url()
        else:
            conv = db.get_dsh_conversation(cid)
            if conv and conv["title"] in ("新对话", "新任务", ""):
                db.rename_dsh_conversation(cid, message[:28])

        db.add_dsh_message(cid, "user", message)
        update_header()
        render_thread()
        shell.set_active_session(f"agent:{cid}")
        shell.refresh_history()

        conv = db.get_dsh_conversation(cid) or {}
        session_id = (conv.get("dsh_session_id") or "") or None
        raw_workspace = Path(conv.get("workspace") or state["workspace"]).expanduser()
        permission = conv.get("permission") or state["permission"]
        if permission not in PERMISSIONS:
            permission = "read-only"

        workspace = raw_workspace
        workspace_error = ""
        try:
            workspace = security.ensure_workspace(raw_workspace)
        except (OSError, security.SecurityError) as exc:
            workspace_error = str(exc)

        with message_box:
            with ui.element("div").classes("msg-row assistant"):
                with ui.element("div").classes("msg-bubble work-bubble"):
                    with ui.element("div").classes("work-msg-head"):
                        ui.icon("auto_awesome")
                        ui.label("AI").classes("work-msg-name")
                        status_text = ui.label(
                            f"正在启动 · {decision.model}"
                        ).classes("work-msg-meta")
                    answer_md = ui.markdown("").classes("ws-markdown")
                    trace = ui.expansion("执行轨迹", icon="account_tree").classes("agent-trace")
                    trace.set_visibility(False)
                    with trace:
                        with ui.element("div").classes("agent-trace-body"):
                            thinking_md = ui.markdown("").classes("ws-markdown agent-thinking")
                            thinking_md.set_visibility(False)
                            trace_box = ui.element("div").classes("w-full")
        scroll.scroll_to(percent=1.0)

        answer = ""
        thinking = ""
        steps = 0
        calls: dict[str, tuple[ui.label, ui.element]] = {}
        stored_events: list[dict] = []
        final_reason = ""
        exit_error = ""
        stderr_text = ""
        snapshot_id = ""
        snapshot_error = ""
        used_fallback = False
        route_used = decision.model
        attempt_models = [decision.model]
        if decision.fallback and decision.fallback != decision.model:
            attempt_models.append(decision.fallback)

        def reset_live() -> None:
            nonlocal answer, thinking, steps, stored_events, final_reason, exit_error, stderr_text
            answer = ""
            thinking = ""
            steps = 0
            stored_events = []
            final_reason = ""
            exit_error = ""
            stderr_text = ""
            calls.clear()
            answer_md.set_content("")
            thinking_md.set_content("")
            thinking_md.set_visibility(False)
            trace.set_visibility(False)
            trace_box.clear()
            scroll.scroll_to(percent=1.0)

        try:
            if workspace_error:
                exit_error = f"工作区不可用：{workspace_error}"
            elif permission != "read-only" and settings.get("dsh.snapshot_enabled", True):
                status_text.set_text("正在创建文件快照…")
                try:
                    info = await asyncio.to_thread(
                        snapshots.capture, workspace, label=message[:80]
                    )
                    snapshot_id = info.id
                    if info.skipped and page_alive():
                        ui.notify(
                            f"有 {len(info.skipped)} 个文件未纳入快照（过大或不可读）",
                            type="info",
                        )
                except Exception as exc:  # noqa: BLE001
                    snapshot_error = str(exc)
                    exit_error = f"无法创建文件快照，任务已取消：{exc}"
                    status_text.set_text("已取消")

            if not workspace_error and not snapshot_error:
                for attempt, active_model in enumerate(attempt_models):
                    if attempt:
                        reset_live()
                        used_fallback = True
                        route_used = active_model
                        status_text.set_text(f"主力模型不可用，切换到 {active_model}…")
                    produced = False
                    status_text.set_text(f"执行中 · {active_model}")
                    try:
                        async for event in dsh_agent.stream(
                            message,
                            session_id=session_id,
                            workspace=workspace,
                            permission=PERMISSIONS[permission]["dsh"],
                            model=active_model,
                        ):
                            if not page_alive():
                                dsh_agent.cancel()
                                continue

                            kind = event.get("type")
                            if kind == "session":
                                sid = event.get("sessionId", "")
                                if sid:
                                    state["dsh_session"] = sid
                                    db.set_dsh_session(cid, sid)
                                    update_header()
                            elif kind == "status":
                                phase = event.get("phase")
                                if phase == "step_start":
                                    steps = max(steps, int(event.get("step", 0)))
                                    status_text.set_text(
                                        f"执行中 · {active_model} · 第 {steps} 步"
                                    )
                                elif phase == "turn_end":
                                    reason = event.get("reason") or {}
                                    if reason.get("kind") == "error":
                                        err = reason.get("error") or {}
                                        final_reason = (
                                            f"{err.get('code', 'ERROR')}: "
                                            f"{err.get('message', '执行失败')}"
                                        )
                            elif kind == "thinking":
                                chunk = event.get("text", "")
                                if chunk:
                                    thinking += chunk
                                    trace.set_visibility(True)
                                    thinking_md.set_visibility(True)
                                    thinking_md.set_content(thinking)
                                    stored_events.append({"type": "thinking", "text": chunk})
                                    scroll.scroll_to(percent=1.0)
                            elif kind == "text":
                                chunk = event.get("text", "")
                                if chunk:
                                    produced = True
                                    answer += ("\n\n" if answer.strip() else "") + chunk
                                    answer_md.set_content(answer)
                                    scroll.scroll_to(percent=1.0)
                            elif kind == "tool_call":
                                produced = True
                                trace.set_visibility(True)
                                trace.open()
                                status_text.set_text(
                                    f"执行中 · {active_model} · 调用 "
                                    f"{event.get('tool', 'tool')}"
                                )
                                with trace_box:
                                    status, body = _tool_card(
                                        event.get("tool") or "tool",
                                        event.get("input"),
                                        event.get("callId", ""),
                                    )
                                calls[event.get("callId", "")] = (status, body)
                                stored_events.append(
                                    {
                                        "type": "tool_call",
                                        "callId": event.get("callId", ""),
                                        "tool": event.get("tool", ""),
                                        "input": event.get("input"),
                                    }
                                )
                                scroll.scroll_to(percent=1.0)
                            elif kind == "tool_result":
                                produced = True
                                pair = calls.get(event.get("callId", ""))
                                if pair:
                                    _fill_tool_result(
                                        pair[0],
                                        pair[1],
                                        event.get("status", ""),
                                        event.get("result", ""),
                                    )
                                stored_events.append(
                                    {
                                        "type": "tool_result",
                                        "callId": event.get("callId", ""),
                                        "status": event.get("status", ""),
                                        "result": event.get("result", ""),
                                    }
                                )
                                status_text.set_text(f"执行中 · {active_model}…")
                                scroll.scroll_to(percent=1.0)
                            elif kind == "final":
                                text_value = event.get("text", "")
                                if isinstance(text_value, str) and text_value:
                                    produced = True
                                    answer = text_value
                                    answer_md.set_content(answer)
                            elif kind == "error":
                                exit_error = event.get("message", "执行失败")
                            elif kind == "_exit":
                                if event.get("returncode"):
                                    exit_error = exit_error or event.get("stderr", "")
                                stderr_text = event.get("stderr", "") or ""
                                if event.get("cancelled"):
                                    answer += ("\n\n" if answer.strip() else "") + "*（已停止）*"
                                    answer_md.set_content(answer)
                                status_text.set_text(
                                    "已完成"
                                    if event.get("returncode") == 0
                                    else "执行超时"
                                    if event.get("timed_out")
                                    else "执行结束"
                                )
                                scroll.scroll_to(percent=1.0)
                    except Exception as exc:  # noqa: BLE001
                        exit_error = f"运行异常：{exc}"

                    failure_text = "\n".join(
                        [final_reason, exit_error, stderr_text, dsh_agent.last_error]
                    )
                    if (
                        attempt + 1 < len(attempt_models)
                        and not produced
                        and model_router.is_balance_error(failure_text)
                    ):
                        continue
                    break
        finally:
            finish_approval(False)
            if approval.broker.handler is on_approval_request:
                approval.broker.handler = None
            state["busy"] = False
            state["cancel"] = False
            if page_alive():
                send_btn.enable()
                stop_btn.disable()

            if not answer.strip():
                if exit_error or final_reason:
                    reason = " ".join(str(final_reason or exit_error).split())
                    answer = f"⚠️ 执行未完成。\n\n> {reason}"
                elif stderr_text.strip():
                    answer = f"⚠️ 执行未完成。\n\n> {' '.join(stderr_text.split())[-800:]}"
                else:
                    answer = "没有返回结果。"

            if stderr_text.strip() and not final_reason:
                stored_events.append({"type": "stderr", "text": stderr_text[-6000:]})
            if final_reason and final_reason not in answer:
                stored_events.append({"type": "thinking", "text": f"⚠️ {final_reason}"})
            if not snapshot_error and not workspace_error:
                route_label = f"备用模型 · {route_used}" if used_fallback else decision.display()
                stored_events.insert(0, {"type": "route", "text": route_label})

            db.add_dsh_message(cid, "assistant", answer, stored_events)

            if snapshot_id:
                try:
                    changes = await asyncio.to_thread(snapshots.diff, snapshot_id)
                except Exception as exc:  # noqa: BLE001
                    changes = []
                    if page_alive():
                        ui.notify(f"生成文件对比失败：{exc}", type="warning")
                if changes and page_alive():
                    show_diff(snapshot_id, changes)
                else:
                    snapshots.discard(snapshot_id)

            if page_alive():
                update_header()
                render_thread()
                shell.set_active_session(f"agent:{cid}")
                shell.refresh_history()
                if exit_error:
                    ui.notify("执行结束，但没有完整完成", type="warning")

    # ------------------------------------------------------------------ #
    # 键盘：Enter 发送，Shift+Enter 换行
    # ------------------------------------------------------------------ #
    ui.add_body_html(
        """
        <script>
        (function () {
          if (window.__anvilWorkEnterBound) return;
          window.__anvilWorkEnterBound = true;
          document.addEventListener('keydown', function (event) {
            var target = event.target;
            if (!target || !target.closest || !target.closest('.composer-input')) return;
            if (event.key !== 'Enter' || event.shiftKey) return;
            if (event.isComposing || event.keyCode === 229) return;
            event.preventDefault();
            var button = document.querySelector('.work-send');
            if (button) button.click();
          }, true);
        })();
        </script>
        """
    )

    # 初始状态
    update_header()
    update_composer()
    render_thread()
    shell.set_active_session(f"agent:{state['cid']}" if state["cid"] else None)


# ---------------------------------------------------------------------- #
# Agent 工具卡片
# ---------------------------------------------------------------------- #
def _tool_card(tool: str, tool_input, call_id: str) -> tuple[ui.label, ui.element]:
    with ui.element("div").classes("tool-card"):
        with ui.element("div").classes("tool-head"):
            with ui.element("div").classes("tool-icon"):
                ui.icon("build")
            ui.label(tool).classes("tool-name")
            status = ui.label("运行中").classes("tool-status")
        preview = (
            json.dumps(tool_input, ensure_ascii=False)
            if not isinstance(tool_input, str)
            else tool_input
        )
        preview = preview.strip()
        if preview and preview not in ("{}", "null"):
            ui.label(preview[:300] + ("…" if len(preview) > 300 else "")).classes("tool-args")
        body = ui.element("div").classes("tool-body")
    return status, body


def _fill_tool_result(
    status: ui.label, body: ui.element, result_status: str, result: str
) -> None:
    ok = result_status != "error"
    status.set_text("完成" if ok else "失败")
    status.classes(remove="ok err", add="ok" if ok else "err")
    text = (result or "").strip() or "（无输出）"
    with body:
        ui.code(text[:4000], language="text").classes("w-full")
