"""提醒字段、到期领取与服务商 CRUD 测试。"""

from __future__ import annotations

import sqlite3

from core import db, reminders


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_FILE", tmp_path / "workstation.db")
    db.init_db()


def test_normalize_remind_at() -> None:
    assert reminders.normalize_remind_at("2026-11-01T09:30") == "2026-11-01 09:30:00"
    assert reminders.normalize_remind_at("2026-11-01 09:30:00") == "2026-11-01 09:30:00"
    assert reminders.normalize_remind_at("") == ""
    try:
        reminders.normalize_remind_at("not-a-date")
    except ValueError as exc:
        assert "格式" in str(exc)
    else:
        raise AssertionError("should reject invalid reminder")


def test_reminder_claim_and_mark(monkeypatch, tmp_path) -> None:
    _isolate_db(monkeypatch, tmp_path)
    task_id = db.create_task("交周报", remind_at="2026-11-01 09:00:00")
    note_id = db.create_note("会议纪要", remind_at="2026-11-01 10:00:00")
    assert db.due_reminders("2026-11-01 08:59:59") == []

    items = db.due_reminders("2026-11-01 09:30:00")
    assert {(item["kind"], item["id"]) for item in items} == {("task", task_id)}
    db.mark_reminders_sent(items)
    assert db.due_reminders("2026-11-01 09:30:00") == []

    items = db.due_reminders("2026-11-01 10:00:00")
    assert [(item["kind"], item["id"]) for item in items] == [("note", note_id)]
    db.mark_reminders_sent(items)
    assert db.due_reminders("2026-11-01 23:59:59") == []

    # 完成后不再提醒。
    other = db.create_task("已完成任务", remind_at="2026-11-01 09:00:00")
    db.toggle_task(other, True)
    assert db.due_reminders("2026-12-01 00:00:00") == []


def test_reminder_migration(monkeypatch, tmp_path) -> None:
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'normal',
            done INTEGER NOT NULL DEFAULT 0,
            due TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            done_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db, "DB_FILE", path)
    db.init_db()
    with sqlite3.connect(path) as check:
        task_cols = {row[1] for row in check.execute("PRAGMA table_info(tasks)")}
        note_cols = {row[1] for row in check.execute("PRAGMA table_info(notes)")}
    assert {"remind_at", "reminder_sent"} <= task_cols
    assert {"remind_at", "reminder_sent"} <= note_cols


def test_ai_provider_crud(monkeypatch, tmp_path) -> None:
    _isolate_db(monkeypatch, tmp_path)
    provider_id = db.create_ai_provider(
        "测试节点", "https://example.com/anthropic", "sk-test", "deepseek-chat"
    )
    provider = db.get_ai_provider(provider_id)
    assert provider and provider["name"] == "测试节点"
    assert db.list_ai_providers()[0]["model"] == "deepseek-chat"

    db.update_ai_provider(
        provider_id, "测试节点 2", "https://example.com/v1", "sk-new", "deepseek-pro"
    )
    provider = db.get_ai_provider(provider_id)
    assert provider and provider["name"] == "测试节点 2"
    assert provider["base_url"].endswith("/v1")

    db.delete_ai_provider(provider_id)
    assert db.get_ai_provider(provider_id) is None
