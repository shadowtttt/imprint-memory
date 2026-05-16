# Changelog

## 0.1.1 - 2026-05-17

- Rewrote onboarding docs around three setup paths: MCP-only, browser sync, and surfacing hook.
- Added `.env.example` covering storage, embeddings, receiver, HTTP/OAuth, hook, and search tuning.
- Removed non-memory WebDriverAgent tools and hardcoded personal device/network settings from the public MCP server.
- Made HTTP host/port, OAuth file path, receiver host/port, receiver CORS, summary models, and chunk skip platforms configurable.
- Switched default embeddings to local Ollama with graceful FTS5/LIKE fallback when no provider is available.
- Fixed fresh database setup for browser-ingested conversations by adding the missing `conversation_log.model` column.
- Hardened `hooks/memory-check.sh` for macOS/Linux shells, env files with spaces, missing Python, and malformed `.env` lines.
- Added CI import smoke tests for Python 3.10, 3.11, and 3.12.
