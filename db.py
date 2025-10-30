import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from typing import Iterable, List, Optional, Tuple


DB_PATH = "tasks.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                priority TEXT,
                date TEXT,
                timestamp INTEGER,
                is_done INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            """
        )


def get_or_create_user(chat_id: int, username: Optional[str]) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row:
            return int(row[0])
        conn.execute(
            "INSERT INTO users (chat_id, username) VALUES (?, ?)",
            (chat_id, username),
        )
        new_id = conn.execute("SELECT id FROM users WHERE chat_id = ?", (chat_id,)).fetchone()[0]
        return int(new_id)


def add_task(user_id: int, text: str, priority: str) -> None:
    ts = int(datetime.now().timestamp())
    d = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO tasks (user_id, text, priority, date, timestamp, is_done)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, text, priority, d, ts),
        )


def _priority_order_clause() -> str:
    # high first, then medium, then low; then by id asc (older first)
    return "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id"


def list_active_tasks(chat_id: int) -> List[Tuple[int, str, str, str, int]]:
    # Returns list of tuples: (task_id, text, priority, date, timestamp)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, t.text, t.priority, t.date, t.timestamp
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE u.chat_id = ? AND t.is_done = 0
            ORDER BY {_priority_order_clause()}
            """,
            (chat_id,),
        ).fetchall()
        return [(int(r[0]), r[1], r[2], r[3], int(r[4])) for r in rows]


def list_today_tasks(chat_id: int) -> List[Tuple[int, str, str, str, int]]:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, t.text, t.priority, t.date, t.timestamp
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE u.chat_id = ? AND t.is_done = 0 AND t.date = ?
            ORDER BY {_priority_order_clause()}
            """,
            (chat_id, today),
        ).fetchall()
        return [(int(r[0]), r[1], r[2], r[3], int(r[4])) for r in rows]


def list_high_priority_tasks(chat_id: int) -> List[Tuple[int, str, str, str, int]]:
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT t.id, t.text, t.priority, t.date, t.timestamp
            FROM tasks t
            JOIN users u ON u.id = t.user_id
            WHERE u.chat_id = ? AND t.is_done = 0 AND t.priority = 'high'
            ORDER BY id
            """,
            (chat_id,),
        ).fetchall()
        return [(int(r[0]), r[1], r[2], r[3], int(r[4])) for r in rows]


def mark_done_by_index(chat_id: int, index_in_list: int) -> Optional[Tuple[int, str]]:
    # Map index (1-based) to ordered active tasks, mark as done, return (id, text)
    tasks = list_active_tasks(chat_id)
    if index_in_list < 1 or index_in_list > len(tasks):
        return None
    task_id, text, *_ = tasks[index_in_list - 1]
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET is_done = 1 WHERE id = ?", (task_id,))
    return (task_id, text)


def delete_by_index(chat_id: int, index_in_list: int) -> Optional[Tuple[int, str]]:
    tasks = list_active_tasks(chat_id)
    if index_in_list < 1 or index_in_list > len(tasks):
        return None
    task_id, text, *_ = tasks[index_in_list - 1]
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return (task_id, text)


def clear_done(chat_id: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM tasks
            WHERE id IN (
                SELECT t.id FROM tasks t
                JOIN users u ON u.id = t.user_id
                WHERE u.chat_id = ? AND t.is_done = 1
            )
            """,
            (chat_id,),
        )
        return cur.rowcount


