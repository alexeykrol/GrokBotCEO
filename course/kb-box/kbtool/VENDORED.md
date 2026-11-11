# Vendored: kbtool subset (BestMentor plugin)

| Field | Value |
|---|---|
| Version | 0.4.0 |
| Commit | 1b9aebb |
| Synced | 2026-11-10 |

The part of the owner's knowledge-base tool that Mentor needs on the bot computer, copied
unmodified. Standard library only (Python 3.9+), no model calls, no network.

- `kbtool/`: the build modules (scan, extract, markup reading, SQLite build). Used by
  `../build_kb.py`.
- `search.py`: the search script of a ready base ("base in a box"). Used by `../search.py`.

Not included: the command line, the markup prompts and the packing scripts; markup is done by
the owner, the result ships in `course/kb-markup/`.

Do not edit these files: they are replaced whole on update.
