"""工具注册表 — 所有工具在此注册，agent 启动时自动绑定。"""

from langchain_core.tools import BaseTool

TOOLS: list[BaseTool] = []
TOOL_MAP: dict[str, BaseTool] = {}

# 工具元数据 — 用于 SBERT 编码的描述文本（自然中文，越具体检索越准）
TOOL_META: dict[str, dict] = {}


def _register(name: str, category: str, description: str, tool: BaseTool):
    """内部注册：同时记录 TOOLS 列表、TOOL_MAP 映射、元数据。"""
    TOOLS.append(tool)
    TOOL_MAP[name] = tool
    TOOL_META[name] = {
        "category": category,
        "description": description,
        "fc_schema": {
            "name": name,
            "description": tool.description,
            "parameters": tool.args_schema.schema() if tool.args_schema else {},
        },
    }


def set_user_context(user_id: str):
    """在所有需要 user_id 的工具中设置当前用户上下文。"""
    from . import mode_switch, status, clear
    mode_switch.set_context(user_id)
    status.set_context(user_id)
    clear.set_context(user_id)


def register_tools() -> list[BaseTool]:
    """注册全部工具，返回工具列表供 agent bind。懒加载避免循环导入。"""
    global TOOLS
    if TOOLS:
        return TOOLS

    from . import weibo, mode_switch, status, clear, reload_char

    _register(
        "search_weibo", "search",
        "搜索微博热搜，查找社交媒体上的热门帖子和新闻话题，按热度排序返回结果",
        weibo.search_weibo,
    )
    _register(
        "switch_chat_model", "utility",
        "切换AI模型后端，可以选择DeepSeek快速版、DeepSeek专业推理版或Claude长上下文版本",
        mode_switch.switch_chat_model,
    )
    _register(
        "switch_output_mode", "utility",
        "切换输出模式，文字输出或语音播报，语音通过TTS合成真人发音",
        mode_switch.switch_output_mode,
    )
    _register(
        "show_bot_status", "utility",
        "查看机器人当前状态，包括使用的模型、对话轮数、输出模式等配置信息",
        status.show_bot_status,
    )
    _register(
        "clear_conversation_history", "utility",
        "清除当前用户的对话记忆，忘记之前聊过的内容，开始全新的对话",
        clear.clear_conversation_history,
    )
    _register(
        "reload_character_prompt", "utility",
        "强制重新加载机器人的角色人设、学到的经验和用户画像文件",
        reload_char.reload_character_prompt,
    )

    return TOOLS
