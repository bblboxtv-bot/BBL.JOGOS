import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
import bblia_session_sqlite as store

class DurableSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "sessions.sqlite3")
        store.initialize(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_survives_reopen(self):
        sid = store.create(self.path, "phone", "phone:+5521999999999", now=100)
        self.assertEqual(store.load(self.path, sid, now=101)["subject"], "phone:+5521999999999")
        store.initialize(self.path)
        self.assertEqual(store.load(self.path, sid, now=102)["provider"], "phone")

    def test_logout_persists(self):
        sid = store.create(self.path, "facebook", "facebook:123", now=100)
        self.assertTrue(store.revoke(self.path, sid))
        store.initialize(self.path)
        self.assertIsNone(store.load(self.path, sid, now=101))
        self.assertFalse(store.revoke(self.path, sid))

    def test_expired_session(self):
        sid = store.create(self.path, "google", "google:123", now=100)
        self.assertIsNone(store.load(self.path, sid, now=100+store.TTL))

    def test_token_not_saved_plaintext(self):
        sid = store.create(self.path, "google", "google:123", now=100)
        with sqlite3.connect(self.path) as db:
            stored = db.execute("SELECT sid_hash FROM bblia_sessions").fetchone()[0]
        self.assertNotEqual(sid, stored)
        self.assertEqual(len(stored), 64)

    def test_rejects_invalid_provider_and_subject(self):
        with self.assertRaises(store.DurableSessionError):
            store.create(self.path, "email", "email:test", now=100)
        with self.assertRaises(store.DurableSessionError):
            store.create(self.path, "phone", "google:123", now=100)

    def test_unknown_session(self):
        self.assertIsNone(store.load(self.path, "invalid"))
        self.assertFalse(store.revoke(self.path, "invalid"))

if __name__ == "__main__":
    unittest.main()
