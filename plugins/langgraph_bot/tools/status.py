"""状态查询工具。"""

from langchain_core.tools import tool

from ..sessions import sessions

_ctx: dict = {}


def set_context(user_id: str):
    _ctx["user_id"] = user_id


@tool
async def show_bot_status() -> str:
    """显示当前机器人配置状态。

    当用户询问"当前状态"、"现在用的是什么模型"、"/status"时使用此工具。
    返回当前后端、模型、轮数和输出模式。
    """
    user_id = _ctx.get("user_id", "")
    session = sessions[user_id]

    b = session["backend"]
    ds_r = session["deepseek"]["rounds"]
    cl_r = session["claude"]["rounds"]
    override = session["model_override"]
    out = session["output_mode"]

    model_info = f" (锁定: {override})" if override else " (自动按轮数升级)"

    return "\n".join([
        f"后端: {b}{model_info} 喵",
        f"输出: {out} 喵",
        f"DeepSeek 轮数: {ds_r}",
        f"Claude 轮数: {cl_r}",
    ])
