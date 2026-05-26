"""工具元数据 SQLite CRUD — 存储工具描述、分类、FC schema。"""

import json
import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "chat_history.db")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def init_tools_table():
    """创建 tools 元数据表（幂等）。"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL DEFAULT 'general',
            description TEXT NOT NULL,
            fc_schema TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def register_tool(name: str, category: str, description: str, fc_schema: dict):
    """注册或更新一个工具的元数据。"""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO tools (name, category, description, fc_schema)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(name) DO UPDATE SET
             category=excluded.category,
             description=excluded.description,
             fc_schema=excluded.fc_schema,
             active=1""",
        (name, category, description, json.dumps(fc_schema, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_all_active() -> list[dict]:
    """获取所有活跃工具。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, name, category, description, fc_schema FROM tools WHERE active=1 ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "name": r["name"], "category": r["category"],
         "description": r["description"], "fc_schema": json.loads(r["fc_schema"])}
        for r in rows
    ]


def get_by_ids(ids: list[int]) -> list[dict]:
    """按 ID 批量查询工具元数据。"""
    if not ids:
        return []
    conn = _get_conn()
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, name, category, description, fc_schema FROM tools WHERE id IN ({placeholders}) ORDER BY id",
        ids,
    ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "name": r["name"], "category": r["category"],
         "description": r["description"], "fc_schema": json.loads(r["fc_schema"])}
        for r in rows
    ]


def get_all_descriptions() -> list[tuple[int, str]]:
    """获取所有活跃工具的 (id, description) 列表，用于构建索引。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, description FROM tools WHERE active=1 ORDER BY id"
    ).fetchall()
    conn.close()
    return [(r["id"], r["description"]) for r in rows]
