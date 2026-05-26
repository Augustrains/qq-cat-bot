"""人设 prompt 加载 — mtime 感知缓存，从 auto_chat.py 提取。"""

import os
from nonebot.log import logger

_character_prompt: str = ""
_character_mtimes: dict[str, float] = {}

CHARACTER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "characters", "default")
LEGACY_CHARACTER_FILE = os.getenv("CHARACTER_FILE", "")
FALLBACK_PROMPT = os.getenv("FALLBACK_PROMPT", "你是一个友善、有用的QQ机器人助手。用简洁自然的中文回复。")


def load_character() -> str:
    """读取人设文件（system.md + memory.md + profile.md）。
    仅在 mtime 变化或首次加载时才重新读盘。
    """
    global _character_prompt, _character_mtimes

    sources: list[tuple[str, str]] = []

    system_file = os.path.join(CHARACTER_DIR, "system.md")
    if os.path.isfile(system_file):
        for fname in ("system.md", "memory.md", "profile.md"):
            fpath = os.path.join(CHARACTER_DIR, fname)
            if os.path.isfile(fpath):
                sources.append((fname, fpath))
    elif LEGACY_CHARACTER_FILE:
        path = os.path.join(os.path.dirname(__file__), "..", "..", LEGACY_CHARACTER_FILE)
        if os.path.isfile(path):
            sources.append(("legacy", path))

    if not sources:
        logger.warning("Character prompt not found, using fallback")
        return FALLBACK_PROMPT

    needs_reload = not _character_prompt
    for _, fpath in sources:
        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            continue
        if _character_mtimes.get(fpath, 0) != mtime:
            needs_reload = True
            _character_mtimes[fpath] = mtime

    if not needs_reload:
        return _character_prompt

    parts = []
    for _, fpath in sources:
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(content)
        except FileNotFoundError:
            pass

    if parts:
        _character_prompt = "\n\n".join(parts)
        logger.info("[langgraph] character prompt reloaded (mtime changed)")
    else:
        _character_prompt = FALLBACK_PROMPT

    return _character_prompt


def invalidate_character_cache():
    """强制下次 load_character() 重新读盘。"""
    global _character_mtimes
    _character_mtimes.clear()
