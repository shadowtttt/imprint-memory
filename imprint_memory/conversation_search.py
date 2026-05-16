"""
Semantic search for conversation_log using Gemini Embedding 2 vectors.
Supports Parent-Child retrieval: hit a single message, return surrounding context.
"""

import math
import re
import struct

from .db import _get_db
from .memory_manager import _embed


THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
CONTEXT_WINDOW = 5  # messages before/after the hit


def _ensure_table(db):
    db.execute(
        """CREATE TABLE IF NOT EXISTS conversation_vectors (
            msg_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            model TEXT DEFAULT 'gemini-embedding-2'
        )"""
    )
    db.commit()


def _embed_query(text: str) -> list[float] | None:
    """Embed query using Gemini Embedding 2 (same model as memory_vectors)."""
    try:
        return _embed(text[:2000])
    except Exception:
        return None


def _blob_to_vec(blob: bytes) -> list[float]:
    size = len(blob) // 4
    return list(struct.unpack(f"{size}f", blob))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _strip_thinking(content: str, direction: str) -> str:
    if direction == "out":
        return THINK_RE.sub("", content).strip()
    return content


def _fetch_context(db, msg_id: int, session_id: str) -> list[dict]:
    """Fetch surrounding messages from the same session."""
    rows = db.execute(
        """SELECT id, platform, direction, speaker, content, session_id, created_at
           FROM conversation_log
           WHERE session_id = ? AND id BETWEEN ? AND ?
           ORDER BY id""",
        (session_id, msg_id - 500, msg_id + 500),
    ).fetchall()

    messages = [dict(r) for r in rows]
    hit_idx = next((i for i, m in enumerate(messages) if m["id"] == msg_id), None)
    if hit_idx is None:
        return []

    start = max(0, hit_idx - CONTEXT_WINDOW)
    end = min(len(messages), hit_idx + CONTEXT_WINDOW + 1)
    context = messages[start:end]

    for msg in context:
        msg["content"] = _strip_thinking(msg["content"], msg["direction"])
        msg["is_hit"] = msg["id"] == msg_id

    return context


def search_conversations_semantic(query: str, limit: int = 10, with_context: bool = False) -> list[dict]:
    """
    Search conversation_log by vector similarity.

    If with_context=False (default): returns flat list of matching messages.
    If with_context=True: returns list of conversation snippets, each with
      {"hit": matched_msg, "context": [surrounding messages], "similarity": score}
    """
    query = (query or "").strip()
    if not query:
        return []

    limit = max(1, min(int(limit or 10), 50))
    query_vec = _embed_query(query)
    if not query_vec:
        return []

    db = _get_db()
    try:
        _ensure_table(db)
        rows = db.execute(
            """SELECT c.id, c.platform, c.direction, c.speaker, c.content,
                      c.session_id, c.entrypoint, c.created_at, v.embedding
               FROM conversation_vectors v
               JOIN conversation_log c ON c.id = v.msg_id"""
        ).fetchall()

        scored = []
        for row in rows:
            sim = _cosine_similarity(query_vec, _blob_to_vec(row["embedding"]))
            if sim <= 0:
                continue
            item = dict(row)
            item.pop("embedding", None)
            item["similarity"] = sim
            scored.append(item)

        scored.sort(key=lambda item: item["similarity"], reverse=True)

        if not with_context:
            for item in scored[:limit]:
                item["content"] = _strip_thinking(item["content"], item["direction"])
            return scored[:limit]

        # Parent-Child: group by session, deduplicate, fetch context
        seen_sessions = set()
        snippets = []
        for item in scored:
            if len(snippets) >= limit:
                break
            session_id = item.get("session_id", "")
            if session_id in seen_sessions:
                continue
            seen_sessions.add(session_id)

            hit = dict(item)
            hit["content"] = _strip_thinking(hit["content"], hit["direction"])
            context = _fetch_context(db, item["id"], session_id)

            linked = _fetch_linked_topics(db, item["id"])

            snippets.append({
                "hit": hit,
                "context": context,
                "similarity": item["similarity"],
                "session_id": session_id,
                "linked_topics": linked,
            })

        return snippets
    finally:
        db.close()


def _fetch_linked_topics(db, msg_id):
    """Find topic-shift linked messages via conversation_edges."""
    try:
        rows = db.execute(
            """SELECT msg_before, msg_after, similarity FROM conversation_edges
               WHERE (msg_before = ? OR msg_after = ?) AND status != 'dormant'
               ORDER BY strength DESC LIMIT 3""",
            (msg_id, msg_id),
        ).fetchall()
    except Exception:
        return []

    linked = []
    for row in rows:
        other_id = row["msg_after"] if row["msg_before"] == msg_id else row["msg_before"]
        other = db.execute(
            "SELECT id, speaker, content, direction, created_at FROM conversation_log WHERE id=?",
            (other_id,),
        ).fetchone()
        if not other:
            continue
        content = _strip_thinking(other["content"], other["direction"])
        linked.append({
            "id": other["id"],
            "speaker": other["speaker"],
            "content": content[:200],
            "created_at": other["created_at"],
            "shift_similarity": row["similarity"],
        })

        # Strengthen edge
        try:
            db.execute(
                """UPDATE conversation_edges
                   SET surfaced_count = surfaced_count + 1,
                       strength = min(strength + 0.1, 5.0),
                       last_surfaced_at = datetime('now'),
                       status = CASE WHEN status='dormant' THEN 'active' ELSE status END
                   WHERE msg_before=? AND msg_after=?""",
                (row["msg_before"], row["msg_after"]),
            )
        except Exception:
            pass

    if linked:
        try:
            db.commit()
        except Exception:
            pass
    return linked
