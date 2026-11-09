#!/usr/bin/env python3
"""
Reading dedup and sort utility for X/Telegram readers.
Safe generic implementation - no external API calls, file-only operations.

Commands (run in this order by a reader cycle):
  precheck     compare newest IDs with state.json            (read-only)
  dedup        drop posts already seen / repeated in batch   (read-only on stats.db)
  sort         order posts by score, highest first           (rewrites file atomically)
  mark-seen    record delivered posts in seen_texts          (run only AFTER the digest)
  record-stats write cycles/posts/registry from a cycle JSON (parameterized, one transaction)
  report       print funnel numbers as JSON                  (read-only)
  migrate      upgrade an older stats.db to the shipped schema

The database structure comes only from data-schemas/stats-db-schema.sql. Field names
are canonical there: `platform` (legacy input alias `source`), `post_id` (alias `id`),
`user_id` (alias `author`). Aliases are converted in normalize_post() and nowhere else.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Module-level contract (shared by every command)
# ---------------------------------------------------------------------------
MAX_INPUT_SIZE = 100 * 1024 * 1024  # 100 MB per input file
MAX_POST_COUNT = 100000  # max posts per batch
KNOWN_PLATFORMS = ("x", "telegram")
CYCLE_STATUSES = ("running", "completed", "failed")
FULLTEXT_VALUES = ("full", "teaser", "error")
REGISTRY_DAYS = 14
SELECTION_THRESHOLD = 3  # stars; default for "selected" when not given

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "data-schemas" / "stats-db-schema.sql"

# Expected structure, checked against every database before use
EXPECTED_PK = {
    "seen_texts": ["text_hash", "user_id", "platform"],
    "posts": ["platform", "post_id"],
}
REQUIRED_COLUMNS = {
    "posts": {"platform", "post_id", "text", "score", "score_teaser", "fulltext",
              "registry_key", "orig_id", "cycle_no", "created_at", "channel"},
    "registry": {"registry_key", "platform", "post_id", "first_seen", "expires_at"},
    "seen_texts": {"text_hash", "user_id", "post_id", "platform", "first_seen"},
    "cycles": {"cycle_id", "reader", "started_at", "completed_at", "status",
               "posts_read", "posts_selected"},
}

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
TRAILING_PUNCT = ".,;:!?)]}>\"'"


class InputError(Exception):
    """Invalid input; nothing has been written."""


class SchemaError(Exception):
    """Database structure differs from the shipped schema."""


def err(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Input loading and normalization
# ---------------------------------------------------------------------------
def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise InputError(f"Input file {path} not found")
    if not path.is_file():
        raise InputError(f"Input {path} is not a regular file")
    size = path.stat().st_size
    if size > MAX_INPUT_SIZE:
        raise InputError(f"Input file too large ({size} bytes, max {MAX_INPUT_SIZE})")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise InputError(f"reading input: {e}")


def check_post_list(posts: Any, what: str = "Input") -> List[Dict[str, Any]]:
    if not isinstance(posts, list):
        raise InputError(f"{what} must be JSON array of posts")
    if len(posts) > MAX_POST_COUNT:
        raise InputError(f"Too many posts ({len(posts)}, max {MAX_POST_COUNT})")
    for i, post in enumerate(posts):
        if not isinstance(post, dict):
            raise InputError(f"Post {i} is not a dict: {type(post).__name__}")
    return posts


def load_posts(path: Path) -> List[Dict[str, Any]]:
    return check_post_list(load_json_file(path))


def _aliased(post: Dict[str, Any], i: int, canonical: str, alias: str) -> Any:
    """Return the value of `canonical`, accepting legacy `alias`; both given must agree."""
    has_c, has_a = canonical in post, alias in post
    if has_c and has_a and post[canonical] != post[alias]:
        raise InputError(f"Post {i} has conflicting '{canonical}' and legacy '{alias}'")
    return post[canonical] if has_c else post.get(alias)


def _required_str(value: Any, i: int, name: str) -> str:
    if value is None:
        raise InputError(f"Post {i} missing required field '{name}'")
    if not isinstance(value, str):
        raise InputError(f"Post {i} {name} must be string, got {type(value).__name__}")
    if not value.strip():
        raise InputError(f"Post {i} {name} must not be empty")
    return value


def normalize_platform(value: Any, i: int) -> str:
    platform = _required_str(value, i, "platform").strip().lower()
    if platform not in KNOWN_PLATFORMS:
        raise InputError(f"Post {i} platform must be one of {', '.join(KNOWN_PLATFORMS)}, got {value!r}")
    return platform


def normalize_post(post: Dict[str, Any], i: int, need_user: bool = True) -> Dict[str, Any]:
    """Single place where legacy input is adapted to canonical fields.

    Returns {'platform', 'post_id', 'user_id', 'text'}; raises InputError on bad input.
    """
    platform = normalize_platform(_aliased(post, i, "platform", "source"), i)
    post_id = _required_str(_aliased(post, i, "post_id", "id"), i, "id")
    user_id = _aliased(post, i, "user_id", "author")
    if need_user:
        user_id = _required_str(user_id, i, "user_id")
    text = post.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise InputError(f"Post {i} text must be string, got {type(text).__name__}")
    return {"platform": platform, "post_id": post_id, "user_id": user_id, "text": text}


def canonical_output(post: Dict[str, Any], norm: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in post.items() if k != "source"}
    out["platform"] = norm["platform"]
    return out


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(TRAILING_PUNCT)
    url = url.split("#", 1)[0]
    if "?" in url:
        base, query = url.split("?", 1)
        kept = [p for p in query.split("&") if p and not p.lower().startswith("utm_")]
        url = base + ("?" + "&".join(kept) if kept else "")
    m = re.match(r"^(https?)://([^/?]*)(.*)$", url, re.IGNORECASE)
    if m:
        url = "https://" + m.group(2).lower() + m.group(3)
    return url.rstrip("/")


def content_key(norm: Dict[str, Any]) -> str:
    """Content key stored as seen_texts.text_hash (definition in the schema file)."""
    words = norm["text"].lower().split()
    clean = " ".join(w for w in words if not URL_RE.match(w))
    if clean:
        return hashlib.sha1(clean.encode("utf-8")).hexdigest()
    urls = sorted({normalize_url(w) for w in words if URL_RE.match(w)})
    if urls:
        return hashlib.sha1(("urls:" + " ".join(urls)).encode("utf-8")).hexdigest()
    return hashlib.sha1(f"id:{norm['platform']}:{norm['post_id']}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Atomic file output
# ---------------------------------------------------------------------------
def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to `path` via unique temp file + rename; the old file stays intact on failure."""
    out_dir = path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".tmp", prefix=f".{path.name}.", dir=out_dir)
    tmp = Path(tmp_name)
    try:
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))  # keep the file's permissions
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Database: shipped schema is the only DDL
# ---------------------------------------------------------------------------
def schema_statements() -> List[str]:
    if not SCHEMA_PATH.is_file():
        raise SchemaError(f"shipped schema not found: {SCHEMA_PATH}")
    statements, buf = [], ""
    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if stmt:
                statements.append(stmt)
            buf = ""
    if buf.strip() and not all(l.strip().startswith("--") or not l.strip() for l in buf.splitlines()):
        raise SchemaError("shipped schema ends with an incomplete statement")
    return statements


def table_columns(conn: sqlite3.Connection, table: str) -> List[Tuple[str, int]]:
    return [(row[1], row[5]) for row in conn.execute(f"PRAGMA table_info({table})")]


def check_schema(conn: sqlite3.Connection) -> None:
    """Refuse a database whose existing tables differ from the shipped schema."""
    problems = []
    for table, required in REQUIRED_COLUMNS.items():
        cols = table_columns(conn, table)
        if not cols:
            continue  # created by apply_schema
        names = {c for c, _ in cols}
        if "source" in names:
            problems.append(f"{table} uses legacy column 'source' (canonical: 'platform')")
        missing = required - names
        if missing:
            problems.append(f"{table} lacks columns {sorted(missing)}")
        if table in EXPECTED_PK:
            pk = [c for c, n in sorted((c for c in cols if c[1] > 0), key=lambda c: c[1])]
            if pk != EXPECTED_PK[table]:
                problems.append(f"{table} primary key is {pk}, expected {EXPECTED_PK[table]}")
    if problems:
        raise SchemaError("stats.db does not match data-schemas/stats-db-schema.sql: "
                          + "; ".join(problems) + ". Run: reading-dedup-sort.py migrate --db <stats.db>")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None)  # explicit transactions
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_db(db_path: Path) -> sqlite3.Connection:
    """Open stats.db, verify structure, apply the shipped (idempotent) schema."""
    conn = connect(db_path)
    try:
        check_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        for stmt in schema_statements():
            conn.execute(stmt)
        conn.execute("COMMIT")
        check_schema(conn)
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.close()
        raise
    return conn


def migrate(db_path: Path) -> int:
    """Upgrade an older stats.db in one transaction; idempotent."""
    conn = connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # table rebuild; re-enabled and checked below
    try:
        conn.execute("BEGIN IMMEDIATE")
        changes = []
        for table in ("posts", "registry", "seen_texts"):
            names = {c for c, _ in table_columns(conn, table)}
            if "source" in names and "platform" not in names:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN source TO platform")
                changes.append(f"{table}.source -> platform")
        cols = table_columns(conn, "seen_texts")
        if cols:
            names = {c for c, _ in cols}
            if "platform" not in names:
                raise SchemaError("seen_texts has no platform column; cannot assign platforms safely")
            pk = [c for c, n in sorted((c for c in cols if c[1] > 0), key=lambda c: c[1])]
            if pk != EXPECTED_PK["seen_texts"]:
                conn.execute("DROP INDEX IF EXISTS idx_seen_texts_hash_user")
                conn.execute("ALTER TABLE seen_texts RENAME TO seen_texts_legacy")
                changes.append(f"seen_texts primary key {pk} -> {EXPECTED_PK['seen_texts']}")
        for stmt in schema_statements():
            conn.execute(stmt)
        if table_columns(conn, "seen_texts_legacy"):
            conn.execute(
                "INSERT OR IGNORE INTO seen_texts (text_hash, user_id, post_id, platform, first_seen) "
                "SELECT text_hash, user_id, post_id, platform, first_seen FROM seen_texts_legacy")
            conn.execute("DROP TABLE seen_texts_legacy")
        check_schema(conn)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise SchemaError(f"foreign key violations after migration: {len(violations)}")
        conn.execute("COMMIT")
    except (sqlite3.Error, SchemaError) as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.close()
        err(f"migration failed, database unchanged: {e}")
        return 1
    conn.close()
    print("Migrated: " + (", ".join(changes) if changes else "already current"), file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def precheck(state_file: Path, key: str, ids: List[str]) -> int:
    """Check if any IDs are new compared to state file.
    Returns: 0 if new IDs found, 2 if nothing new, 1 on error.
    """
    if not ids:
        return 1  # No IDs to check = error
    if not state_file.exists():
        return 0  # No state = all new
    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        err(f"reading state file: {e}")
        return 1
    if not isinstance(state, dict):
        err("state file must be a JSON object")
        return 1
    last_id = state.get(key)
    if not last_id:
        return 0  # No last ID = all new
    if ids[0] == last_id:
        print("NOTHING_NEW", file=sys.stderr)
        return 2
    return 0


def dedup(input_file: Path, db_path: Path, output_file: Path) -> int:
    """Drop posts already marked seen, or repeated within the batch. Read-only on stats.db.

    A post is a repeat when the same (platform, post_id) was seen, or the same user on the
    same platform already has the same content key. Posts are recorded as seen only by
    `mark-seen`, after the digest; so a failure in any later stage loses nothing.
    """
    try:
        posts = load_posts(input_file)
        norms = [normalize_post(p, i) for i, p in enumerate(posts)]
    except InputError as e:
        err(str(e))
        return 1
    try:
        conn = open_db(db_path)
    except (sqlite3.Error, SchemaError) as e:
        err(f"during dedup: {e}")
        return 1
    try:
        deduped = []
        batch_ids = set()
        batch_keys = set()
        for post, norm in zip(posts, norms):
            id_key = (norm["platform"], norm["post_id"])
            if id_key in batch_ids:
                continue
            batch_ids.add(id_key)
            key = content_key(norm)
            text_key = (key, norm["user_id"], norm["platform"])
            if text_key in batch_keys:
                continue
            batch_keys.add(text_key)
            if conn.execute("SELECT 1 FROM seen_texts WHERE platform = ? AND post_id = ?",
                            id_key).fetchone():
                continue
            if conn.execute("SELECT 1 FROM seen_texts WHERE text_hash = ? AND user_id = ? AND platform = ?",
                            text_key).fetchone():
                continue
            deduped.append(canonical_output(post, norm))
    except sqlite3.Error as e:
        err(f"during dedup: {e}")
        return 1
    finally:
        conn.close()
    try:
        atomic_write_json(output_file, deduped)
    except OSError as e:
        err(f"writing output: {e}")
        return 1
    print(f"Deduped: {len(posts)} -> {len(deduped)} posts", file=sys.stderr)
    return 0


def mark_seen(input_file: Path, db_path: Path) -> int:
    """Record posts as seen (single writer of seen_texts). Idempotent; one transaction."""
    try:
        posts = load_posts(input_file)
        norms = [normalize_post(p, i) for i, p in enumerate(posts)]
    except InputError as e:
        err(str(e))
        return 1
    try:
        conn = open_db(db_path)
    except (sqlite3.Error, SchemaError) as e:
        err(f"during mark-seen: {e}")
        return 1
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO seen_texts (text_hash, user_id, post_id, platform, first_seen) "
            "VALUES (?, ?, ?, ?, ?)",
            [(content_key(n), n["user_id"], n["post_id"], n["platform"], now) for n in norms])
        added = conn.total_changes - before
        conn.execute("COMMIT")
    except sqlite3.Error as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        err(f"during mark-seen: {e}")
        return 1
    finally:
        conn.close()
    print(f"Marked seen: {added} new of {len(posts)} posts", file=sys.stderr)
    return 0


def score_value(post: Dict[str, Any], i: int) -> float:
    score = post.get("score")
    if score is None:
        return 0
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise InputError(f"Post {i} score is not numeric: {score!r}")
    return score


def sort_posts(input_file: Path) -> int:
    """Sort posts by score, highest first; missing score counts as 0; ties keep input order.

    Rewrites the file atomically; on any error the original file is left byte-for-byte unchanged.
    """
    try:
        posts = load_posts(input_file)
        keys = [score_value(p, i) for i, p in enumerate(posts)]
    except InputError as e:
        err(str(e))
        return 1
    order = sorted(range(len(posts)), key=lambda i: -keys[i])  # stable
    sorted_posts = [posts[i] for i in order]
    try:
        atomic_write_json(input_file, sorted_posts)
    except OSError as e:
        err(f"writing sorted output: {e}")
        return 1
    print(f"Sorted {len(sorted_posts)} posts by score", file=sys.stderr)
    return 0


def _opt_str(value: Any, i: int, name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InputError(f"Post {i} {name} must be string, got {type(value).__name__}")
    return value


def _opt_stars(value: Any, i: int, name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise InputError(f"Post {i} {name} must be integer 1-5, got {value!r}")
    return value


def parse_iso(value: Any, name: str) -> datetime.datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{name} must be an ISO8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise InputError(f"{name} is not ISO8601: {value!r}")
    if parsed.tzinfo is None:
        raise InputError(f"{name} must include a time zone: {value!r}")
    return parsed


def validate_cycle(data: Any) -> Dict[str, Any]:
    """Validate the structured cycle result a reader passes to record-stats."""
    if not isinstance(data, dict):
        raise InputError("record-stats input must be a JSON object")
    reader = data.get("reader")
    if not isinstance(reader, str) or reader.strip().lower() not in KNOWN_PLATFORMS:
        raise InputError(f"reader must be one of {', '.join(KNOWN_PLATFORMS)}, got {reader!r}")
    reader = reader.strip().lower()
    started = parse_iso(data.get("started_at"), "started_at")
    completed_at = data.get("completed_at")
    if completed_at is not None:
        parse_iso(completed_at, "completed_at")
    status = data.get("status", "completed")
    if status not in CYCLE_STATUSES:
        raise InputError(f"status must be one of {', '.join(CYCLE_STATUSES)}, got {status!r}")
    posts = check_post_list(data.get("posts", []), "posts")
    rows, seen = [], set()
    for i, post in enumerate(posts):
        norm = normalize_post(post, i, need_user=False)
        if norm["platform"] != reader:
            raise InputError(f"Post {i} platform {norm['platform']!r} does not match reader {reader!r}")
        if norm["post_id"] in seen:
            raise InputError(f"Post {i} duplicates post_id {norm['post_id']!r}")
        seen.add(norm["post_id"])
        score = _opt_stars(post.get("score"), i, "score")
        selected = post.get("selected")
        if selected is None:
            selected = score is not None and score >= SELECTION_THRESHOLD
        if not isinstance(selected, bool):
            raise InputError(f"Post {i} selected must be true/false")
        fulltext = post.get("fulltext")
        if fulltext is not None and fulltext not in FULLTEXT_VALUES:
            raise InputError(f"Post {i} fulltext must be one of {', '.join(FULLTEXT_VALUES)}")
        rows.append({
            "platform": norm["platform"], "post_id": norm["post_id"], "text": norm["text"],
            "channel": _opt_str(post.get("channel"), i, "channel"),
            "score": score, "score_teaser": _opt_stars(post.get("score_teaser"), i, "score_teaser"),
            "fulltext": fulltext, "orig_id": _opt_str(post.get("orig_id"), i, "orig_id"),
            "selected": selected,
        })
    posts_read = data.get("posts_read", len(rows))
    if isinstance(posts_read, bool) or not isinstance(posts_read, int) or posts_read < len(rows):
        raise InputError("posts_read must be an integer >= number of posts listed")
    return {"reader": reader, "started_at": data["started_at"], "started": started,
            "completed_at": completed_at, "status": status, "posts_read": posts_read, "posts": rows}


def record_stats(input_file: Path, db_path: Path) -> int:
    """Write one reader cycle (cycles, posts, registry) in a single transaction.

    Re-recording the same cycle (same reader and started_at) updates it; nothing duplicates.
    """
    try:
        cycle = validate_cycle(load_json_file(input_file))
    except InputError as e:
        err(str(e))
        return 1
    try:
        conn = open_db(db_path)
    except (sqlite3.Error, SchemaError) as e:
        err(f"during record-stats: {e}")
        return 1
    selected = [p for p in cycle["posts"] if p["selected"]]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    first_seen = cycle["started"].isoformat()
    expires_at = (cycle["started"] + datetime.timedelta(days=REGISTRY_DAYS)).isoformat()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO cycles (reader, started_at, completed_at, status, posts_read, posts_selected) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(reader, started_at) DO UPDATE SET completed_at = excluded.completed_at, "
            "status = excluded.status, posts_read = excluded.posts_read, "
            "posts_selected = excluded.posts_selected",
            (cycle["reader"], cycle["started_at"], cycle["completed_at"], cycle["status"],
             cycle["posts_read"], len(selected)))
        cycle_id = conn.execute("SELECT cycle_id FROM cycles WHERE reader = ? AND started_at = ?",
                                (cycle["reader"], cycle["started_at"])).fetchone()[0]
        for p in cycle["posts"]:
            registry_key = f"{p['platform']}:{p['post_id']}" if p["selected"] else None
            conn.execute(
                "INSERT INTO posts (platform, post_id, channel, text, score, score_teaser, fulltext, "
                "registry_key, orig_id, cycle_no, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(platform, post_id) DO UPDATE SET channel = excluded.channel, "
                "text = excluded.text, score = excluded.score, score_teaser = excluded.score_teaser, "
                "fulltext = excluded.fulltext, registry_key = excluded.registry_key, "
                "orig_id = excluded.orig_id, cycle_no = excluded.cycle_no",
                (p["platform"], p["post_id"], p["channel"], p["text"], p["score"], p["score_teaser"],
                 p["fulltext"], registry_key, p["orig_id"], cycle_id, now))
            if registry_key:
                conn.execute(
                    "INSERT OR IGNORE INTO registry (registry_key, platform, post_id, first_seen, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (registry_key, p["platform"], p["post_id"], first_seen, expires_at))
        conn.execute("COMMIT")
    except sqlite3.Error as e:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        err(f"during record-stats, nothing written: {e}")
        return 1
    finally:
        conn.close()
    print(f"Recorded cycle {cycle_id} ({cycle['reader']}): {len(cycle['posts'])} posts, "
          f"{len(selected)} selected", file=sys.stderr)
    return 0


REPORT_QUERIES = {
    "cycles": "SELECT reader, COUNT(*), SUM(status = 'completed'), SUM(status = 'failed'), "
              "COALESCE(SUM(posts_read), 0), COALESCE(SUM(posts_selected), 0) "
              "FROM cycles GROUP BY reader ORDER BY reader",
    "posts": "SELECT platform, COUNT(*), SUM(registry_key IS NOT NULL), ROUND(AVG(score), 2) "
             "FROM posts GROUP BY platform ORDER BY platform",
    "registry": "SELECT platform, COUNT(*) FROM registry GROUP BY platform ORDER BY platform",
}


def report(db_path: Path) -> int:
    """Print funnel numbers per reader/platform as JSON (for the monitor)."""
    if not db_path.exists():
        err(f"database {db_path} not found")
        return 1
    try:
        conn = open_db(db_path)
    except (sqlite3.Error, SchemaError) as e:
        err(f"during report: {e}")
        return 1
    try:
        out: Dict[str, Any] = {"cycles": {}, "posts": {}, "registry": {}}
        for reader, n, done, failed, read, sel in conn.execute(REPORT_QUERIES["cycles"]):
            out["cycles"][reader] = {"cycles": n, "completed": done, "failed": failed,
                                     "posts_read": read, "posts_selected": sel}
        for platform, n, sel, avg in conn.execute(REPORT_QUERIES["posts"]):
            out["posts"][platform] = {"posts": n, "selected": sel, "avg_score": avg}
        for platform, n in conn.execute(REPORT_QUERIES["registry"]):
            out["registry"][platform] = n
    except sqlite3.Error as e:
        err(f"during report: {e}")
        return 1
    finally:
        conn.close()
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description='Reading dedup/sort utility')
    parser.add_argument('command', choices=['precheck', 'dedup', 'sort', 'mark-seen',
                                            'record-stats', 'report', 'migrate'])
    parser.add_argument('--state', type=Path, help='State JSON file (for precheck)')
    parser.add_argument('--key', help='State key to check (for precheck)')
    parser.add_argument('--ids', nargs='+', help='IDs to check (for precheck)')
    parser.add_argument('input_file', nargs='?', type=Path, help='Input JSON file')
    parser.add_argument('--db', type=Path, help='Stats database path')
    parser.add_argument('-o', '--output', type=Path, help='Output file (for dedup)')

    args = parser.parse_args()

    if args.command == 'precheck':
        if not args.state or not args.key or not args.ids:
            err("precheck requires --state, --key, and --ids")
            return 1
        return precheck(args.state, args.key, args.ids)
    if args.command == 'dedup':
        if not args.input_file or not args.db or not args.output:
            err("dedup requires input_file, --db, and -o")
            return 1
        return dedup(args.input_file, args.db, args.output)
    if args.command == 'sort':
        if not args.input_file:
            err("sort requires input_file")
            return 1
        return sort_posts(args.input_file)
    if args.command in ('mark-seen', 'record-stats'):
        if not args.input_file or not args.db:
            err(f"{args.command} requires input_file and --db")
            return 1
        fn = mark_seen if args.command == 'mark-seen' else record_stats
        return fn(args.input_file, args.db)
    if args.command in ('report', 'migrate'):
        if not args.db:
            err(f"{args.command} requires --db")
            return 1
        return report(args.db) if args.command == 'report' else migrate(args.db)
    return 1


if __name__ == '__main__':
    sys.exit(main())
