"""Opening ``kb.sqlite`` (moved out of store.py in 0.3.0 — search does not need the build modules).

A self-built base (``~/.kb/<slug>/``) is opened for writing only for user records.
The plugin's ready-made base (``skills/kb-ask/data/``) is always read-only: ``mode=ro`` and
``immutable=1`` (the plugin folder may be read-only; no journal or -wal next to it).
"""
from __future__ import annotations

import sqlite3
from urllib.parse import quote

from . import SCHEMA_VERSION
from .config import KbError


def db_uri(path, readonly: bool = True, immutable: bool = False) -> str:
    uri = f"file:{quote(str(path))}?mode={'ro' if readonly else 'rw'}"
    return uri + ("&immutable=1" if immutable else "")


def connect(base, write: bool = False) -> sqlite3.Connection:
    if not base.db.exists():
        raise KbError(f"no base: {base.db} — run kbtool build first")
    boxed = getattr(base, "boxed", False)
    if write and boxed:
        raise KbError("the plugin's ready-made base is opened read-only")
    con = sqlite3.connect(db_uri(base.db, readonly=not write, immutable=boxed), uri=True)
    con.row_factory = sqlite3.Row
    v = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if not v or int(v[0]) != SCHEMA_VERSION:
        con.close()
        raise KbError("the base schema version does not match the plugin — rebuild: kbtool build")
    return con
