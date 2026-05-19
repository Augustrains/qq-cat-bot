import os
import json
import httpx
from abc import ABC, abstractmethod
from collections import defaultdict
from nonebot import on_message
from nonebot.rule import Rule
from nonebot.log import logger
from nonebot.adapters.qq import Bot, C2CMessageCreateEvent, GroupAtMessageCreateEvent, MessageSegment

# ============================================================
# 配置
# ============================================================
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

FAST_MODEL = "deepseek-chat"
PRO_MODEL = "deepseek-v4-pro"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
SWITCH_ROUNDS = 10
MAX_HISTORY = int(os.getenv("DEEPSEEK_MAX_HISTORY", "20"))

FISH_AUDIO_KEY = os.getenv("FISH_AUDIO_KEY", "")
FISH_AUDIO_VOICE_ID = os.getenv("FISH_AUDIO_VOICE_ID", "450c6bf0e6ac41c892edf698c7f69630")  # 苍白高
FISH_AUDIO_PROXY = os.getenv("FISH_AUDIO_PROXY", "")  # 如 http://127.0.0.1:7897

FALLBACK_PROMPT = "你是一个友善、有用的QQ机器人助手。用简洁自然的中文回复。"
CHARACTER_FILE = os.getenv("CHARACTER_FILE", "characters/default.md")


def _load_character() -> str:
    try:
        path = os.path.join(os.path.dirname(__file__), "..", CHARACTER_FILE)
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"Character file not found: {CHARACTER_FILE}")
        return FALLBACK_PROMPT


# ============================================================
# 后端抽象
# ============================================================
class LLMBackend(ABC):
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def chat(self, system_prompt: str, history: list[dict], user_msg: str, model: str, timeout: int):
        ...


class DeepSeekBackend(LLMBackend):
    def name(self) -> str:
        return "deepseek"

    async def chat(self, system_prompt: str, history: list[dict], user_msg: str, model: str, timeout: int):
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{DEEPSEEK_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
                json={"model": model, "messages": messages, "max_tokens": 2048, "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    data = resp.json()
                    raise RuntimeError(f"DeepSeek error: {data.get('error', data)}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]


class ClaudeBackend(LLMBackend):
    def name(self) -> str:
        return "claude"

    async def chat(self, system_prompt: str, history: list[dict], user_msg: str, model: str, timeout: int):
        if not ANTHROPIC_KEY:
            raise RuntimeError("Anthropic API Key 未配置")

        messages = list(history)
        messages.append({"role": "user", "content": user_msg})

        body = {
            "model": model,
            "system": system_prompt,
            "messages": messages,
            "max_tokens": 2048,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{ANTHROPIC_URL}/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json=body,
            ) as resp:
                if resp.status_code != 200:
                    data = resp.json()
                    raise RuntimeError(f"Claude error: {data.get('error', data)}")
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if "text" in delta:
                                yield delta["text"]


# ============================================================
# 后端注册
# ============================================================
_backends: dict[str, LLMBackend] = {
    "deepseek": DeepSeekBackend(),
    "claude": ClaudeBackend(),
}

# ============================================================
# 输出抽象
# ============================================================
class OutputHandler(ABC):
    @abstractmethod
    async def send_chunk(self, bot, event, text: str):
        ...

    @abstractmethod
    async def send_final(self, bot, event, full_text: str):
        ...


class TextOutput(OutputHandler):
    async def send_chunk(self, bot, event, text: str):
        await bot.send(event, text)

    async def send_final(self, bot, event, full_text: str):
        pass


class VoiceOutput(OutputHandler):
    async def send_chunk(self, bot, event, text: str):
        pass

    async def send_final(self, bot, event, full_text: str):
        if not FISH_AUDIO_KEY:
            await bot.send(event, "语音功能还没配置好喵...主人需要先设置 FISH_AUDIO_KEY 喵")
            return
        try:
            client_kwargs = {"timeout": 60}
            if FISH_AUDIO_PROXY:
                client_kwargs["proxy"] = FISH_AUDIO_PROXY
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.post(
                    "https://api.fish.audio/v1/tts",
                    json={
                        "text": full_text,
                        "format": "mp3",
                        "reference_id": FISH_AUDIO_VOICE_ID,
                        "latency": "balanced",
                    },
                    headers={
                        "Authorization": f"Bearer {FISH_AUDIO_KEY}",
                        "Content-Type": "application/json",
                        "model": "s2-pro",
                    },
                )
                if resp.status_code == 200:
                    await bot.send(event, MessageSegment.file_audio(resp.content, "reply.mp3"))
                else:
                    logger.error(f"[auto_chat] Fish Audio error: {resp.text}")
                    await bot.send(event, full_text)
        except Exception as e:
            logger.error(f"[auto_chat] Fish Audio TTS error: {e}")
            await bot.send(event, full_text)


_outputs: dict[str, OutputHandler] = {
    "text": TextOutput(),
    "voice": VoiceOutput(),
}

# ============================================================
# 菜单（模型 + 输出模式）
# ============================================================
MODEL_OPTIONS = [
    {"backend": "deepseek", "model": FAST_MODEL, "label": "DeepSeek Chat (flash) — 快速回复，日常聊天"},
    {"backend": "deepseek", "model": PRO_MODEL,  "label": "DeepSeek Pro       — 更强推理，慢但聪明"},
    {"backend": "claude",   "model": CLAUDE_MODEL, "label": "Claude Sonnet 4.6  — 长上下文，理解力强"},
]

def _build_menu() -> tuple[str, list[dict]]:
    lines = ["「切换模式」回复数字选择喵：", "", "── 模型 ──"]
    counter = 0
    entries = []

    for opt in MODEL_OPTIONS:
        counter += 1
        if opt["backend"] == "claude" and not ANTHROPIC_KEY:
            lines.append(f"  {counter}. {opt['label']} (未配置 Key，不可用)")
        else:
            lines.append(f"  {counter}. {opt['label']}")
            entries.append({"num": str(counter), "type": "model", "backend": opt["backend"], "model": opt["model"]})

    lines.append("── 输出 ──")
    for mode, label in [("text", "文字输出"), ("voice", "语音输出")]:
        counter += 1
        if mode == "voice" and not FISH_AUDIO_KEY:
            lines.append(f"  {counter}. {label} (未配置 Key，不可用)")
        else:
            lines.append(f"  {counter}. {label}")
            entries.append({"num": str(counter), "type": "output", "mode": mode})

    lines.append("")
    lines.append("回复其它内容取消喵")
    return "\n".join(lines), entries


# ============================================================
# 会话存储
# ============================================================
def _new_session():
    return {
        "backend": "deepseek",
        "model_override": None,
        "output_mode": "text",
        "pending": None,
        "deepseek":  {"messages": [], "rounds": 0},
        "claude": {"messages": [], "rounds": 0},
    }

sessions: dict[str, dict] = defaultdict(_new_session)


def _get_user_id(event) -> str:
    if isinstance(event, C2CMessageCreateEvent):
        return f"c2c:{event.author.id}"
    elif isinstance(event, GroupAtMessageCreateEvent):
        return f"group:{event.group_openid}:{event.author.id}"
    return "unknown"


async def _is_qq_chat(event) -> bool:
    return isinstance(event, (C2CMessageCreateEvent, GroupAtMessageCreateEvent))


auto_chat = on_message(rule=Rule(_is_qq_chat), priority=99, block=False)


# ============================================================
# 主处理
# ============================================================
@auto_chat.handle()
async def handle_auto_chat(bot: Bot, event):
    text = event.get_plaintext().strip()
    if not text:
        await auto_chat.finish()

    user_id = _get_user_id(event)
    session = sessions[user_id]
    raw = text.strip()

    # ---- 等待菜单选择 ----
    if session["pending"] == "switch":
        await _handle_menu_selection(bot, event, session, raw)
        return

    # ---- 指令 ----
    if raw in ("/switch", "/model", "切换模型", "切换模式"):
        menu, entries = _build_menu()
        session["pending"] = "switch"
        session["_menu_entries"] = entries
        await bot.send(event, menu)
        return

    if raw.startswith("/deepseek ") or raw == "/deepseek":
        session["backend"] = "deepseek"
        content = raw.removeprefix("/deepseek").strip()
        if not content:
            await bot.send(event, "已切换到 DeepSeek 喵。想说什么喵？")
            return
        text = content
    elif raw.startswith("/claude ") or raw == "/claude":
        if not ANTHROPIC_KEY:
            await bot.send(event, "Claude 还没配置好喵...主人需要先设置 ANTHROPIC_API_KEY 喵")
            return
        session["backend"] = "claude"
        content = raw.removeprefix("/claude").strip()
        if not content:
            await bot.send(event, "已切换到 Claude 喵。想说什么喵？")
            return
        text = content
    elif raw in ("/clear", "/reset", "清除记忆", "重置对话"):
        session.update(_new_session())
        logger.info(f"[auto_chat] Cleared all sessions for {user_id}")
        await bot.send(event, "对话记忆已清除喵")
        return
    elif raw in ("/status", "当前后端", "当前状态"):
        await _show_status(bot, event, session)
        return

    await _call_llm(bot, event, user_id, session, text)


# ============================================================
# 子处理
# ============================================================
async def _handle_menu_selection(bot, event, session, raw):
    """处理菜单的数字选择（模型 + 输出模式）"""
    entries = session.pop("_menu_entries", [])
    session["pending"] = None

    for entry in entries:
        if raw == entry["num"]:
            if entry["type"] == "model":
                session["backend"] = entry["backend"]
                session["model_override"] = entry["model"]
                logger.info(f"[auto_chat] model switch -> {entry['backend']}:{entry['model']}")
                await bot.send(event, f"已切换到 {entry['model']} 喵。想聊什么喵？")
                return
            elif entry["type"] == "output":
                session["output_mode"] = entry["mode"]
                label = "语音" if entry["mode"] == "voice" else "文字"
                logger.info(f"[auto_chat] output switch -> {entry['mode']}")
                await bot.send(event, f"已切换到{label}输出喵。想聊什么喵？")
                return

    await bot.send(event, "已取消切换喵~")


async def _show_status(bot, event, session):
    b = session["backend"]
    ds_r = session["deepseek"]["rounds"]
    cl_r = session["claude"]["rounds"]
    override = session["model_override"]
    out = session["output_mode"]
    model_info = f" (锁定: {override})" if override else " (自动按轮数)"
    lines = [
        f"后端: {b}{model_info} 喵",
        f"输出: {out} 喵",
        f"DeepSeek 轮数: {ds_r}",
        f"Claude 轮数: {cl_r}",
        f"/switch 切换模型 | /voice 语音 | /text 文字 | /clear 清除记忆 喵",
    ]
    await bot.send(event, "\n".join(lines))


async def _call_llm(bot, event, user_id, session, text):
    backend_name = session["backend"]
    backend = _backends[backend_name]
    output = _outputs[session["output_mode"]]
    hist = session[backend_name]
    rounds = hist["rounds"]

    if session["model_override"]:
        model = session["model_override"]
    elif backend_name == "deepseek":
        model = PRO_MODEL if rounds >= SWITCH_ROUNDS else FAST_MODEL
    else:
        model = CLAUDE_MODEL

    timeout = 90 if model in (PRO_MODEL, CLAUDE_MODEL) else 60

    system_prompt = _load_character()
    logger.info(f"[auto_chat] [{backend_name}:{model}] round={rounds} user={user_id}: {text}")

    try:
        reply = ""
        buffer = ""
        async for chunk in backend.chat(system_prompt, hist["messages"], text, model, timeout):
            reply += chunk
            buffer += chunk
            if buffer.endswith(("。", "！", "？", "\n")) or len(buffer) >= 200:
                await output.send_chunk(bot, event, buffer)
                buffer = ""
        if buffer:
            await output.send_chunk(bot, event, buffer)
        await output.send_final(bot, event, reply)

        logger.info(f"[auto_chat] [{backend_name}] Reply: {reply[:100]}...")

        hist["messages"].append({"role": "user", "content": text})
        hist["messages"].append({"role": "assistant", "content": reply})
        hist["rounds"] += 1

        if len(hist["messages"]) > MAX_HISTORY:
            hist["messages"] = hist["messages"][-MAX_HISTORY:]

    except httpx.TimeoutException:
        logger.error(f"[auto_chat] {backend_name} timeout")
        await bot.send(event, "思考太久了喵...主人稍后再试喵")
    except Exception as e:
        logger.error(f"[auto_chat] {backend_name} error: {e}")
        await bot.send(event, "猫脑过载了喵...等会儿再试试喵")
