#!/usr/bin/env python3
"""每日对话分析 — 读 SQLite 历史 → LLM 分析 → 更新 memory.md + profile.md

由 cron 每天触发一次。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx

ROOT = Path(__file__).resolve().parent.parent

# cron 环境没有这些变量，先加载 .env
load_dotenv(ROOT / ".env")
DB_PATH = ROOT / "chat_history.db"
CHAR_DIR = ROOT / "characters" / "default"
PROMPT_PATH = CHAR_DIR / "analysis_prompt.md"

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
ANALYSIS_MODEL = os.getenv("DEEPSEEK_FAST_MODEL", "deepseek-chat")

MEMORY_PATH = CHAR_DIR / "memory.md"
PROFILE_PATH = CHAR_DIR / "profile.md"

SECTION_SEP = "%%% SECTION %%%"

# 24 小时前
SINCE = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")


def load_recent(limit: int = 100) -> str:
    """从 SQLite 读取最近 24 小时的消息，格式化为文本。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA busy_timeout=5000")
    rows = conn.execute(
        "SELECT user_id, role, content, created_at FROM messages "
        "WHERE created_at >= ? ORDER BY created_at ASC LIMIT ?",
        (SINCE, limit),
    ).fetchall()
    conn.close()

    if not rows:
        return "（本周期内无对话记录）"

    lines = []
    for user_id, role, content, ts in rows:
        tag = "用户" if role == "user" else "机器人"
        short_id = user_id.split(":")[-1][:8]
        lines.append(f"[{ts}] {tag}({short_id}): {content}")

    return "\n".join(lines)


def call_llm(prompt: str) -> str:
    """调用 DeepSeek 进行分析。"""
    if not DEEPSEEK_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    messages = [
        {"role": "system", "content": "你是一个严谨的分析助手。严格按照用户要求的格式输出，不添加额外解释。"},
        {"role": "user", "content": prompt},
    ]

    reply = ""
    with httpx.Client(timeout=120) as client:
        with client.stream(
            "POST",
            f"{DEEPSEEK_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={"model": ANALYSIS_MODEL, "messages": messages, "max_tokens": 2048, "stream": True},
        ) as resp:
            if resp.status_code != 200:
                data = resp.json()
                raise RuntimeError(f"DeepSeek error: {data.get('error', data)}")
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta:
                        reply += delta["content"]

    return reply


def parse_sections(reply: str) -> dict[str, str]:
    """将 LLM 回复按 %%% SECTION %%% 拆分为三个部分。"""
    # 清理可能的前缀（LLM 有时会在开头加 "好的，以下是分析结果："）
    # 找到第一个 %%% SECTION %%% 的位置
    idx = reply.find(SECTION_SEP)
    if idx == -1:
        raise ValueError(f"LLM 回复中未找到分隔符 {SECTION_SEP}，回复: {reply[:500]}")

    # 去掉第一个分隔符之前的内容
    after_first = reply[idx + len(SECTION_SEP):]

    # 按剩余分隔符拆分
    parts = after_first.split(SECTION_SEP)
    if len(parts) < 3:
        raise ValueError(f"分隔符数量不足，期望 3 个部分，实际 {len(parts)} 个")

    return {
        "memory": parts[0].strip(),
        "profile": parts[1].strip(),
        "suggestions": parts[2].strip(),
    }


def write_if_changed(path: Path, new_content: str, section_name: str):
    """如果内容有变化才写入文件。"""
    old_content = ""
    if path.exists():
        old_content = path.read_text(encoding="utf-8").strip()

    if new_content.strip() == old_content:
        print(f"[{section_name}] 无变化，跳过写入")
        return False

    # 保留文件头注释
    header_lines = []
    if old_content:
        for line in old_content.split("\n"):
            if line.startswith("<!--") or line.startswith("# ") or line.startswith("暂无"):
                if line.startswith("暂无"):
                    continue  # 替换占位文本
                header_lines.append(line)
            else:
                break

    output = "\n".join(header_lines) + "\n\n" + new_content.strip()
    if header_lines:
        output = "\n".join(header_lines) + "\n\n" + new_content.strip()
    else:
        output = new_content.strip()

    path.write_text(output + "\n", encoding="utf-8")
    print(f"[{section_name}] 已更新: {path}")
    return True


def main():
    print(f"=== 每日对话分析 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 1. 读历史
    history = load_recent()
    if history == "（本周期内无对话记录）":
        print("无对话记录，跳过分析")
        return

    print(f"读取聊天记录 {history.count(chr(10))} 行")

    # 2. 组装 prompt
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.replace("{chat_history}", history)
    print(f"Prompt 长度: {len(prompt)} 字符")

    # 3. 调用 LLM
    print("调用 DeepSeek 分析中...")
    try:
        reply = call_llm(prompt)
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        sys.exit(1)

    print(f"LLM 回复长度: {len(reply)} 字符")

    # 4. 解析
    try:
        sections = parse_sections(reply)
    except ValueError as e:
        print(f"解析失败: {e}")
        # 即使解析失败也保存原始回复供人工检查
        debug_path = CHAR_DIR / "analysis_debug.txt"
        debug_path.write_text(reply, encoding="utf-8")
        print(f"原始回复已保存到 {debug_path}")
        sys.exit(1)

    # 5. 写入
    memory_text = sections["memory"]
    if memory_text != "（无新增）":
        write_if_changed(MEMORY_PATH, memory_text, "memory")

    profile_text = sections["profile"]
    if profile_text != "（无新增）":
        write_if_changed(PROFILE_PATH, profile_text, "profile")

    # 6. 保存建议供人查看
    suggestions_text = sections["suggestions"]
    if suggestions_text and suggestions_text.strip():
        sugg_path = CHAR_DIR / "suggestions.txt"
        sugg_path.write_text(
            f"## {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{suggestions_text.strip()}\n",
            encoding="utf-8",
        )
        print(f"[suggestions] 已保存到 {sugg_path}")

    print("分析完成")


if __name__ == "__main__":
    main()
