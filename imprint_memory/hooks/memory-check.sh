#!/bin/bash
# UserPromptSubmit hook for imprint-memory
#
# On every user message:
#   1) Scan for recall-worthy signals (time refs, emotion, "remember", etc.)
#   2) If found, call surfacing_search() to inject a <recall> block with
#      the most relevant chunks and a graph neighbor.
#   3) Always append a <memory-check> reminder so the model knows to use
#      memory_search when the turn touches past events, people, or promises.
#
# Configuration via env vars:
#   IMPRINT_PYTHON     Python interpreter (default: python3)
#   IMPRINT_DATA_DIR   Where memory.db lives (default: ~/.imprint)
#   IMPRINT_HOOK_LANG  "en" or "zh" prompt (default: en)
#
# Install:
#   cp hooks/memory-check.sh ~/.claude/hooks/memory-check.sh
#   chmod +x ~/.claude/hooks/memory-check.sh
#   Add to ~/.claude/settings.json:
#     "hooks": {
#       "UserPromptSubmit": [
#         { "hooks": [{ "type": "command", "command": "bash $HOME/.claude/hooks/memory-check.sh" }] }
#       ]
#     }

PYTHON_BIN="${IMPRINT_PYTHON:-}"
HOOK_LANG="${IMPRINT_HOOK_LANG:-en}"

_imprint_python_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

if [ -n "$PYTHON_BIN" ] && ! _imprint_python_ok "$PYTHON_BIN"; then
    PYTHON_BIN=""
fi
if [ -z "$PYTHON_BIN" ]; then
    for candidate in python3.12 python3.11 python3.10 python3 python; do
        if _imprint_python_ok "$candidate"; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

# Load API keys / config from an env file if one exists. By default we look
# at $IMPRINT_ENV_FILE (if set) and ~/.imprint/.env. Each line is KEY=VALUE.
# Pre-existing environment variables are NOT overridden.
ENV_FILES=()
[ -n "${IMPRINT_ENV_FILE:-}" ] && ENV_FILES+=("$IMPRINT_ENV_FILE")
ENV_FILES+=("${HOME}/.imprint/.env")
for ef in "${ENV_FILES[@]}"; do
    [ -n "$ef" ] && [ -f "$ef" ] || continue
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue;; esac
        key="${line%%=*}"
        val="${line#*=}"
        key="${key// /}"
        # Ignore malformed keys so a comments-heavy .env cannot break the hook.
        if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && [ -z "${!key:-}" ]; then
            export "$key=$val"
        fi
    done < "$ef"
done

# Read the full JSON payload from Claude Code (stdin) once.
INPUT=$(cat)

if [ -z "$PYTHON_BIN" ]; then
    USER_MSG=""
    SHOULD_SURFACE=""
else

# Extract the user's latest message text.
USER_MSG=$(printf '%s' "$INPUT" | "$PYTHON_BIN" -c '
import sys, json
try:
    d = json.load(sys.stdin)
    content = (
        d.get("user_prompt", "")
        or d.get("prompt", "")
        or d.get("message", "")
        or d.get("content", "")
    )
    if isinstance(content, list):
        content = " ".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    elif isinstance(content, dict):
        content = content.get("text", "") or content.get("content", "")
    print(str(content)[:200])
except Exception:
    print("")
' 2>/dev/null)

# Cheap signal check: only call the search if the message references the past,
# carries emotion, or asks a recall-style question. Skips embedding cost on
# every-turn small talk / code-only requests.
SHOULD_SURFACE=$(printf '%s' "$USER_MSG" | "$PYTHON_BIN" -c '
import sys, re
msg = sys.stdin.read().strip()
signals = [
    # English
    r"\bremember\b|\blast\s+time\b|\bback\s+then\b|\bbefore\b|\bused\s+to\b|\bago\b",
    r"\byesterday\b|\blast\s+(week|month|year|night)\b|\bthe\s+other\s+day\b",
    r"\bI\s+(feel|felt|miss|love|hate|fear|want|wanted)\b",
    r"\b(sad|happy|angry|tired|afraid|anxious|lonely|excited|worried)\b",
    r"\byou\s+(said|told|promised|mentioned)\b|\bwe\s+(talked|discussed|agreed)\b",
    r"\bdo\s+you\s+remember\b|\brecall\b",
    # Chinese (kept here so CJK users do not need a custom build)
    r"记得|之前|上次|那时|那次|以前|第一次|最近|当时|那天|那年|那会",
    r"想起来|想起|突然想到|说起|提到|有一次",
    r"累|难过|开心|想你|害怕|迷茫|烦|伤心|生气|焦虑|崩溃|委屈",
    r"你还记|我们的|那个时候|你说过|我说过|我们说|咱们",
    r"今天.{0,4}了|刚才|刚刚|昨天|前天|[\d一二两三四五六七八九十几]+[天周月年]前",
]
if any(re.search(p, msg, re.IGNORECASE) for p in signals):
    print("yes")
' 2>/dev/null)
fi

if [ "$SHOULD_SURFACE" = "yes" ] && [ -n "$USER_MSG" ]; then
    SURFACING=$(printf '%s' "$USER_MSG" | "$PYTHON_BIN" -c '
import sys
try:
    from imprint_memory.memory_manager import surfacing_search
except Exception:
    sys.exit(0)
msg = sys.stdin.read().strip()[:200]
try:
    r = surfacing_search(msg)
    if r:
        print(r)
except Exception:
    pass
' 2>/dev/null)
    if [ -n "$SURFACING" ]; then
        if [ "$HOOK_LANG" = "zh" ]; then
            echo "<recall>"
            echo "这句话让我想到了这些。自动匹配的，不一定都准，看着用就好，别刻意引用。"
            echo "$SURFACING"
            echo "</recall>"
        else
            echo "<recall>"
            echo "Auto-surfaced from memory based on this message — use loosely, may not be perfectly relevant."
            echo "$SURFACING"
            echo "</recall>"
        fi
        echo ""
    fi
fi

if [ "$HOOK_LANG" = "zh" ]; then
    cat <<'EOF'
<memory-check>
这轮是否涉及：过去的事 / 人 / 承诺 / 偏好 / 事件，或任何上下文里没有的信息？
涉及 → memory_search（会自动带 edge 关联的邻居记忆）
纯当下的技术任务或闲聊 → 跳过
在思考里判断即可，不用回复这条。
</memory-check>
EOF
else
    cat <<'EOF'
<memory-check>
Does this turn touch past events, people, promises, preferences, or anything not in the current context?
If yes → call memory_search (edge-linked neighbors come along automatically).
If it's just a here-and-now technical task or small talk → skip.
Judge silently — no need to respond to this reminder.
</memory-check>
EOF
fi
