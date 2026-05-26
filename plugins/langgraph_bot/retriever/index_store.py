"""FAISS 索引管理 — 构建、保存、加载、搜索。"""

import os
import numpy as np
import faiss
from nonebot.log import logger

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools.index")
_ID_MAP_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools_ids.npy")

_index: faiss.IndexFlatIP | None = None
_id_map: np.ndarray | None = None  # 映射 index[n] → tool_id


def _get_index() -> faiss.IndexFlatIP:
    global _index
    if _index is None:
        _load_or_build()
    return _index


def _get_id_map() -> np.ndarray:
    global _id_map
    if _id_map is None:
        _load_or_build()
    return _id_map


def _load_or_build():
    """从磁盘加载索引，如不存在则报错（需先 build_index）。"""
    global _index, _id_map
    if os.path.exists(_INDEX_PATH) and os.path.exists(_ID_MAP_PATH):
        _index = faiss.read_index(_INDEX_PATH)
        _id_map = np.load(_ID_MAP_PATH)
        logger.info(f"[retriever] FAISS index loaded: {_index.ntotal} tools, dim={_index.d}")
    else:
        raise RuntimeError("FAISS index not found. Call build_index() first.")


def build_index(descriptions: list[tuple[int, str]]):
    """从 (id, description) 列表构建 FAISS 索引。

    首次启动时调用，持久化到磁盘。
    """
    from .encoder import encode

    global _index, _id_map

    ids = [t[0] for t in descriptions]
    texts = [t[1] for t in descriptions]

    vectors = encode(texts)

    dim = vectors.shape[1]
    _index = faiss.IndexFlatIP(dim)  # 内积 = 余弦（因为向量已 normalize）
    _index.add(vectors)
    _id_map = np.array(ids, dtype=np.int64)

    faiss.write_index(_index, _INDEX_PATH)
    np.save(_ID_MAP_PATH, _id_map)

    logger.info(f"[retriever] FAISS index built: {len(ids)} tools, dim={dim}")


def add_tool(tool_id: int, description: str):
    """向索引新增一个工具。"""
    from .encoder import encode

    idx = _get_index()
    id_map = _get_id_map()

    vector = encode([description])
    idx.add(vector)

    global _id_map
    _id_map = np.append(id_map, tool_id)

    faiss.write_index(idx, _INDEX_PATH)
    np.save(_ID_MAP_PATH, _id_map)


def search(query: str, k: int = 5) -> list[int]:
    """检索最相关的 k 个 tool_id。"""
    from .encoder import encode

    idx = _get_index()
    id_map = _get_id_map()
    k = min(k, idx.ntotal)

    vector = encode([query])
    scores, indices = idx.search(vector, k)

    # indices[0] 是 FAISS 内部索引 → 映射到真实 tool_id
    return [int(id_map[i]) for i in indices[0] if i >= 0]


def reload_index():
    """强制重新加载索引（新增工具后调用）。"""
    global _index, _id_map
    _index = None
    _id_map = None
    _load_or_build()
