"""Minimal programmatic memory search example."""

import os
import tempfile

os.environ.setdefault("IMPRINT_DATA_DIR", tempfile.mkdtemp(prefix="imprint-demo-"))

from imprint_memory.memory_manager import remember, unified_search_text

remember("I prefer concise PR summaries with risks called out first.", category="facts")

print(unified_search_text("How should PR summaries be written?", limit=3))
