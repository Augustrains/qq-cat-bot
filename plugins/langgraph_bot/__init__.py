"""LangGraph Bot 插件 — NoneBot2 入口。

当 LANGGRAPH_ENABLED=true 时，拦截所有消息并用 LangGraph ReAct agent 处理。
当 LANGGRAPH_ENABLED=false 时，退回到旧架构（auto_chat.py + weibo_search.py）。
"""

import os
import asyncio
import json
from nonebot import on_message
from nonebot.rule import Rule
from nonebot.log import logger
from nonebot.adapters.qq import Bot, C2CMessageCreateEvent, GroupAtMessageCreateEvent

from .agent import run_agent
from .sessions import sessions, get_user_id, get_active_model, new_session
from .context import load_character, invalidate_character_cache
from .streaming import process_response
from .tools import register_tools, set_user_context
from .tools import mode_switch as _mode_switch
from .tools import clear as _clear
from .tools import status as _status
from .tools import reload_char as _reload_char
from ..chat_history import save_message

LANGGRAPH_ENABLED = os.getenv("LANGGRAPH_ENABLED", "false").lower() == "true"


async def _is_qq_chat(event) -> bool:
    return isinstance(event, (C2CMessageCreateEvent, GroupAtMessageCreateEvent))


# ============================================================
# Slash 命令预处理 — 精确匹配的命令直接执行，不走 LLM
# ============================================================

SLASH_TOOL: dict[str, str] = {
    "/clear": "clear",
    "/reset": "clear",
    "清除记忆": "clear",
    "重置对话": "clear",
    "/reload": "reload",
    "重载人设": "reload",
    "/status": "status",
    "当前后端": "status",
    "当前状态": "status",
}

SLASH_SWITCH: dict[str, dict] = {
    "/deepseek": {"backend": "deepseek", "model": "deepseek-chat"},
    "/claude": {"backend": "claude", "model": "claude-sonnet-4-6"},
}


async def _handle_slash_command(bot: Bot, event, user_id: str, raw: str) -> bool:
    """精确匹配 slash 命令，直接执行并发送结果。返回 True 表示已处理。"""
    set_user_context(user_id)

    if raw in SLASH_SWITCH:
        cfg = SLASH_SWITCH[raw]
        session = sessions[user_id]
        session["backend"] = cfg["backend"]
        session["model_override"] = cfg["model"]
        label = cfg["model"]
        await bot.send(event, f"已切换到 {label} 喵。想聊什么喵？")
        return True

    if raw in SLASH_TOOL:
        tool_name = SLASH_TOOL[raw]
        if tool_name == "clear":
            result = await _clear.clear_conversation_history.ainvoke({})
        elif tool_name == "reload":
            result = await _reload_char.reload_character_prompt.ainvoke({})
        elif tool_name == "status":
            result = await _status.show_bot_status.ainvoke({})
        else:
            return False
        await bot.send(event, str(result))
        return True

    # /deepseek <message> 或 /claude <message>：切换后端 + 发送消息
    for prefix, cfg in SLASH_SWITCH.items():
        if raw.startswith(prefix + " "):
            content = raw[len(prefix):].strip()
            if not content:
                continue
            session = sessions[user_id]
            session["backend"] = cfg["backend"]
            session["model_override"] = cfg["model"]
            # 不 return False — 让后续 agent 处理消息
            # 但先去掉了前缀，agent 收到的就是纯消息
            new_event_text = content
            # 修改 event 的 text... 不行，event 是只读的
            # 直接调用 agent 处理
            return await _handle_agent(bot, event, user_id, content)

    return False


async def _handle_agent(bot: Bot, event, user_id: str, text: str) -> bool:
    """通过 LangGraph agent 处理一条消息。返回 True 表示成功。"""
    session = sessions[user_id]
    backend_name, model_name = get_active_model(session)
    output_mode = session["output_mode"]

    logger.info(f"[langgraph] [{backend_name}:{model_name}] user={user_id}: {text[:50]}...")

    try:
        # 保存用户消息到 DB
        asyncio.create_task(save_message(user_id, "user", text, backend_name, model_name))

        # 运行 agent 并流式输出
        token_stream = run_agent(
            user_message=text,
            user_id=user_id,
            backend_name=backend_name,
            model_name=model_name,
            output_mode=output_mode,
        )

        full_text = await process_response(
            bot, event, token_stream, output_mode,
            user_id, backend_name, model_name,
        )

        # 更新轮数
        session[backend_name]["rounds"] = session[backend_name].get("rounds", 0) + 1

        logger.info(f"[langgraph] reply: {full_text[:100]}...")
        return True

    except Exception as e:
        logger.error(f"[langgraph] error: {e}")
        await bot.send(event, "猫脑过载了喵...等会儿再试试喵")
        return False


# ============================================================
# 注册 NoneBot 消息处理器（仅在 LANGGRAPH_ENABLED=true 时）
# ============================================================

if LANGGRAPH_ENABLED:
    # 预热：加载工具 + 初始化检索器 + 注册工具元数据
    register_tools()
    load_character()

    try:
        from .retriever import init_retriever, register_and_index
        from .retriever import tool_meta as _tool_meta
        from .tools import TOOL_META
        # Phase 1: 注册工具元数据到 SQLite（不触发模型加载）
        for name, meta in TOOL_META.items():
            _tool_meta.register_tool(name, meta["category"], meta["description"], meta["fc_schema"])
        # Phase 2: 构建/加载 FAISS 索引（触发 SBERT 模型下载）
        init_retriever()
        logger.info("[langgraph] retriever initialized (FAISS + SBERT)")
    except Exception as e:
        logger.warning(f"[langgraph] retriever init failed ({e}), using all-tools fallback")

    logger.info("[langgraph] plugin loaded, LANGGRAPH_ENABLED=true")

    langgraph_chat = on_message(rule=Rule(_is_qq_chat), priority=98, block=True)

    @langgraph_chat.handle()
    async def handle_langgraph_chat(bot: Bot, event):
        text = event.get_plaintext().strip()
        if not text:
            await langgraph_chat.finish()

        user_id = get_user_id(event)

        # 1) 精确匹配 slash 命令
        handled = await _handle_slash_command(bot, event, user_id, text)
        if handled:
            await langgraph_chat.finish()

        # 2) 其余消息交给 LangGraph agent
        await _handle_agent(bot, event, user_id, text)
        await langgraph_chat.finish()
else:
    logger.info("[langgraph] plugin loaded, LANGGRAPH_ENABLED=false — using legacy routing")
