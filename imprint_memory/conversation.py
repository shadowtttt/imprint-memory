"""
Conversation log — Layer 3 of the memory architecture.
Stores full conversation history from all platforms with FTS5 search.
"""

import re
import struct
from pathlib import Path

from .db import _get_db, now_str, LOCAL_TZ, segment_cjk, sanitize_fts_query
from datetime import datetime


# Match a channel-adapter-injected upload header. Looking for the Chinese
# convention used across our channels: "上传了一个文件: 文件名=...; MIME=...;
# 路径=/abs/path.ext". Other adapters can adopt the same shape to get
# automatic multimodal indexing.
_UPLOAD_PATH_RE = re.compile(
    r"上传了一个文件:.*?路径=([^;\]]+?\.(?:jpg|jpeg|png|gif|webp))(?:\s|;|\])",
    re.IGNORECASE | re.DOTALL,
)
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _maybe_embed_image(msg_id: int, content: str, db) -> None:
    """If the just-logged message announces a file upload with a real image
    path, run a multimodal embed (text + image) and store it in
    conversation_vectors. Best-effort: any failure is swallowed so logging
    stays robust; the periodic backfill job will catch missed ones.
    """
    if not content or "上传了一个文件" not in content:
        return
    m = _UPLOAD_PATH_RE.search(content)
    if not m:
        return
    path_str = m.group(1).strip()
    p = Path(path_str)
    if not p.exists() or p.suffix.lower() not in _IMG_EXTS:
        return
    try:
        # Late import to avoid a circular dependency at module load time.
        from .memory_manager import _embed, EMBED_MODEL
        vec = _embed(content, image_path=str(p))
        if not vec:
            return
        blob = struct.pack(f"{len(vec)}f", *vec)
        db.execute(
            "INSERT OR REPLACE INTO conversation_vectors (msg_id, embedding, model) "
            "VALUES (?, ?, ?)",
            (msg_id, blob, EMBED_MODEL),
        )
        db.commit()
    except Exception:
        # Silent failure on purpose — backfill job is the safety net.
        pass


# Matches "测试：xx" / "测试: xx" / "test: xx" prefix on a user message,
# case-insensitive, optional whitespace. When the *user* opens a turn with
# this prefix we treat the whole turn as test data: it still lands in
# conversation_log for traceability, but with is_test=1 so chunker,
# surfacing, and search all skip it cleanly.
_TEST_PREFIX_RE = re.compile(r"^\s*(?:测试|test)\s*[：:]", re.IGNORECASE)


def _is_test_content(content: str) -> bool:
    """True if the user-side content opens with a test marker."""
    if not content:
        return False
    return bool(_TEST_PREFIX_RE.match(content))


# Process-local marker — when a turn is flagged as test (either by the
# user prompt prefix or explicitly by the caller), subsequent log writes
# in the same process for that turn inherit the flag. Channel adapters
# write the inbound "in" message first and then the outbound "out" reply;
# we want both to share the same is_test status.
_test_turn_active = False


def _turn_is_test() -> bool:
    return _test_turn_active


def begin_test_turn():
    """Mark the rest of the current logical turn as test data. Channel
    adapters call this when they detect the user prompt starts with a
    test marker, so the agent's reply also gets is_test=1."""
    global _test_turn_active
    _test_turn_active = True


def end_test_turn():
    global _test_turn_active
    _test_turn_active = False


def log_message(
    platform: str,
    direction: str,
    content: str,
    speaker: str = "",
    session_id: str = "",
    entrypoint: str = "",
    created_at: str = "",
    summary: str = "",
    model: str = "",
    external_id: str = "",
    is_test: bool | None = None,
) -> dict:
    """Write one message to conversation_log.

    external_id is a stable upstream message id used for dedup when available.
    Older clients can omit it and fall back to content/timestamp dedup.

    `is_test`: if None (default), auto-detect from content for direction='in'
    messages, and inherit from the active test-turn marker for 'out'. Pass
    True/False explicitly to override.
    """
    if not content or not content.strip():
        return {"ok": False, "error": "empty content"}

    ts = created_at or now_str()
    clean_content = content.strip()
    external_id = (external_id or "").strip()

    # Resolve is_test
    if is_test is None:
        if direction == "in":
            # Every new user turn resets test mode — only the explicit prefix
            # opens it back up. Without this reset, one stray "测试：" earlier
            # in the process would mark every subsequent turn as test forever.
            if _is_test_content(clean_content):
                begin_test_turn()
                is_test = True
            else:
                end_test_turn()
                is_test = False
        else:
            # 'out' (and any non-'in' direction) inherits whatever the
            # current turn was flagged as. So an assistant reply to a
            # "测试：..." prompt is also is_test=1.
            is_test = _turn_is_test()
    test_flag = 1 if is_test else 0

    db = _get_db()
    try:
        # Browser/API sources should provide a stable message id. Treat it as
        # authoritative so branch re-syncs and repeated text stay distinct.
        if external_id:
            existing = db.execute(
                """SELECT id FROM conversation_log
                   WHERE platform=? AND external_id=?
                   LIMIT 1""",
                (platform, external_id),
            ).fetchone()
        else:
            # Fallback for older clients that predate external message ids.
            existing = db.execute(
                """SELECT id FROM conversation_log
                   WHERE platform=? AND direction=? AND created_at=? AND content=?
                   LIMIT 1""",
                (platform, direction, ts, clean_content),
            ).fetchone()
        if existing:
            return {"ok": True, "id": existing["id"], "skipped": "duplicate"}

        cur = db.execute(
            """INSERT INTO conversation_log
               (platform, direction, speaker, content, external_id, session_id, entrypoint, created_at, summary, model, is_test)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                platform,
                direction,
                speaker,
                clean_content,
                external_id,
                session_id,
                entrypoint,
                ts,
                summary,
                model,
                test_flag,
            ),
        )
        db.commit()
        msg_id = cur.lastrowid
        # Skip multimodal embed for test messages — saves API tokens and
        # keeps test-image vectors out of the live search pool.
        if not test_flag:
            _maybe_embed_image(msg_id, clean_content, db)
        return {"ok": True, "id": msg_id, "is_test": bool(test_flag)}
    finally:
        db.close()


def search_conversations(
    query: str, platform: str = "", platforms: list[str] | None = None, limit: int = 20
) -> list[dict]:
    """FTS5 keyword search over conversation history.
    platform: single platform filter (legacy)
    platforms: list of platforms to include (e.g. ["telegram", "heartbeat"])
    """
    db = _get_db()
    try:
        safe_query = _sanitize_fts_query(query)
        if not safe_query:
            return []

        if platforms:
            placeholders = ",".join("?" for _ in platforms)
            rows = db.execute(
                f"""SELECT c.id, c.platform, c.direction, c.speaker, c.content,
                          c.session_id, c.entrypoint, c.created_at
                   FROM conversation_log_fts f
                   JOIN conversation_log c ON c.id = f.rowid
                   WHERE conversation_log_fts MATCH ? AND c.platform IN ({placeholders})
                   ORDER BY c.id DESC LIMIT ?""",
                (safe_query, *platforms, limit),
            ).fetchall()
        elif platform:
            rows = db.execute(
                """SELECT c.id, c.platform, c.direction, c.speaker, c.content,
                          c.session_id, c.entrypoint, c.created_at
                   FROM conversation_log_fts f
                   JOIN conversation_log c ON c.id = f.rowid
                   WHERE conversation_log_fts MATCH ? AND c.platform = ?
                   ORDER BY c.id DESC LIMIT ?""",
                (safe_query, platform, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT c.id, c.platform, c.direction, c.speaker, c.content,
                          c.session_id, c.entrypoint, c.created_at
                   FROM conversation_log_fts f
                   JOIN conversation_log c ON c.id = f.rowid
                   WHERE conversation_log_fts MATCH ?
                   ORDER BY c.id DESC LIMIT ?""",
                (safe_query, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _sanitize_fts_query(query: str) -> str:
    """Sanitize and segment a query string for FTS5 MATCH.
    Uses shared sanitize_fts_query + segment_cjk from db.py."""
    cleaned = sanitize_fts_query(query)
    if not cleaned:
        return ""
    return segment_cjk(cleaned)


def get_recent(platform: str = "", exclude_platforms: list = None, limit: int = 30) -> list[dict]:
    """Get the most recent N messages, optionally filtered by platform.
    exclude_platforms: list of platforms to skip (for cross-channel context)."""
    db = _get_db()
    try:
        if platform:
            rows = db.execute(
                """SELECT id, platform, direction, speaker, content, session_id, entrypoint, created_at, summary
                   FROM conversation_log WHERE platform = ?
                   ORDER BY created_at DESC, id DESC LIMIT ?""",
                (platform, limit),
            ).fetchall()
        elif exclude_platforms:
            placeholders = ",".join("?" for _ in exclude_platforms)
            rows = db.execute(
                f"""SELECT id, platform, direction, speaker, content, session_id, entrypoint, created_at, summary
                   FROM conversation_log WHERE platform NOT IN ({placeholders})
                   ORDER BY created_at DESC, id DESC LIMIT ?""",
                (*exclude_platforms, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT id, platform, direction, speaker, content, session_id, entrypoint, created_at, summary
                   FROM conversation_log ORDER BY created_at DESC, id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]  # chronological order
    finally:
        db.close()


def format_recent(messages: list[dict], max_content_len: int = 300) -> str:
    """Format recent messages for recent_context.md.
    Uses pre-computed summary if available; falls back to truncation."""
    platform_short = {"telegram": "tg", "wechat": "wx", "cc": "cc", "heartbeat": "hb"}
    lines = []
    for m in messages:
        p = platform_short.get(m["platform"], m["platform"])
        d = "in" if m["direction"] == "in" else "out"
        ts = m["created_at"]
        # Show only MM-DD HH:MM
        if len(ts) >= 16:
            ts = ts[5:16]

        content = m["content"]

        # Collapse multiline to single line for clean parsing
        flat = " ".join(content.split())
        if len(flat) > max_content_len:
            display = flat[:max_content_len] + "..."
        else:
            display = flat

        lines.append(f"[{ts} {p}/{d}] {display}")
    return "\n".join(lines)


def format_search_results(results: list[dict]) -> str:
    """Format search results for MCP tool output."""
    if not results:
        return "没有找到相关对话记录"
    lines = []
    for r in results:
        p = r["platform"]
        d = "←" if r["direction"] == "in" else "→"
        ts = r["created_at"]
        content = r["content"]
        if len(content) > 200:
            content = content[:200] + "..."
        lines.append(f"[{ts}] {p}{d} {content}")
    return "\n".join(lines)
