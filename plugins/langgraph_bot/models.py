"""LLM 后端工厂 — 通过 langchain_openai.ChatOpenAI 连接 DeepSeek。"""

import os
from langchain_openai import ChatOpenAI
from nonebot.log import logger

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
FAST_MODEL = os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-chat")
PRO_MODEL = os.getenv("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def build_chat_model(backend_name: str, model_name: str, streaming: bool = True) -> ChatOpenAI:
    """创建 LangChain ChatModel 实例。

    DeepSeek API 完全兼容 OpenAI 接口，包括 tool calling。
    Claude 后端暂不支持（待配置 Key 后对接 langchain_anthropic）。
    """
    if backend_name == "deepseek":
        if not DEEPSEEK_KEY:
            raise RuntimeError("DeepSeek API Key 未配置")

        timeout = 90 if "pro" in model_name.lower() else 60
        return ChatOpenAI(
            model=model_name,
            api_key=DEEPSEEK_KEY,
            base_url=DEEPSEEK_URL,
            streaming=streaming,
            temperature=0.7,
            max_tokens=2048,
            timeout=timeout,
        )

    elif backend_name == "claude":
        raise NotImplementedError(
            "Claude 后端暂未迁移到 LangGraph。"
            "配置 ANTHROPIC_API_KEY 后可对接 langchain_anthropic.ChatAnthropic。"
        )
    raise ValueError(f"Unknown backend: {backend_name}")
