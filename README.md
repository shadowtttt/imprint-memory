# imprint-memory

Persistent memory system for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Gives Claude long-term memory that survives across conversations.

Built as an [MCP server](https://modelcontextprotocol.io/) — works locally (stdio) or remotely via HTTP with OAuth.

## Features

- **Hybrid search** — FTS5 full-text + vector embeddings + exact-match, fused with [RRF](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) ranking and time-decay scoring
- **CJK support** — Chinese/Japanese/Korean text is segmented with jieba for accurate full-text search
- **Memory CRUD** — store, search, update, delete memories with category/source/importance tags
- **Conversation search** — search logged conversations by keyword, filterable by platform
- **Knowledge bank** — drop `.md` files in `bank/`; they're auto-chunked, embedded, and searchable
- **Daily logs** — append-only daily journal
- **Message bus** — shared timeline across all sources
- **Task queue** — submit tasks for Claude Code to execute asynchronously (supports multi-turn sessions)
- **Context compression** — summarize old context lines with a local Ollama model, with truncation fallback

All data in a single SQLite database (WAL mode).

## Quick start

```bash
# Install
pip install git+https://github.com/Qizhan7/imprint-memory.git

# Register with Claude Code
claude mcp add -s user imprint-memory -- imprint-memory
```

Or clone locally:

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory && pip install -e .
```

## Tools

| Tool | Description |
|------|-------------|
| `memory_remember` | Store a memory (category, source, importance) |
| `memory_search` | **RRF unified search** across memories, bank, and conversations |
| `memory_list` | List recent memories |
| `memory_update` | Update a memory by ID |
| `memory_delete` | Delete a memory by ID |
| `memory_forget` | Delete memories matching a keyword |
| `memory_pin` / `memory_unpin` | Pin/unpin core memories (pinned = no time-decay) |
| `memory_add_tags` | Add tags to a memory (comma-separated) |
| `memory_add_edge` | Link two memories with a typed relationship |
| `memory_get_graph` | View a memory's tags, edges, and neighbor previews |
| `memory_find_duplicates` | Find semantically similar pairs (dedup audit) |
| `memory_find_stale` | Find low-activity old memories |
| `memory_decay` | Reduce importance of inactive memories (dry-run by default) |
| `memory_reindex` | Rebuild all embeddings (after switching providers) |
| `memory_daily_log` | Append to today's log |
| `conversation_search` | Search conversation history (all platforms) |
| `search_telegram` | Search Telegram + heartbeat conversations |
| `search_channel` | Search any specific channel (discord, slack, etc.) |
| `message_bus_read` / `post` | Read/write the shared message bus |
| `cc_execute` | Submit a task for Claude Code |
| `cc_check` / `cc_tasks` | Check task status, list recent tasks |

## Configuration

All via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPRINT_DATA_DIR` | `~/.imprint/` | Base directory for all data |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | SQLite database path |
| `TZ_OFFSET` | `0` | Hours offset from UTC (e.g. `12` for NZST) |
| `EMBED_PROVIDER` | `ollama` | `ollama`, `openai`, or `google` |
| `EMBED_MODEL` | auto | Model name (default: `bge-m3` / `text-embedding-3-small` / `gemini-embedding-2`) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `OPENAI_API_KEY` | — | For OpenAI-compatible providers |
| `EMBED_API_BASE` | `https://api.openai.com` | Base URL for OpenAI-compatible API |
| `GOOGLE_API_KEYS` | — | Comma-separated keys for Google Gemini Embedding (or `GOOGLE_API_KEY` for a single key) |

### Embedding providers

**Ollama (default)** — free, local:
```bash
ollama pull bge-m3 && ollama serve
```

**OpenAI API** — no local GPU:
```bash
export EMBED_PROVIDER=openai OPENAI_API_KEY=sk-...
```

**Any OpenAI-compatible API** (Voyage AI, Azure, etc.):
```bash
export EMBED_PROVIDER=openai OPENAI_API_KEY=... EMBED_API_BASE=https://... EMBED_MODEL=...
```

**Google Gemini Embedding** — supports text + image (multimodal):
```bash
export EMBED_PROVIDER=google GOOGLE_API_KEYS=key1,key2  # comma-separated for round-robin
```

No embedding provider? Falls back to FTS5 keyword search only — still works, just less semantic.

After switching providers, run `memory_reindex` to rebuild embeddings.

## HTTP mode

For Claude.ai access through a tunnel:

```bash
pip install imprint-memory[http]
imprint-memory --http   # → http://0.0.0.0:8000/mcp
```

OAuth credentials via `~/.imprint-oauth.json` or env vars (`OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_ACCESS_TOKEN`).

## Data layout

```
~/.imprint/
├── memory.db           # SQLite (memories, vectors, tasks, bus)
├── MEMORY.md           # Auto-generated index
└── memory/
    ├── 2026-04-01.md   # Daily logs
    └── bank/           # Knowledge files (.md)
```

## Standalone vs Full Stack

**This package works on its own** — `pip install` and you get persistent memory in Claude Code. No other dependencies.

If you also want multi-channel messaging (Telegram, etc.), Claude.ai integration, heartbeat automation, a dashboard, and scheduled tasks, see the full system: [claude-imprint](https://github.com/Qizhan7/claude-imprint). It installs imprint-memory as a dependency.

## Companion: claude.ai conversation sync

The chat-sync pipeline lets you ingest conversations from anywhere (browser, scripts, other tools) into the same memory database:

```
imprint-chat-sync (browser ext)  ──POST──>  imprint-memory-receiver  ──>  memory.db
                                             (auto embed + chunk + edges)
```

**1. Run the receiver** (needs `imprint-memory[http]`):

```bash
pip install 'imprint-memory[http]'
imprint-memory-receiver              # listens on 127.0.0.1:8001
# or:  PORT=9001 imprint-memory-receiver --no-backfill
```

Endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/ingest` | Submit messages — `{ conversation_id, messages: [{ direction, content, ... }] }` |
| `GET`  | `/api/health` | Liveness check |
| `GET`  | `/api/status` | Recent count + embedded vector count |

The receiver embeds new messages in the background and runs incremental chunking → topic summaries → graph edges, so search results stay rich.

**2. Browser extension**: [imprint-chat-sync](https://github.com/Qizhan7/imprint-chat-sync) — pulls conversations (including `<thinking>` blocks) from claude.ai using your browser session and POSTs to this receiver.

## Surfacing hook (recall as you type)

`hooks/memory-check.sh` is a [UserPromptSubmit](https://docs.anthropic.com/en/docs/claude-code/hooks) hook that scans each message for recall-worthy signals (time references, emotion, "remember"...) and, if any are found, calls `surfacing_search()` to inject a `<recall>` block with the most relevant memory chunks plus one graph-linked neighbor. It always appends a `<memory-check>` reminder so the model knows to dig deeper when the turn touches the past.

**Install:**

```bash
cp hooks/memory-check.sh ~/.claude/hooks/memory-check.sh
chmod +x ~/.claude/hooks/memory-check.sh
```

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "bash $HOME/.claude/hooks/memory-check.sh" }] }
    ]
  }
}
```

**Hook environment variables:**

| Variable | Purpose | Default |
|----------|---------|---------|
| `IMPRINT_PYTHON` | Python interpreter to use | `python3` |
| `IMPRINT_DATA_DIR` | Where `memory.db` lives | `~/.imprint` |
| `IMPRINT_ENV_FILE` | Path to a `KEY=VALUE` file (e.g. for `GOOGLE_API_KEY`, `CF_API_TOKEN`) | falls back to `~/.imprint/.env` if it exists |
| `IMPRINT_HOOK_LANG` | Prompt language: `en` or `zh` | `en` |

## License

MIT
