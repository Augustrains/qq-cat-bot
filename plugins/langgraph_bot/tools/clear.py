"""清除对话记忆工具。"""

from langchain_core.tools import tool

from ..sessions import sessions, new_session

_ctx: dict = {}


def set_context(user_id: str):
    _ctx["user_id"] = user_id


@tool
async def clear_conversation_history() -> str:
    """清除当前用户的对话记忆，开始全新对话。

    当用户要求清除记忆、忘记之前聊了什么、重置对话、/clear、/reset 时使用此工具。
    """
    user_id = _ctx.get("user_id", "")
    session = sessions[user_id]
    session.update(new_session())
    return "对话记忆已清除喵~"
