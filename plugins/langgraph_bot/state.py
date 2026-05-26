"""LangGraph AgentState — 定义图中流转的全部字段。"""

from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    """对话历史，由 LangGraph 的 add_messages reducer 自动累加。"""

    user_id: str
    """当前用户 ID (e.g. 'c2c:abc123')。"""

    backend_name: str
    """活跃后端: 'deepseek' 或 'claude'。"""

    model_name: str
    """本轮使用的模型名。"""

    output_mode: str
    """输出模式: 'text' 或 'voice'。"""

    round_count: int
    """当前后端已完成轮数。"""

    full_response: str
    """本轮累积完整回复（用于语音模式和 DB 存储）。"""

    tool_calls_remaining: int
    """剩余 tool call 次数，防止死循环。上限 MAX_TOOL_ITERATIONS。"""

    system_prompt: str
    """当前人设 prompt（含 system.md + memory.md + profile.md）。"""
