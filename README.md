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
- **模型自动切换** — DeepSeek 后端 <=10 轮用 fast 模型，>10 轮自动切 pro 模型

---

## 前置准备

部署本项目需要准备以下账号和服务。**整个流程大约需要 30 分钟**。

### 1. QQ 机器人申请

1. 打开 [QQ 开放平台](https://q.qq.com)，用 QQ 号登录
2. 点击「创建机器人」→ 填写名称、简介、头像
3. 创建完成后进入「开发设置」页面，获取：
   - **Bot ID** (机器人唯一标识，如 `1234567890`)
   - **Token** (用于 WebSocket 鉴权)
   - **Secret** (用于 WebSocket 鉴权)
4. 在「消息 Intent」中，**至少开启**以下两项：
   - `C2C_MESSAGE` — 私聊消息
   - `GROUP_AT_MESSAGE` — 群聊 @消息
5. 部署初期建议开启**沙箱模式** (`QQ_IS_SANDBOX=true`)：
   - 沙箱模式下只有创建者和添加的测试人员能与机器人对话
   - 正式上线前改为 `false` 即可对全部用户开放

> 完整文档: [QQ 机器人官方文档](https://bot.q.qq.com/wiki/)

### 2. 域名准备（可选但推荐）

QQ WebSocket 是机器人主要通信方式，不需要域名。但以下场景需要域名 + HTTPS：

- **Webhook 备用通道**: 当 WebSocket 不可用时，QQ 会通过 HTTP 回调推送消息
- **沙箱退出后的正式环境**: QQ 平台要求 Webhook 地址为 HTTPS

推荐使用免费 DDNS：

1. 注册 [DuckDNS](https://www.duckdns.org)，用 GitHub/Google 账号登录
2. 创建域名（如 `your-bot.duckdns.org`），记录 **Token**
3. 将域名指向你的服务器公网 IP

### 3. 服务器要求

- Ubuntu 22.04 (其他 Linux 发行版也可)
- Python 3.10+
- 安全组/防火墙开放 **443 端口** (HTTPS)
- 如果要使用 Claude 后端，需要代理访问国外 API（见下方 mihomo 部署章节）

---

## 安装

```bash
git clone https://github.com/<your-username>/qq-cat-bot.git
cd qq-cat-bot
python -m venv venv
source venv/bin/activate
pip install nonebot2 httpx python-dotenv
```

### 配置

复制配置模板并填入实际值：

```bash
cp .env.example .env
# 编辑 .env，填入你的 QQ Bot 凭证和 API Key
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

**API Key 获取地址：**
- DeepSeek: [platform.deepseek.com](https://platform.deepseek.com) → API Keys
- Anthropic: [console.anthropic.com](https://console.anthropic.com) → API Keys
- 阿里云百炼 (TTS): [bailian.console.aliyun.com](https://bailian.console.aliyun.com) → 模型广场 → Qwen3-TTS

### 验证安装

```bash
source venv/bin/activate
python bot.py
```

看到 `NoneBot is starting` 即为成功。此时机器人应该已经在 QQ 上上线（WebSocket 已连接）。

---

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

---

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

---

## 人设系统

机器人的人设由 `characters/default/` 下的三个文件定义：

| 文件 | 内容 | 编辑方式 |
|------|------|----------|
| `system.md` | 基础人格、语言风格、行为约束 | 手动编辑 |
| `memory.md` | 学到的经验 | 分析脚本自动 **追加** |
| `profile.md` | 用户画像 | 分析脚本自动 **覆写+合并** |

### 加载机制

启动时加载并冻结在内存中。每次收到消息时检查各文件 mtime（仅 stat 系统调用，无磁盘 IO）：

- mtime 变化 -> 自动重新读盘（cron 更新后自动感知，无需重启）
- mtime 不变 -> 直接返回冻结值（99.9% 的情况）

与 Hermes Agent 的「每会话冻结快照」不同，本项目选择 **mtime 感知的全局缓存**。原因是 QQ 机器人会话生命周期极长（数天到数周），用户没有「开新会话」的心智模型——如果按会话冻结，记忆更新几乎永远不会被读到。mtime 方案让 cron 更新在数小时后自然生效，同时保持 stat 系统调用的零成本。

`/reload` 命令可手动强制刷新，跳过 mtime 检查。

---

## 自进化记忆管道

每日凌晨 2:07 通过 cron 触发分析脚本：

1. 从 SQLite 读取最近 24 小时聊天记录，同时注入旧的 memory.md 和 profile.md 作为上下文
2. 调用 DeepSeek 分析（按 `analysis_prompt.md` 模板），LLM 基于旧内容做增删改
3. LLM 按 `%%% SECTION %%%` 分隔输出三段：memory / profile / suggestions
4. memory.md **追加**写入 — 仅新增行，旧内容物理保留；profile.md **覆写合并** — LLM 输出完整新版
5. 人设系统通过 mtime 感知自动热加载新记忆

---

## 部署指南

本项目不使用 Docker/容器，直接通过 systemd 在宿主机运行。以下是从零完成生产部署的完整步骤。

### 1. SSL 证书 (acme.sh + DuckDNS)

适用场景：需要 HTTPS Webhook 备用通道，或退出沙箱模式后 QQ 平台的 Webhook 要求。

```bash
# 安装 acme.sh
curl https://get.acme.sh | sh
source ~/.bashrc

# 申请证书 (DNS-01 验证，不需要开 80 端口)
export DuckDNS_Token="your-duckdns-token"
acme.sh --issue --dns dns_duckdns -d your-bot.duckdns.org

# 安装证书到 nginx 目录
sudo mkdir -p /etc/nginx/ssl/your-bot.duckdns.org
acme.sh --install-cert -d your-bot.duckdns.org \
  --key-file       /etc/nginx/ssl/your-bot.duckdns.org/key.pem \
  --fullchain-file /etc/nginx/ssl/your-bot.duckdns.org/fullchain.pem \
  --reloadcmd     "systemctl reload nginx"
```

证书每 60 天自动续期（acme.sh 安装时已添加 cron）。

### 2. nginx 反向代理

安装 nginx：

```bash
sudo apt install nginx
sudo systemctl enable --now nginx
```

创建站点配置 `/etc/nginx/sites-available/your-bot`：

```nginx
# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name your-bot.duckdns.org;
    return 301 https://$server_name$request_uri;
}

# HTTPS 主站
server {
    listen 443 ssl;
    server_name your-bot.duckdns.org;

    ssl_certificate     /etc/nginx/ssl/your-bot.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/your-bot.duckdns.org/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # QQ Webhook → NoneBot2
    location /qq/ {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 默认静态页面
    location / {
        root /var/www/html;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/your-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default  # 删除默认站点（可选）
sudo nginx -t           # 检查配置语法
sudo systemctl reload nginx
```

> 如果只使用 WebSocket 模式（不需要 Webhook），nginx 和 SSL 可跳过。

### 3. mihomo 代理 (Clash Meta)

国内服务器访问 Anthropic API (Claude) 需要代理。DeepSeek 和阿里云百炼 TTS 均为国内服务，**无需代理**。

```bash
# 安装 mihomo
sudo bash -c 'curl -fsSL https://github.com/MetaCubeX/mihomo/releases/latest/download/mihomo-linux-amd64 -o /usr/bin/mihomo'
sudo chmod +x /usr/bin/mihomo
```

创建配置目录和文件 `/etc/mihomo/config.yaml`：

```yaml
# 配置结构示例 — 替换为你的实际节点信息
mixed-port: 7897
allow-lan: false
bind-address: 127.0.0.1
mode: rule
log-level: info

proxies:
  - name: "your-node"
    type: vmess
    server: your-node.example.com
    port: 12901
    uuid: your-uuid
    alterId: 0
    cipher: auto
    network: ws
    ws-opts:
      path: /

proxy-groups:
  - name: Proxy
    type: select
    proxies:
      - "your-node"

rules:
  - DOMAIN-SUFFIX,anthropic.com,Proxy
  - DOMAIN-SUFFIX,openai.com,Proxy
  - GEOIP,CN,DIRECT
  - MATCH,DIRECT
```

安装 systemd 服务：

```bash
sudo cp /home/ubuntu/robot/clash/mihomo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mihomo
```

验证代理是否工作：

```bash
curl --proxy http://127.0.0.1:7897 https://api.anthropic.com/v1/messages
# 应该返回认证错误（说明网络通了），而非连接超时
```

> 配置文件含节点密钥，已在 `.gitignore` 中排除。配置模板参考 `clash/` 目录，源文件 `/home/ubuntu/robot/clash/mihomo.service`。

### 4. systemd 服务

创建 `/etc/systemd/system/qqbot.service`：

```ini
[Unit]
Description=QQ AI Chatbot (NoneBot2)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/robot
ExecStart=/home/ubuntu/robot/venv/bin/python bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now qqbot
```

日常管理命令：

```bash
sudo systemctl status qqbot          # 查看状态
sudo journalctl -u qqbot -f          # 实时日志
sudo systemctl restart qqbot         # 重启
sudo systemctl stop qqbot            # 停止
```

> **注意**: 短时间内多次 `systemctl restart` 会触发 QQ 平台的身份验证风控。修改代码后一次性重启即可。

### 5. 定时分析 (cron)

设置每日凌晨 2:07 自动分析对话记录：

```bash
crontab -e
# 添加以下行:
7 2 * * * /home/ubuntu/robot/venv/bin/python /home/ubuntu/robot/scripts/analyze_history.py >> /home/ubuntu/robot/logs/analysis.log 2>&1
```

查看分析日志：

```bash
cat /home/ubuntu/robot/logs/analysis.log
```

### 6. 部署架构总览

```
┌─────────────────────────────────────────────────┐
│  服务器 (Ubuntu 22.04)                            │
│                                                   │
│  nginx :443 ──→ 127.0.0.1:8085 (NoneBot2)        │
│                     │                             │
│  qqbot.service       ├── DeepSeek (国内直连)       │
│  (systemd)           ├── Claude  (→ mihomo 代理)  │
│                      └── Qwen3-TTS (国内直连)     │
│                                                   │
│  mihomo.service :7897 ──→ vmess 境外节点          │
│  cron (2:07 AM) ──→ analyze_history.py            │
│                      │                             │
│                      └── SQLite ←→ characters/     │
└─────────────────────────────────────────────────┘
```

本项目不使用 Docker——所有服务均由 systemd 直接管理。这意味着：
- 日志通过 `journalctl` 查看，而非 `docker logs`
- 更新代码后 `sudo systemctl restart qqbot` 即生效
- 没有容器网络隔离，NoneBot2 监听 `127.0.0.1:8085` 仅本地可达

---

## 设计说明

- **正交设计**: LLM 后端 (DeepSeek/Claude) 和输出模式 (文字/语音) 独立抽象，新后端/新模式只需实现对应接口
- **配置集中**: 所有配置在 `.env`，`bot.py` 启动时 `load_dotenv()` 注入 `os.environ`，systemd 服务文件不含密钥
- **会话隔离**: 每用户独立 sessions dict，不同后端间对话历史独立
- **并发安全**: SQLite WAL 模式 + `busy_timeout=5000`，多线程写入不冲突，跨进程读写不互斥
- **人设缓存**: mtime 感知冻结快照 — 平衡即时性与性能，适合 QQ 机器人超长会话场景

---

## 已知问题

- **频繁重启触发 QQ 身份验证**: 短时间内多次 `systemctl restart` 会触发验证。改完代码一次性重启即可
- **Claude 后端需要代理**: 国内服务器直连 Anthropic API 不可达，需 mihomo 代理
- **分析管道混用多用户**: 当前分析脚本将所有用户的消息混合分析，profile.md 画像不区分用户。后续需要按 user_id 拆分独立画像

## License

MIT
