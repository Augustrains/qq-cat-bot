# QQ机器人 + DeepSeek 部署进度

## 目标
基于 NoneBot2 + QQ官方API，实现 QQ 机器人接入 DeepSeek + Claude 模型对话，支持文字/语音双模输出。

## 架构

```
用户 QQ ←→ WebSocket ←→ NoneBot2(:8085) ──┬── DeepSeek API (流式)
                        │                  ├── Claude API (流式，待配置Key)
                        │                  └── Fish Audio API (TTS 语音合成)
                        ├─ plugins/auto_chat.py    LLM 后端 + 输出模式
                        └─ characters/default.md   人设文件（热加载）
```

## 代码结构

| 文件 | 职责 |
|------|------|
| `bot.py` | 框架入口，注册 QQ 适配器，加载插件 |
| `plugins/auto_chat.py` | 核心：LLMBackend 抽象（DeepSeek/Claude）+ OutputHandler 抽象（文字/语音）|
| `characters/default.md` | 人设 prompt（黑色布偶猫），热加载无需重启 |
| `.env` | QQ Bot 凭证 + 驱动 + 沙箱模式 + API Keys |
| `qqbot.service` | systemd 服务定义 + 环境变量注入 |

## 功能特性

- [x] 自然对话 — 无需命令前缀，直接发消息即回复
- [x] 流式输出 — 文字模式逐句发送，语音模式合成后发送
- [x] 上下文记忆 — 内存 dict，每用户 20 条历史，独立会话
- [x] 模型自动切换 — ≤10 轮用 deepseek-chat，>10 轮自动切 deepseek-v4-pro
- [x] 统一菜单 — `切换模式` 弹出模型 + 输出模式菜单，选数字切换
- [x] 多后端支持 — DeepSeek (默认) + Claude (需 API Key)，后端间记忆独立
- [x] 语音输出 — Fish Audio TTS，音色 ID 可配，失败自动 fallback 文字
- [x] 人设系统 — `characters/` 目录下 md 文件，编辑即时生效

## 用户命令

| 命令 | 效果 |
|------|------|
| 直接发消息 | 用当前后端 + 输出模式回复 |
| `切换模式` / `/switch` | 弹出统一菜单（模型 1-3 + 输出 4-5）|
| `/deepseek <msg>` | 切到 DeepSeek 并发送 |
| `/claude <msg>` | 切到 Claude 并发送 |
| `/status` / `当前状态` | 显示后端、输出模式、轮数 |
| `/clear` / `清除记忆` | 重置对话 |

## 基础设施

- 服务器: 腾讯云 VM-0-13-ubuntu / 82.156.69.26
- 系统: Ubuntu 22.04, Python 3.10.12
- 域名: talkrob.duckdns.org
- SSL: acme.sh DNS-01
- nginx: 443 HTTPS → 127.0.0.1:8085 (webhook 备用)
- systemd: qqbot.service (开机自启, 崩溃自动重启)

## API Keys 状态

| 服务 | 状态 |
|------|------|
| DeepSeek | 已配置 |
| Claude (Anthropic) | 未配置 |
| Fish Audio | 已配置 (Key + 音色 ID) |

## 已知问题

- **频繁重启触发 QQ 身份验证**：短时间多次 `systemctl restart` 会导致 QQ 安全系统标记异常，要求重新验证。正常运维应避免频繁重启，改完代码一次重启即可。QQ WebSocket 每 30 分钟自动轮换会话是正常行为，不会触发验证。

## 命令速查

- 状态: `sudo systemctl status qqbot`
- 日志: `sudo journalctl -u qqbot -f`
- 重启: `sudo systemctl restart qqbot`
- 停止: `sudo systemctl stop qqbot`
