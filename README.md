<p align="center">
  <strong>English</strong> | <a href="#zh">中文</a>
</p>

# imprint-memory

Give Claude a memory that lasts. Everything you tell it stays — searchable across conversations, private, on your machine.

No cloud storage. No API key required. Works offline.

```
You: "Remember I'm allergic to shellfish"
          ↓ stored locally
... weeks later, new conversation ...
Claude: (recalls your allergy before suggesting a recipe)
```

## What it does

- **Remembers things** — facts, events, insights. You say it once, Claude knows it next time.
- **Searches smart** — keyword + meaning combined. Ask "what did I say about that project last week?" and it finds it.
- **Links memories together** — "this contradicts that", "this evolved from that". Claude sees the connections.
- **Syncs your claude.ai chats** — optional Chrome extension captures your web conversations too.
- **Auto-surfaces** — a hook can remind Claude of relevant memories before you even ask.
- **Stays fresh** — old unused memories fade, important ones stay pinned. No endless pile-up.
- **Speaks Chinese** — full CJK search, time expressions like `昨天`、`上个月`.

## Quick Start

### One command (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Qizhan7/imprint-memory/main/scripts/setup.sh | bash
```

Installs imprint-memory and registers the MCP server. You'll then need a
`GOOGLE_API_KEY` for embeddings — see **[Models & Cost](#models--cost)**
below (5-min, free, no card). Data lives in `~/.imprint/`.

### Manual install

```bash
pip install imprint-memory
claude mcp add -s user imprint-memory -- imprint-memory
export GOOGLE_API_KEY=...          # for embeddings, see below
```

Restart Claude Code. That's it.

### Prefer fully-local (no API keys)?

Set `EMBED_PROVIDER=ollama` BEFORE the first write, then:

```bash
ollama pull bge-m3 && ollama serve
```

You lose multimodal (text+image) — bge-m3 is text-only. See the
[embedding consistency](#%EF%B8%8F-embedding-consistency--do-not-mix)
note about *why this choice must be made up front*.

### Sync your claude.ai conversations (optional)

```bash
pip install 'imprint-memory[receiver]'
imprint-memory-receiver
```

Then install the [imprint-chat-sync](https://github.com/Qizhan7/imprint-chat-sync) Chrome extension to capture your web chats.

### Auto-surfacing hook (optional)

Makes Claude automatically recall relevant memories when you ask something:

```bash
mkdir -p ~/.claude/hooks
HOOK_PATH="$(python - <<'PY'
from importlib.resources import files
print(files("imprint_memory") / "hooks" / "memory-check.sh")
PY
)"
cp "$HOOK_PATH" ~/.claude/hooks/memory-check.sh
chmod +x ~/.claude/hooks/memory-check.sh
```

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/hooks/memory-check.sh"
          }
        ]
      }
    ]
  }
}
```

## Models & Cost

imprint-memory uses three categories of model. The defaults all stay
inside vendors' free tiers for normal personal use — **no payment card
required, no billing to enable, no surprise charges**. You sign up for
a free account, copy an API key, and you're done.

### What's used by default

| Purpose | Model | Provider | Cost |
|---|---|---|---|
| Embedding (text + image) | `gemini-embedding-2` (3072 dim) | Google AI Studio | Free tier (~1500 req/day) |
| Chunk-summary LLM | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare Workers AI | Free tier (10k neurons/day) |
| Context compression *(optional)* | `qwen3:8b` | Local Ollama | Local, no API |

### Free-tier setup (5 min)

1. **Google API key** — for embeddings:
   - Visit https://aistudio.google.com/apikey
   - Click "Create API key" (Google account is enough; no credit card,
     no Cloud project required for AI Studio keys)
   - Export it: `export GOOGLE_API_KEY=AIza...`

2. **Cloudflare Workers AI** — for chunk summaries (optional but
   recommended for the `chunker` pipeline):
   - Sign up free at https://dash.cloudflare.com/sign-up (no card)
   - Workers AI is free-tier enabled by default
   - Account ID: visible in the dashboard URL
   - API token: https://dash.cloudflare.com/profile/api-tokens →
     "Create Token" → "Workers AI" template
   - Export: `export CF_ACCOUNT_ID=...` and `export CF_API_TOKEN=...`

3. **Ollama** — for the `compress.py` script (only if you use it):
   - `brew install ollama && ollama pull qwen3:8b`

For normal daily use, the free tiers are *not* close to running out.
You only have to "enable" Workers AI in the dashboard (one click, no
card) — same for Google AI Studio API access. Neither provider can
charge you without you explicitly switching plans.

### ⚠️ Embedding consistency — DO NOT MIX

The vector dimension MUST stay constant across the lifetime of one DB.

| Provider / model | Dim |
|---|---|
| Google `gemini-embedding-2` | **3072** |
| Ollama `bge-m3` | **1024** |
| OpenAI `text-embedding-3-small` | **1536** |

Switching `EMBED_PROVIDER` mid-stream means new vectors get a different
shape than old ones. Cosine similarity then returns 0 across the
boundary and search silently goes half-blind — FTS still works, but
the semantic channel is dead for everything written before the switch.

**Pick once, before the first write.** If you absolutely must switch:
drop `conversation_vectors` and `memory_vectors`, then re-embed
everything with `imprint-memory-reindex`.

## MCP Tools (27 total)

### Memory CRUD

| Tool | What it does |
| --- | --- |
| `memory_remember` | Store a memory. Categories: `facts` (preferences, truths), `events` (things that happened), `insights` (reflections). Auto-deduplicates. |
| `memory_search` | Search everything — memories, notes, conversations. Combines keyword + vector + exact match. Supports time filters (`after`/`before`). |
| `memory_list` | List recent memories, filter by category or date range. |
| `memory_update` | Edit a memory's content, category, or importance. |
| `memory_delete` | Delete one memory by ID. |
| `memory_forget` | Delete all memories containing a keyword. |
| `memory_daily_log` | Add a timestamped note to today's log. |

### Graph Structure

| Tool | What it does |
| --- | --- |
| `memory_pin` | Pin an important memory — it won't fade over time. |
| `memory_unpin` | Unpin — restore normal aging. |
| `memory_add_tags` | Tag a memory (e.g. `"climbing,sport"`). |
| `memory_add_edge` | Link two memories with a relationship (`causal`, `analogy`, `evolution`, `contradiction`, etc). Linked memories show up together in search. |
| `memory_get_graph` | See a memory's tags, links, and what it's connected to. |

### Memory Maintenance

| Tool | What it does |
| --- | --- |
| `memory_find_duplicates` | Find memories that say nearly the same thing. |
| `memory_find_stale` | Find old, unused, low-importance memories. |
| `memory_decay` | Gradually fade memories that haven't been recalled. Preview first, then apply. |
| `memory_reindex` | Rebuild search index after changing embedding model. |

### Conversation Search

| Tool | What it does |
| --- | --- |
| `conversation_search` | Keyword search over past conversations. |
| `conversation_search_semantic` | Meaning-based search — finds relevant chats even with different wording. |
| `search_telegram` | Search Telegram conversations. |
| `search_channel` | Search any connected channel (Discord, Slack, WeChat, etc). |

### Search Quality

| Tool | What it does |
| --- | --- |
| `stopwords_build` | Auto-detect common words that hurt search quality. |
| `stopwords_show` | See what words are being filtered. |
| `stopwords_add` | Manually filter a word from search. |
| `stopwords_remove` | Unfilter a word. |

### Message Bus

| Tool | What it does |
| --- | --- |
| `message_bus_read` | See recent messages across all sources. |
| `message_bus_post` | Log a message to the shared timeline. |

### Experience Bank

| Tool | What it does |
| --- | --- |
| `experience_append` | Save a technical lesson learned (debugging tips, workflow patterns). |

## How Search Works

1. Parse time expressions (`昨天`, `last week`, `after:2026-04-01`)
2. Optionally expand the query with synonyms/variants
3. Search all pools in parallel: memories, notes, conversations, summaries
4. Fuse results by rank (best across all methods wins)
5. Boost pinned memories, recent items, high-importance entries
6. Expand hits: show linked memories and surrounding conversation context
7. Update recall counters (frequently recalled memories stay relevant)

## Configuration

All via environment variables. Defaults work out of the box for local use.

<details>
<summary>Full configuration reference</summary>

| Variable | Default | Description |
| --- | --- | --- |
| `IMPRINT_DATA_DIR` | `~/.imprint` | Where data lives |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | Database path |
| `TZ_OFFSET` | `0` | Your timezone offset from UTC (hours) |
| `IMPRINT_USER_NAME` | `User` | Your name in conversation summaries |
| `IMPRINT_AGENT_NAME` | `Assistant` | AI name in conversation summaries |
| `IMPRINT_LOCALE` | `en` | Output language: `en` or `zh` |
| `EMBED_PROVIDER` | `google` | Embedding provider: `google` (default, 3072-dim multimodal), `ollama` (1024-dim local), `openai`, `cloudflare`. **Pick once — see consistency warning above.** |
| `EMBED_MODEL` | varies | Model for embeddings. Defaults: `bge-m3` (Ollama), `text-embedding-3-small` (OpenAI), `gemini-embedding-2` (Google) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OPENAI_API_KEY` | unset | For OpenAI embeddings |
| `EMBED_API_BASE` | `https://api.openai.com` | OpenAI-compatible API base |
| `GOOGLE_API_KEY` | unset | For Google Gemini embeddings |
| `GOOGLE_API_KEYS` | unset | Multiple Google keys (comma-separated, round-robin) |
| `CF_ACCOUNT_ID` | unset | Cloudflare account for query expansion |
| `CF_API_TOKEN` | unset | Cloudflare API token |
| `IMPRINT_HTTP_HOST` | `0.0.0.0` | HTTP mode bind address |
| `IMPRINT_HTTP_PORT` | `8000` | HTTP mode port |
| `IMPRINT_HOOK_LANG` | `en` | Hook reminder language |
| `STOPWORD_THRESHOLD` | `0.15` | Auto-stopword frequency threshold |
| `MESSAGE_BUS_LIMIT` | `40` | Max messages in bus |

</details>

## Data Layout

```
~/.imprint/
├── memory.db          ← all memories + vectors
├── MEMORY.md          ← human-readable memory guide
└── memory/
    ├── 2026-05-17.md  ← today's daily log
    └── bank/
        └── experience.md  ← technical notes
```

## Development

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory
pip install -e '.[all]'
pytest
```

## Acknowledgements

Built on top of these open-source libraries:

- **[JioNLP](https://github.com/dongrixinyu/JioNLP)** by *dongrixinyu* (Apache 2.0) — powers the natural-language time parsing in `_extract_time_intent` (`昨天`/`上周`/`5月15日` → date ranges via `jionlp.ner.extract_time`). Without it, queries like "what we talked about yesterday" couldn't pin a real time window.
- **[jieba](https://github.com/fxsjy/jieba)** (MIT) — Chinese tokenisation for FTS5 indexing and keyword extraction.
- **[NumPy](https://numpy.org/)** (BSD) — vector-space matrix operations for the graph build (Top-K edges, MMR diversification).
- **Embedding providers**: Google Gemini Embedding 2 (multimodal), OpenAI `text-embedding-3-small`, or local Ollama `bge-m3` — configured via `EMBED_PROVIDER`.

## License

MIT

---

<a id="zh"></a>

<p align="center">
  <a href="#imprint-memory">English</a> | <strong>中文</strong>
</p>

# imprint-memory

让 Claude 记住你说过的话。下次聊天还在，搜得到，全部存在本地。

不上传云端。不需要 API key。离线也能用。

```
你: "记住我对虾过敏"
          ↓ 本地存储
... 几周后，新对话 ...
Claude: (推荐菜谱前自动回忆起你的过敏)
```

## 能做什么

- **记东西** — 事实、事件、想法。说一次，下次 Claude 就知道。
- **智能搜索** — 关键词 + 语义混合。问"上周说的那个项目是什么来着"也能找到。
- **记忆关联** — "这个和那个矛盾"、"这个从那个演化来"。Claude 能看到记忆之间的联系。
- **同步 claude.ai 对话** — 可选的 Chrome 扩展，把网页端聊天也收进来。
- **自动浮现** — hook 能在你提问前就把相关记忆提醒给 Claude。
- **保持新鲜** — 旧的没用的记忆会自动淡化，重要的可以钉住。不会越积越多。
- **中文友好** — 完整中文搜索，支持 `昨天`、`上个月`、`去年冬天` 等时间表达。

## 快速开始

### 一行搞定（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/Qizhan7/imprint-memory/main/scripts/setup.sh | bash
```

装好 imprint-memory + 注册 MCP。embedding 需要 `GOOGLE_API_KEY` ——
看下面 **[模型与费用](#%E6%A8%A1%E5%9E%8B%E4%B8%8E%E8%B4%B9%E7%94%A8)** 章节（5 分钟搞定，全程免费，无需信用卡）。
数据存在 `~/.imprint/`。

### 手动安装

```bash
pip install imprint-memory
claude mcp add -s user imprint-memory -- imprint-memory
export GOOGLE_API_KEY=...          # 嵌入用，见下方
```

重启 Claude Code 就能用。

### 想全本地不要 API key？

**首次写入前**设 `EMBED_PROVIDER=ollama`，然后：

```bash
ollama pull bge-m3 && ollama serve
```

代价：失去多模态（文字+图片）—— bge-m3 只支持文字。看下面
[嵌入维度一致性](#%E2%9A%A0%EF%B8%8F-%E5%B5%8C%E5%85%A5%E4%B8%80%E8%87%B4%E6%80%A7-%E7%BB%9D%E5%AF%B9%E4%B8%8D%E8%83%BD%E6%B7%B7%E7%94%A8) 警告，*这选择必须一开始就定下来*。

### 同步 claude.ai 对话（可选）

```bash
pip install 'imprint-memory[receiver]'
imprint-memory-receiver
```

然后装 [imprint-chat-sync](https://github.com/Qizhan7/imprint-chat-sync) Chrome 扩展，把网页端对话也收进来。

### 自动浮现 hook（可选）

让 Claude 在你提问时自动想起相关的记忆：

```bash
mkdir -p ~/.claude/hooks
HOOK_PATH="$(python3 -c '
from importlib.resources import files
print(files("imprint_memory") / "hooks" / "memory-check.sh")
')"
cp "$HOOK_PATH" ~/.claude/hooks/memory-check.sh
chmod +x ~/.claude/hooks/memory-check.sh
```

加到 `~/.claude/settings.json`：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $HOME/.claude/hooks/memory-check.sh"
          }
        ]
      }
    ]
  }
}
```

中文输出设置：在 `~/.imprint/.env` 里加 `IMPRINT_LOCALE=zh` 和 `IMPRINT_HOOK_LANG=zh`。

## 模型与费用

imprint-memory 用到三类模型，默认全部走各厂商的**免费档**——
**不需要绑卡、不需要开 billing、不会冒出账单**。注册免费账号、拿
API key、配上就行。

### 默认用什么

| 用途 | 模型 | 厂商 | 费用 |
|---|---|---|---|
| 嵌入（文字+图片） | `gemini-embedding-2`（3072 维） | Google AI Studio | 免费档（约 1500 req/天） |
| chunk 摘要 LLM | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare Workers AI | 免费档（10k neurons/天） |
| 上下文压缩 *(可选)* | `qwen3:8b` | 本地 Ollama | 本地，不走 API |

### 免费档配置（5 分钟）

1. **Google API key** — 嵌入用：
   - 打开 https://aistudio.google.com/apikey
   - 点 "Create API key"（用 Google 账号就够，不要信用卡，
     AI Studio key 不需要建 Cloud project）
   - 导出环境变量：`export GOOGLE_API_KEY=AIza...`

2. **Cloudflare Workers AI** — chunk 摘要用（可选，但跑 chunker
   pipeline 推荐）：
   - 免费注册 https://dash.cloudflare.com/sign-up（不要卡）
   - Workers AI 默认免费档已开
   - Account ID：dashboard 网址里能看到
   - API token：https://dash.cloudflare.com/profile/api-tokens →
     "Create Token" → 选 "Workers AI" 模板
   - 导出：`export CF_ACCOUNT_ID=...` 和 `export CF_API_TOKEN=...`

3. **Ollama** — 给 `compress.py` 脚本用（不用脚本就跳过）：
   - `brew install ollama && ollama pull qwen3:8b`

日常使用根本碰不到免费档上限。两边都只要"启用 / 注册"一下（点
一下、不要卡），Google AI Studio 和 Cloudflare 都不可能在你没主
动换套餐的情况下扣钱。

### ⚠️ 嵌入一致性 — 绝对不能混用

向量维度**必须**在同一个 DB 的整个生命周期里保持一致。

| 厂商 / 模型 | 维度 |
|---|---|
| Google `gemini-embedding-2` | **3072** |
| Ollama `bge-m3` | **1024** |
| OpenAI `text-embedding-3-small` | **1536** |

中途切 `EMBED_PROVIDER` = 新写入的 vec 跟旧的维度不一样。
跨边界的 cosine sim 一律返回 0，搜索悄悄变瞎子——FTS 还能用，但
语义通道对切换之前写入的所有数据都失效了。

**写第一条之前就选好**。如果非得切：清掉 `conversation_vectors`
和 `memory_vectors`，用 `imprint-memory-reindex` 全部重做。

## MCP 工具（共 27 个）

### 记忆 CRUD

| 工具 | 干什么的 |
| --- | --- |
| `memory_remember` | 存一条记忆。分类：`facts`（事实/偏好）、`events`（发生的事）、`insights`（感悟）。自动去重。 |
| `memory_search` | 搜所有东西——记忆、笔记、对话。关键词 + 语义 + 精确匹配混合。支持时间过滤。 |
| `memory_list` | 列出最近的记忆，可以按分类或日期过滤。 |
| `memory_update` | 改一条记忆的内容、分类或重要度。 |
| `memory_delete` | 按 ID 删一条。 |
| `memory_forget` | 按关键词批量删。 |
| `memory_daily_log` | 往今天的日志里加一条带时间戳的笔记。 |

### 图谱结构

| 工具 | 干什么的 |
| --- | --- |
| `memory_pin` | 钉住重要的记忆——不会随时间淡化。 |
| `memory_unpin` | 取消钉住，恢复自然淡化。 |
| `memory_add_tags` | 给记忆打标签（如 `"攀岩,运动"`）。 |
| `memory_add_edge` | 把两条记忆关联起来（因果、类比、演化、矛盾等）。搜索时关联的记忆会一起出现。 |
| `memory_get_graph` | 看一条记忆的标签、关联、连接了什么。 |

### 记忆维护

| 工具 | 干什么的 |
| --- | --- |
| `memory_find_duplicates` | 找内容差不多的重复记忆。 |
| `memory_find_stale` | 找长时间没用过的、不重要的旧记忆。 |
| `memory_decay` | 让没被想起过的记忆慢慢淡化。可以先预览再执行。 |
| `memory_reindex` | 换了嵌入模型后重建搜索索引。 |

### 对话搜索

| 工具 | 干什么的 |
| --- | --- |
| `conversation_search` | 关键词搜过去的对话。 |
| `conversation_search_semantic` | 按意思搜——措辞不一样也能找到。 |
| `search_telegram` | 搜 Telegram 对话。 |
| `search_channel` | 搜任意接入的频道（Discord、Slack、微信等）。 |

### 搜索质量

| 工具 | 干什么的 |
| --- | --- |
| `stopwords_build` | 自动找出影响搜索质量的常见词。 |
| `stopwords_show` | 看哪些词被过滤了。 |
| `stopwords_add` | 手动加一个过滤词。 |
| `stopwords_remove` | 取消过滤。 |

### 消息总线

| 工具 | 干什么的 |
| --- | --- |
| `message_bus_read` | 看所有来源的最近消息。 |
| `message_bus_post` | 往共享时间线写一条消息。 |

### 经验库

| 工具 | 干什么的 |
| --- | --- |
| `experience_append` | 存一条技术笔记（踩坑记录、工作流经验等）。 |

## 搜索原理

1. 解析时间表达（`昨天`、`上个月`、`after:2026-04-01`）
2. 可选扩展查询（加同义词/口语变体）
3. 所有池子并行搜索：记忆、笔记、对话、摘要
4. 按排名融合结果（各种方法里排最高的赢）
5. 加分：钉住的记忆、最近的、重要度高的
6. 展开命中：显示关联记忆和前后对话上下文
7. 更新 recall 计数（经常被想起的记忆保持相关性）

## 数据在哪

```
~/.imprint/
├── memory.db          ← 所有记忆 + 向量
├── MEMORY.md          ← 记忆使用指南
└── memory/
    ├── 2026-05-17.md  ← 今天的日志
    └── bank/
        └── experience.md  ← 技术笔记
```

## 开发

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory
pip install -e '.[all]'
pytest
```

## 致谢

记忆系统建立在这些开源项目之上：

- **[JioNLP](https://github.com/dongrixinyu/JioNLP)** by *dongrixinyu* (Apache 2.0) — 提供自然语言时间解析（`_extract_time_intent`），让"昨天/上周/5 月 15 日"能转成具体日期范围。没有它，"昨天我们聊了什么"这种 query 锚不到真正的时间窗。
- **[jieba](https://github.com/fxsjy/jieba)** (MIT) — 中文分词，用于 FTS5 索引和关键词提取。
- **[NumPy](https://numpy.org/)** (BSD) — 图谱构建（Top-K 边、MMR 去重）的矩阵运算。
- **Embedding 提供方**：Google Gemini Embedding 2（多模态）、OpenAI `text-embedding-3-small`、或本地 Ollama `bge-m3` —— 通过 `EMBED_PROVIDER` 配置。

## 许可证

MIT
