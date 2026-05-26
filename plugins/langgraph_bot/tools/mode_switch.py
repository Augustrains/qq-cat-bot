"""模型 + 输出模式切换工具。"""

from langchain_core.tools import tool

from ..sessions import sessions, check_backend_available

# Module-level current user context（单线程 asyncio，无并发问题）
_ctx: dict = {}


def set_context(user_id: str):
    _ctx["user_id"] = user_id


@tool
async def switch_chat_model(model: str) -> str:
    """切换 AI 模型后端。

    当用户要求切换模型、换后端、用 DeepSeek/Claude 时使用此工具。

    Args:
        model: 模型选择，可选值:
            - "deepseek-fast" : DeepSeek Chat — 快速回复，适合日常聊天
            - "deepseek-pro"  : DeepSeek Pro — 更强推理，适合复杂问题
            - "claude"        : Claude Sonnet — 长上下文，理解力强
    """
    user_id = _ctx.get("user_id", "")
    session = sessions[user_id]

    mapping = {
        "deepseek-fast": ("deepseek", "deepseek-chat"),
        "deepseek-pro": ("deepseek", "deepseek-v4-pro"),
        "claude": ("claude", "claude-sonnet-4-6"),
    }

    if model not in mapping:
        return f"没有这个模型喵...可选: {', '.join(mapping.keys())}"

    backend, model_name = mapping[model]

    if backend == "claude" and not check_backend_available("claude"):
        return "Claude 还没配置好喵...主人需要先设置 ANTHROPIC_API_KEY 喵"

    session["backend"] = backend
    session["model_override"] = model_name
    return f"已切换到 {model} 喵。想聊什么喵？"


@tool
async def switch_output_mode(mode: str) -> str:
    """切换输出模式：文字或语音。

    当用户要求切换输出方式、打字/语音、或者说"用文字/语音回复"时使用此工具。

    Args:
        mode: "text" 表示文字输出, "voice" 表示语音输出
    """
    user_id = _ctx.get("user_id", "")
    session = sessions[user_id]

    if mode not in ("text", "voice"):
        return "输出模式只能是 text 或 voice 喵"

    session["output_mode"] = mode
    label = "语音" if mode == "voice" else "文字"
    return f"已切换到{label}输出喵。想聊什么喵？"
