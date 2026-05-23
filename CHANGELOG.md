# Changelog

## 0.3.8 — 2026-05-24

Two-step search guidance + chunker keeps external system names.

- README documents the two-step search fallback (`memory_search` →
  `conversation_search`) with a copy-pasteable CLAUDE.md snippet. Without
  this hint LLMs commonly stop after the first miss even though the raw
  conversation_log still has 20+ matching messages.
- `conversation_chunker.SUMMARIZE_PROMPT` now requires the chunker to keep
  external system names (frameworks, papers, GitHub repos) in `entities`
  and reference them by name in `recap`. Previously the LLM summarizer
  routinely dropped proper nouns, leaving research/comparison threads
  unsearchable by keyword.
- `memory_search` / `unified_search` docstrings clarify the default pools
  are `["memory", "bank", "chunk"]`, explain that chunk hits expand into
  raw messages, and point to `conversation_search` as the fallback path.

## 0.2.1 — 2026-05-20

Docs-only release that gets the new architecture diagram + restructured
"How it actually works" section into the PyPI-shipped README. No code
changes since 0.2.0.

- Added mermaid architecture diagram with four flows: 📥 Capture,
  🔎 Search, ✨ Surface (all automatic), and 📝 Curate (optional,
  dotted arrows).
- "Optional curation tools" restored as a visible second table next
  to the automatic pipeline table — no longer hidden in a `<details>`
  block. The framing makes auxiliary vs. core unmissable while still
  letting power users see the tools at a glance.
- Bilingual (EN + ZH) sections kept parallel.

## 0.2.0 — 2026-05-20

### Default change (read this first)

- **`EMBED_PROVIDER` now defaults to `google`** (`gemini-embedding-2`,
  3072-dim, multimodal text+image), not `ollama`/`bge-m3` (1024-dim,
  text-only). Reason: multimodal support is now central, and mixing
  vector dimensions in one database silently breaks vec search.
  If you were on `ollama` before and want to stay there, set
  `EMBED_PROVIDER=ollama` **before** your first write. See README
  *"Embedding consistency — DO NOT MIX"* for full discussion.

### New features

- **Test mode** — three granularities for keeping debug runs out of
  your real memory store: per-message `测试：` / `test:` prefix,
  per-session marker file (`<DATA_DIR>/.test-sessions/<sid>`), and
  global kill switch (`<DATA_DIR>/.test-mode`). When active,
  `log_message` returns OK but drops the row.
- **Chunk-as-navigator rendering** — `unified_search_text` now surfaces
  chunk hits as grouped raw conversation turns under a single banner
  (`━━ 原文 <date> (score) ━━`) instead of repeating per-line tags.
  Companion messages get paired automatically (user → next assistant,
  or vice versa) so dialogue context isn't lost.
- **Image multimodal embed inline** — when `log_message` sees an
  upload header (`路径=/abs/path.jpg`), it writes a combined
  text+image vector immediately rather than waiting for a backfill.
- **True graph traversal** — `_graph_expansion_section` no longer
  requires neighbours to re-match the query keywords. Edges are
  selected purely by `similarity × strength`, with the near-duplicate
  cap (>70% keyword overlap with seed) as the only filter. Matches
  the Zep/Graphiti "anchor + expand" pattern.
- **Smart truncation** — `_smart_truncate` no longer breaks inside
  ASCII decimals (`o4.7`, `v1.2.3`) or URLs. `.` only counts as a
  sentence end when followed by whitespace or end-of-text.

### Fixes

- **`is_test` semantics fixed** — test-prefixed messages are now
  *dropped* from the DB entirely (the original intent) rather than
  written with `is_test=1` and excluded from search after the fact.
  Surfacing still runs.
- **Image upload regex** (`_UPLOAD_PATH_RE`, `_PATH_RE`) — required
  absolute path, ASCII filesystem chars, 1-300 chars, real image
  extension. Old regex was matching narrative quotes of the header
  text (chat messages discussing the feature) and producing 1000+
  char fake paths that crashed `Path.exists()` with errno 63.
- **Stopword filter no longer leaves dangling OR operators** —
  `_sanitize_fts` used to OR-join first and then drop stop tokens,
  leaving `"上次 OR OR OR p5js"` syntax errors that silently zeroed
  out FTS search. Order is now: tokenize → drop stopwords → OR-join
  survivors.
- **`chunks_fts` query missing `ORDER BY rank`** — was returning
  rows in rowid (insertion) order rather than BM25 relevance order.
- **`_extract_time_intent` no longer pins bare time-of-day words to
  today** — "凌晨", "下午", "晚上" alone don't trigger date-pinning
  unless the matched text carries a real date anchor (digits, 今 /
  昨 / 明 / 前 etc.).
- **`has_fts` confidence threshold** — lowered from 0.02 to 0.01 so
  the conversation pool (currently no vec channel) can qualify as
  "has FTS signal" on rank-1 hits and avoid the 0.15 noise penalty.
- **Conversation-pool think-block filter** — `<think>…</think>` blocks
  are stripped before deciding whether a row carries actual content.
  Reasoning-only assistant turns are dropped from rank+render.
- **`_expand_chunk_hybrid` crash on image-anchor expansion** —
  `msg_by_id` values are `sqlite3.Row` not `dict`; the previous
  `.get()` call raised `AttributeError`.

### Search-quality tuning

- **Time decay disabled** — `_rerank_memory` / `_rerank_bank` /
  `_rerank_conv` no longer compress old-but-still-relevant hits.
  `WEIGHT_RECENCY = 0`.
- **Chunk pool opt-in for default search** — `unified_search`
  default pools are `memory + bank + chunk`; the chunk renderer
  expands chunks into originals so users see real chat, not chunk
  summaries. `surfacing_search` uses the same pool set.
- **Short-message density bonus in chunk expansion** — concise lines
  that directly hit a query term get a density-weighted score boost
  so they rank above paragraph-length tangential mentions inside the
  same chunk.
- **Expansion message dedup** — repeated identical user messages
  ("@gemini …" tapped four times) collapse to a single line in the
  rendered expansion.
- **Pair expansion turns with opposite direction** — each picked top
  message also pulls in its nearest opposite-direction neighbour so
  expansion never shows one side of a turn in isolation.

### Docs

- **README "Models & Cost" section** — inventory of every helper
  model imprint-memory invokes (embedding, chunk summarizer, optional
  context compressor) plus a 5-minute free-tier signup walkthrough
  for Google AI Studio and Cloudflare Workers AI. Calls out the
  separation between your main chat LLM (Claude / ChatGPT / Gemini)
  and the internal helper models, with concrete alternatives listed
  per row.
- **README "How it actually works"** (rewritten from previous
  "Capabilities" section) — leads with the 9-row automatic pipeline.
  Optional curation tools (`memory_remember`, `memory_pin`, etc.)
  collapsed into a `<details>` block with explicit "system works
  fully without any of these" callout.
- **README intro bullets rewritten** to lead with auto-capture as
  the first feature.

### Internal

- `pyproject.toml` description updated from
  *"Persistent memory system for Claude Code"* to
  *"Automatic memory layer for any LLM agent — captures every
  conversation turn, multimodal embed (text+image), hybrid search
  (vec + FTS5 + RRF), auto-surfacing recall hook."*

---

## 0.1.1 — 2026-05-17

- Rewrote onboarding docs around three setup paths: MCP-only, browser sync, and surfacing hook.
- Added `.env.example` covering storage, embeddings, receiver, HTTP/OAuth, hook, and search tuning.
- Removed non-memory WebDriverAgent tools and hardcoded personal device/network settings from the public MCP server.
- Made HTTP host/port, OAuth file path, receiver host/port, receiver CORS, summary models, and chunk skip platforms configurable.
- Switched default embeddings to local Ollama with graceful FTS5/LIKE fallback when no provider is available.
- Fixed fresh database setup for browser-ingested conversations by adding the missing `conversation_log.model` column.
- Hardened `hooks/memory-check.sh` for macOS/Linux shells, env files with spaces, missing Python, and malformed `.env` lines.
- Added CI import smoke tests for Python 3.10, 3.11, and 3.12.
</content>
</invoke>