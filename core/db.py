"""SQLite 数据层：会话、消息、笔记、待办。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .settings import DATA_DIR

DB_FILE = DATA_DIR / "workstation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '新对话',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    priority    TEXT NOT NULL DEFAULT 'normal',
    done        INTEGER NOT NULL DEFAULT 0,
    due         TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    done_at     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dsh_conversations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '新任务',
    dsh_session_id  TEXT NOT NULL DEFAULT '',
    workspace       TEXT NOT NULL DEFAULT '',
    permission      TEXT NOT NULL DEFAULT 'read-only',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dsh_messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL,
    role             TEXT NOT NULL,
    content          TEXT NOT NULL DEFAULT '',
    events_json      TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES dsh_conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dsh_conv_updated ON dsh_conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dsh_messages_conv ON dsh_messages(conversation_id);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(dsh_conversations)").fetchall()
        }
        if "permission" not in columns:
            conn.execute(
                "ALTER TABLE dsh_conversations "
                "ADD COLUMN permission TEXT NOT NULL DEFAULT 'read-only'"
            )
        _migrate_legacy_sessions(conn)


def _migrate_legacy_sessions(conn: sqlite3.Connection) -> None:
    """把旧版普通对话迁移成统一的 AI 工作记录，避免历史丢失。"""
    now = _now()
    sessions = conn.execute(
        """SELECT s.* FROM sessions s
           WHERE EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.id)"""
    ).fetchall()
    for session in sessions:
        conversation_id = f"legacy-{session['id']}"
        exists = conn.execute(
            "SELECT 1 FROM dsh_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO dsh_conversations
               (id, title, dsh_session_id, workspace, permission, created_at, updated_at)
               VALUES (?, ?, '', '', 'read-only', ?, ?)""",
            (
                conversation_id,
                session["title"] or "历史对话",
                session["created_at"] or now,
                session["updated_at"] or now,
            ),
        )
        messages = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session["id"],),
        ).fetchall()
        for message in messages:
            if message["role"] not in ("user", "assistant"):
                continue
            conn.execute(
                """INSERT INTO dsh_messages
                   (conversation_id, role, content, events_json, created_at)
                   VALUES (?, ?, ?, '[]', ?)""",
                (
                    conversation_id,
                    message["role"],
                    message["content"] or "",
                    message["created_at"] or now,
                ),
            )


def _rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _one(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


# --------------------------------------------------------------------------- #
# 会话与消息
# --------------------------------------------------------------------------- #
def create_session(title: str = "新对话") -> str:
    sid = uuid.uuid4().hex[:12]
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, title, now, now),
        )
    return sid


def list_sessions(limit: int = 100, only_with_messages: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM sessions"
    if only_with_messages:
        sql += " WHERE EXISTS (SELECT 1 FROM messages m WHERE m.session_id = sessions.id)"
    sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
    with _connect() as conn:
        return _rows(conn.execute(sql, (limit,)).fetchall())


def get_session(session_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _one(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def rename_session(session_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip()[:60] or "新对话", _now(), session_id),
        )


def delete_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def add_message(session_id: str, role: str, content: str) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))


def list_messages(session_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)
            ).fetchall()
        )


def auto_title(session_id: str, first_message: str) -> None:
    session = get_session(session_id)
    if not session or session["title"] not in ("新对话", ""):
        return
    title = " ".join(first_message.strip().split())
    rename_session(session_id, title[:24])


# --------------------------------------------------------------------------- #
# 笔记
# --------------------------------------------------------------------------- #
def list_notes(query: str = "") -> list[dict[str, Any]]:
    with _connect() as conn:
        if query.strip():
            like = f"%{query.strip()}%"
            rows = conn.execute(
                """SELECT * FROM notes
                   WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
                   ORDER BY updated_at DESC""",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY updated_at DESC").fetchall()
    return _rows(rows)


def get_note(note_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        return _one(conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone())


def create_note(title: str, content: str = "", tags: str = "") -> int:
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO notes (title, content, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (title.strip() or "未命名笔记", content, tags.strip(), now, now),
        )
        return int(cur.lastrowid)


def update_note(note_id: int, title: str, content: str, tags: str) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE notes SET title = ?, content = ?, tags = ?, updated_at = ?
               WHERE id = ?""",
            (title.strip() or "未命名笔记", content, tags.strip(), _now(), note_id),
        )


def delete_note(note_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


# --------------------------------------------------------------------------- #
# 待办
# --------------------------------------------------------------------------- #
def list_tasks(status: str = "all") -> list[dict[str, Any]]:
    with _connect() as conn:
        if status == "open":
            rows = conn.execute(
                "SELECT * FROM tasks WHERE done = 0 ORDER BY done ASC, created_at DESC"
            ).fetchall()
        elif status == "done":
            rows = conn.execute(
                "SELECT * FROM tasks WHERE done = 1 ORDER BY done_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY done ASC, created_at DESC"
            ).fetchall()
    return _rows(rows)


def create_task(title: str, priority: str = "normal", due: str = "", detail: str = "") -> int:
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (title, detail, priority, due, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (title.strip(), detail, priority, due, _now()),
        )
        return int(cur.lastrowid)


def toggle_task(task_id: int, done: bool) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET done = ?, done_at = ? WHERE id = ?",
            (1 if done else 0, _now() if done else "", task_id),
        )


def delete_task(task_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def clear_done_tasks() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE done = 1")


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
def stats() -> dict[str, int]:
    with _connect() as conn:
        sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) AS n FROM messages"
        ).fetchone()["n"]
        messages = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
        notes = conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"]
        open_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE done = 0").fetchone()["n"]
        done_tasks = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE done = 1").fetchone()["n"]
    return {
        "sessions": int(sessions),
        "messages": int(messages),
        "notes": int(notes),
        "open_tasks": int(open_tasks),
        "done_tasks": int(done_tasks),
    }


def recent_sessions(limit: int = 5) -> list[dict[str, Any]]:
    sessions = list_sessions(limit=limit)
    for session in sessions:
        with _connect() as conn:
            last = conn.execute(
                "SELECT content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session["id"],),
            ).fetchone()
        session["preview"] = (last["content"][:80] if last else "").replace("\n", " ")
    return sessions


# --------------------------------------------------------------------------- #
# DSH Agent 会话
# --------------------------------------------------------------------------- #
def create_dsh_conversation(
    title: str = "新任务",
    workspace: str = "",
    permission: str = "read-only",
) -> str:
    cid = uuid.uuid4().hex[:12]
    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO dsh_conversations
               (id, title, workspace, permission, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cid, title.strip() or "新任务", workspace, permission, now, now),
        )
    return cid


def list_dsh_conversations(limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        return _rows(
            conn.execute(
                """SELECT c.*,
                          (SELECT COUNT(*) FROM dsh_messages m WHERE m.conversation_id = c.id) AS message_count
                   FROM dsh_conversations c
                   ORDER BY c.updated_at DESC, c.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        )


def get_dsh_conversation(conversation_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _one(
            conn.execute("SELECT * FROM dsh_conversations WHERE id = ?", (conversation_id,)).fetchone()
        )


def rename_dsh_conversation(conversation_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE dsh_conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip()[:60] or "新任务", _now(), conversation_id),
        )


def set_dsh_session(conversation_id: str, session_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE dsh_conversations SET dsh_session_id = ?, updated_at = ? WHERE id = ?",
            (session_id, _now(), conversation_id),
        )


def delete_dsh_conversation(conversation_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM dsh_messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM dsh_conversations WHERE id = ?", (conversation_id,))


def add_dsh_message(
    conversation_id: str,
    role: str,
    content: str,
    events: list[dict[str, Any]] | None = None,
) -> None:
    import json

    now = _now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO dsh_messages (conversation_id, role, content, events_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, role, content, json.dumps(events or [], ensure_ascii=False), now),
        )
        conn.execute(
            "UPDATE dsh_conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
        )


def list_dsh_messages(conversation_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM dsh_messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        )


def dsh_stats() -> dict[str, int]:
    with _connect() as conn:
        conversations = conn.execute("SELECT COUNT(*) AS n FROM dsh_conversations").fetchone()["n"]
        messages = conn.execute("SELECT COUNT(*) AS n FROM dsh_messages").fetchone()["n"]
    return {"conversations": int(conversations), "messages": int(messages)}


# --------------------------------------------------------------------------- #
# 统一历史：普通对话 + Agent 任务
# --------------------------------------------------------------------------- #
def list_all_conversations(limit: int = 160) -> list[dict[str, Any]]:
    """返回统一历史记录，供侧边栏按日期归档。

    对话框与 Agent 执行已经合并为同一个「AI 工作」线程，因此新记录全部
    保存为 DSH 会话；旧版普通对话会在启动时迁移到同一张表。
    """
    items: list[dict[str, Any]] = []
    for conv in list_dsh_conversations(limit=limit):
        if int(conv.get("message_count") or 0) <= 0:
            continue
        items.append(
            {
                "key": f"agent:{conv['id']}",
                "source": "agent",
                "id": conv["id"],
                "title": conv.get("title") or "新对话",
                "updated_at": conv.get("updated_at") or conv.get("created_at") or "",
                "kind_label": "AI 工作",
                "meta": f"{int(conv.get('message_count') or 0)} 条",
            }
        )
    items.sort(key=lambda item: (item["updated_at"], item["key"]), reverse=True)
    return items[:limit]
