"""工具检索 — Sentence-BERT + FAISS + SQLite 统一接口。

用法:
    from .retriever import init_retriever, search_tools

    init_retriever()                      # 启动时初始化
    tools = search_tools("帮我搜微博AI")   # 返回 Top-5 LangChain Tool 对象
"""

from nonebot.log import logger

from . import tool_meta, index_store
from ..tools import TOOL_MAP as _TOOL_MAP

_initialized = False


def init_retriever():
    """启动时初始化：建表 + 构建/加载 FAISS 索引。

    幂等调用，多次调用不会重复初始化。
    """
    global _initialized
    tool_meta.init_tools_table()

    try:
        index_store.reload_index()
        logger.info("[retriever] index loaded from disk")
    except RuntimeError:
        # 首次启动：从 DB 读取工具描述，构建索引
        descs = tool_meta.get_all_descriptions()
        if descs:
            index_store.build_index(descs)
            logger.info("[retriever] index built from DB")
        else:
            logger.warning("[retriever] no tools registered, skipping index build")

    _initialized = True


def search_tools(query: str, k: int = 5):
    """检索最相关的 k 个工具。

    Returns:
        list[BaseTool]: LangChain Tool 对象列表，可直接 bind 给 LLM。
    """
    ids = index_store.search(query, k=k)
    metas = tool_meta.get_by_ids(ids)

    tools = []
    for meta in metas:
        name = meta["name"]
        if name in _TOOL_MAP:
            tools.append(_TOOL_MAP[name])
        else:
            logger.warning(f"[retriever] tool '{name}' not found in TOOL_MAP")

    return tools


def register_and_index(name: str, category: str, description: str, fc_schema: dict):
    """注册新工具的元数据，并增量更新 FAISS 索引。"""
    tool_meta.register_tool(name, category, description, fc_schema)

    # 查找该工具的 DB ID
    import sqlite3
    db_path = tool_meta._DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    row = conn.execute("SELECT id FROM tools WHERE name=?", (name,)).fetchone()
    conn.close()

    if row:
        index_store.add_tool(row[0], description)
