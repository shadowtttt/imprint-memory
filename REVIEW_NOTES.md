# Review Notes

## Addressed in this pass

- Removed WebDriverAgent/iPhone control MCP tools from `imprint_memory.server`; they exposed personal device IDs, network addresses, local paths, and sudo command assumptions unrelated to a memory package.
- Fixed a fresh-install receiver bug: `log_message()` inserted `conversation_log.model`, but the schema did not create or migrate that column.
- Aligned default embedding behavior with the advertised deployment path: Ollama first, then keyword-only fallback if embeddings are unavailable.
- Made HTTP host/port, receiver host/port, OAuth file path, receiver CORS regex, summary/rerank model names, and chunk skip platforms configurable.
- Hardened `hooks/memory-check.sh` for macOS/Linux, env file paths with spaces, malformed `.env` lines, and missing `python3`.
- Added missing docstrings for public functions found by AST inspection.

## Decisions to consider

1. Should `cc_execute`, `cc_check`, and `cc_tasks` stay in the core memory server?
   They are useful for a full personal-agent stack, but they let an MCP client spawn local Claude Code tasks. Some users may expect `imprint-memory` to be storage/search only.

2. Should the browser receiver require `numpy` by default?
   The base `pip install imprint-memory` path now stays lightweight, while `imprint-memory[receiver]` includes vector graph dependencies. If most users install browser sync, making `numpy` a base dependency would reduce optional-extra confusion.

3. Should receiver URL configuration move into `imprint-chat-sync` UI?
   The extension currently targets `http://localhost:8001`. That keeps permissions minimal, but users who change `IMPRINT_RECEIVER_PORT` must also edit/rebuild the extension.

4. Should Chinese summary prompts be configurable by template file?
   The current chunk summaries are optimized for a Chinese personal-memory style. English users can still search, but summary tone/language may surprise them.
