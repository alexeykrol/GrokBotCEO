#!/usr/bin/env python3
"""Merge course/sections/S*.json into course/course.json.

Each section file holds one section object (as in course.json "sections").
A section file replaces the section with the same id; section order follows
the id (S1, S2, ...). Writes atomically. Use --check to validate the merge
without writing.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

COURSE_DIR = Path(__file__).resolve().parent.parent / "course"


def merge(course_dir: Path) -> dict:
    doc = json.loads((course_dir / "course.json").read_text(encoding="utf-8"))
    course = doc["course"]
    by_id = {s["id"]: s for s in course["sections"]}
    sec_dir = course_dir / "sections"
    if sec_dir.is_dir():
        for f in sorted(sec_dir.glob("S*.json")):
            section = json.loads(f.read_text(encoding="utf-8"))
            if section.get("id") != f.stem:
                raise SystemExit(f"{f.name}: id {section.get('id')!r} does not match file name")
            by_id[section["id"]] = section
    course["sections"] = [by_id[k] for k in sorted(by_id, key=lambda x: int(x[1:]))]
    return doc


def main() -> None:
    doc = merge(COURSE_DIR)
    course = doc["course"]
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if "--check" in sys.argv:
        print(f"ok: {len(course['sections'])} sections, "
              f"{sum(len(s['lessons']) for s in course['sections'])} lessons")
        return
    fd, tmp = tempfile.mkstemp(dir=COURSE_DIR, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, COURSE_DIR / "course.json")
    print(f"merged: {len(course['sections'])} sections")


if __name__ == "__main__":
    main()
