# 项目运行流程

## 1. 启动初始化

```mermaid
flowchart TD
    A[systemd 启动 qqbot] --> B[bot.py: load_dotenv]
    B --> C[NoneBot2 初始化]
    C --> D{LANGGRAPH_ENABLED?}

    D -->|true| E[加载 langgraph_bot 插件]
    D -->|false| F[加载 auto_chat 旧架构]

    E --> G[register_tools]
    G --> H[注册 6 个 MCP 工具到 TOOLS / TOOL_MAP / TOOL_META]

    H --> I[Phase 1: 工具元数据写入 SQLite tools 表]
    I --> J[Phase 2: init_retriever]

    J --> K{FAISS 索引文件存在?}
    K -->|是| L[加载 tools.index + tools_ids.npy]
    K -->|否| M[从 DB 读取工具描述]

    M --> N[加载 SBERT 模型]
    N --> O[编码 6 条工具描述 → 512-dim 向量]
    O --> P[构建 FAISS IndexFlatIP]
    P --> Q[持久化到磁盘]

    L --> R[retriever 就绪]
    Q --> R

    R --> S{初始化成功?}
    S -->|是| T[语义检索模式: 按查询检索 Top-K 工具]
    S -->|否| U[Fallback 模式: 全部 6 工具给 LLM]

    T --> V[加载人设 system/memory/profile]
    U --> V

    V --> W[启动 WebSocket 连接 QQ]
    W --> X[🤖 Bot 就绪, 等待消息]
```

## 2. 消息处理主流程

```mermaid
flowchart TD
    A[📩 QQ 用户消息] --> B[WebSocket → NoneBot2]
    B --> C{优先级路由}

    C -->|priority=50| D["/weibo 命令 → weibo_search 旧 handler"]
    C -->|priority=98| E[langgraph_bot ReAct agent]
    C -->|priority=99| F[auto_chat 旧架构<br/>仅 LANGGRAPH_ENABLED=false]

    D --> G[直接返回微博搜索结果]
    G --> Z[📤 发送回复]

    E --> H[获取 user_id + session]
    H --> I{Slash 命令精确匹配?}

    I -->|是| J["/clear /status /reload /deepseek /claude"]
    J --> K[直接执行工具, 绕过 LLM]
    K --> Z

    I -->|否| L["进入 ReAct agent →"]

    L --> M[构建消息上下文]
    M --> N[人设 system.md + memory.md + profile.md]
    M --> O[最近对话历史 最多 20 条]

    N --> P[语义检索: 查询 → SBERT encode → FAISS search]
    O --> P
    P --> Q{检索成功?}
    Q -->|是| R[bind_tools Top-K 个]
    Q -->|否| S[bind_tools 全部 6 个]

    R --> T[调用 ChatOpenAI.stream]
    S --> T

    T --> U{LLM 返回?}

    U -->|tool_calls| V[ToolNode 执行工具]
    V --> W[工具结果追加到消息历史]
    W --> T

    U -->|text content| X[流式输出 token stream]
    X --> Y{output_mode?}

    Y -->|text| AA[缓冲逐句发送<br/>分隔符或 200 字触发]
    Y -->|voice| AB[完整收集文本<br/>→ Qwen3-TTS 合成]
    AB --> AC{TTS 成功?}
    AC -->|是| AD[发送语音消息]
    AC -->|否| AE[Fallback 发送文字]

    AA --> AF[保存到 SQLite chat_history]
    AD --> AF
    AE --> AF

    AF --> AG[更新 session 对话轮数]
    AG --> Z
```

## 3. Tool Calling 内部循环

```mermaid
flowchart TD
    A[agent_node<br/>sync, ChatOpenAI.stream] --> B{LLM 决策}

    B -->|"finish_reason=tool_calls"| C[提取 tool_calls]
    B -->|"finish_reason=stop"| D[流式输出文本 → END]

    C --> E[ToolNode 路由]
    E --> F1[search_weibo<br/>微博关键词搜索]
    E --> F2[switch_chat_model<br/>切换 DeepSeek/Claude]
    E --> F3[switch_output_mode<br/>切换文字/语音]
    E --> F4[show_bot_status<br/>查看当前状态]
    E --> F5[clear_conversation_history<br/>清除会话]
    E --> F6[reload_character_prompt<br/>重载人设文件]

    F1 --> G[工具结果写入 ToolMessage]
    F2 --> G
    F3 --> G
    F4 --> G
    F5 --> G
    F6 --> G

    G --> H[消息历史追加 tool result]
    H --> A
```

## 4. 语义检索流程

```mermaid
flowchart LR
    A["🔍 用户查询<br/>'帮我搜微博AI'"] --> B[SBERT encode]
    B --> C["512-dim 归一化向量"]

    C --> D[FAISS IndexFlatIP<br/>内积 = 余弦相似度]
    D --> E["Top-K tool_id<br/>按相似度排序"]

    E --> F[SQLite tools 表<br/>查完整 name/description/schema]
    F --> G["bind_tools 给 LLM<br/>只给最相关的 K 个"]

    H[工具注册表 6 个] --> I[SBERT 编码全部描述]
    I --> J[FAISS 索引持久化<br/>tools.index + tools_ids.npy]
    J -.->|启动时加载| D

    K[新工具注册] --> L[增量更新索引]
    L -.-> J
```

## 5. 每日分析管道

```mermaid
flowchart TD
    A["⏰ cron 2:07 AM"] --> B[analyze_history.py]
    B --> C[读取 SQLite 最近 24h 对话]
    C --> D[读取旧 memory.md + profile.md]

    D --> E[拼装分析 prompt<br/>analysis_prompt.md 模板]

    E --> F[调用 DeepSeek 分析]
    F --> G[LLM 按 %%% SECTION %%%<br/>分隔输出三段]

    G --> H1["SECTION 1: memory.md<br/>追加模式写入"]
    G --> H2["SECTION 2: profile.md<br/>覆写合并模式"]
    G --> H3["SECTION 3: suggestions.txt<br/>覆写模式"]

    H1 --> I[文件 mtime 变化]
    H2 --> I
    H3 --> I

    I --> J[下次消息到来时<br/>context.py mtime 感知<br/>自动热加载新内容]
```

## 6. 完整架构拓扑

```mermaid
flowchart TB
    subgraph External[外部]
        QQ[💬 QQ 用户]
        DS[DeepSeek API<br/>platform.deepseek.com]
        TTS[Qwen3-TTS<br/>dashscope.aliyuncs.com]
        WB[微博 API<br/>m.weibo.cn]
    end

    subgraph Server[服务器 Ubuntu 22.04]
        subgraph Proxy[代理层]
            NGINX[nginx :443<br/>Webhook 备用]
            MIHOMO[mihomo :7897<br/>vmess → 新加坡]
        end

        subgraph Core[核心进程]
            NB[NoneBot2 :8085<br/>WebSocket 主通道]
            LG[LangGraph Agent]
            FAISS[FAISS + SBERT<br/>语义检索]
            SQLITE[(SQLite WAL<br/>chat_history.db)]
            CHAR[characters/<br/>system/memory/profile]
        end

        subgraph Cron[定时任务]
            CRON[cron 2:07 AM]
            ANALYZE[analyze_history.py]
        end
    end

    QQ <-->|WebSocket| NB
    NB --> LG
    LG --> FAISS
    LG --> DS
    LG --> TTS
    LG --> WB
    LG --> SQLITE

    CRON --> ANALYZE
    ANALYZE --> SQLITE
    ANALYZE --> DS
    ANALYZE --> CHAR

    CHAR -.->|mtime 热加载| LG
    FAISS -.->|工具元数据| SQLITE

    NB -.->|Webhook 备用| NGINX
    LG -.->|Claude 出国| MIHOMO
    FAISS -.->|模型下载| MIHOMO
```

## 关键数据流

| 数据 | 来源 | 去向 | 时机 |
|------|------|------|------|
| 用户消息 | QQ WebSocket | agent_node | 实时 |
| Token 流 | DeepSeek SSE | streaming.py → QQ | 实时 |
| 对话记录 | streaming.py | SQLite chat_history | 每条消息 |
| 工具元数据 | tools/__init__.py | SQLite tools 表 | 启动时 |
| FAISS 索引 | SBERT encode | tools.index + tools_ids.npy | 启动时 |
| 每日分析 | cron → DeepSeek | memory.md / profile.md | 凌晨 2:07 |
| 人设加载 | characters/*.md | agent_node system prompt | 每次请求 (mtime 缓存) |
| 工具选择 | 用户查询 → FAISS | bind_tools → LLM | 每次请求 |
