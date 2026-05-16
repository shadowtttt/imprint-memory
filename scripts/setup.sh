#!/bin/bash
# imprint-memory one-line setup
# curl -fsSL https://raw.githubusercontent.com/Qizhan7/imprint-memory/main/scripts/setup.sh | bash

set -e

echo "=== imprint-memory setup ==="
echo ""

# 1. Install imprint-memory
echo "[1/3] Installing imprint-memory..."
if command -v pip3 &>/dev/null; then
    PIP=pip3
elif command -v pip &>/dev/null; then
    PIP=pip
else
    echo "Error: pip not found. Install Python 3.10+ first."
    exit 1
fi

$PIP install imprint-memory --quiet 2>/dev/null || $PIP install imprint-memory --quiet --break-system-packages
echo "  Done."

# 2. Install Ollama + bge-m3
echo "[2/3] Setting up Ollama + bge-m3 embeddings..."
if command -v ollama &>/dev/null; then
    echo "  Ollama already installed."
else
    echo "  Installing Ollama..."
    case "$(uname -s)" in
        Darwin)
            if command -v brew &>/dev/null; then
                brew install ollama --quiet
            else
                curl -fsSL https://ollama.com/install.sh | sh
            fi
            ;;
        Linux)
            curl -fsSL https://ollama.com/install.sh | sh
            ;;
        *)
            echo "  Unsupported OS. Install Ollama manually: https://ollama.com/download"
            exit 1
            ;;
    esac
fi

# Start Ollama if not running
if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
    echo "  Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 3
fi

# Pull bge-m3
if ollama list 2>/dev/null | grep -q "bge-m3"; then
    echo "  bge-m3 already downloaded."
else
    echo "  Downloading bge-m3 (this may take a minute)..."
    ollama pull bge-m3
fi
echo "  Done."

# 3. Register MCP in Claude Code
echo "[3/3] Registering MCP server in Claude Code..."
if command -v claude &>/dev/null; then
    claude mcp add -s user imprint-memory -- imprint-memory 2>/dev/null && echo "  Done." || echo "  Claude Code not configured (add manually later)."
else
    echo "  Claude Code CLI not found. Add manually:"
    echo "    claude mcp add -s user imprint-memory -- imprint-memory"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Restart Claude Code and you'll have persistent memory."
echo ""
echo "Optional next steps:"
echo "  - Chinese text search:  $PIP install 'imprint-memory[chinese]'"
echo "  - Sync claude.ai chats: $PIP install 'imprint-memory[receiver]'"
echo "  - Full docs: https://github.com/Qizhan7/imprint-memory"
