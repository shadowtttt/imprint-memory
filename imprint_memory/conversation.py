"""
Conversation log — Layer 3 of the memory architecture.
Stores full conversation history from all platforms with FTS5 search.
"""

from .db import _get_db, now_str, LOCAL_TZ, segment_cjk, sanitize_fts_query
from datetime import datetime


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
) -> dict:
    """Write one message to conversation_log.

    external_id is a stable upstream message id used for dedup when available.
    Older clients can omit it and fall back to content/timestamp dedup.
    """
    if not content or not content.strip():
        return {"ok": False, "error": "empty content"}

    ts = created_at or now_str()
    clean_content = content.strip()
    external_id = (external_id or "").strip()
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
               (platform, direction, speaker, content, external_id, session_id, entrypoint, created_at, summary, model)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        db.commit()
        return {"ok": True, "id": cur.lastrowid}
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
