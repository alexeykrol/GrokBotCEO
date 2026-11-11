#!/usr/bin/env python3
"""
Tests for Mentor's knowledge base (course/kb-box/).

The release ships no built base (no *.sqlite in the public tree). It ships the course articles
(course/kb/), their markup (course/kb-markup/), a vendored kbtool subset (kb-box/kbtool/) and two
scripts: build_kb.py builds the base into <workspace>/mentor/kb/base/, search.py searches it and
rebuilds it when it is missing or stale (self-heal). Checks: the release has every part and no
binary; a build from release-only files works, is idempotent and deterministic, holds no local
paths and covers every article with markup; a known question finds its article; user records go
to <workspace>/mentor/kb-user/; the release copy is never written to; links.tsv references only
existing concepts, competency ids and lesson ids. Each check returns a list of errors; the real
release must give none (GREEN), small broken fixtures prove the checks catch defects (RED).
Stdlib only, no network.
"""
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
COURSE_DIR = RELEASE_DIR / "course"
KB_DIR = COURSE_DIR / "kb"
BOX_DIR = COURSE_DIR / "kb-box"
LINKS = COURSE_DIR / "kb-markup" / "links.tsv"
REMARK = "run scripts/kb-build.sh"
UNIT_ID_RE = re.compile(r"^[0-9a-f]{12}(?:-\d{2})?$")
COMPETENCY_RE = re.compile(r"^\|\s*(P\d+\.\d{2})\s*\|", re.M)
# Absolute or personal paths that must never be inside a built base.
PATH_PATTERNS = [rb"/Users/", rb"/home/", rb"/private/", rb"/var/folders/", rb"C:\\Users", rb"/workspace/"]
EXAMPLE = "как удалить бота"
EXAMPLE_ARTICLE = "s3-delete-bot.md"
BOX_PARTS = ["README.md", "build_kb.py", "search.py", "kbtool/VENDORED.md", "kbtool/search.py",
             "kbtool/kbtool/__init__.py", "kbtool/kbtool/store.py", "kbtool/kbtool/ingest.py",
             "kbtool/kbtool/markup.py", "kbtool/kbtool/config.py"]
BINARY_SUFFIXES = (".sqlite", ".sqlite3", ".db", ".db-wal", ".db-journal", ".pyc")


def run_py(script, *args, cwd=None):
    return subprocess.run([sys.executable, "-B", str(script), *args], cwd=cwd, capture_output=True, text=True)


def read_tsv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


# ---------------------------------------------------------------- checks
def check_release(release=RELEASE_DIR):
    errors = []
    box = release / "course" / "kb-box"
    for rel in BOX_PARTS:
        if not (box / rel).is_file():
            errors.append(f"kb-box: missing {rel}")
    for p in release.rglob("*"):
        if p.name.lower().endswith(BINARY_SUFFIXES):
            errors.append(f"binary in the release: {p.relative_to(release)} (the base is built by the user's bot)")
        if p.name in ("__pycache__", ".DS_Store"):
            errors.append(f"junk in the release: {p.relative_to(release)}")
    vendored = box / "kbtool" / "VENDORED.md"
    if vendored.is_file():
        text = vendored.read_text(encoding="utf-8")
        for field in ("Version", "Commit"):
            if not re.search(rf"^\|\s*{field}\s*\|\s*\S", text, re.M):
                errors.append(f"kbtool/VENDORED.md: no {field}")
    return errors


def check_no_paths(db, extra=()):
    errors = []
    raw = db.read_bytes()
    for pat in PATH_PATTERNS + [e.encode() for e in extra]:
        if pat in raw:
            errors.append(f"{db.name}: contains path pattern {pat.decode(errors='replace')!r}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta"))
        if meta.get("corpus_path"):
            errors.append(f"{db.name}: meta.corpus_path is not empty")
        if "built" in meta:
            errors.append(f"{db.name}: meta.built timestamp makes the base non-deterministic")
        for (path,) in con.execute("SELECT path FROM sources UNION SELECT path FROM units"):
            if path.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", path):
                errors.append(f"{db.name}: absolute path {path!r}")
        for (uid,) in con.execute("SELECT id FROM units WHERE text LIKE '---%'"):
            errors.append(f"{db.name}: unit {uid} still has article front matter (source URLs in the index)")
        for table in ("runs", "misses"):
            if con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                errors.append(f"{db.name}: table {table} must be empty")
    finally:
        con.close()
    return errors


def check_coverage(db, kb_dir=KB_DIR):
    """Every article is a unit with its current content, and every unit has markup."""
    errors = []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        built = {path: sha for path, sha in con.execute(
            "SELECT s.path, s.sha256 FROM sources s WHERE s.id IN (SELECT source_id FROM units)")}
        unmarked = [r[0] for r in con.execute(
            "SELECT u.path FROM units u LEFT JOIN markup m ON m.unit_id = u.id WHERE m.unit_id IS NULL")]
    finally:
        con.close()
    articles = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(kb_dir.glob("*.md"))}
    for name, sha in articles.items():
        if name not in built:
            errors.append(f"kb/{name}: no unit after build")
        elif built[name] != sha:
            errors.append(f"kb/{name}: built from other content")
    for name in sorted(set(built) - set(articles)):
        errors.append(f"base has {name}, which is not in kb/")
    errors += [f"kb/{p}: no markup (summary, concepts) — {REMARK}" for p in sorted(set(unmarked))]
    return errors


def known_lessons(course_dir=COURSE_DIR):
    ids = set()
    files = [course_dir / "course.json"] + sorted((course_dir / "sections").glob("*.json"))
    for f in files:
        if not f.is_file():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        sections = data["course"]["sections"] if "course" in data else [data]
        for s in sections:
            ids.update(l["id"] for l in s.get("lessons", []))
    return ids


def known_competencies(course_dir=COURSE_DIR):
    path = course_dir / "COMPETENCIES.md"
    return set(COMPETENCY_RE.findall(path.read_text(encoding="utf-8"))) if path.is_file() else set()


def check_links(db, links=LINKS, lessons=None, competencies=None):
    errors = []
    lessons = known_lessons() if lessons is None else lessons
    competencies = known_competencies() if competencies is None else competencies
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        concepts = {r[0] for r in con.execute("SELECT name FROM concepts")}
    finally:
        con.close()
    rows = read_tsv(links)
    seen = set()
    for i, r in enumerate(rows, 2):
        c = (r.get("concept") or "").strip()
        if c in seen:
            errors.append(f"links.tsv:{i}: duplicate concept {c!r}")
        seen.add(c)
        if c not in concepts:
            errors.append(f"links.tsv:{i}: concept {c!r} is not in the base")
        comps = [x.strip() for x in (r.get("competencies") or "").split(",") if x.strip()]
        less = [x.strip() for x in (r.get("lessons") or "").split(",") if x.strip()]
        if not comps and not less:
            errors.append(f"links.tsv:{i}: {c!r} has neither competencies nor lessons")
        for x in comps:
            if not re.match(r"^P\d+\.\d{2}$", x):
                errors.append(f"links.tsv:{i}: bad competency id {x!r}")
            elif competencies and x not in competencies:
                errors.append(f"links.tsv:{i}: competency {x} is not in COMPETENCIES.md")
        for x in less:
            if not re.match(r"^S\d+\.L\d{2}$", x):
                errors.append(f"links.tsv:{i}: bad lesson id {x!r}")
            elif lessons and x not in lessons:
                errors.append(f"links.tsv:{i}: lesson {x} is not in the course")
    for c in sorted(concepts - seen):
        errors.append(f"links.tsv: no row for concept {c!r} — add it, then {REMARK}")
    return errors


# ---------------------------------------------------------------- tests
class BuiltFromRelease(unittest.TestCase):
    """A copy of the public tree only (no private files), built the way the user's bot builds it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kb-test-"))
        cls.rel = cls.tmp / "grokbotceo"
        shutil.copytree(RELEASE_DIR, cls.rel, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", ".git"))
        cls.home = cls.tmp / "mentor"
        cls.box = cls.rel / "course" / "kb-box"
        cls.before = tree(cls.rel)
        cls.build = run_py(cls.box / "build_kb.py", "--kb-home", str(cls.home), "--json", cwd=cls.tmp)
        cls.db = cls.home / "kb" / "base" / "kb.sqlite"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def assertClean(self, errors):
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def ask(self, *args):
        return run_py(self.box / "search.py", *args, "--kb-home", str(self.home), cwd=self.tmp)

    def test_build_ok(self):
        self.assertEqual(self.build.returncode, 0, self.build.stderr)
        r = json.loads(self.build.stdout)
        self.assertEqual(r["status"], "built")
        meta = json.loads((self.home / "kb" / "base" / "box.json").read_text(encoding="utf-8"))
        course = json.loads((COURSE_DIR / "course.json").read_text(encoding="utf-8"))["course"]
        self.assertEqual(meta["course_version"], course["version"])
        self.assertRegex(meta["inputs_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(meta["sha256"], hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_no_local_paths(self):
        self.assertClean(check_no_paths(self.db, extra=[str(self.tmp)]))
        self.assertNotIn("/Users/", (self.home / "kb" / "base" / "box.json").read_text(encoding="utf-8"))

    def test_every_article_has_a_unit(self):
        self.assertClean(check_coverage(self.db))

    def test_links(self):
        self.assertClean(check_links(self.db))

    def test_idempotent_and_deterministic(self):
        r = run_py(self.box / "build_kb.py", "--kb-home", str(self.home), "--json")
        self.assertEqual(json.loads(r.stdout)["status"], "up to date", r.stderr)
        first = self.db.read_bytes()
        other = self.tmp / "other-mentor"
        r = run_py(self.box / "build_kb.py", "--kb-home", str(other))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((other / "kb" / "base" / "kb.sqlite").read_bytes(), first, "same inputs, different base")

    def test_known_question_finds_its_article(self):
        r = self.ask("ask", EXAMPLE, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        ids = [x["id"] for x in d["results"]]
        self.assertTrue(ids and all(UNIT_ID_RE.match(i) for i in ids))
        expected = hashlib.sha256((KB_DIR / EXAMPLE_ARTICLE).read_bytes()).hexdigest()[:12]
        self.assertIn(expected, ids[:3])
        self.assertTrue(d["lessons"], "a search lists the course lessons on the topic")
        self.assertTrue(all(re.match(r"^S\d+\.L\d{2}$", l["id"]) and l["title"] for l in d["lessons"]))
        r2 = self.ask(EXAMPLE, "--json")                                  # 'ask' is optional
        self.assertEqual(json.loads(r2.stdout)["results"][0]["id"], ids[0])

    def test_info_intact(self):
        r = self.ask("--info", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        info = json.loads(r.stdout)
        self.assertEqual(info.get("name"), "mentor-kb")
        self.assertTrue(info.get("intact"))

    def test_miss_goes_to_kb_user(self):
        r = self.ask("miss", "вопрос без ответа")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.home / "kb-user" / "mentor-kb" / "user" / "misses.tsv").is_file())

    def test_release_copy_is_never_written(self):
        self.ask("ask", EXAMPLE)
        self.ask("miss", "ещё вопрос")
        self.assertEqual(tree(self.rel), self.before)

    def test_self_heal(self):
        home = self.tmp / "heal" / "mentor"
        db = home / "kb" / "base" / "kb.sqlite"
        meta = home / "kb" / "base" / "box.json"
        for label, damage in [("missing", lambda: db.unlink()),
                              ("damaged", lambda: db.write_bytes(db.read_bytes()[:-100])),
                              ("stale", lambda: meta.write_text(
                                  meta.read_text(encoding="utf-8").replace('"inputs_sha256": "', '"inputs_sha256": "0'),
                                  encoding="utf-8"))]:
            with self.subTest(base=label):
                if db.is_file():
                    damage()
                r = run_py(self.box / "search.py", "ask", EXAMPLE, "--json", "--kb-home", str(home))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(json.loads(r.stdout)["results"])
                self.assertIn("base built", r.stderr)
                self.assertEqual(json.loads(meta.read_text(encoding="utf-8"))["sha256"],
                                 hashlib.sha256(db.read_bytes()).hexdigest())


class GreenRelease(unittest.TestCase):
    def test_release_parts_and_no_binary(self):
        errors = check_release()
        self.assertEqual(errors, [], "\n" + "\n".join(errors))


class RedFixtures(unittest.TestCase):
    """Broken copies prove the checks catch their defect."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kb-red-"))
        r = run_py(BOX_DIR / "build_kb.py", "--kb-home", str(cls.tmp / "mentor"))
        assert r.returncode == 0, r.stderr
        cls.built = cls.tmp / "mentor" / "kb" / "base" / "kb.sqlite"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.db = self.tmp / f"{self._testMethodName}.sqlite"
        shutil.copyfile(self.built, self.db)

    def _exec(self, sql, *args):
        con = sqlite3.connect(self.db)
        con.execute(sql, args)
        con.commit()
        con.close()

    def test_binary_in_release(self):
        rel = self.tmp / "rel"
        shutil.copytree(BOX_DIR, rel / "course" / "kb-box")
        (rel / "course" / "kb-box" / "base").mkdir()
        shutil.copyfile(self.built, rel / "course" / "kb-box" / "base" / "kb.sqlite")
        errs = check_release(rel)
        self.assertTrue(any("binary in the release" in e for e in errs))

    def test_missing_part(self):
        rel = self.tmp / "rel2"
        shutil.copytree(BOX_DIR, rel / "course" / "kb-box")
        (rel / "course" / "kb-box" / "build_kb.py").unlink()
        self.assertTrue(any("build_kb.py" in e for e in check_release(rel)))

    def test_private_path_in_meta(self):
        self._exec("UPDATE meta SET value=? WHERE key='corpus_path'", "/Users/someone/kb")
        self.assertTrue(check_no_paths(self.db))

    def test_front_matter_left(self):
        self._exec("UPDATE units SET text='---' || char(10) || 'id: x' || char(10) || '---' || char(10) || text "
                   "WHERE rowid=(SELECT MIN(rowid) FROM units)")
        self.assertTrue(check_no_paths(self.db))

    def test_absolute_source_path(self):
        self._exec("UPDATE sources SET path='/opt/kb/x.md' WHERE rowid=(SELECT MIN(rowid) FROM sources)")
        self.assertTrue(check_no_paths(self.db))

    def test_article_without_unit_or_markup(self):
        kb = self.tmp / "kb"
        shutil.copytree(KB_DIR, kb, dirs_exist_ok=True)
        (kb / "new-article.md").write_text("---\nid: x\n---\nтекст\n", encoding="utf-8")
        self.assertTrue(any("new-article.md" in e for e in check_coverage(self.db, kb)))
        self._exec("DELETE FROM markup WHERE unit_id=(SELECT MIN(id) FROM units)")
        self.assertTrue(any(REMARK in e for e in check_coverage(self.db)))

    def test_links_unknown_ids(self):
        bad = self.tmp / "links.tsv"
        bad.write_text(LINKS.read_text(encoding="utf-8") + "нет такого\tP9.99\tS9.L99\n", encoding="utf-8")
        errs = check_links(self.db, bad, lessons={"S3.L01"}, competencies={"P3.01"})
        self.assertTrue(any("not in the base" in e for e in errs))
        self.assertTrue(any("P9.99" in e for e in errs))
        self.assertTrue(any("S9.L99" in e for e in errs))

    def test_links_missing_concept(self):
        rows = LINKS.read_text(encoding="utf-8").splitlines()
        short = self.tmp / "links-short.tsv"
        short.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
        self.assertTrue(any("no row for concept" in e for e in check_links(self.db, short)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
