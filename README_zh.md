# imprint-memory

给 Claude Code 用户的本地长期记忆系统。支持中文分词、混合搜索（FTS5 + 向量）、对话同步、被动浮现。

```
Claude Code ── MCP stdio ───────────────────────────────┐
                                                        │
手动记忆 / 日志 / bank/*.md ────────────────────────────┤
                                                        ▼
                                              imprint-memory
                                         SQLite + FTS5 + vectors
                                                        │
claude.ai ── Chrome 扩展 ── POST :8001/api/ingest ─────┤
                                                        ▼
                            日志 → 嵌入 → 分块 → 图谱边 → 搜索
                                                        │
UserPromptSubmit hook ── surfacing_search ── <recall> ──┘
```

## 功能

| 功能 | 说明 |
| --- | --- |
| 记忆 CRUD | 存储、更新、删除、置顶、标签、关联记忆 |
| 混合检索 | FTS5 关键词 + 精确匹配 + 向量相似度 + RRF 融合 + 可选 LLM 重排 |
| 时间感知 | 解析 `昨天`、`上次`、`三周前`、`去年冬天` 等中文时间表达（需安装 jionlp） |
| 查询扩展 | 可选 Cloudflare Workers AI，为查询生成口语化变体 |
| 对话块检索 | 搜索对话摘要，展开最佳块的源消息 |
| 图谱邻居 | 自动浮现关联记忆和相邻对话块 |
| 浏览器对话同步 | 通过 `imprint-chat-sync` Chrome 扩展接收 claude.ai 对话 |
| 被动浮现 | Claude Code `UserPromptSubmit` hook 在相关时自动注入 `<recall>` 块 |
| 中文友好 FTS | 使用 jieba 分词，无 jieba 时回退到字符级别切分 |
| 零依赖降级 | 没有 Ollama/API 嵌入时，仍可用 FTS5 和精确匹配 |

## 快速开始

### 1. 基础安装 — Claude Code 里用记忆

```bash
pip install imprint-memory
claude mcp add -s user imprint-memory -- imprint-memory
```

重启 Claude Code，你会看到 `imprint-memory` 的 MCP 工具。不需要 API key。默认数据存在 `~/.imprint/memory.db`，嵌入尝试本地 Ollama；如果 Ollama 没跑，自动降级为纯关键词搜索。

可选本地嵌入（推荐，显著提升搜索质量）：

```bash
ollama pull bge-m3
ollama serve
```

### 2. 同步 claude.ai 对话

```bash
pip install 'imprint-memory[receiver]'
imprint-memory-receiver
```

Receiver 监听 `127.0.0.1:8001`。然后装浏览器扩展：

```bash
git clone https://github.com/Qizhan7/imprint-chat-sync.git
```

Chrome → `chrome://extensions/` → 开启开发者模式 → 加载已解压的扩展 → 选择克隆的 `imprint-chat-sync` 文件夹。保持 claude.ai 登录状态，用扩展弹窗同步。

### 3. 完整体验 — 被动浮现 hook

安装 hook 脚本：

```bash
mkdir -p ~/.claude/hooks
HOOK_PATH="$(python3 -c '
from importlib.resources import files
print(files("imprint_memory") / "hooks" / "memory-check.sh")
')"
cp "$HOOK_PATH" ~/.claude/hooks/memory-check.sh
chmod +x ~/.claude/hooks/memory-check.sh
```

添加到 `~/.claude/settings.json`：

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

设置中文输出：

```bash
# 在 ~/.imprint/.env 中添加
IMPRINT_LOCALE=zh
IMPRINT_HOOK_LANG=zh
```

API key 等配置见 `.env.example`，复制到 `~/.imprint/.env` 按需填写。

## 配置

所有配置通过环境变量。默认值为本地私有使用设计。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `IMPRINT_DATA_DIR` | `~/.imprint` | 数据库、日志、bank 文件的根目录 |
| `IMPRINT_DB` | `$IMPRINT_DATA_DIR/memory.db` | SQLite 数据库路径 |
| `TZ_OFFSET` | `0` | 本地时区相对 UTC 的偏移（小时） |
| `IMPRINT_USER_NAME` | `User` | 对话摘要中的人类说话人标签 |
| `IMPRINT_AGENT_NAME` | `Assistant` | 对话摘要中的 AI 说话人标签 |
| `IMPRINT_LOCALE` | `en` | 搜索输出标签语言：`en` 或 `zh` |
| `EMBED_PROVIDER` | `ollama` | 嵌入提供者：`ollama`、`openai`、`google` |
| `EMBED_MODEL` | 按提供者默认 | 嵌入模型。默认：`bge-m3`、`text-embedding-3-small`、`gemini-embedding-2` |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 基础 URL |
| `OPENAI_API_KEY` | 未设置 | OpenAI 或兼容 API 的 key |
| `EMBED_API_BASE` | `https://api.openai.com` | OpenAI 兼容嵌入 API 基础 URL |
| `GOOGLE_API_KEY` | 未设置 | Google Gemini API key |
| `GOOGLE_API_KEYS` | 未设置 | 逗号分隔的 Google key，用于轮询嵌入调用 |
| `CF_ACCOUNT_ID` | 未设置 | Cloudflare 账号 ID，用于查询扩展和重排 |
| `CF_API_TOKEN` | 未设置 | Cloudflare API token |
| `IMPRINT_HOOK_LANG` | `en` | Hook 提示语言：`en` 或 `zh` |
| `STOPWORD_THRESHOLD` | `0.15` | 自动停用词的文档频率阈值 |

完整配置列表见英文 README。

## MCP 工具列表

| 工具 | 说明 |
| --- | --- |
| `memory_remember` | 存储记忆（自动分类、去重、嵌入） |
| `memory_search` | 混合搜索记忆、bank 文件、对话、对话块、图谱邻居 |
| `memory_list` | 列出最近活跃记忆，按分类或时间范围过滤 |
| `memory_update` | 按 ID 更新内容、分类、重要度 |
| `memory_delete` | 按 ID 删除记忆 |
| `memory_forget` | 按关键词删除记忆 |
| `memory_daily_log` | 向今天的日志追加带时间戳的条目 |
| `memory_pin` / `memory_unpin` | 置顶核心记忆（豁免时间衰减） |
| `memory_add_tags` | 给记忆添加标签 |
| `memory_add_edge` | 关联两条记忆（带关系类型和上下文） |
| `memory_get_graph` | 查看记忆的标签、边、邻居预览 |
| `memory_find_duplicates` | 语义去重审计（只读） |
| `memory_find_stale` | 过期记忆审计（只读） |
| `memory_decay` | 预览或应用不活跃记忆的重要度衰减 |
| `memory_reindex` | 更换嵌入模型后重建索引 |
| `stopwords_build` | 从文档频率重建自动停用词 |
| `stopwords_show` | 查看当前停用词 |
| `stopwords_add` / `stopwords_remove` | 手动增删停用词 |
| `conversation_search` | 对话日志关键词搜索 |
| `conversation_search_semantic` | 对话向量搜索（先搜块摘要，再搜消息向量） |
| `message_bus_read` / `message_bus_post` | 读写共享消息总线 |
| `experience_append` | 向 experience.md 追加技术笔记 |

## 搜索原理

1. 可选时间解析（`昨天`、`上次`、`三周前`）并可选 Cloudflare 查询扩展
2. 嵌入查询向量（有嵌入提供者时）
3. 各池独立搜索：记忆、bank 块、原始对话、对话摘要块、精确/LIKE 匹配
4. 用 Reciprocal Rank Fusion 融合排名
5. 池级重排：考虑时间衰减、重要度、置顶、文件新鲜度
6. 可选 Cloudflare 语义重排
7. 块命中展开为源消息；记忆和块的图谱邻居按相关性追加
8. 更新 recall 计数器（内部浮现搜索除外）

## 数据布局

```
~/.imprint/
├── memory.db
├── MEMORY.md
└── memory/
    ├── 2026-05-17.md      ← 今日日志
    └── bank/
        └── experience.md  ← 技术经验
```

## 开发

```bash
git clone https://github.com/Qizhan7/imprint-memory.git
cd imprint-memory
pip install -e '.[all]'
pip install pytest
pytest
```

运行 stdio 模式（Claude Code 用）：

```bash
imprint-memory
```

运行 HTTP MCP 模式：

```bash
imprint-memory --http --host 0.0.0.0 --port 8000
```

## 中文搜索说明

imprint-memory 对中文搜索做了专门优化：

- **分词**：安装 jieba 后自动启用，否则回退到字符级切分
- **时间解析**：安装 jionlp 后支持丰富的中文时间表达（`昨天`、`上个月`、`去年冬天`）
- **停用词**：`stopwords_build` 自动从语料统计高频词，支持手动增删
- **标签**：设置 `IMPRINT_LOCALE=zh` 后搜索结果用中文标签显示

安装中文增强依赖：

```bash
pip install 'imprint-memory[chinese]'
```

## 许可证

MIT
