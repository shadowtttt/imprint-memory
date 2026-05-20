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

- **Captures every turn automatically** — every message you send or
  receive lands in a searchable log, gets segmented into events, and
  gets multimodal-embedded (text + image). The LLM never needs to
  "decide to remember" — it's already stored.
- **Hybrid search out of the box** — keyword (FTS5/BM25) + semantic
  (vector) + RRF rank fusion across memory / bank / chunk pools.
  "What did I say about that project last week?" → it finds it.
- **Auto-surfaces context before you even ask** — a
  `UserPromptSubmit` hook calls `surfacing_search` on every prompt
  and injects a `<recall>` block with up to ~6 related events.
- **Multimodal** — images sent in a conversation get text + image
  embeddings, so "the red screenshot I sent" lands on the right
  message even if the caption doesn't mention "red".
- **Syncs your claude.ai chats** — optional Chrome extension captures
  your web conversations into the same memory store.
- **AI-flagged highlights** *(optional)* — the LLM can call
  `memory_remember` to bump a specific fact higher in search results,
  but the system fully works without it.
- **Stays organised** — facts can be pinned, tagged, and linked
  (graph edges between memories). Importance can be tuned per-entry.
- **Speaks Chinese** — full CJK search, time expressions like
  `昨天`、`上个月`、`去年冬天`.

## How it actually works

A common misconception: *"the AI still has to choose what to
remember, right?"* — **No.** Every piece of the recall pipeline is
automatic. The LLM never has to invoke `memory_remember` for things
to be remembered. Curation tools exist (`memory_remember`, `pin`,
`add_tags`, etc.) but they're *optional annotations* on top of an
already-complete automatic system — search, recall, and
auto-surfacing all work without any of them.

### Automatic pipeline (this is the whole system)

| What | How |
|---|---|
| Every message stored verbatim | Channel adapters call `log_message()` on every in/out turn — Claude Code hook, claude.ai sync, Telegram bot, custom apps. No "decide to save" step. |
| Multimodal embed of images | When a message carries an upload header (e.g. `路径=/abs/path.jpg`), `_maybe_embed_image` runs inline and writes a combined text+image vector |
| Segment conversations into "events" | `incremental_chunk_update` runs on a schedule, groups consecutive messages into chunks, generates a one-paragraph LLM summary + keywords per chunk |
| Top-K similarity graph between events | After each chunk batch, similarity edges are built so related events surface together in graph-mode retrieval |
| Hybrid search across all pools | `memory_search` runs vector cosine + BM25 keyword + RRF rank-fusion across memory / bank / chunk pools every call |
| Auto-surface relevant context on every prompt | A `UserPromptSubmit` hook calls `surfacing_search` before the LLM sees the prompt and injects a `<recall>` block with ~6 related events |
| FTS5 + CJK indexing | SQLite triggers + `jieba` segmentation; index stays synced with every write |
| Stopword auto-detection | `build_stopwords` discovers high-frequency low-information tokens nightly |
| Embedding backfill | A launchd job catches anything missed (e.g. embed API was briefly down) |

**This is the whole system.** Even if you never touch the curation
tools below, `memory_search` will find anything you've said or sent
in any conversation, surface it on relevant prompts, and link related
events together via the chunk graph.

<details>
<summary>Optional curation tools (the system works fully without any of these)</summary>

These exist so the LLM (or you) can annotate memories for slightly
higher-quality retrieval. **None of them are required.** Recall,
search, and auto-surfacing all work without ever calling them.

- `memory_remember(content)` — flag a *specific* fact as a "highlight"
  so it ranks higher when relevant. Useful for ground-truth facts
  ("I'm lactose intolerant") that you want pulled up reliably.
- `memory_pin(id)` — pin a memory so it never time-decays.
- `memory_add_tags(id, tags)`, `memory_add_edge(...)` — manual
  taxonomy / relationship annotation.
- `memory_find_stale`, `memory_decay`, `memory_delete` — bulk
  maintenance of the curated set.

If your LLM never calls any of these, you lose nothing structural —
just the small ranking boost that an explicit "highlight" gives.

</details>

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

**imprint-memory does NOT replace your main chat model** — Claude /
ChatGPT / Gemini / whichever LLM you talk to keeps doing that job
unchanged. What imprint-memory runs internally is a small handful of
**helper models** that turn raw chat history into searchable memory:
one for *embedding* (turning text and images into vectors), one for
*chunk summarization* (the chunker's LLM that compresses each
conversation segment into a one-paragraph summary), and an optional
one for *context compression*. The helpers below are all that
imprint-memory itself calls — your main chat LLM and your API bill
for it are completely separate.

Default helper config is tuned to **fit inside vendors' free tiers
for normal personal use** — no payment card required, no billing to
enable, no surprise charges.

### Helper models (what imprint-memory actually calls)

| Helper | Required? | Default | Provider | Cost on default | How to get it |
|---|---|---|---|---|---|
| **Embedding** (text + image → vector) | **Required** | `gemini-embedding-2` (3072 dim, multimodal) | Google AI Studio | Free tier (~1500 req/day) | Sign up free at [aistudio.google.com](https://aistudio.google.com/apikey) → "Create API key" (Google account is enough; no credit card, no Cloud project). `export GOOGLE_API_KEY=...` |
| Embedding (alternative 1) | — | `bge-m3` (1024 dim, **text only, no image**) | Local Ollama | $0, local | `brew install ollama && ollama pull bge-m3 && ollama serve` |
| Embedding (alternative 2) | — | `text-embedding-3-small` (1536 dim, text only) | OpenAI | Paid, no free tier | Buy API credits, `export OPENAI_API_KEY=...` |
| **Chunk-summary LLM** (chunker's LLM) | Optional but recommended | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare Workers AI | Free tier (10k neurons/day) | Sign up free at [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up) (no card). Workers AI free tier is on by default. Account ID is in the dashboard URL. Create a token at [/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) → "Create Token" → "Workers AI" template. `export CF_ACCOUNT_ID=... CF_API_TOKEN=...` |
| Chunk-summary LLM (alternative 1) | — | `gemini-1.5-flash` or `gemini-2.0-flash` | Google AI Studio | Free tier (~15 req/min) | Same `GOOGLE_API_KEY` as embedding. Set `CF_SUMMARY_MODEL` to the Gemini model name |
| Chunk-summary LLM (alternative 2) | — | Any Ollama model | Local Ollama | $0, local | Slower / lower quality summaries; set `CF_SUMMARY_MODEL` accordingly |
| **Context compression** (`compress.py`) | Optional, separate script | `qwen3:8b` | Local Ollama | $0, local | Only if you actually use the `compress.py` CLI. `brew install ollama && ollama pull qwen3:8b` |

**Bottom line**: the *only* thing strictly required to get up and running
is **one** embedding provider. If you set up Google for embedding,
chunk summarization can reuse the same `GOOGLE_API_KEY`. Daily personal
use never gets close to free-tier limits, and "enabling" Workers AI
or Google AI Studio is a single click — neither provider can charge
you without you explicitly switching plans.

### ⚠️ Embedding consistency — DO NOT MIX

The vector dimension MUST stay constant across the lifetime of one DB.

| Provider / model | Dim | Multimodal? |
|---|---|---|
| Google `gemini-embedding-2` | **3072** | ✓ text + image |
| OpenAI `text-embedding-3-small` | **1536** | text only |
| Ollama `bge-m3` | **1024** | text only |

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

- **每个对话 turn 自动捕获** — 你发的、AI 回的每条消息都自动写入
  可搜索的日志、自动切成事件、自动做多模态 embedding（文字 + 图片）。
  LLM **不需要"决定要不要记住"**，写进 DB 是默认发生的。
- **混合搜索开箱即用** — 关键词（FTS5/BM25）+ 语义（向量）+ RRF
  rank 融合，覆盖 memory / bank / chunk 三池。问"上周那个项目是
  什么来着"也能找到。
- **提问前自动浮现相关上下文** — `UserPromptSubmit` hook 每次提问前
  调 `surfacing_search`，注入 `<recall>` 块（约 6 条相关事件）。
- **多模态** — 对话里发的图片会跟文字一起 embed，所以"我发的那张
  红色截图"就算 caption 不提"红色"也能命中。
- **同步 claude.ai 对话** — 可选 Chrome 扩展，把网页端聊天也存进
  同一套记忆库。
- **AI 主动标"高亮"** *(可选)* — LLM 可以调 `memory_remember` 把
  某条事实顶到搜索结果靠前，但**系统跑起来不依赖这步**。
- **可整理** — 记忆能 pin（不衰减）、加标签、加图谱边（记忆之间
  的关系）。每条 importance 也可调。
- **中文友好** — 完整中文搜索，支持 `昨天`、`上个月`、`去年冬天`
  等时间表达。

## 真正的工作流程

常见误解："是不是还是要 AI 自己决定要记什么？" —— **不是**。
整个 recall 管线**全自动**。LLM **从来不需要**调 `memory_remember`，
东西就已经被记下来了。整理工具（`memory_remember`、`pin`、
`add_tags` 等）确实存在，但它们是**可选的标注层**，叠在一套已经
完整运转的自动系统**之上** —— 搜索、召回、自动浮现都跟它们无关。

### 自动管线（这就是整个系统）

| 能力 | 怎么做到 |
|---|---|
| 每条消息原文入库 | Channel adapter 在每个 in/out turn 都调 `log_message()` — Claude Code hook、claude.ai 同步、Telegram bot、自定义 app。**没有"要不要存"那一步**。 |
| 图片多模态嵌入 | 消息带上传 header（如 `路径=/abs/path.jpg`）时，`_maybe_embed_image` 立即跑，写入 text+image 联合向量 |
| 对话切分成"事件" | `incremental_chunk_update` 定时跑，把连续消息切成 chunk，用 LLM 生成一段摘要 + keywords |
| 事件之间的 Top-K 相似度图谱 | 每批 chunk 切完后自动建相似度边，graph 检索时让相关事件链到一起 |
| 全池混合搜索 | `memory_search` 每次调用都跑向量 cosine + BM25 关键词 + RRF rank 融合，覆盖 memory / bank / chunk 三池 |
| 每次提问自动浮现相关上下文 | `UserPromptSubmit` hook 在 LLM 看到 prompt 前就调 `surfacing_search`，注入 `<recall>` 块（约 6 条相关事件） |
| FTS5 全文索引 + 中文分词 | SQLite trigger + `jieba` 分词，索引随写入实时同步 |
| 停用词自动识别 | `build_stopwords` 夜跑，识别高频低信息词 |
| Embedding 补漏 | launchd 兜底 job 处理 API 偶发不可用造成的漏 embed |

**这就是整个系统。**就算你**永远不碰**下面那些整理工具，
`memory_search` 也能搜到你说过、发过的任何东西，在相关 prompt 上
自动浮现，并通过 chunk 图谱把相关事件链到一起。

<details>
<summary>可选整理工具（不调系统照常工作）</summary>

这些工具让 LLM（或你）给记忆做**标注**，让检索质量稍微再好一点。
**没有一项是必需的。**召回 / 搜索 / 自动浮现都不依赖它们。

- `memory_remember(content)` — 把**特定**事实标成"高亮"，让它在相关
  时排到结果列表更靠前。适合像"我乳糖不耐受"这种你希望可靠拉出来
  的 ground-truth 事实。
- `memory_pin(id)` — 钉住某条记忆使它永不时间衰减。
- `memory_add_tags(id, tags)`、`memory_add_edge(...)` — 手动加分类
  / 关系标注。
- `memory_find_stale`、`memory_decay`、`memory_delete` — 批量维护
  整理后的集合。

如果你的 LLM 一次都不调这些，你**不会失去任何结构性能力** —— 只是
少了"高亮事实排前面"那点微调 ranking。

</details>

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

**imprint-memory 不取代你的主对话模型** —— 你日常聊天用的 Claude /
ChatGPT / Gemini 还是它自己干活。imprint-memory 内部跑的是几个
**辅助模型**，把对话历史转成可搜索的记忆：一个负责**嵌入**（把文字
和图片转成向量）、一个负责 **chunk 摘要**（chunker 用 LLM 把每段对话
压成一段总结）、还有一个可选的**上下文压缩**。下面列的就是
imprint-memory 自己会调用的全部模型 —— 你的主对话 LLM 和它的 API
账单跟这里**完全无关**。

默认配置都调成**塞进各厂商免费档**的水位 —— 不需要绑卡、不需要开
billing、不会冒出账单。

### 辅助模型清单（imprint-memory 真正调的）

| 辅助模型 | 必需？ | 默认 | 厂商 | 默认配置费用 | 怎么拿 |
|---|---|---|---|---|---|
| **嵌入**（文字+图片 → 向量） | **必需** | `gemini-embedding-2`（3072 维，多模态） | Google AI Studio | 免费档（约 1500 req/天） | 免费注册 [aistudio.google.com](https://aistudio.google.com/apikey) → "Create API key"（Google 账号就够，**不需要信用卡、不需要建 Cloud project**）。`export GOOGLE_API_KEY=...` |
| 嵌入（替代项 1） | — | `bge-m3`（1024 维，**只支持文字、不支持图片**） | 本地 Ollama | $0，本地 | `brew install ollama && ollama pull bge-m3 && ollama serve` |
| 嵌入（替代项 2） | — | `text-embedding-3-small`（1536 维，只支持文字） | OpenAI | 付费，无免费档 | 充值 API 余额，`export OPENAI_API_KEY=...` |
| **Chunk 摘要 LLM** | 可选但推荐 | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare Workers AI | 免费档（10k neurons/天） | 免费注册 [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up)（**不要卡**）。Workers AI 默认免费档开着。Account ID 在 dashboard 网址里能看到。在 [/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) → "Create Token" → 选 "Workers AI" 模板创建 token。`export CF_ACCOUNT_ID=... CF_API_TOKEN=...` |
| Chunk 摘要 LLM（替代项 1） | — | `gemini-1.5-flash` / `gemini-2.0-flash` | Google AI Studio | 免费档（约 15 req/分钟） | 复用嵌入那把 `GOOGLE_API_KEY`，设 `CF_SUMMARY_MODEL` 为 Gemini 模型名 |
| Chunk 摘要 LLM（替代项 2） | — | 任意 Ollama 模型 | 本地 Ollama | $0，本地 | 摘要质量稍低、速度稍慢；设对应 `CF_SUMMARY_MODEL` |
| **上下文压缩**（`compress.py` 用） | 可选，单独脚本 | `qwen3:8b` | 本地 Ollama | $0，本地 | 仅当你用 `compress.py` CLI 时才装。`brew install ollama && ollama pull qwen3:8b` |

**底线**：开起来**绝对必需的**只有**一个**嵌入服务。如果你用了
Google 做嵌入，chunk 摘要可以直接复用同一把 `GOOGLE_API_KEY`。日常
个人使用根本碰不到免费档上限，"启用" Workers AI 或 Google AI Studio
都是点一下（**不要卡**），两边都不可能在你没主动换套餐的情况下扣钱。

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
