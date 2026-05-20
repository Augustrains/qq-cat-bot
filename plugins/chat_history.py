import sqlite3
import asyncio
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chat_history.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """在 bot 启动时调用一次。"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            backend TEXT DEFAULT '',
            model TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON messages(created_at)")
    conn.commit()
    conn.close()


async def save_message(user_id: str, role: str, content: str, backend: str = "", model: str = ""):
    """异步写入一条消息。"""
    def _write():
        conn = _get_conn()
        conn.execute(
            "INSERT INTO messages (user_id, role, content, backend, model) VALUES (?, ?, ?, ?, ?)",
            (user_id, role, content, backend, model),
        )
        conn.commit()
        conn.close()

    await asyncio.to_thread(_write)
