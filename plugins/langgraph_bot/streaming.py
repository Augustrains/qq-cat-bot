"""流式输出 + 语音 TTS + DB 持久化。"""

import os
import asyncio
from typing import AsyncIterator

import httpx
from nonebot.log import logger
from nonebot.adapters.qq import Bot, MessageSegment

from ..chat_history import save_message

DASHSCOPE_KEY = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_TTS_URL = os.getenv("QWEN_TTS_URL",
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
QWEN_TTS_VOICE = os.getenv("QWEN_TTS_VOICE", "Cherry")
QWEN_TTS_MODEL = os.getenv("QWEN_TTS_MODEL", "qwen3-tts-flash")


async def process_response(
    bot: Bot,
    event,
    token_stream: AsyncIterator[str],
    output_mode: str,
    user_id: str,
    backend_name: str,
    model_name: str,
) -> str:
    """处理 agent token 流：分模式发送 + 持久化。

    Returns:
        full_text: 完整回复文本（供后续 history 使用）
    """
    full_text = ""

    if output_mode == "voice":
        async for chunk in token_stream:
            if chunk:
                full_text += chunk
        await _send_tts(bot, event, full_text)
    else:
        buffer = ""
        async for chunk in token_stream:
            if chunk:
                full_text += chunk
                buffer += chunk
                if buffer.endswith(("。", "！", "？", "\n")) or len(buffer) >= 200:
                    await bot.send(event, buffer)
                    buffer = ""
        if buffer:
            await bot.send(event, buffer)

    # 异步写 DB（user 消息由 __init__.py 保存，这里只保存 assistant）
    asyncio.create_task(save_message(user_id, "assistant", full_text, backend_name, model_name))

    return full_text


async def _send_tts(bot: Bot, event, text: str):
    """通过 Qwen3-TTS 将文本转为语音发送。失败时 fallback 文字。"""
    if not DASHSCOPE_KEY:
        await bot.send(event, "语音功能还没配置好喵...主人需要先设置 DASHSCOPE_API_KEY 喵")
        return

    try:
        if len(text) > 600:
            text = text[:600]
            logger.warning("[langgraph] TTS text truncated to 600 chars")

        async with httpx.AsyncClient(timeout=60) as client:
            tts_resp = await client.post(
                QWEN_TTS_URL,
                json={
                    "model": QWEN_TTS_MODEL,
                    "input": {
                        "text": text,
                        "voice": QWEN_TTS_VOICE,
                        "language_type": "Chinese",
                    },
                },
                headers={
                    "Authorization": f"Bearer {DASHSCOPE_KEY}",
                    "Content-Type": "application/json",
                },
            )
            if tts_resp.status_code != 200:
                logger.error(f"[langgraph] Qwen TTS error: {tts_resp.text}")
                await bot.send(event, text)
                return

            tts_data = tts_resp.json()
            audio_url = tts_data.get("output", {}).get("audio", {}).get("url")
            if not audio_url:
                logger.error(f"[langgraph] Qwen TTS: no audio URL in response")
                await bot.send(event, text)
                return

            audio_resp = await client.get(audio_url)
            if audio_resp.status_code == 200:
                await bot.send(event, MessageSegment.file_audio(audio_resp.content, "reply.wav"))
            else:
                logger.error(f"[langgraph] Qwen TTS audio download error: {audio_resp.status_code}")
                await bot.send(event, text)

    except Exception as e:
        logger.error(f"[langgraph] Qwen TTS error: {e}")
        await bot.send(event, text)
