"""Tool Gate — 上下文溢出保护。

当工具数超过 TOOL_GATE_THRESHOLD 时，根据用户消息关键词筛选相关工具子集，
避免工具定义占用过多上下文窗口。

工作原理：
1. 维护每个工具的触发关键词列表
2. 用户消息匹配到哪些关键词 → 只发送匹配的工具给 LLM
3. 纯聊天消息（无关键词匹配）→ 返回空工具列表，LLM 直接回复

未来（工具 > 20）：可替换为 embedding 语义检索。
"""

import os
from langchain_core.tools import BaseTool

# 工具 → 触发关键词
TOOL_KEYWORDS: dict[str, list[str]] = {
    "search_weibo": ["微博", "weibo", "搜", "热搜", "搜索微博"],
    "switch_chat_model": ["切换", "模型", "deepseek", "claude", "模式", "切到", "换到", "后端"],
    "switch_output_mode": ["语音", "文字", "声音", "输出", "说话", "tts"],
    "show_bot_status": ["状态", "status", "当前", "配置"],
    "clear_conversation_history": ["清除", "清空", "忘记", "重置", "重来", "记忆"],
    "reload_character_prompt": ["重载", "人设", "刷新"],
}


def filter_tools_for_message(user_message: str, all_tools: list[BaseTool]) -> list[BaseTool]:
    """根据用户消息返回相关的工具子集。"""
    matched: set[str] = set()
    msg = user_message.lower()

    for tool_name, keywords in TOOL_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in msg:
                matched.add(tool_name)
                break

    if not matched:
        # 纯聊天消息 — 不加任何工具，LLM 直接回复
        return []

    return [t for t in all_tools if t.name in matched]
