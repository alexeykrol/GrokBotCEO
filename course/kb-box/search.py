#!/usr/bin/env python3
"""Mentor's knowledge base: search it and record the user's decisions.

Standard library only (Python 3.9+), no network, runs from any folder.

    python3 search.py ask "вопрос" [-n 8] [--json]     search (``ask`` is optional)
    python3 search.py --unit ID [--full]                one article of the base
    python3 search.py --concept "рутина"                where a concept occurs
    python3 search.py --info                            what the base is, intact or not
    python3 search.py miss "вопрос" [ID]                no answer found (or search missed one)
    python3 search.py verdict ID valuable|rejected|outdated|disputed ["note"]

    --kb-home DIR   Mentor's folder in the workspace: <workspace>/mentor (default: the ``mentor``
                    folder next to the release copy). The base is DIR/kb/base/ (derived, built by
                    ``build_kb.py``); the user's records go to DIR/kb-user/mentor-kb/user/
                    (misses.tsv, verdicts.tsv, conflicts.tsv).

Self-heal: if the base is missing, damaged or was built from other course files, it is built
first (``build_kb.py``, a fraction of a second), then the command runs. A search also lists the
course lessons on the found topics (``lessons``: id, title, concepts), from ``../kb-markup/links.tsv``.

The search engine is ``kbtool/search.py``, an unmodified copy of the BestMentor box script; this
file points it at the base, builds the base when needed and adds the lessons.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.dont_write_bytecode = True                     # the release copy stays untouched: no __pycache__

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_kb  # noqa: E402

WRITE_CMDS = ("verdict", "miss", "conflict")
OTHER_MODES = ("--unit", "--concept", "--info", "-h", "--help")
MAX_LESSONS = 5


def _take_kb_home(argv):
    out, home, i = [], None, 0
    while i < len(argv):
        a = argv[i]
        if a == "--kb-home" and i + 1 < len(argv):
            home, i = argv[i + 1], i + 2
            continue
        if a.startswith("--kb-home="):
            home, i = a.split("=", 1)[1], i + 1
            continue
        out.append(a)
        i += 1
    return out, Path(home).expanduser() if home else build_kb.default_kb_home()


def _engine():
    spec = importlib.util.spec_from_file_location("mentor_kb_engine", HERE / "kbtool" / "search.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


def _ensure_base(kb_home: Path) -> bool:
    reason = build_kb.freshness(kb_home)
    if not reason:
        return True
    try:
        r = build_kb.build(kb_home, force=True)
    except (build_kb.BuildError, OSError, sqlite3.Error) as exc:
        print(f"kb: the base could not be built ({reason}): {exc}", file=sys.stderr)
        return False
    print(f"kb: base built ({reason}): {r['units']} articles", file=sys.stderr)
    return True


# ---------------------------------------------------------------- lessons
def _read_tsv(path):
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    except OSError:
        return []


def _lesson_titles():
    try:
        course = json.loads((build_kb.COURSE / "course.json").read_text(encoding="utf-8"))["course"]
    except (OSError, ValueError, KeyError):
        return {}
    return {l["id"]: l.get("title", "") for s in course.get("sections", []) for l in s.get("lessons", [])}


def lessons_for(db: Path, result_ids, touched) -> list:
    """Course lessons for the found units' central concepts and the concepts the question touched."""
    links = {r["concept"]: [x.strip() for x in (r.get("lessons") or "").split(",") if x.strip()]
             for r in _read_tsv(build_kb.MARKUP / "links.tsv")}
    concepts = []
    if result_ids:
        con = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
        try:
            for uid in result_ids:
                concepts += [c for (c,) in con.execute(
                    "SELECT concept FROM unit_concepts WHERE unit_id=? AND weight=2 ORDER BY concept", (uid,))]
        finally:
            con.close()
    concepts += list(touched)
    titles = _lesson_titles()
    out = {}
    for c in dict.fromkeys(concepts):
        for lid in links.get(c, []):
            out.setdefault(lid, dict(id=lid, title=titles.get(lid, ""), concepts=[]))["concepts"].append(c)
    return list(out.values())[:MAX_LESSONS]


def _search(engine, argv) -> int:
    p = argparse.ArgumentParser(prog="search.py ask")
    p.add_argument("question", nargs="?")
    p.add_argument("-n", type=int, default=8)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    if not a.question or not a.question.strip():
        p.print_help()
        return 0
    try:
        if not 1 <= a.n <= 20:
            raise engine.KbError("-n must be an integer 1..20")
        box = engine.Box(engine.DATA)
        d = engine.search(box, a.question, a.n)
        d["lessons"] = lessons_for(box.db, [r["id"] for r in d["results"]], [c["concept"] for c in d["concepts"]])
    except (engine.KbError, sqlite3.Error) as exc:
        print(f"kb: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    engine._print_search(d)
    if d["lessons"]:
        print("\n== Course lessons on this (offer one the user has not passed)")
        for l in d["lessons"]:
            print(f"  {l['id']} «{l['title']}» ({', '.join(l['concepts'])})")
    return 0


def main(argv=None) -> int:
    argv, kb_home = _take_kb_home(list(sys.argv[1:] if argv is None else argv))
    os.environ["KB_HOME"] = str(kb_home / "kb-user")
    if not _ensure_base(kb_home):
        return 2
    engine = _engine()
    engine.DATA = build_kb.base_dir(kb_home)
    if argv and argv[0] == "ask":
        argv = argv[1:]
        if argv and argv[0] in WRITE_CMDS:          # a question that looks like a command word
            argv = ["--"] + argv
    elif argv and argv[0] in WRITE_CMDS:
        return engine.main(argv)
    if any(a in OTHER_MODES for a in argv):
        return engine.main(argv)
    return _search(engine, argv)


if __name__ == "__main__":
    sys.exit(main())
