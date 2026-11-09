#!/usr/bin/env python3
"""
Comprehensive tests for reading-dedup-sort.py
RED/GREEN with isolated fictional fixtures
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Get script path
SCRIPT_DIR = Path(__file__).parent
READER_SCRIPT = SCRIPT_DIR / "reading-dedup-sort.py"
SCHEMA_FILE = SCRIPT_DIR.parent / "data-schemas" / "stats-db-schema.sql"
REPO_ROOT = SCRIPT_DIR.parent


def make_db(db_path):
    """Apply the shipped schema file with foreign keys on."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_FILE.read_text())
    conn.commit()
    conn.close()


def run_reader(*args):
    return subprocess.run([sys.executable, str(READER_SCRIPT), *[str(a) for a in args]],
                          capture_output=True)

class TestReaderPrecheck(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_file = self.tmpdir / "state.json"
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_precheck_no_state_with_ids_is_new(self):
        """New IDs with no prior state should be considered new (return 0)"""
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "precheck",
             "--state", str(self.state_file),
             "--key", "x_last_id",
             "--ids", "123", "122", "121"],
            capture_output=True
        )
        # No state = all new
        self.assertEqual(result.returncode, 0, "New IDs should return 0")
    
    def test_precheck_different_id_is_new(self):
        """Different first ID from last_id should be new (return 0)"""
        self.state_file.write_text(json.dumps({"x_last_id": "100"}))
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "precheck",
             "--state", str(self.state_file),
             "--key", "x_last_id",
             "--ids", "123", "122", "121"],
            capture_output=True
        )
        # Different ID = new
        self.assertEqual(result.returncode, 0, "Different ID should return 0 (new)")
    
    def test_precheck_same_id_is_nothing_new(self):
        """Same first ID as last_id should be nothing new (return 2)"""
        self.state_file.write_text(json.dumps({"x_last_id": "123"}))
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "precheck",
             "--state", str(self.state_file),
             "--key", "x_last_id",
             "--ids", "123", "122", "121"],
            capture_output=True
        )
        # Same ID = nothing new
        self.assertEqual(result.returncode, 2, "Same ID should return 2 (nothing new)")
        self.assertIn(b"NOTHING_NEW", result.stderr)

class TestReaderDedup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "stats.db"
        self.input_file = self.tmpdir / "input.json"
        self.output_file = self.tmpdir / "output.json"
        
        # Create DB from the shipped schema (never a hand-written copy)
        make_db(self.db_path)
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_dedup_new_posts_retained(self):
        """New posts should be retained"""
        posts = [
            {"id": "x_1", "platform": "x", "user_id": "alice", "text": "Hello world"},
            {"id": "x_2", "platform": "x", "user_id": "bob", "text": "Different text"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        output_posts = json.loads(self.output_file.read_text())
        self.assertEqual(len(output_posts), 2, "Both new posts should be retained")
    
    def test_dedup_known_same_user_excluded(self):
        """Known text from same user should be excluded"""
        # Seed DB with known post
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        import hashlib
        text_hash = hashlib.sha1(b"hello world").hexdigest()
        cursor.execute(
            "INSERT INTO seen_texts VALUES (?, ?, ?, ?, datetime('now'))",
            (text_hash, "alice", "x_100", "x")
        )
        conn.commit()
        conn.close()
        
        posts = [
            {"id": "x_200", "platform": "x", "user_id": "alice", "text": "Hello world"},
            {"id": "x_300", "platform": "x", "user_id": "bob", "text": "New content"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        output_posts = json.loads(self.output_file.read_text())
        self.assertEqual(len(output_posts), 1, "Known post should be excluded")
        self.assertEqual(output_posts[0]["id"], "x_300")
    
    def test_dedup_intra_batch_duplicates_excluded(self):
        """Duplicate post_id within same batch should be excluded"""
        posts = [
            {"id": "x_1", "platform": "x", "user_id": "alice", "text": "First"},
            {"id": "x_1", "platform": "x", "user_id": "alice", "text": "First"},  # duplicate ID
            {"id": "x_2", "platform": "x", "user_id": "alice", "text": "Second"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        output_posts = json.loads(self.output_file.read_text())
        self.assertEqual(len(output_posts), 2, "Duplicate within batch should be excluded")
        ids = [p["id"] for p in output_posts]
        self.assertEqual(ids.count("x_1"), 1, "ID x_1 should appear only once")
    
    def test_dedup_cross_platform_ids_distinct(self):
        """Same ID from different platforms should be distinct"""
        posts = [
            {"id": "123", "platform": "x", "user_id": "alice", "text": "X post"},
            {"id": "123", "platform": "telegram", "user_id": "alice", "text": "TG post"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        output_posts = json.loads(self.output_file.read_text())
        self.assertEqual(len(output_posts), 2, "Cross-platform IDs should be distinct")
    
    def test_dedup_cross_platform_same_text_same_user_distinct(self):
        """Same text from same user on different platforms should be distinct across runs"""
        # Run 1: Process X post
        posts_x = [
            {"id": "x_100", "platform": "x", "user_id": "alice", "text": "Shared announcement"}
        ]
        self.input_file.write_text(json.dumps(posts_x))
        
        result1 = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result1.returncode, 0)
        output1 = json.loads(self.output_file.read_text())
        self.assertEqual(len(output1), 1, "X post should be kept")
        
        # Run 2: Process Telegram post with same text and user
        posts_tg = [
            {"id": "tg_200", "platform": "telegram", "user_id": "alice", "text": "Shared announcement"}
        ]
        self.input_file.write_text(json.dumps(posts_tg))
        
        result2 = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertEqual(result2.returncode, 0)
        output2 = json.loads(self.output_file.read_text())
        
        # Bug: Telegram post incorrectly filtered as duplicate because query doesn't check platform
        self.assertEqual(len(output2), 1, "Telegram post should be kept (different platform)")
        self.assertEqual(output2[0]["platform"], "telegram")
    
    def test_dedup_atomic_failure_preserves_db(self):
        """Invalid input should not corrupt DB"""
        # Seed DB with known data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        import hashlib
        text_hash = hashlib.sha1(b"existing").hexdigest()
        cursor.execute(
            "INSERT INTO seen_texts VALUES (?, ?, ?, ?, datetime('now'))",
            (text_hash, "alice", "x_1", "x")
        )
        conn.commit()
        before_count = cursor.execute("SELECT COUNT(*) FROM seen_texts").fetchone()[0]
        conn.close()
        
        # Invalid input (not array)
        self.input_file.write_text('{"invalid": "not array"}')
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        self.assertNotEqual(result.returncode, 0, "Should fail on invalid input")
        
        # DB should be unchanged
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        after_count = cursor.execute("SELECT COUNT(*) FROM seen_texts").fetchone()[0]
        conn.close()
        self.assertEqual(before_count, after_count, "DB should be unchanged after failure")
    
    def test_dedup_output_failure_preserves_seen(self):
        """Output write failure must not commit seen_texts (no data loss on retry)"""
        posts = [
            {"id": "x_1", "platform": "x", "user_id": "alice", "text": "Important post"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        # Make output directory read-only to force write failure
        output_dir = self.output_file.parent
        (output_dir / "blocker").mkdir()  # Create subdirectory
        self.output_file = output_dir / "blocker" / "cannot_write_here.json"
        os.chmod(output_dir / "blocker", 0o555)  # Read-only
        
        try:
            result = subprocess.run(
                [sys.executable, str(READER_SCRIPT), "dedup",
                 str(self.input_file), "--db", str(self.db_path),
                 "-o", str(self.output_file)],
                capture_output=True
            )
            
            # Should fail on output write
            self.assertNotEqual(result.returncode, 0, "Should fail when output write fails")
            
            # DB should NOT have post marked as seen (allow retry without data loss)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            count = cursor.execute("SELECT COUNT(*) FROM seen_texts").fetchone()[0]
            conn.close()
            
            self.assertEqual(count, 0, "seen_texts should be empty after output failure (no commit)")
        
        finally:
            os.chmod(output_dir / "blocker", 0o755)  # Restore permissions

class TestReaderSort(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.input_file = self.tmpdir / "input.json"
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_sort_by_score_descending(self):
        """Posts should be sorted by score descending"""
        posts = [
            {"id": "1", "score": 2},
            {"id": "2", "score": 5},
            {"id": "3", "score": 1},
            {"id": "4", "score": 4}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "sort", str(self.input_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        sorted_posts = json.loads(self.input_file.read_text())
        scores = [p["score"] for p in sorted_posts]
        self.assertEqual(scores, [5, 4, 2, 1], "Should be sorted descending")
    
    def test_sort_missing_score_defaults_zero(self):
        """Posts without score should default to 0"""
        posts = [
            {"id": "1", "score": 3},
            {"id": "2"},  # no score
            {"id": "3", "score": 5}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "sort", str(self.input_file)],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        
        sorted_posts = json.loads(self.input_file.read_text())
        self.assertEqual(sorted_posts[0]["id"], "3", "Score 5 first")
        self.assertEqual(sorted_posts[1]["id"], "1", "Score 3 second")
        self.assertEqual(sorted_posts[2]["id"], "2", "No score (0) last")

class TestReaderBoundedInput(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "stats.db"
        self.input_file = self.tmpdir / "input.json"
        self.output_file = self.tmpdir / "output.json"
        
        # Create DB from the shipped schema
        make_db(self.db_path)
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_dedup_rejects_non_dict_post(self):
        """Non-dict posts must be rejected"""
        posts = [
            {"id": "1", "platform": "x", "user_id": "alice", "text": "Valid"},
            "invalid_string_post",  # Not a dict
            {"id": "2", "platform": "x", "user_id": "bob", "text": "Also valid"}
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should reject non-dict post")
        self.assertIn(b"not a dict", result.stderr)
    
    def test_dedup_validates_types(self):
        """Post fields must have correct types"""
        posts = [
            {"id": 123, "platform": "x", "user_id": "alice", "text": "Text"}  # id should be string
        ]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should reject non-string id")
        self.assertIn(b"must be string", result.stderr)
    
    def test_dedup_rejects_too_many_posts(self):
        """Excessive post count must be rejected"""
        # Create a list with 100001 posts (over limit)
        posts = [{"id": str(i), "platform": "x", "user_id": "alice", "text": f"Post {i}"} 
                 for i in range(100001)]
        self.input_file.write_text(json.dumps(posts))
        
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "dedup",
             str(self.input_file), "--db", str(self.db_path),
             "-o", str(self.output_file)],
            capture_output=True
        )
        
        self.assertNotEqual(result.returncode, 0, "Should reject excessive post count")
        self.assertIn(b"Too many posts", result.stderr)

class TestReaderSortContract(unittest.TestCase):
    """A04: sort shares the module-level limits and validation; bad input never changes the file."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.input_file = self.tmpdir / "input.json"

    def tearDown(self):
        os.chmod(self.tmpdir, 0o755)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def assert_rejected_unchanged(self, raw: bytes, message: bytes):
        self.input_file.write_bytes(raw)
        result = run_reader("sort", self.input_file)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(self.input_file.read_bytes(), raw, "input must be byte-for-byte unchanged")

    def test_sort_ties_keep_input_order(self):
        posts = [{"id": "a", "score": 3}, {"id": "b", "score": 5}, {"id": "c", "score": 3},
                 {"id": "d"}, {"id": "e", "score": 3.5}]
        self.input_file.write_text(json.dumps(posts))
        result = run_reader("sort", self.input_file)
        self.assertEqual(result.returncode, 0, result.stderr)
        ids = [p["id"] for p in json.loads(self.input_file.read_text())]
        self.assertEqual(ids, ["b", "e", "a", "c", "d"])

    def test_sort_rejects_non_numeric_score(self):
        self.assert_rejected_unchanged(json.dumps([{"id": "1", "score": "5"}]).encode(), b"not numeric")

    def test_sort_rejects_bool_score(self):
        self.assert_rejected_unchanged(json.dumps([{"id": "1", "score": True}]).encode(), b"not numeric")

    def test_sort_rejects_non_dict_element(self):
        self.assert_rejected_unchanged(json.dumps([{"id": "1"}, 7]).encode(), b"not a dict")

    def test_sort_rejects_non_array(self):
        self.assert_rejected_unchanged(b'{"id": "1"}', b"must be JSON array")

    def test_sort_rejects_too_many_posts(self):
        raw = json.dumps([{"id": str(i)} for i in range(100001)]).encode()
        self.assert_rejected_unchanged(raw, b"Too many posts")

    def test_sort_rejects_oversize_file(self):
        with open(self.input_file, "wb") as f:
            f.truncate(100 * 1024 * 1024 + 1)  # sparse; no real disk use
        result = run_reader("sort", self.input_file)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"too large", result.stderr)
        self.assertEqual(self.input_file.stat().st_size, 100 * 1024 * 1024 + 1)

    def test_sort_missing_input(self):
        result = run_reader("sort", self.tmpdir / "absent.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"not found", result.stderr)

    def test_sort_write_failure_leaves_file_unchanged(self):
        raw = json.dumps([{"id": "1", "score": 1}, {"id": "2", "score": 2}]).encode()
        self.input_file.write_bytes(raw)
        os.chmod(self.tmpdir, 0o555)  # temp file cannot be created
        try:
            result = run_reader("sort", self.input_file)
        finally:
            os.chmod(self.tmpdir, 0o755)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"writing sorted output", result.stderr)
        self.assertEqual(self.input_file.read_bytes(), raw)
        self.assertEqual([p.name for p in self.tmpdir.iterdir()], ["input.json"], "no temp leftovers")


class TestReaderDedupState(unittest.TestCase):
    """A05: one schema, platform-separated state, nothing marked seen before the digest."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "stats.db"
        self.batch = self.tmpdir / "batch.json"
        self.out = self.tmpdir / "out.json"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def dedup(self, posts):
        self.batch.write_text(json.dumps(posts))
        result = run_reader("dedup", self.batch, "--db", self.db_path, "-o", self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(self.out.read_text())

    def mark_seen(self, path=None):
        result = run_reader("mark-seen", path or self.out, "--db", self.db_path)
        self.assertEqual(result.returncode, 0, result.stderr)

    def seen_pk(self):
        conn = sqlite3.connect(self.db_path)
        cols = conn.execute("PRAGMA table_info(seen_texts)").fetchall()
        conn.close()
        return [c[1] for c in sorted((c for c in cols if c[5] > 0), key=lambda c: c[5])]

    def test_fresh_db_gets_shipped_schema(self):
        """Old helper created seen_texts with its own DDL keyed (text_hash, user_id)."""
        self.dedup([{"id": "1", "platform": "x", "user_id": "u1", "text": "hello"}])
        self.assertEqual(self.seen_pk(), ["text_hash", "user_id", "platform"])

    def test_x_then_telegram_then_telegram_repeat(self):
        """Same author and text: X kept, Telegram kept, Telegram repeat dropped."""
        x = [{"id": "x1", "platform": "x", "user_id": "u1", "text": "Shared announcement"}]
        tg = [{"id": "t1", "platform": "telegram", "user_id": "u1", "text": "Shared announcement"}]
        self.assertEqual(len(self.dedup(x)), 1); self.mark_seen()
        self.assertEqual(len(self.dedup(tg)), 1); self.mark_seen()
        tg_repeat = [{"id": "t2", "platform": "telegram", "user_id": "u1", "text": "Shared announcement"}]
        self.assertEqual(self.dedup(tg_repeat), [], "Telegram repeat must not pass again")
        conn = sqlite3.connect(self.db_path)
        platforms = sorted(r[0] for r in conn.execute("SELECT platform FROM seen_texts"))
        conn.close()
        self.assertEqual(platforms, ["telegram", "x"])

    def test_link_only_posts_with_different_urls_not_collapsed(self):
        """Old code hashed '' for link-only posts, so two different links became one."""
        posts = [{"id": "1", "platform": "x", "user_id": "u1", "text": "https://example.com/a"},
                 {"id": "2", "platform": "x", "user_id": "u1", "text": "https://example.com/b"}]
        self.assertEqual([p["id"] for p in self.dedup(posts)], ["1", "2"])

    def test_link_only_same_url_collapsed(self):
        posts = [{"id": "1", "platform": "x", "user_id": "u1", "text": "https://Example.com/a/?utm_source=z"},
                 {"id": "2", "platform": "x", "user_id": "u1", "text": "https://example.com/a"}]
        self.assertEqual([p["id"] for p in self.dedup(posts)], ["1"])

    def test_empty_text_posts_kept_by_id(self):
        """Old code silently dropped posts without text."""
        posts = [{"id": "1", "platform": "telegram", "user_id": "c1", "text": ""},
                 {"id": "2", "platform": "telegram", "user_id": "c1"}]
        self.assertEqual([p["id"] for p in self.dedup(posts)], ["1", "2"])

    def test_dedup_does_not_mark_seen(self):
        """A failure after dedup (scoring, digest) must not lose posts: rerun returns them again.
        Old code marked posts seen inside dedup, so the rerun returned nothing."""
        posts = [{"id": "1", "platform": "x", "user_id": "u1", "text": "Important post"}]
        self.assertEqual(len(self.dedup(posts)), 1)
        self.assertEqual(len(self.dedup(posts)), 1, "not delivered yet -> still new")
        self.mark_seen()
        self.assertEqual(self.dedup(posts), [], "delivered -> dropped on rerun")

    def test_mark_seen_idempotent(self):
        posts = [{"id": "1", "platform": "x", "user_id": "u1", "text": "a"},
                 {"id": "2", "platform": "telegram", "user_id": "u1", "text": "a"}]
        self.dedup(posts)
        self.mark_seen(); self.mark_seen()
        conn = sqlite3.connect(self.db_path)
        n = conn.execute("SELECT COUNT(*) FROM seen_texts").fetchone()[0]
        conn.close()
        self.assertEqual(n, 2)

    def test_rerun_same_post_id_with_edited_text_dropped(self):
        self.dedup([{"id": "1", "platform": "x", "user_id": "u1", "text": "draft"}])
        self.mark_seen()
        self.assertEqual(self.dedup([{"id": "1", "platform": "x", "user_id": "u1", "text": "edited"}]), [])

    def test_missing_user_id_rejected(self):
        """Old code dropped such posts silently and exited 0."""
        self.batch.write_text(json.dumps([{"id": "1", "platform": "x", "text": "t"}]))
        result = run_reader("dedup", self.batch, "--db", self.db_path, "-o", self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"user_id", result.stderr)
        self.assertFalse(self.out.exists())

    def test_unknown_platform_rejected(self):
        """Old code defaulted a missing platform to 'unknown'."""
        self.batch.write_text(json.dumps([{"id": "1", "user_id": "u1", "text": "t"}]))
        result = run_reader("dedup", self.batch, "--db", self.db_path, "-o", self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"platform", result.stderr)

    def test_legacy_source_alias_normalized(self):
        """Legacy `source` is converted to canonical `platform` in the output."""
        out = self.dedup([{"id": "1", "source": "Telegram", "user_id": "c1", "text": "t"}])
        self.assertEqual(out[0]["platform"], "telegram")
        self.assertNotIn("source", out[0])

    def test_conflicting_platform_and_source_rejected(self):
        self.batch.write_text(json.dumps([{"id": "1", "platform": "x", "source": "telegram",
                                           "user_id": "u1", "text": "t"}]))
        result = run_reader("dedup", self.batch, "--db", self.db_path, "-o", self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"conflicting", result.stderr)

    def test_legacy_schema_refused_until_migrated(self):
        """A DB keyed the old way is refused (old code used it and lost state); migrate fixes it."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE seen_texts (text_hash TEXT NOT NULL, user_id TEXT NOT NULL, "
                     "post_id TEXT NOT NULL, platform TEXT NOT NULL, first_seen TEXT NOT NULL, "
                     "PRIMARY KEY (text_hash, user_id))")
        conn.execute("INSERT INTO seen_texts VALUES ('h1', 'u1', 'x9', 'x', '2026-01-01')")
        conn.commit(); conn.close()
        self.batch.write_text(json.dumps([{"id": "1", "platform": "x", "user_id": "u1", "text": "t"}]))
        result = run_reader("dedup", self.batch, "--db", self.db_path, "-o", self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"migrate", result.stderr)
        self.assertFalse(self.out.exists())
        result = run_reader("migrate", "--db", self.db_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.seen_pk(), ["text_hash", "user_id", "platform"])
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT post_id FROM seen_texts").fetchall(), [("x9",)])
        conn.close()
        self.assertEqual(run_reader("migrate", "--db", self.db_path).returncode, 0, "idempotent")
        # after migration, platforms keep separate state
        x = [{"id": "x1", "platform": "x", "user_id": "u2", "text": "same"}]
        tg = [{"id": "t1", "platform": "telegram", "user_id": "u2", "text": "same"}]
        self.assertEqual(len(self.dedup(x)), 1); self.mark_seen()
        self.assertEqual(len(self.dedup(tg)), 1); self.mark_seen()
        self.assertEqual(self.dedup([{"id": "t2", "platform": "telegram", "user_id": "u2", "text": "same"}]), [])


class TestStatsContract(unittest.TestCase):
    """A06: shipped SQL schema + record-stats helper + report queries, X and Telegram."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "stats.db"
        make_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def cycle_file(self, name, data):
        path = self.tmpdir / name
        path.write_text(json.dumps(data))
        return path

    def x_cycle(self):
        return {"reader": "x", "started_at": "2026-11-01T06:00:00+00:00",
                "completed_at": "2026-11-01T06:20:00+00:00", "status": "completed",
                "posts_read": 5,
                "posts": [
                    {"platform": "x", "post_id": "x1", "channel": "author_a", "text": "tool post",
                     "score": 4, "score_teaser": 3, "fulltext": "full", "orig_id": "x1"},
                    {"platform": "x", "post_id": "x2", "channel": "author_b", "text": "meh", "score": 2},
                ]}

    def tg_cycle(self):
        return {"reader": "telegram", "started_at": "2026-11-01T07:00:00Z", "status": "completed",
                "posts": [
                    {"source": "telegram", "id": "t1", "channel": "chan_a", "text": "guide", "score": 5},
                    {"platform": "telegram", "post_id": "t2", "channel": "chan_b", "text": "", "score": 1},
                ]}

    def query(self, sql):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(sql).fetchall()
        conn.close()
        return rows

    def record(self, path):
        return run_reader("record-stats", path, "--db", self.db_path)

    def test_schema_has_no_source_column_and_fk_clean(self):
        conn = sqlite3.connect(self.db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({t})")]
            self.assertNotIn("source", cols, t)
        for t in ("posts", "registry", "seen_texts"):
            self.assertIn("platform", [c[1] for c in conn.execute(f"PRAGMA table_info({t})")], t)
        conn.close()

    def test_record_x_and_telegram_then_report(self):
        """Old code had no helper: prompts wrote free-form SQL with `source`."""
        for name, data in (("x.json", self.x_cycle()), ("tg.json", self.tg_cycle())):
            result = self.record(self.cycle_file(name, data))
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.query("SELECT reader, posts_read, posts_selected FROM cycles ORDER BY reader"),
                         [("telegram", 2, 1), ("x", 5, 1)])
        self.assertEqual(self.query("SELECT platform, post_id, registry_key FROM posts ORDER BY platform, post_id"),
                         [("telegram", "t1", "telegram:t1"), ("telegram", "t2", None),
                          ("x", "x1", "x:x1"), ("x", "x2", None)])
        self.assertEqual(self.query("SELECT registry_key, expires_at FROM registry ORDER BY registry_key"),
                         [("telegram:t1", "2026-11-15T07:00:00+00:00"), ("x:x1", "2026-11-15T06:00:00+00:00")])
        self.assertEqual(self.query("PRAGMA foreign_key_check"), [])
        result = run_reader("report", "--db", self.db_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["cycles"]["x"], {"cycles": 1, "completed": 1, "failed": 0,
                                                 "posts_read": 5, "posts_selected": 1})
        self.assertEqual(report["posts"]["telegram"], {"posts": 2, "selected": 1, "avg_score": 3.0})
        self.assertEqual(report["registry"], {"telegram": 1, "x": 1})

    def test_record_rerun_is_idempotent(self):
        path = self.cycle_file("x.json", self.x_cycle())
        self.assertEqual(self.record(path).returncode, 0)
        before = [self.query(f"SELECT * FROM {t} ORDER BY 1") for t in ("cycles", "posts", "registry")]
        self.assertEqual(self.record(path).returncode, 0)
        after = [self.query(f"SELECT * FROM {t} ORDER BY 1") for t in ("cycles", "posts", "registry")]
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[2], after[2])
        self.assertEqual([r[:10] for r in before[1]], [r[:10] for r in after[1]])

    def test_invalid_cycle_writes_nothing(self):
        data = self.x_cycle()
        data["posts"][1]["score"] = 7
        result = self.record(self.cycle_file("bad.json", data))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"score must be integer 1-5", result.stderr)
        for t in ("cycles", "posts", "registry"):
            self.assertEqual(self.query(f"SELECT COUNT(*) FROM {t}"), [(0,)], t)

    def test_platform_must_match_reader(self):
        data = self.x_cycle()
        data["posts"][0]["platform"] = "telegram"
        result = self.record(self.cycle_file("bad.json", data))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"does not match reader", result.stderr)

    def test_migrate_legacy_posts_source_column(self):
        legacy = self.tmpdir / "legacy.db"
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE posts (source TEXT NOT NULL, post_id TEXT NOT NULL, channel TEXT, "
                     "text TEXT NOT NULL, score INTEGER, score_teaser INTEGER, fulltext TEXT, "
                     "registry_key TEXT, orig_id TEXT, cycle_no INTEGER, created_at TEXT NOT NULL, "
                     "PRIMARY KEY (source, post_id))")
        conn.execute("INSERT INTO posts (source, post_id, text, created_at) VALUES ('x', 'x1', 't', '2026-01-01')")
        conn.commit(); conn.close()
        result = run_reader("record-stats", self.cycle_file("x.json", self.x_cycle()), "--db", legacy)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"legacy column 'source'", result.stderr)
        self.assertEqual(run_reader("migrate", "--db", legacy).returncode, 0)
        conn = sqlite3.connect(legacy)
        self.assertEqual(conn.execute("SELECT platform, post_id FROM posts").fetchall(), [("x", "x1")])
        conn.close()
        result = run_reader("record-stats", self.tmpdir / "x.json", "--db", legacy)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_consumers_use_canonical_platform(self):
        """Prompts and process docs must not tell bots to write `source` or hand-written SQL."""
        docs = list((REPO_ROOT / "bots").glob("*/prompt.md")) + \
            list((REPO_ROOT / "company-structure").rglob("*.md"))
        offenders = []
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            if re.search(r"posts\s*\(\s*source\b", text) or re.search(r"\bsource\s*=\s*'(x|telegram)'", text):
                offenders.append(str(doc.relative_to(REPO_ROOT)))
            if "stats.db" in text and doc.name == "prompt.md" and "record-stats" not in text:
                offenders.append(str(doc.relative_to(REPO_ROOT)) + " (stats.db without record-stats)")
        self.assertEqual(offenders, [])
        schema = SCHEMA_FILE.read_text()
        self.assertIn("platform", schema)
        self.assertNotRegex(schema, r"(?m)^\s*source\s+TEXT")


class TestReaderCLI(unittest.TestCase):
    def test_help_works(self):
        """CLI help should work"""
        result = subprocess.run(
            [sys.executable, str(READER_SCRIPT), "--help"],
            capture_output=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Reading dedup/sort", result.stdout)

if __name__ == "__main__":
    print(f"Testing: {READER_SCRIPT}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    # Run tests with verbose output
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stderr)
    result = runner.run(suite)
    
    # Exit with proper code
    sys.exit(0 if result.wasSuccessful() else 1)
