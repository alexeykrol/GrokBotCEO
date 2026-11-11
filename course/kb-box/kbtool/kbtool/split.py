"""Long document -> parts at paragraph boundaries (SPEC §5 step 3, methodology K8).

Contract: ``"".join(split_text(t, n)) == t`` byte for byte; every part <= n chars; split at blank
lines, inside a paragraph that is too long — at newlines, then at sentence ends, as a last resort —
hard. The "reconstruction == source" contract idea comes from SD scripts/_chunk.py (INV-11); the
code is written anew for the flat "part = unit" model.
"""
from __future__ import annotations

import re

_LEVELS = (re.compile(r"(\n[ \t]*\n+)"), re.compile(r"(\n)"), re.compile(r"((?<=[.!?…])\s+)"))


def _pieces(text: str, level: int) -> list[str]:
    """Pieces of text with the separator attached to the left piece; their concatenation = the text."""
    parts = _LEVELS[level].split(text)
    out = []
    for i in range(0, len(parts), 2):
        chunk = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
        if chunk:
            out.append(chunk)
    return out


def _atoms(text: str, limit: int, level: int = 0) -> list[str]:
    if len(text) <= limit:
        return [text]
    if level >= len(_LEVELS):
        return [text[i:i + limit] for i in range(0, len(text), limit)]
    out = []
    for piece in _pieces(text, level):
        out.extend(_atoms(piece, limit, level + 1) if len(piece) > limit else [piece])
    return out


def split_text(text: str, limit: int) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for atom in _atoms(text, limit):
        if cur and len(cur) + len(atom) > limit:
            parts.append(cur)
            cur = ""
        cur += atom
    if cur:
        parts.append(cur)
    assert "".join(parts) == text
    return parts
