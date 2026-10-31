"""待办页：任务增删改查、提醒与完成归档。"""

from __future__ import annotations

from nicegui import ui

from core import db, reminders
from ui.theme import empty_state, page_shell, panel

PRIORITY_LABEL = {"high": "高", "normal": "中", "low": "低"}
PRIORITY_OPTIONS = {"high": "高优先级", "normal": "中优先级", "low": "低优先级"}
FILTER_MAP = {"全部": "all", "进行中": "open", "已完成": "done"}


@ui.page("/tasks", title="待办 · Anvil")
def tasks_page() -> None:
    content = page_shell("待办事项", "管理优先级，把精力放在重要的地方", "tasks")
    state = {"filter": "all"}
    delete_state: dict = {"task": None}

    with content:
        @ui.refreshable
        def summary() -> None:
            all_tasks = db.list_tasks()
            done = sum(1 for t in all_tasks if t["done"])
            open_count = len(all_tasks) - done
            with ui.element("div").classes("summary-strip fade-up"):
                for label, value, color, hint in [
                    ("全部任务", len(all_tasks), "var(--ws-text)", "包含已完成"),
                    ("进行中", open_count, "#22d3ee", "需要你处理"),
                    ("已完成", done, "#34d399", f"完成率 {int(done / len(all_tasks) * 100) if all_tasks else 0}%"),
                ]:
                    with ui.element("div").classes("glass summary-cell"):
                        ui.label(str(value)).classes("summary-num").style(f"color:{color}")
                        ui.label(label).classes("summary-label")
                        ui.label(hint).classes("dim").style("font-size:10px;margin-top:2px")

        summary()

        # 添加任务
        with ui.element("div").classes("glass panel fade-up-1").style("margin-bottom:16px"):
            with ui.element("div").classes("task-add"):
                task_input = ui.input(placeholder="添加一个新任务，按 Enter 快速创建…").props(
                    "outlined dense"
                ).style("flex:1;min-width:240px")
                priority = ui.select(PRIORITY_OPTIONS, value="normal").props(
                    "outlined dense options-dense"
                ).style("width:132px")
                due = ui.input(placeholder="截止日期").props(
                    "outlined dense type=date"
                ).style("width:152px")
                remind = ui.input(placeholder="提醒时间（可选）").props(
                    "outlined dense type=datetime-local clearable"
                ).style("width:202px")
                ui.button("添加", icon="add", on_click=lambda: add_task()).props(
                    "unelevated no-caps"
                ).classes("gradient-btn")
            task_input.on("keydown.enter", lambda: add_task())

        # 筛选
        with ui.element("div").classes("toolbar"):
            ui.toggle(
                list(FILTER_MAP.keys()),
                value="全部",
                on_change=lambda e: (state.__setitem__("filter", FILTER_MAP[e.value]), task_list.refresh()),
            ).props("unelevated no-caps toggle-color=primary")
            ui.space()
            ui.button("清除已完成", icon="delete_sweep", on_click=lambda: clear_done()).props(
                "flat no-caps"
            ).classes("soft-btn")

        @ui.refreshable
        def task_list() -> None:
            tasks = db.list_tasks(state["filter"])
            open_tasks = [task for task in tasks if not task["done"]]
            done_tasks = [task for task in tasks if task["done"]]

            def render_task(task: dict) -> None:
                with ui.element("div").classes(f"task-row{' done' if task['done'] else ''}"):
                    with ui.element("div").classes("min-w-0").style("flex:1"):
                        ui.label(task["title"]).classes("task-name")
                        if task["detail"]:
                            ui.label(task["detail"]).classes("dim").style("font-size:10.5px")
                    if task["due"]:
                        ui.label(f"截止 {task['due']}").classes("task-due")
                    if task.get("remind_at"):
                        with ui.element("div").classes("task-remind"):
                            ui.icon("alarm")
                            ui.label(reminders.display_value(task["remind_at"]))
                    ui.label(PRIORITY_LABEL.get(task["priority"], "中")).classes(
                        f"prio {task['priority']}"
                    )
                    if task["done"]:
                        ui.button(
                            "恢复", icon="undo", on_click=lambda t=task: set_done(t, False)
                        ).props("flat dense no-caps").classes("task-action")
                    else:
                        ui.button(
                            "完成", icon="check", on_click=lambda t=task: set_done(t, True)
                        ).props("flat dense no-caps").classes("task-action complete")
                    ui.button(
                        "删除", icon="close", on_click=lambda t=task: ask_delete(t)
                    ).props("flat dense no-caps").classes("task-action delete")

            with panel(
                "任务清单",
                "checklist",
                {
                    "all": "全部任务",
                    "open": "进行中的任务",
                    "done": "已完成的任务",
                }[state["filter"]],
            ):
                if not tasks:
                    empty_state("task_alt", "这里还没有任务", "在上方输入框里添加第一条待办")
                    return
                if state["filter"] == "done":
                    for task in done_tasks:
                        render_task(task)
                    return
                if open_tasks:
                    for task in open_tasks:
                        render_task(task)
                else:
                    empty_state("task_alt", "没有进行中的任务", "所有任务都已完成")
                if state["filter"] == "all" and done_tasks:
                    with ui.expansion(
                        f"已完成 · {len(done_tasks)}",
                        icon="task_alt",
                    ).classes("done-expansion"):
                        for task in done_tasks:
                            render_task(task)

        task_list()

    # 删除确认
    with ui.dialog() as delete_dialog, ui.card().classes("glass").style(
        "padding:20px 22px;min-width:340px"
    ):
        delete_title = ui.label("").style("font-size:14px;font-weight:700")
        ui.label("删除后无法恢复，确定要继续吗？").classes("muted").style(
            "font-size:11.5px;margin-top:5px"
        )

        def confirm_delete() -> None:
            task = delete_state.get("task")
            if task:
                db.delete_task(task["id"])
            delete_state["task"] = None
            delete_dialog.close()
            summary.refresh()
            task_list.refresh()
            ui.notify("任务已删除", type="positive")

        with ui.row().classes("w-full justify-end gap-2").style("margin-top:16px"):
            ui.button("取消", on_click=delete_dialog.close).props("flat no-caps")
            ui.button("确认删除", icon="delete", on_click=confirm_delete).props(
                "unelevated no-caps"
            ).style("background:#e11d48;color:#fff")

    # -------------------------------------------------------------------- #
    def add_task() -> None:
        title = (task_input.value or "").strip()
        if not title:
            ui.notify("任务内容不能为空", type="warning")
            return
        try:
            remind_at = reminders.normalize_remind_at(remind.value)
        except ValueError as exc:
            ui.notify(str(exc), type="negative")
            return
        db.create_task(
            title,
            priority=priority.value or "normal",
            due=due.value or "",
            remind_at=remind_at,
        )
        task_input.value = ""
        due.value = ""
        remind.value = ""
        summary.refresh()
        task_list.refresh()
        if state["filter"] == "done":
            ui.notify("任务已创建，切换到「进行中」查看", type="info")
        else:
            ui.notify("任务已添加", type="positive")

    def set_done(task: dict, done: bool) -> None:
        db.toggle_task(task["id"], done)
        summary.refresh()
        task_list.refresh()

    def ask_delete(task: dict) -> None:
        delete_state["task"] = task
        delete_title.set_text(f"删除「{task['title'][:40]}」？")
        delete_dialog.open()

    def clear_done() -> None:
        db.clear_done_tasks()
        summary.refresh()
        task_list.refresh()
        ui.notify("已清除完成的任务", type="positive")
