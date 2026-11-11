#!/usr/bin/env python3
"""Build Mentor's knowledge base on the bot computer, from the course files of this release.

    python3 build_kb.py [--kb-home DIR] [--force] [--json]

Inputs (read only, found next to this file at run time): the course articles ``../kb/*.md`` and
their markup ``../kb-markup/*.tsv`` (summaries, concepts, typed edges; made by the owner).
Output: ``DIR/kb/base/kb.sqlite`` and ``DIR/kb/base/box.json``. DIR is ``<workspace>/mentor``
(default: the ``mentor`` folder next to the release copy). The base is derived: it is never
committed and can be deleted at any time; ``search.py`` rebuilds it when needed.

- Deterministic: same inputs give the same base; no timestamps, no absolute paths inside.
- Idempotent: if the base is intact and was built from the same inputs, nothing is done
  (``--force`` rebuilds anyway).
- Atomic: built in a staging folder, then moved into place with ``os.replace``; a failed build
  leaves the old base untouched.
- ``box.json`` records the course version and ``inputs_sha256``, a hash of the inputs (articles,
  markup, this script, the vendored build modules).

Standard library only (Python 3.9+), no model, no network. Writes nothing inside the release copy.
Exit codes: 0 built or up to date · 2 error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True                     # the release copy stays untouched: no __pycache__

HERE = Path(__file__).resolve().parent             # <release>/course/kb-box
COURSE = HERE.parent                               # <release>/course
RELEASE = COURSE.parent                            # <release>
CORPUS = COURSE / "kb"
MARKUP = COURSE / "kb-markup"
KBTOOL = HERE / "kbtool"
NAME = "mentor-kb"
TITLE = "База знаний Ментора"
TOPIC = "Grok Bot и наша система ботов: как заказать, проверить, изменить, удалить бота, рутины, разделы"
EXAMPLE = "как удалить бота"
FRONT = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n+", re.S)


class BuildError(Exception):
    pass


def default_kb_home() -> Path:
    return RELEASE.parent / "mentor"


def base_dir(kb_home: Path) -> Path:
    return Path(kb_home) / "kb" / "base"


def input_files() -> list[Path]:
    return (sorted(CORPUS.glob("*.md")) + sorted(MARKUP.glob("*.tsv")) + [Path(__file__).resolve()]
            + sorted((KBTOOL / "kbtool").glob("*.py")))


def inputs_hash() -> str:
    h = hashlib.sha256()
    for p in input_files():
        h.update(p.relative_to(RELEASE).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def course_version() -> str:
    try:
        return str(json.loads((COURSE / "course.json").read_text(encoding="utf-8"))["course"]["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def kbtool_version() -> str:
    m = re.search(r'^__version__ = "(.+)"', (KBTOOL / "kbtool" / "__init__.py").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freshness(kb_home: Path) -> str:
    """'' when the base is intact and built from the current inputs, else the reason to build."""
    d = base_dir(kb_home)
    db, meta_path = d / "kb.sqlite", d / "box.json"
    if not db.is_file() or not meta_path.is_file():
        return "no base yet"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "box.json is unreadable"
    if meta.get("inputs_sha256") != inputs_hash():
        return "the course files changed"
    if meta.get("sha256") != _sha(db):
        return "the base file is damaged"
    return ""


# ---------------------------------------------------------------- build
def _postprocess(db: Path, version: str, ihash: str) -> dict:
    """Article front matter out of texts and the index; title and date from it; no machine traces."""
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT id, source_id, part_no, parts, text FROM units").fetchall()
        fm = {}
        for uid, sid, part, parts, text in rows:
            m = FRONT.match(text)
            if m and sid not in fm:
                head = m.group(1)
                t = re.search(r"^title:[ \t]*(.+)$", head, re.M)
                u = re.search(r"^updated:[ \t]*[\"']?(\d{4}-\d{2}-\d{2})", head, re.M)
                fm[sid] = (t.group(1).strip().strip("\"'") if t else None, u.group(1) if u else None)
        for uid, sid, part, parts, text in rows:
            m = FRONT.match(text)
            body = text[m.end():] if m else text
            title, updated = fm.get(sid, (None, None))
            sets, args = ["text=?", "chars=?"], [body, len(body)]
            if title:
                sets.append("title=?")
                args.append(f"{title} (part {part}/{parts})" if parts > 1 else title)
            if updated:
                sets += ["date=?", "date_basis=?"]
                args += [updated, "frontmatter"]
            con.execute(f"UPDATE units SET {', '.join(sets)} WHERE id=?", (*args, uid))
        con.execute("UPDATE sources SET mtime=NULL")
        con.execute("DELETE FROM runs")
        con.execute("DELETE FROM misses")
        con.execute("DELETE FROM meta WHERE key IN ('built', 'corpus_path')")
        con.executemany("INSERT INTO meta VALUES (?,?)",
                        [("corpus_path", ""), ("course_version", version), ("inputs_sha256", ihash),
                         ("kbtool_version", kbtool_version())])
        con.execute("DELETE FROM units_fts")
        con.execute("INSERT INTO units_fts (id, title, summary, text) SELECT u.id, u.title, COALESCE(m.summary, ''), "
                    "u.text FROM units u LEFT JOIN markup m ON m.unit_id = u.id ORDER BY u.id")
        con.execute("INSERT INTO units_fts(units_fts) VALUES ('optimize')")
        con.commit()
        con.execute("VACUUM")
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BuildError("the built base failed integrity_check")
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("units", "concepts", "edges")}
    finally:
        con.close()
    return counts


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def build(kb_home: Path | None = None, force: bool = False) -> dict:
    kb_home = Path(kb_home or default_kb_home()).expanduser().resolve()
    if kb_home == RELEASE or str(kb_home).startswith(str(RELEASE) + os.sep):
        raise BuildError(f"the base folder must be outside the release copy: {kb_home}")
    out = base_dir(kb_home)
    ihash = inputs_hash()
    if not force and not freshness(kb_home):
        return dict(status="up to date", base=str(out))
    if not CORPUS.is_dir() or not any(CORPUS.glob("*.md")):
        raise BuildError(f"no course articles in {CORPUS}")

    sys.path.insert(0, str(KBTOOL))
    try:
        from kbtool import store                                    # noqa: PLC0415 (vendored, stdlib only)
        from kbtool.config import DEFAULT_LIMITS, DEFAULTS, Base, KbError
        from kbtool.ingest import extract, scan
    finally:
        sys.path.remove(str(KBTOOL))

    out.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=str(out.parent)))
    try:
        base = Base(stage / NAME)
        base.ensure_dirs()
        base.markup = MARKUP                                         # read only: build never writes markup
        base.save_config({"corpus_path": str(CORPUS), **DEFAULTS, "limits": dict(DEFAULT_LIMITS)})
        try:
            scan(base)
            ex = extract(base)
            res = store.build(base)
        except KbError as exc:
            raise BuildError(str(exc)) from None
        if not ex["units"]:
            raise BuildError("no article could be read")
        version = course_version()
        counts = _postprocess(base.db, version, ihash)
        raw = base.db.read_bytes()
        for trace in {str(RELEASE), str(CORPUS), str(stage), str(kb_home), str(Path.home())}:
            if len(trace) > 1 and trace.encode() in raw:
                raise BuildError(f"the built base contains a local path ({trace}); not installed")
        meta = dict(name=NAME, title=TITLE, topic=TOPIC, example_question=EXAMPLE, **counts,
                    schema_version=1, kbtool_version=kbtool_version(), course_version=version,
                    inputs_sha256=ihash, sha256=hashlib.sha256(raw).hexdigest())
        os.chmod(base.db, 0o644)
        os.replace(base.db, out / "kb.sqlite")                       # atomic; box.json last
        _write_atomic(out / "box.json", json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return dict(status="built", base=str(out), warnings=len(res.get("warnings") or []), **counts,
                course_version=version)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kb-home", help="Mentor's folder in the workspace (<workspace>/mentor)")
    ap.add_argument("--force", action="store_true", help="rebuild even if the base is up to date")
    ap.add_argument("--json", action="store_true", help="JSON output")
    a = ap.parse_args(argv)
    try:
        r = build(Path(a.kb_home) if a.kb_home else None, force=a.force)
    except (BuildError, OSError, sqlite3.Error) as exc:
        print(f"build_kb: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    elif r["status"] == "built":
        print(f"Mentor's knowledge base: built ({r['units']} articles, {r['concepts']} concepts, {r['edges']} links)")
    else:
        print("Mentor's knowledge base: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
