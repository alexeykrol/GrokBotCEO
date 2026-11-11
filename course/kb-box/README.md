# Mentor knowledge base

The base Mentor answers from when a question falls outside the current lesson. The release ships
no built base: it ships the course articles (`../kb/`), their markup (`../kb-markup/`: summaries,
concepts, typed links, concept → lesson links) and the code to build and search. The user's bot
builds the base on the bot computer in a fraction of a second, at install and again whenever the
course files change.

| File | What it is |
|---|---|
| `build_kb.py` | builds the base into `<workspace>/mentor/kb/base/` (deterministic, atomic, idempotent) |
| `search.py` | the command to call; builds the base first if it is missing, damaged or stale |
| `kbtool/` | vendored part of the owner's knowledge-base tool (build modules + search script), unmodified; see `kbtool/VENDORED.md` |

```bash
python3 course/kb-box/build_kb.py --kb-home <workspace>/mentor
python3 course/kb-box/search.py ask "как удалить бота" --kb-home <workspace>/mentor
python3 course/kb-box/search.py --unit <id> --kb-home <workspace>/mentor
python3 course/kb-box/search.py miss "вопрос, на который ответа не нашлось" --kb-home <workspace>/mentor
```

Every result carries a unit id and a quote; a search also lists the course lessons on the found
topics (`lessons`). If nothing is found, Mentor says honestly that the base has no answer and
records a miss. Writes: the derived base in `<workspace>/mentor/kb/` (not kept in the history of
changes) and the user's records (misses, verdicts) in `<workspace>/mentor/kb-user/`. Nothing is
written inside the release copy. Standard library only, no model, no network.
