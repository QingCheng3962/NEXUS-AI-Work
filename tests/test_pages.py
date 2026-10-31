"""页面冒烟测试：统一 AI 工作窗口与基础页面。"""

import asyncio

import pytest

from core import approval, db, settings
from core.dsh_agent import dsh_agent

pytest_plugins = ["nicegui.testing.user_plugin"]


@pytest.fixture
def selected_model():
    """测试发送流程时临时指定模型，避免依赖本机自动检测结果。"""
    previous = settings.get("dsh.model", "")
    settings.set_value("dsh.model", "test-model")
    yield
    settings.set_value("dsh.model", previous)


async def test_work_page(user) -> None:
    await user.open("/")
    await user.should_see("AI 工作")
    await user.should_see("只读")
    await user.should_see("读写")
    await user.should_see("完全控制")
    await user.should_see("新对话")
    user.find(marker="chat-input")
    user.find(marker="chat-send")
    user.find(marker="history-tab")


async def test_work_aliases(user) -> None:
    await user.open("/chat")
    await user.should_see("AI 工作")
    await user.open("/dsh")
    await user.should_see("AI 工作")


async def test_notes(user) -> None:
    await user.open("/notes")
    await user.should_see("知识笔记")
    await user.should_see("新建笔记")


async def test_tasks(user) -> None:
    await user.open("/tasks")
    await user.should_see("待办事项")
    await user.should_see("添加")


async def test_settings(user) -> None:
    await user.open("/settings")
    await user.should_see("AI 连接")
    await user.should_see("保存设置")


async def test_work_send(user, monkeypatch, tmp_path, selected_model) -> None:
    await user.open("/")
    await user.should_see("简易")
    await user.should_see("调度")
    await user.open("/notes")
    await user.should_see("知识笔记")
    await user.should_see("新建笔记")
    await user.should_see("导入文档")

    async def fake_stream(task, session_id=None, workspace=None, permission="read-only", model=None):
        yield {"type": "session", "sessionId": "fake-session"}
        yield {"type": "status", "phase": "step_start", "step": 1}
        yield {
            "type": "tool_call",
            "callId": "call-1",
            "tool": "read_file",
            "input": {"path": "demo.txt"},
        }
        yield {
            "type": "tool_result",
            "callId": "call-1",
            "status": "ok",
            "result": "demo",
        }
        yield {"type": "text", "text": "这是测试任务的回复。"}
        yield {"type": "_exit", "returncode": 0, "stderr": "", "cancelled": False}

    monkeypatch.setattr(dsh_agent, "available", lambda: True)
    monkeypatch.setattr(dsh_agent, "has_stored_credentials", lambda: True)
    monkeypatch.setattr(dsh_agent, "workspace", lambda: tmp_path)
    monkeypatch.setattr(dsh_agent, "cancel", lambda: None)
    monkeypatch.setattr(dsh_agent, "stream", fake_stream)

    await user.open("/")
    user.find(marker="permission-read-only").click()
    user.find(marker="chat-input").type("执行一个测试任务")
    user.find(marker="chat-send").click()
    await asyncio.sleep(0.4)
    await user.should_see("这是测试任务的回复。")
    await user.should_see("1 次工具调用")

    latest = db.list_dsh_conversations(limit=1)
    if latest:
        db.delete_dsh_conversation(latest[0]["id"])


async def test_read_write_approval(user, monkeypatch, tmp_path, selected_model) -> None:
    async def fake_stream(task, session_id=None, workspace=None, permission="read-only", model=None):
        yield {"type": "tool_call", "callId": "call-1", "tool": "pwsh", "input": "dir"}
        handler = approval.broker.handler
        allowed = await handler({"toolName": "pwsh", "reason": "需要在工作区外执行命令"})
        yield {
            "type": "tool_result",
            "callId": "call-1",
            "status": "ok" if allowed else "error",
            "result": "allowed" if allowed else "rejected",
        }
        yield {"type": "text", "text": "授权流程测试完成。"}
        yield {"type": "_exit", "returncode": 0, "stderr": "", "cancelled": False}

    monkeypatch.setattr(dsh_agent, "available", lambda: True)
    monkeypatch.setattr(dsh_agent, "has_stored_credentials", lambda: True)
    monkeypatch.setattr(dsh_agent, "workspace", lambda: tmp_path)
    monkeypatch.setattr(dsh_agent, "cancel", lambda: None)
    monkeypatch.setattr(dsh_agent, "stream", fake_stream)

    await user.open("/")
    user.find(marker="permission-read-write").click()
    user.find(marker="chat-input").type("执行需要授权的命令")
    user.find(marker="chat-send").click()
    await user.should_see("允许执行这次任务？")
    user.find("允许并运行").click()
    await user.should_see("需要你的授权", retries=20)
    await asyncio.sleep(0.3)
    user.find("允许一次").click()
    await user.should_see("授权流程测试完成。", retries=20)

    settings.set_value("dsh.permission", "read-only")
    latest = db.list_dsh_conversations(limit=1)
    if latest:
        db.delete_dsh_conversation(latest[0]["id"])


async def test_snapshot_diff_and_undo(user, monkeypatch, tmp_path, selected_model) -> None:
    from core import snapshots

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(snapshots, "SNAPSHOT_ROOT", tmp_path / "snapshots")
    monkeypatch.setattr(dsh_agent, "available", lambda: True)
    monkeypatch.setattr(dsh_agent, "has_stored_credentials", lambda: True)
    monkeypatch.setattr(dsh_agent, "workspace", lambda: workspace)
    monkeypatch.setattr(dsh_agent, "cancel", lambda: None)

    async def fake_stream(task, session_id=None, workspace=None, permission="read-only", model=None):
        (workspace / "created.txt").write_text("AI 新建的文件\n", encoding="utf-8")
        yield {"type": "text", "text": "文件已创建。"}
        yield {"type": "_exit", "returncode": 0, "stderr": "", "cancelled": False}

    monkeypatch.setattr(dsh_agent, "stream", fake_stream)
    previous_permission = settings.get("dsh.permission", "read-only")
    settings.set_value("dsh.permission", "read-write")
    try:
        await user.open("/")
        user.find(marker="chat-input").type("创建一个测试文件")
        user.find(marker="chat-send").click()
        await user.should_see("允许执行这次任务？")
        user.find("允许并运行").click()
        await user.should_see("文件已创建。", retries=30)
        await asyncio.sleep(0.8)
        assert (workspace / "created.txt").exists()
        await user.should_see("AI 修改了工作区文件")
        user.find("撤销全部").click()
        await asyncio.sleep(0.8)
        assert not (workspace / "created.txt").exists()
    finally:
        settings.set_value("dsh.permission", previous_permission)
        latest = db.list_dsh_conversations(limit=1)
        if latest:
            db.delete_dsh_conversation(latest[0]["id"])
