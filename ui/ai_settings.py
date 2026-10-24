"""AI 设置：DSH 连接、模型与工作区。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from nicegui import ui

from core import model_catalog, settings, system

REASONING_OPTIONS = {
    "默认": "",
    "关闭": "off",
    "低": "low",
    "高": "high",
    "最高": "max",
}


class AISettingsDialog:
    """AI 工作窗口共用的连接设置。"""

    def __init__(self, on_saved: Callable[[], None] | None = None) -> None:
        self.on_saved = on_saved
        self.models: list[dict] = model_catalog.cached_models()
        self.detected_source = ""
        self.detecting = False
        self._model_select: ui.select | None = None
        self._status_label: ui.label | None = None
        self._base_input: ui.input | None = None
        self._key_input: ui.input | None = None

        with ui.dialog() as self.dialog, ui.card().classes("glass ai-dialog"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.element("div"):
                    ui.label("AI 设置").classes("dialog-title")
                    ui.label("DSH 连接、模型与工作区").classes("dialog-sub")
                ui.button(icon="close", on_click=self.dialog.close).props(
                    "flat round dense"
                ).classes("icon-btn")

            self.body = self._make_body()
            self.body()

    def open(self) -> None:
        if not self.detecting:
            self.models = model_catalog.cached_models()
        self.body.refresh()
        self.dialog.open()
        if (
            model_catalog.has_credentials()
            and (not self.models or not model_catalog.cache_is_current())
        ):
            self._start_detect(auto=True)

    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, kind: str = "") -> None:
        label = self._status_label
        if label is None:
            return
        try:
            label.set_text(text)
            label.classes(remove="ok err", add=kind)
        except RuntimeError:
            # 对话框已经关闭、元素已被 NiceGUI 回收。
            pass

    def _start_detect(self, auto: bool = False) -> None:
        if self.detecting:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.create_task(self._detect(auto=auto))

    async def _detect(self, auto: bool = False) -> None:
        if self.detecting:
            return
        self.detecting = True
        self._set_status("正在连接 API 检测模型…")
        base = (self._base_input.value or "").strip() if self._base_input else ""
        form_key = (self._key_input.value or "").strip() if self._key_input else ""
        base_arg = base or None
        key_arg = form_key or None
        try:
            models = await asyncio.to_thread(model_catalog.detect_models, base_arg, key_arg)
        except model_catalog.ModelCatalogError as exc:
            self._set_status(str(exc), "err")
            if not auto:
                ui.notify(str(exc), type="negative")
            self.detecting = False
            return
        except Exception as exc:  # noqa: BLE001 - 检测失败不应影响设置窗口
            message = f"检测模型失败：{exc}"
            self._set_status(message, "err")
            if not auto:
                ui.notify(message, type="negative")
            self.detecting = False
            return

        self.models = models
        self.detected_source = model_catalog.source_id(base_arg, key_arg)
        self._apply_model_options(models)
        self._set_status(
            f"已检测到 {len(models)} 个模型，可直接从列表选择。", "ok"
        )

        # 如果当前表单就是已保存的连接，顺手更新缓存，AI 工作窗口即可复用。
        saved = settings.load().get("dsh", {})
        saved_source = model_catalog.source_id(
            (saved.get("base_url") or "").strip(),
            (saved.get("api_key") or "").strip() or None,
        )
        if self.detected_source == saved_source:
            model_catalog.save_catalog(
                models,
                (saved.get("base_url") or "").strip(),
                (saved.get("api_key") or "").strip() or None,
            )
        self.detecting = False

    def _apply_model_options(self, models: list[dict]) -> None:
        select = self._model_select
        if select is None:
            return
        options = model_catalog.select_options(models)
        current = str(select.value or "").strip()
        if current and current not in options:
            options[current] = f"{current} · 当前 API 未返回"
        try:
            select.options = options
            select.update()
            if not current and models:
                select.value = models[0]["id"]
        except RuntimeError:
            pass

    # ------------------------------------------------------------------ #
    def _make_body(self):
        @ui.refreshable
        def body() -> None:
            cfg = settings.load()["dsh"]
            current_model = (cfg.get("model") or "").strip()
            current_effort = (cfg.get("reasoning_effort") or "").strip()
            effort_label = next(
                (label for label, value in REASONING_OPTIONS.items() if value == current_effort),
                "默认",
            )
            options = model_catalog.select_options(self.models)
            if current_model and current_model not in options:
                options[current_model] = (
                    f"{current_model} · 当前 API 未返回"
                    if self.models
                    else f"{current_model} · 未检测"
                )
            initial_model = current_model
            if not initial_model and self.models:
                initial_model = str(self.models[0].get("id") or "")

            with ui.element("div").classes("ai-form").style("margin-top:14px"):
                self._base_input = ui.input(
                    label="API Base URL",
                    value=cfg.get("base_url", ""),
                    placeholder="留空使用 https://api.deepseek.com/anthropic",
                ).props("outlined dense").classes("full")
                self._key_input = ui.input(
                    label="API Key",
                    value=cfg.get("api_key", ""),
                    password=True,
                    password_toggle_button=True,
                ).props("outlined dense").classes("full")

                with ui.row().classes("w-full items-center gap-2 no-wrap full"):
                    self._model_select = ui.select(
                        options,
                        label="模型 · 自动检测",
                        value=initial_model or None,
                        with_input=True,
                        new_value_mode="add-unique",
                    ).props("outlined dense options-dense").classes(
                        "w-full"
                    ).style("flex:1")
                    ui.button(
                        "检测模型",
                        icon="refresh",
                        on_click=lambda: self._start_detect(auto=False),
                    ).props("flat dense no-caps").classes("soft-btn")
                if self.models:
                    status = f"已加载 {len(self.models)} 个模型；检测结果来自当前 API。"
                    kind = "ok"
                elif model_catalog.has_credentials():
                    status = "正在准备自动检测，也可以点击右侧按钮重新检测。"
                    kind = ""
                else:
                    status = "配置 API Key 或启用 DSH 凭据后，会自动检测可用模型。"
                    kind = ""
                self._status_label = ui.label(status).classes(
                    f"model-status full {kind}".strip()
                )

                effort = ui.select(
                    list(REASONING_OPTIONS),
                    label="推理强度",
                    value=effort_label,
                ).props("outlined dense options-dense").classes("w-full")
                workspace = ui.input(
                    label="工作区",
                    value=cfg.get("workspace", str(settings.WORKSPACE_DIR)),
                ).props("outlined dense").classes("full")

            async def browse() -> None:
                selected = await asyncio.to_thread(
                    system.pick_directory, workspace.value or ""
                )
                if selected:
                    workspace.value = selected

            with ui.row().classes("w-full items-center gap-2").style("margin-top:8px"):
                ui.button("浏览…", icon="folder_open", on_click=browse).props(
                    "flat dense no-caps"
                ).classes("soft-btn")
                ui.label("AI 只能在这个目录内读写文件。").classes("dim").style(
                    "font-size:10.5px"
                )

            with ui.element("div").classes("setting-row").style("margin-top:10px"):
                with ui.element("div"):
                    ui.label("使用 DSH 已保存的凭据").classes("setting-label")
                    ui.label("优先使用 ~/.dsh 中 DSH 桌面版保存的登录信息").classes(
                        "setting-desc"
                    )
                stored = ui.switch(
                    value=bool(cfg.get("use_stored_credentials", True))
                ).props("dense")

            with ui.element("div").classes("hint-box").style("margin-top:12px"):
                ui.html(
                    "API Key 以明文保存在本地 <code>data/config.json</code>。"
                    "DSH 使用 Anthropic Messages 兼容端点，默认 "
                    "<code>https://api.deepseek.com/anthropic</code>。"
                    "模型列表从当前 API 的 <code>/models</code> 接口自动读取；"
                    "修改工作区后，新任务会使用新目录，当前对话会自动另起一段。",
                    sanitize=False,
                )

            with ui.element("div").classes("ai-actions"):
                ui.space()
                ui.button("取消", on_click=self.dialog.close).props("flat no-caps")
                save_btn = ui.button("保存", icon="save").props(
                    "unelevated no-caps"
                ).classes("gradient-btn")

            def save() -> None:
                path_text = (workspace.value or str(settings.WORKSPACE_DIR)).strip()
                path = Path(path_text).expanduser()
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    ui.notify(f"无法使用这个工作区：{exc}", type="negative")
                    return

                model_value = str((self._model_select.value if self._model_select else "") or "").strip()
                if not model_value:
                    ui.notify("请先检测并选择一个模型，或直接填写模型 ID", type="warning")
                    return

                new_base = (self._base_input.value or "").strip() if self._base_input else ""
                new_key = (self._key_input.value or "").strip() if self._key_input else ""
                old_base = (cfg.get("base_url") or "").strip()
                old_key = (cfg.get("api_key") or "").strip()
                connection_changed = new_base != old_base or new_key != old_key

                settings.update(
                    {
                        "dsh": {
                            "base_url": new_base,
                            "api_key": new_key,
                            "model": model_value,
                            "reasoning_effort": REASONING_OPTIONS.get(
                                effort.value or "默认", ""
                            ),
                            "workspace": str(path),
                            "use_stored_credentials": bool(stored.value),
                        }
                    }
                )

                saved_key = new_key or None
                source = model_catalog.source_id(new_base, saved_key)
                if self.models and self.detected_source == source:
                    model_catalog.save_catalog(self.models, new_base, saved_key)
                elif connection_changed:
                    model_catalog.clear_catalog()
                if self.on_saved:
                    self.on_saved()
                self.dialog.close()
                ui.notify("AI 设置已保存", type="positive")

            save_btn.on("click", save)

        return body
