# QQ机器人 + DeepSeek 部署进度 (截至 2026-05-20)

## 目标
基于 NoneBot2 + QQ官方API，实现 QQ 机器人接入 DeepSeek + Claude 模型对话，支持文字/语音双模输出，配备自进化记忆系统。

## 架构

```
QQ 消息 → WebSocket → NoneBot2(:8085) ──┬── DeepSeek API (流式 SSE)
                                         ├── Claude API (流式 SSE)
                                         └── Qwen3-TTS → dashscope.aliyuncs.com (国内直连)

定时管道:
cron(2:07 AM) → analyze_history.py → SQLite(24h 消息) → DeepSeek 分析 → memory.md + profile.md
```

## 代码结构

```
/home/ubuntu/robot/
├── bot.py                    # NoneBot2 入口，load_dotenv 加载 .env
├── chat_history.db           # SQLite 聊天记录持久化（WAL 模式 + busy_timeout）
├── .env                      # 唯一配置入口：QQ Bot 凭证 + API Keys + TTS 参数
├── .env.example              # 配置模板（可安全提交到公开仓库）
├── .gitignore                # 排除 .env、*.db、logs/、clash/config.yaml
├── README.md                 # 项目文档
├── characters/
│   └── default/
│       ├── system.md         # 基础人设 — 黑色布偶猫（手动编辑）
│       ├── memory.md         # 经验积累（分析脚本每日自动更新）
│       ├── profile.md        # 用户画像（分析脚本每日自动更新）
│       ├── analysis_prompt.md # 分析提示词模板
│       └── suggestions.txt   # 优化建议（分析脚本输出，仅供人工查看）
├── scripts/
│   └── analyze_history.py    # 每日对话分析脚本（cron 2:07 AM 触发）
├── clash/
│   └── mihomo.service        # mihomo systemd 单元文件
│   (config.yaml 含节点 UUID，已 gitignore + git filter-branch 清除历史)
└── plugins/
    ├── __init__.py
    ├── auto_chat.py          # 核心：LLMBackend + OutputHandler + mtime 人设加载
    ├── chat_history.py       # SQLite 存储模块（asyncio.to_thread 异步写入）
    └── weibo_search.py       # 微博搜索：JSON API + 访客认证 + 热度排序 Top 5
```

## 功能特性

- [x] 自然对话 — 无需命令前缀，直接发消息即回复
- [x] 流式输出 — SSE 流式 + 逐句发送（文字）/ 完整合成后发送（语音）
- [x] 上下文记忆 — sessions dict，每用户最多 20 条历史，后端间独立
- [x] 模型自动切换 — ≤10 轮 fast (deepseek-chat)，>10 轮 pro (deepseek-v4-pro)
- [x] 统一菜单 — `切换模式` 弹出模型 (1-3) + 输出 (4-5) 菜单，选数字切换
- [x] 多后端 — DeepSeek + Claude (待配 Key)，后端间记忆独立
- [x] 语音输出 — Qwen3-TTS (阿里云百炼)，音色 Cherry，免费额度，失败 fallback 文字
- [x] 人设系统 — `characters/default/` 文件夹结构，system.md + memory.md + profile.md
- [x] 人设热加载 — mtime 感知冻结快照，编辑即时生效，/reload 强制刷新
- [x] 微博搜索 — `/weibo <关键词>`，m.weibo.cn JSON API + 访客 Cookie + 热度排序 Top 5
- [x] 聊天持久化 — SQLite WAL 模式 + busy_timeout=5000，asyncio.to_thread 异步写入
- [x] 每日分析管道 — cron(2:07 AM) → DeepSeek 分析 → 更新 memory.md + profile.md
- [x] 并发安全 — WAL + busy_timeout，多线程写入不冲突，跨进程读写不互斥
- [x] Git 安全 — .env/代理配置/数据库均 gitignore，clash/config.yaml 已从历史清除
- [x] 配置集中化 — 所有配置在 .env，systemd 不含密钥

## 用户命令

| 命令 | 效果 |
|------|------|
| 直接发消息 | 用当前后端 + 输出模式回复 |
| `切换模式` / `/switch` | 弹出统一菜单（模型 1-3 + 输出 4-5） |
| `/deepseek <msg>` | 切到 DeepSeek 并发送 |
| `/claude <msg>` | 切到 Claude 并发送（需配 Key） |
| `/status` / `当前状态` | 显示后端、输出模式、轮数 |
| `/clear` / `清除记忆` | 重置所有后端的对话历史 |
| `/reload` / `重载人设` | 强制重载 system.md + memory.md + profile.md |
| `/weibo <关键词>` | 搜索微博，按热度排序推荐 Top 5 |

## 基础设施

- 服务器: 腾讯云 VM-0-13-ubuntu / 82.156.69.26
- 系统: Ubuntu 22.04, Python 3.10.12
- 域名: talkrob.duckdns.org
- SSL: acme.sh DNS-01
- nginx: 443 HTTPS → 127.0.0.1:8085 (webhook 备用)
- systemd: qqbot.service + mihomo.service (均开机自启, 崩溃自动重启)
- 代理: mihomo (Clash Meta)，127.0.0.1:7897，vmess 新加坡节点（仅代理需要出国的 API）

## API Keys 状态

| 服务 | 状态 |
|------|------|
| DeepSeek | 已配置 |
| Claude (Anthropic) | 未配置 (占位 Key) |
| Qwen3-TTS (阿里云百炼) | 已配置，免费额度 |

## 设计决策

- **mtime 缓存 vs 每会话冻结**: 选择 mtime 全局缓存。QQ 机器人会话生命极长（数天到数周），用户无"开新会话"概念，若按会话冻结则记忆更新永远不会被读到。参考 Hermes Agent 的每会话冻结方案，其适用于会话短、用户主动管理会话边界的场景。
- **单实例多租户**: 当前 messages 表以 user_id 区分用户，但分析管道将所有用户混合分析。后续需按 user_id 拆分画像文件夹。

## 已知问题

- **频繁重启触发 QQ 身份验证**: 改代码攒一起一次重启
- **分析管道混用多用户**: profile.md 画像不区分用户，待拆分为 characters/<user_id>/ 结构
- **QQ adapter TypeError**: 日志偶发 `'str' object is not a mapping`，不影响服务运行

## 最新改动 (2026-05-20)

- chat_history.py + analyze_history.py 添加 `busy_timeout=5000`
- .gitignore 添加 `clash/config.yaml`, `*.db`, `logs/`, `!.env.example`
- clash/config.yaml 从 git 历史中 filter-branch 清除
- 创建 .env.example 配置模板
- 创建 README.md

## 命令速查

- 状态: `sudo systemctl status qqbot`
- 日志: `sudo journalctl -u qqbot -f`
- 重启: `sudo systemctl restart qqbot`
- 停止: `sudo systemctl stop qqbot`
- 代理: `sudo systemctl status mihomo`
- 分析日志: `cat /home/ubuntu/robot/logs/analysis.log`
- 每日分析: `crontab -l` (2:07 AM)
