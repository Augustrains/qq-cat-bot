"""重载人设工具。"""

from langchain_core.tools import tool

from ..context import invalidate_character_cache, load_character


@tool
async def reload_character_prompt() -> str:
    """强制从磁盘重新加载机器人的人设、记忆和用户画像。

    当用户要求重载人设、刷新记忆、/reload 时使用此工具。
    通常在编辑了 characters/default/ 下的文件后使用。
    """
    invalidate_character_cache()
    prompt = load_character()
    return f"人设和记忆已重新加载喵~（{len(prompt)} 字符）"
