# imprint-memory

Local long-term memory for Claude Code users who want searchable, private recall across notes, conversations, and Claude.ai history.

```
Claude Code ── MCP stdio ───────────────────────────────┐
                                                        │
manual memories / daily logs / bank/*.md ───────────────┤
                                                        ▼
                                              imprint-memory
                                         SQLite + FTS5 + vectors
                                                        │
claude.ai ── Chrome extension ── POST :8001/api/ingest ─┤
                                                        ▼
                            log → embed → chunk → graph edges → search
                                                        │
UserPromptSubmit hook ── surfacing_search ── <recall> ──┘
```

## Capabilities

| Capability | What it does |
| --- | --- |
| Memory CRUD | Store, update, delete, pin, tag, and link memories. |
| Hybrid retrieval | Combines FTS5 keyword search, exact/LIKE matches, vector similarity, RRF fusion, and optional LLM reranking. |
| Time-aware search | Parses explicit `after`/`before` filters and Chinese temporal expressions such as `昨天`, `上次`, `三周前`, `去年冬天` when `jionlp` is installed. |
| Query expansion | Uses Cloudflare Workers AI when configured to add colloquial query variants before retrieval. |
| Chunk-level conversation retrieval | Searches conversation summaries, then expands the best chunks with matching source messages. |
| Graph neighbors | Surfaces linked memories and neighboring conversation chunks when they add useful context. |
| Browser conversation sync | Receives claude.ai conversations from `imprint-chat-sync` through `POST /api/ingest`. |
| Passive surfacing | A Claude Code `UserPromptSubmit` hook can inject compact `<recall>` blocks when a prompt looks memory-related. |
| CJK-friendly FTS | Uses `jieba` when available, with character-level fallback, so Chinese/Japanese/Korean text remains searchable. |
| Zero-provider fallback | If Ollama/API embeddings are unavailable, tools still work with FTS5 and exact matching. |

## Quick Start

### 1. I just want memory in Claude Code

```bash
pip install imprint-memory
claude mcp add -s user imprint-memory -- imprint-memory
```

Restart Claude Code. You should see the `imprint-memory` MCP tools. No API key is required. By default the server stores data in `~/.imprint/memory.db` and tries Ollama embeddings at `http://localhost:11434`; if Ollama is not running, search falls back to keyword-only.

Optional local embeddings:

```bash
ollama pull bge-m3
ollama serve
```

### 2. I also want to sync my claude.ai conversations

```bash
pip install 'imprint-memory[receiver]'
imprint-memory-receiver
```

The receiver listens on `127.0.0.1:8001`. Then install the companion extension:

```bash
git clone https://github.com/Qizhan7/imprint-chat-sync.git
```

Open Chrome → `chrome://extensions/` → enable Developer mode → Load unpacked → select the cloned `imprint-chat-sync` folder. Stay logged in to [claude.ai](https://claude.ai), then use the extension popup to sync.

### 3. I want the full experience with the surfacing hook

Install the hook script:

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

Add this to `~/.claude/settings.json`:

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

For API keys used by the hook, copy `.env.example` to `~/.imprint/.env` and fill only what you use.

## Configuration

All configuration is via environment variables. Defaults are chosen for local, private use.

| Variable | Default | Description |
| --- | --- | --- |
| `IMPRINT_DATA_DIR` | `~/.imprint` | Base directory for the database, daily logs, and bank files. |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | SQLite database path. |
| `TZ_OFFSET` | `0` | Local timezone offset from UTC, in hours. |
| `IMPRINT_USER_NAME` | `User` | Human speaker label used in summaries and chunk expansion. |
| `IMPRINT_AGENT_NAME` | `Assistant` | Assistant speaker label used in summaries and chunk expansion. |
| `IMPRINT_LOCALE` | `en` | Search output labels: `en` or `zh`. |
| `EMBED_PROVIDER` | `ollama` | Embedding provider: `ollama`, `openai`, or `google`. |
| `EMBED_MODEL` | provider default | Embedding model. Defaults: `bge-m3`, `text-embedding-3-small`, or `gemini-embedding-2`. |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL for embeddings. |
| `OPENAI_API_KEY` | unset | API key for OpenAI or OpenAI-compatible embedding providers. |
| `EMBED_API_BASE` | `https://api.openai.com` | Base URL for OpenAI-compatible embedding APIs. |
| `GOOGLE_API_KEY` | unset | Single Google Gemini API key. |
| `GOOGLE_API_KEYS` | unset | Comma-separated Google keys for round-robin embedding calls. |
| `CF_ACCOUNT_ID` | unset | Cloudflare account ID for query expansion, reranking, and summaries. |
| `CF_API_TOKEN` | unset | Cloudflare API token. |
| `CF_RERANK_MODEL` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare model for query expansion and reranking. |
| `CF_SUMMARY_MODEL` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Cloudflare model for chunk summaries. |
| `GEMINI_SUMMARY_MODEL` | `gemini-2.5-flash-lite` | Gemini model used as a summary fallback. |
| `OLLAMA_CHAT_URL` | `http://localhost:11434/api/chat` | Ollama chat endpoint for summary fallback. |
| `OLLAMA_CHAT_MODEL` | `gemma4:e4b` | Ollama chat model for summaries and causal-edge prediction. |
| `IMPRINT_HTTP_HOST` | `0.0.0.0` in HTTP mode | MCP HTTP bind host. |
| `IMPRINT_HTTP_PORT` | `8000` | MCP HTTP port. |
| `IMPRINT_OAUTH_FILE` | `~/.imprint-oauth.json` | OAuth credential file for HTTP mode. |
| `OAUTH_CLIENT_ID` | unset | OAuth client ID fallback when no credential file exists. |
| `OAUTH_CLIENT_SECRET` | unset | OAuth client secret fallback. |
| `OAUTH_ACCESS_TOKEN` | unset | Bearer token used by HTTP mode. |
| `IMPRINT_RECEIVER_HOST` | `127.0.0.1` | Chat-sync receiver bind host. Legacy `HOST` is also accepted. |
| `IMPRINT_RECEIVER_PORT` | `8001` | Chat-sync receiver port. Legacy `PORT` is also accepted. |
| `IMPRINT_RECEIVER_EMBED_DELAY` | `0.7` | Delay between background embedding calls, in seconds. |
| `IMPRINT_RECEIVER_SHIFT_THRESHOLD` | `0.50` | Topic-shift cosine threshold for adjacent user messages. |
| `IMPRINT_RECEIVER_CORS_ORIGIN_REGEX` | `^chrome-extension://.*$` | Allowed browser-extension origins. |
| `IMPRINT_PYTHON` | auto-detect `python3.12`, `python3.11`, `python3.10`, then generic Python names | Python interpreter used by `hooks/memory-check.sh`. |
| `IMPRINT_ENV_FILE` | unset | Extra `KEY=VALUE` file loaded by the hook before recall. |
| `IMPRINT_HOOK_LANG` | `en` | Hook reminder language: `en` or `zh`. |
| `STOPWORD_THRESHOLD` | `0.15` | Document-frequency threshold for auto-stopwords. |
| `IMPRINT_STOPWORD_SKIP_PLATFORMS` | `cc` | Platforms ignored when building stopwords. |
| `IMPRINT_CHUNK_SKIP_PLATFORMS` | `cc` | Platforms ignored by conversation chunking and chunk expansion. |
| `IMPRINT_CAUSAL_BLACKLIST` | unset | Extra comma-separated terms ignored by causal-edge discovery. |
| `MESSAGE_BUS_LIMIT` | `40` | Max messages retained in the shared message bus. |
| `COMPRESS_MODEL` | `qwen3:8b` | Ollama model for `imprint_memory.compress`. |
| `COMPRESS_KEEP` | `30` | Recent context lines kept uncompressed. |
| `COMPRESS_THRESHOLD` | `50` | Line count that triggers compression. |

## MCP Tool Reference

| Tool | Description |
| --- | --- |
| `memory_remember` | Store a memory with category, source, importance, dedup, and embedding when available. |
| `memory_search` | Search memories, bank files, conversations, chunks, and graph neighbors. |
| `memory_list` | List recent active memories, optionally by category or time range. |
| `memory_update` | Update content, category, or importance by memory ID. |
| `memory_delete` | Delete one memory by ID. |
| `memory_forget` | Delete memories containing a keyword. |
| `memory_daily_log` | Append a timestamped entry to today’s daily log. |
| `memory_pin` / `memory_unpin` | Mark core memories as exempt from search time decay, or restore normal decay. |
| `memory_add_tags` | Add comma-separated tags to a memory. |
| `memory_add_edge` | Link two memories with a typed relationship and short context. |
| `memory_get_graph` | Show a memory’s tags, edges, and neighbor previews. |
| `memory_find_duplicates` | Read-only semantic duplicate audit. |
| `memory_find_stale` | Read-only stale-memory audit. |
| `memory_decay` | Preview or apply importance decay for inactive memories. |
| `memory_reindex` | Rebuild memory and bank embeddings after provider/model changes. |
| `stopwords_build` | Rebuild auto-stopwords from document frequency. |
| `stopwords_show` | Show current stopwords and metadata. |
| `stopwords_add` / `stopwords_remove` | Manually add or suppress stopwords. |
| `conversation_search` | Keyword search over conversation logs. |
| `conversation_search_semantic` | Vector search over chunks first, then message vectors. |
| `search_telegram` | Convenience search over `telegram` and `heartbeat` platforms. |
| `search_channel` | Search any named conversation platform. |
| `message_bus_read` / `message_bus_post` | Read or write the shared message timeline. |
| `experience_append` | Append a technical note to `memory/bank/experience.md`. |

## Receiver API Reference

Run:

```bash
imprint-memory-receiver --host 127.0.0.1 --port 8001
```

### `POST /api/ingest`

Submit one conversation batch.

```bash
curl -X POST http://127.0.0.1:8001/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "claude.ai",
    "conversation_id": "conv_123",
    "conversation_title": "Planning session",
    "model": "claude-opus-4-1",
    "messages": [
      {
        "direction": "in",
        "speaker": "User",
        "content": "Remember that I prefer short PR summaries.",
        "created_at": "2026-05-16 12:30:00",
        "uuid": "msg_1"
      },
      {
        "direction": "out",
        "speaker": "Assistant",
        "content": "Got it.",
        "created_at": "2026-05-16 12:30:04",
        "uuid": "msg_2"
      }
    ]
  }'
```

Response:

```json
{
  "ok": true,
  "ingested": 2,
  "skipped": 0,
  "errors": 0
}
```

The receiver returns quickly, then embeds, detects topic shifts, summarizes chunks, and updates graph edges in background tasks.

### `GET /api/health`

```json
{ "ok": true, "service": "imprint-chat-sync-receiver" }
```

### `GET /api/status`

```json
{
  "ok": true,
  "recent_count": 5,
  "last_message": "2026-05-16 12:30:04",
  "vectors": 42
}
```

## How Search Works

1. The query is optionally time-parsed (`昨天`, `上次`, `三周前`) and optionally expanded with Cloudflare Workers AI.
2. The system embeds the expanded query when an embedding provider is available.
3. Each pool searches independently: memories, bank chunks, raw conversation rows, summarized conversation chunks, and exact/LIKE matches.
4. Ranked channels are fused with Reciprocal Rank Fusion.
5. Pool-specific rerankers adjust for recency, importance, pinned memories, and file freshness.
6. Optional Cloudflare reranking scores the top candidates for semantic relevance.
7. Chunk hits expand to source messages; memory and chunk graph neighbors are appended when useful.
8. Results update recall counters unless the search is an internal surfacing pass.

## Data Layout

```
~/.imprint/
├── memory.db
├── MEMORY.md
└── memory/
    ├── 2026-05-16.md
    └── bank/
        └── experience.md
```

## Development

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory
pip install -e '.[all]'
python -c "from imprint_memory import server"
```

Run the stdio server:

```bash
imprint-memory
```

Run HTTP MCP mode:

```bash
imprint-memory --http --host 0.0.0.0 --port 8000
```

## License

MIT
