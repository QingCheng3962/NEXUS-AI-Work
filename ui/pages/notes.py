"""笔记页：Markdown 笔记的本地管理。"""

from __future__ import annotations

import re

from nicegui import ui

from core import db
from ui.theme import empty_state, page_shell, time_ago

DEFAULT_PREVIEW = "*在左侧输入内容，这里会实时预览 Markdown。*"


def _tags(raw: str) -> list[str]:
    parts = re.split(r"[,，;；\s]+", raw or "")
    return [p.lstrip("#") for p in parts if p.strip()]


def _excerpt(text: str, limit: int = 130) -> str:
    clean = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    clean = re.sub(r"[#>*`_\[\]()~-]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:limit] + ("…" if len(clean) > limit else "")


@ui.page("/notes", title="笔记 · NEXUS")
def notes_page() -> None:
    content = page_shell("知识笔记", "Markdown 笔记 · 数据保存在本地", "notes")
    state = {"query": ""}

    with content:
        with ui.element("div").classes("toolbar"):
            search = ui.input(placeholder="搜索标题、内容或标签…").props(
                "outlined dense clearable"
            ).classes("search")
            ui.space()
            ui.button("新建笔记", icon="add", on_click=lambda: open_editor()).props(
                "unelevated no-caps"
            ).classes("gradient-btn")

        notes_area = ui.element("div").classes("w-full")

    def on_search(event) -> None:
        state["query"] = event.value or ""
        render()

    search.on_value_change(on_search)

    def render() -> None:
        notes_area.clear()
        notes = db.list_notes(state["query"])
        with notes_area:
            if not notes:
                empty_state("sticky_note_2", "没有找到笔记", "点击右上角「新建笔记」记录第一条想法")
                return
            with ui.element("div").classes("notes-grid"):
                for note in notes:
                    with ui.element("div").classes("glass note-card fade-up"):
                        with ui.element("div").style("flex:1").on(
                            "click", lambda n=note: open_editor(n)
                        ):
                            ui.label(note["title"]).classes("note-title")
                            ui.label(_excerpt(note["content"]) or "空白笔记").classes("note-excerpt")
                        with ui.element("div").classes("note-foot"):
                            with ui.element("div").classes("tag-row"):
                                for tag in _tags(note["tags"])[:3]:
                                    ui.label(tag).classes("tag")
                            with ui.row().classes("items-center gap-1 no-wrap"):
                                ui.label(time_ago(note["updated_at"])).classes("note-time")
                                ui.button(
                                    icon="delete_outline", on_click=lambda n=note: delete_note(n)
                                ).props("flat round dense size=xs").classes("icon-btn").tooltip("删除笔记")

    def delete_note(note: dict) -> None:
        db.delete_note(note["id"])
        render()
        ui.notify("笔记已删除", type="positive")

    def open_editor(note: dict | None = None) -> None:
        note = note or {}
        refs: dict = {}

        with ui.dialog() as dialog, ui.card().classes("glass note-dialog"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.element("div"):
                    ui.label("编辑笔记" if note else "新建笔记").style("font-size:16px;font-weight:750")
                    ui.label("支持 Markdown · 保存后立即写入本地 SQLite").classes("panel-sub")
                ui.button(icon="close", on_click=dialog.close).props("flat round dense").classes("icon-btn")

            with ui.element("div").classes("editor-grid").style("margin-top:16px"):
                with ui.element("div").classes("editor-col"):
                    title_input = ui.input(label="标题", value=note.get("title", "")).props(
                        "outlined dense"
                    ).classes("w-full")
                    tag_input = ui.input(
                        label="标签", value=note.get("tags", ""), placeholder="例如：工作, 灵感, 学习"
                    ).props("outlined dense").classes("w-full")
                    content_input = ui.textarea(
                        label="正文", value=note.get("content", ""), placeholder="写点什么…"
                    ).props("outlined autogrow").classes("w-full").style("min-height:300px")

                with ui.element("div").classes("editor-col"):
                    ui.label("实时预览").classes("panel-sub")
                    preview = ui.markdown(note.get("content") or DEFAULT_PREVIEW).classes(
                        "ws-markdown preview-pane"
                    )
                    refs["preview"] = preview

            def update_preview(event=None) -> None:
                value = getattr(event, "value", None) if event is not None else content_input.value
                refs["preview"].set_content(value or DEFAULT_PREVIEW)

            content_input.on_value_change(update_preview)

            def save() -> None:
                title = (title_input.value or "").strip() or "未命名笔记"
                body = content_input.value or ""
                tags = tag_input.value or ""
                if note.get("id"):
                    db.update_note(note["id"], title, body, tags)
                else:
                    db.create_note(title, body, tags)
                dialog.close()
                render()
                ui.notify("笔记已保存", type="positive")

            with ui.row().classes("w-full items-center gap-2").style("margin-top:16px"):
                if note.get("id"):
                    ui.button(
                        "删除", icon="delete_outline", on_click=lambda: confirm_delete.open()
                    ).props("flat no-caps").style("color:#fb7185")
                ui.space()
                ui.button("取消", on_click=dialog.close).props("flat no-caps")
                ui.button("保存", icon="save", on_click=save).props("unelevated no-caps").classes(
                    "gradient-btn"
                )

        with ui.dialog() as confirm_delete, ui.card().classes("glass").style(
            "padding:20px 22px;min-width:300px"
        ):
            ui.label("删除这条笔记？").style("font-size:14px;font-weight:700")
            ui.label("删除后无法恢复。").classes("muted").style("font-size:11.5px;margin-top:4px")

            def do_delete() -> None:
                db.delete_note(note.get("id"))
                confirm_delete.close()
                dialog.close()
                render()
                ui.notify("笔记已删除", type="positive")

            with ui.row().classes("w-full justify-end gap-2").style("margin-top:14px"):
                ui.button("取消", on_click=confirm_delete.close).props("flat no-caps")
                ui.button("删除", on_click=do_delete).props("unelevated no-caps").style(
                    "background:#e11d48;color:#fff"
                )

        dialog.open()

    render()
