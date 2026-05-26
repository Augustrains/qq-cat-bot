"""会话管理 — 从 auto_chat.py 提取。"""

import os
from collections import defaultdict
from nonebot.adapters.qq import C2CMessageCreateEvent, GroupAtMessageCreateEvent

FAST_MODEL = os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-chat")
PRO_MODEL = os.getenv("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
SWITCH_ROUNDS = int(os.getenv("SWITCH_ROUNDS", "10"))
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def new_session() -> dict:
    return {
        "backend": "deepseek",
        "model_override": None,
        "output_mode": "text",
        "deepseek": {"messages": [], "rounds": 0},
        "claude": {"messages": [], "rounds": 0},
    }


sessions: dict[str, dict] = defaultdict(new_session)


def get_user_id(event) -> str:
    if isinstance(event, C2CMessageCreateEvent):
        return f"c2c:{event.author.id}"
    elif isinstance(event, GroupAtMessageCreateEvent):
        return f"group:{event.group_openid}:{event.author.id}"
    return "unknown"


def get_active_model(session: dict) -> tuple[str, str]:
    """返回 (backend_name, model_name)，考虑手动覆盖和自动升级。"""
    backend_name = session["backend"]
    rounds = session[backend_name]["rounds"]

    if session["model_override"]:
        return backend_name, session["model_override"]

    if backend_name == "deepseek":
        return backend_name, PRO_MODEL if rounds >= SWITCH_ROUNDS else FAST_MODEL
    return backend_name, CLAUDE_MODEL


def check_backend_available(backend_name: str) -> bool:
    """检查后端 API Key 是否已配置。"""
    if backend_name == "claude":
        return bool(ANTHROPIC_KEY)
    return True  # deepseek always available


def extract_event_info(event) -> dict:
    """从 NoneBot event 中提取可序列化的信息。"""
    if isinstance(event, C2CMessageCreateEvent):
        return {"type": "c2c", "author_id": str(event.author.id), "group_openid": None}
    elif isinstance(event, GroupAtMessageCreateEvent):
        return {"type": "group", "author_id": str(event.author.id), "group_openid": str(event.group_openid)}
    return {"type": "unknown"}
