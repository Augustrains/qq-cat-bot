"""LangGraph ReAct agent — 核心图定义。

Graph 结构:
    START → agent_node (LLM + tools) ──条件边──
                ↑                    │          │
                │                    ↓          ↓
                └── tools_node ←── tool_call   END (无 tool_call)

流式方案：
  - agent_node 为 sync 函数（Python 3.10 上 async contextvar 不可用）
  - 用 get_stream_writer() + ChatOpenAI.stream() 逐 token 发射到 custom stream
  - 外部通过 graph.astream(stream_mode="custom") 消费 token
"""

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langchain_core.messages import HumanMessage, SystemMessage

from .state import AgentState
from .models import build_chat_model
from .context import load_character
from .tools import register_tools, set_user_context

MAX_TOOL_ITERATIONS = 5

_graph: StateGraph | None = None
_checkpointer: InMemorySaver | None = None


def _get_graph() -> StateGraph:
    """懒初始化编译好的 graph（进程级单例）。"""
    global _graph, _checkpointer
    if _graph is not None:
        return _graph

    tools = register_tools()
    _checkpointer = InMemorySaver()

    builder = StateGraph(AgentState)
    builder.add_node("agent", _agent_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", "__end__": END},
    )
    builder.add_edge("tools", "agent")

    _graph = builder.compile(checkpointer=_checkpointer)
    return _graph


def _should_continue(state: AgentState) -> str:
    """决定：继续调工具 or 结束。"""
    messages = state["messages"]
    last_message = messages[-1] if messages else None

    if last_message and hasattr(last_message, "tool_calls") and last_message.tool_calls:
        remaining = state.get("tool_calls_remaining", 0)
        if remaining <= 0:
            return "__end__"
        return "tools"
    return "__end__"


def _agent_node(state: AgentState) -> dict:
    """Agent 节点（sync）：流式调用 LLM，通过 stream_writer 逐 token 发射。"""
    backend = state.get("backend_name", "deepseek")
    model_name = state.get("model_name", "deepseek-chat")

    llm = build_chat_model(backend, model_name, streaming=True)

    # 用 FAISS 语义检索取出 Top-K 相关工具（失败则全量 fallback）
    last_user_msg = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            last_user_msg = str(msg.content)
            break
    try:
        from .retriever import search_tools as _search_tools
        tools = _search_tools(last_user_msg, k=5) if last_user_msg else register_tools()
    except Exception:
        tools = register_tools()

    llm_with_tools = llm.bind_tools(tools)

    system_prompt = state.get("system_prompt", "") or load_character()
    messages = [SystemMessage(content=system_prompt)]
    messages.extend(state["messages"])

    writer = get_stream_writer()
    full_msg = None

    for chunk in llm_with_tools.stream(messages):
        full_msg = full_msg + chunk if full_msg else chunk
        if chunk.content:
            writer(chunk.content)

    return {
        "messages": [full_msg] if full_msg else [],
        "tool_calls_remaining": state.get("tool_calls_remaining", MAX_TOOL_ITERATIONS) - 1,
    }


async def run_agent(
    user_message: str,
    user_id: str,
    backend_name: str,
    model_name: str,
    output_mode: str,
):
    """执行 agent 并流式产出 token（async generator）。

    每次 yield 一个 token 字符串，来自 LangGraph custom stream。
    """
    graph = _get_graph()

    set_user_context(user_id)
    system_prompt = load_character()

    thread_id = f"{user_id}:{backend_name}"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "backend_name": backend_name,
        "model_name": model_name,
        "output_mode": output_mode,
        "round_count": 0,
        "full_response": "",
        "tool_calls_remaining": MAX_TOOL_ITERATIONS,
        "system_prompt": system_prompt,
    }

    async for chunk in graph.astream(initial_state, config=config, stream_mode="custom"):
        if chunk:
            yield chunk
