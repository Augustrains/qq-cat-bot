# QQ AI Chatbot — 可爱的猫猫

基于 [NoneBot2](https://github.com/nonebot/nonebot2) + QQ 官方 API 的多后端 AI 聊天机器人，支持文字/语音双模输出，配备自进化记忆系统。

## 架构

```
QQ 消息 → WebSocket → NoneBot2(:8085) ──┬── DeepSeek API (流式 SSE)
                                         ├── Claude API (流式 SSE)
                                         └── Qwen3-TTS → dashscope.aliyuncs.com

定时管道:
cron(2:07 AM) → analyze_history.py → SQLite(24h 消息) → DeepSeek 分析 → memory.md + profile.md
```

## 功能

- **自然对话** — 无需命令前缀，直接发消息即可聊天
- **多后端支持** — DeepSeek + Claude，运行时通过菜单切换
- **流式输出** — SSE 流式响应，文字模式逐句发送，语音模式完整收集后 TTS 合成发送
- **语音输出** — Qwen3-TTS (阿里云百炼)，免费额度，失败自动 fallback 文字输出
- **自进化记忆** — 每日定时分析对话记录，自动更新机器人经验记忆和用户画像
- **人设热加载** — mtime 感知冻结快照，编辑文件即时生效无需重启，`/reload` 强制刷新
- **微博搜索** — `/weibo <关键词>`，通过 m.weibo.cn JSON API + 访客认证，热度排序推荐 Top 5
- **聊天持久化** — SQLite WAL 模式 + busy_timeout 并发保护，asyncio.to_thread 异步写入不阻塞响应
- **会话管理** — 后端、模型、输出模式三个维度正交，每用户独立上下文（最多 20 条历史）
- **模型自动切换** — DeepSeek 后端 ≤10 轮用 fast 模型，>10 轮自动切 pro 模型

## 快速开始

### 环境要求

- Python 3.10+
- Ubuntu 22.04 (其他 Linux 发行版也可)
- QQ 开放平台机器人账号

### 安装

```bash
git clone https://github.com/<your-username>/qq-ai-chatbot.git
cd qq-ai-chatbot
python -m venv venv
source venv/bin/activate
pip install nonebot2 httpx python-dotenv
```

### 配置

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

| 变量 | 说明 | 必填 |
|------|------|------|
| `QQ_BOTS` | QQ 机器人 JSON 配置 `[{"id":"xxx","token":"xxx","secret":"xxx"}]` | 是 |
| `QQ_IS_SANDBOX` | 是否沙箱模式 (`true`/`false`) | 是 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 是 |
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key（语音功能需要） | 否 |
| `ANTHROPIC_API_KEY` | Anthropic API Key（Claude 后端需要） | 否 |
| `HOST` | 监听地址，默认 `127.0.0.1` | 否 |
| `PORT` | 监听端口，默认 `8085` | 否 |

完整变量列表见 `.env.example`。

### 运行

```bash
source venv/bin/activate
python bot.py
```

## 用户命令

| 命令 | 效果 |
|------|------|
| 直接发消息 | 用当前后端 + 输出模式回复 |
| `切换模式` / `/switch` | 弹出统一菜单（模型 + 输出模式） |
| `/deepseek <msg>` | 切换到 DeepSeek 并发送消息 |
| `/claude <msg>` | 切换到 Claude 并发送消息 |
| `/status` / `当前状态` | 显示当前后端、输出模式、对话轮数 |
| `/clear` / `清除记忆` | 重置当前会话上下文（所有后端） |
| `/reload` / `重载人设` | 手动重载人设和记忆文件 |
| `/weibo <关键词>` | 搜索微博，热度排序推荐 Top 5 |

## 项目结构

```
.
├── bot.py                         # NoneBot2 入口，load_dotenv 加载 .env
├── .env.example                   # 配置模板（可提交）
├── .gitignore
├── README.md
├── plugins/
│   ├── __init__.py
│   ├── auto_chat.py               # 核心：LLMBackend + OutputHandler + mtime 人设加载
│   ├── chat_history.py            # SQLite 存储模块，asyncio.to_thread 异步写入
│   └── weibo_search.py            # 微博搜索插件，访客认证 + 热度排序
├── characters/
│   └── default/
│       ├── system.md              # 基础人设 — 黑色布偶猫人格（手动编辑）
│       ├── memory.md              # 经验积累（分析脚本每日自动更新）
│       ├── profile.md             # 用户画像（分析脚本每日自动更新）
│       └── analysis_prompt.md     # 分析提示词模板
├── scripts/
│   └── analyze_history.py         # 每日对话分析脚本（cron 2:07 AM 触发）
└── clash/
    └── mihomo.service             # mihomo systemd 单元文件（config.yaml 已 gitignore）
```

## 人设系统

机器人的人设由 `characters/default/` 下的三个文件定义：

| 文件 | 内容 | 编辑方式 |
|------|------|----------|
| `system.md` | 基础人格、语言风格、行为约束 | 手动编辑 |
| `memory.md` | 学到的经验 | 分析脚本自动 **追加** |
| `profile.md` | 用户画像 | 分析脚本自动 **覆写+合并** |

### 加载机制

启动时加载并冻结在内存中。每次收到消息时检查各文件 mtime（仅 stat 系统调用，无磁盘 IO）：

- mtime 变化 → 自动重新读盘（cron 更新后自动感知，无需重启）
- mtime 不变 → 直接返回冻结值（99.9% 的情况）

与 Hermes Agent 的「每会话冻结快照」不同，本项目选择 **mtime 感知的全局缓存**。原因是 QQ 机器人会话生命周期极长（数天到数周），用户没有「开新会话」的心智模型——如果按会话冻结，记忆更新几乎永远不会被读到。mtime 方案让 cron 更新在数小时后自然生效，同时保持 stat 系统调用的零成本。

`/reload` 命令可手动强制刷新，跳过 mtime 检查。

## 自进化记忆管道

每日凌晨 2:07 通过 cron 触发分析脚本：

1. 从 SQLite 读取最近 24 小时聊天记录，同时注入旧的 memory.md 和 profile.md 作为上下文
2. 调用 DeepSeek 分析（按 `analysis_prompt.md` 模板），LLM 基于旧内容做增删改
3. LLM 按 `%%% SECTION %%%` 分隔输出三段：memory / profile / suggestions
4. memory.md **追加**写入 — 仅新增行，旧内容物理保留；profile.md **覆写合并** — LLM 输出完整新版
5. 人设系统通过 mtime 感知自动热加载新记忆

设置 cron：

```bash
crontab -e
# 添加:
7 2 * * * cd /path/to/robot && /path/to/venv/bin/python scripts/analyze_history.py >> logs/analysis.log 2>&1
```

## 部署

### systemd 服务

```ini
# /etc/systemd/system/qqbot.service
[Unit]
Description=QQ AI Chatbot (NoneBot2)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/robot
ExecStart=/path/to/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now qqbot
```

### nginx 反向代理（Webhook 备用通道）

```nginx
location /qq/ {
    proxy_pass http://127.0.0.1:8085/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 代理（访问国外 API）

国内服务器访问 Anthropic API 需要代理。项目包含 mihomo (Clash Meta) 配置参考。
代理配置文件含节点凭证，已加入 `.gitignore`，不会上传到公开仓库。

国内服务（DeepSeek、阿里云百炼）无需代理。

## 设计说明

- **正交设计**: LLM 后端 (DeepSeek/Claude) 和输出模式 (文字/语音) 独立抽象，新后端/新模式只需实现对应接口
- **配置集中**: 所有配置在 `.env`，`bot.py` 启动时 `load_dotenv()` 注入 `os.environ`，systemd 服务文件不含密钥
- **会话隔离**: 每用户独立 sessions dict，不同后端间对话历史独立
- **并发安全**: SQLite WAL 模式 + `busy_timeout=5000`，多线程写入不冲突，跨进程读写不互斥
- **人设缓存**: mtime 感知冻结快照 — 平衡即时性与性能，适合 QQ 机器人超长会话场景

## 已知问题

- **频繁重启触发 QQ 身份验证**: 短时间内多次 `systemctl restart` 会触发 QQ 安全验证。运维时避免频繁重启，改完代码一次性重启即可
- **Claude 后端需要代理**: 国内服务器直连 Anthropic API 不可达，需 mihomo 代理
- **分析管道混用多用户**: 当前分析脚本将所有用户的消息混合分析，profile.md 画像不区分用户。后续需要按 user_id 拆分独立画像

## License

MIT
