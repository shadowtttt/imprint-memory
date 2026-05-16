import asyncio
import json
import os
import sys
import tempfile
import unittest


class ConversationExternalIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_env = {
            "IMPRINT_DATA_DIR": os.environ.get("IMPRINT_DATA_DIR"),
            "IMPRINT_DB": os.environ.get("IMPRINT_DB"),
        }
        os.environ["IMPRINT_DATA_DIR"] = self.tmp.name
        os.environ["IMPRINT_DB"] = os.path.join(self.tmp.name, "memory.db")
        self._purge_imprint_modules()

    def tearDown(self):
        self._purge_imprint_modules()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _purge_imprint_modules(self):
        for name in list(sys.modules):
            if name == "imprint_memory" or name.startswith("imprint_memory."):
                del sys.modules[name]

    def _modules(self):
        from imprint_memory import conversation, db

        return conversation, db

    def test_external_id_dedupes_authoritatively(self):
        conversation, db_module = self._modules()

        first = conversation.log_message(
            platform="claude.ai",
            direction="in",
            content="hello from the first sync",
            session_id="conv-a",
            created_at="2026-05-17 10:00:00",
            external_id="msg-1",
        )
        second = conversation.log_message(
            platform="claude.ai",
            direction="in",
            content="changed text should not create a new row",
            session_id="conv-a",
            created_at="2026-05-17 10:01:00",
            external_id="msg-1",
        )

        self.assertTrue(first["ok"])
        self.assertEqual(second.get("skipped"), "duplicate")
        self.assertEqual(second["id"], first["id"])

        db = db_module._get_db()
        try:
            rows = db.execute(
                "SELECT external_id, content FROM conversation_log"
            ).fetchall()
        finally:
            db.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "msg-1")
        self.assertEqual(rows[0]["content"], "hello from the first sync")

    def test_distinct_external_ids_allow_same_timestamp_and_content(self):
        conversation, db_module = self._modules()

        for external_id in ("msg-1", "msg-2"):
            result = conversation.log_message(
                platform="claude.ai",
                direction="in",
                content="same content",
                session_id="conv-a",
                created_at="2026-05-17 10:00:00",
                external_id=external_id,
            )
            self.assertTrue(result["ok"])
            self.assertNotIn("skipped", result)

        db = db_module._get_db()
        try:
            count = db.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        finally:
            db.close()

        self.assertEqual(count, 2)

    def test_legacy_clients_still_dedupe_by_exact_entry(self):
        conversation, db_module = self._modules()

        first = conversation.log_message(
            platform="claude.ai",
            direction="out",
            content="legacy message",
            session_id="conv-a",
            created_at="2026-05-17 10:00:00",
        )
        second = conversation.log_message(
            platform="claude.ai",
            direction="out",
            content="legacy message",
            session_id="conv-a",
            created_at="2026-05-17 10:00:00",
        )

        self.assertTrue(first["ok"])
        self.assertEqual(second.get("skipped"), "duplicate")

        db = db_module._get_db()
        try:
            count = db.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        finally:
            db.close()

        self.assertEqual(count, 1)

    def test_receiver_db_initializer_creates_core_schema(self):
        try:
            import starlette  # noqa: F401
        except ImportError:
            self.skipTest("starlette is not installed")

        self._purge_imprint_modules()
        from imprint_memory import chat_sync_receiver

        db = chat_sync_receiver._get_db()
        try:
            count = db.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        finally:
            db.close()

        self.assertEqual(count, 0)

    def test_receiver_persists_message_uuid_as_external_id(self):
        try:
            import starlette  # noqa: F401
        except ImportError:
            self.skipTest("starlette is not installed")

        self._purge_imprint_modules()
        from imprint_memory import chat_sync_receiver, db as db_module

        class FakeRequest:
            async def json(self):
                return {
                    "conversation_id": "conv-a",
                    "messages": [
                        {
                            "direction": "in",
                            "content": "message from browser sync",
                            "created_at": "2026-05-17 10:00:00",
                            "uuid": "claude-msg-1",
                        }
                    ],
                }

        response = asyncio.run(chat_sync_receiver.ingest(FakeRequest()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["ingested"], 1)

        db = db_module._get_db()
        try:
            row = db.execute(
                "SELECT external_id, session_id FROM conversation_log"
            ).fetchone()
        finally:
            db.close()

        self.assertEqual(row["external_id"], "claude-msg-1")
        self.assertEqual(row["session_id"], "conv-a")


if __name__ == "__main__":
    unittest.main()
