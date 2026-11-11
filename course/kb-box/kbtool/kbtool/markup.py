"""Markup: batches for the model, accepting its output by contract, vocabulary merges (SPEC §5 steps 4–8).

The model (a host subagent) only makes judgments and returns TSV sections. The code:
splits into batches, assembles the prompt with ids and paths, checks completeness and closed lists,
rejects the whole output on any error (S4), finds candidate concept merges.
Markup is the ``markup/*.tsv`` files (they survive a base rebuild; K1).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import guards
from .config import EDGE_CONFIDENCE, EDGE_TYPES, Base, KbError, write_private
from .ingest import load_extract
from .runlog import log_run, set_status
from .tsvio import append_tsv, fold, norm_concept, read_tsv, write_tsv  # noqa: F401 (re-export)

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
UNIT_COLS = ["id", "category", "subtopic", "genre", "practical", "summary"]
CONCEPT_COLS = ["id", "concept", "weight", "definition"]
EDGE_COLS = ["src", "dst", "type", "confidence", "note"]
VMAP_COLS = ["old", "canonical"]
SECTIONS = {"units": UNIT_COLS, "concepts": CONCEPT_COLS, "edges": EDGE_COLS, "vocab-map": VMAP_COLS}


def all_markup(base: Base, kind: str) -> list[tuple[str, dict]]:
    """Rows of all ``<kind>-*.tsv`` and ``<kind>.tsv`` files with the source file name."""
    out = []
    files = sorted(base.markup.glob(f"{kind}-*.tsv"))
    if (base.markup / f"{kind}.tsv").exists():
        files.append(base.markup / f"{kind}.tsv")
    for p in files:
        out.extend((p.name, r) for r in read_tsv(p))
    return out


def vocab_map(base: Base) -> dict[str, str]:
    m = {norm_concept(r["old"]): norm_concept(r["canonical"]) for r in read_tsv(base.markup / "vocab-map.tsv")}
    for k in list(m):                                    # chains a->b->c are collapsed by code
        seen = {k}
        while m[k] in m and m[k] not in seen:
            seen.add(m[k])
            m[k] = m[m[k]]
    return m


def vocabulary(base: Base) -> Counter:
    vm = vocab_map(base)
    return Counter(vm.get(norm_concept(r["concept"]), norm_concept(r["concept"]))
                   for _, r in all_markup(base, "concepts"))


def marked_ids(base: Base) -> set[str]:
    return {r["id"] for _, r in all_markup(base, "units")}


# ---------------------------------------------------------------------------- batches
def _next_name(base: Base, prefix: str) -> int:
    nums = [int(m.group(1)) for p in list(base.batches.glob(f"{prefix}*.json")) + list(base.markup.glob(f"*-{prefix}*.tsv"))
            for m in [re.search(rf"{prefix}(\d+)", p.name)] if m]
    return max(nums, default=0) + 1


def batch_plan(base: Base, redo: bool = False) -> list[dict]:
    ex = load_extract(base)
    cfg = base.config()
    cap = cfg["limits"]["batch_chars"]
    done = set() if redo else marked_ids(base)
    units = [u for u in ex["units"] if u["id"] not in done]
    units.sort(key=lambda u: (str(Path(u["path"]).parent), u["date"], u["path"], u["part_no"]))
    batches, cur, size = [], [], 0
    for u in units:
        if cur and size + u["chars"] > cap:
            batches.append(cur)
            cur, size = [], 0
        cur.append(u["id"])
        size += u["chars"]
    if cur:
        batches.append(cur)
    start = _next_name(base, "b")
    out = []
    for i, ids in enumerate(batches):
        name = f"b{start + i:02d}"
        rec = dict(name=name, units=ids, chars=sum(u["chars"] for u in units if u["id"] in set(ids)))
        write_private(base.batches / f"{name}.json", json.dumps(rec, ensure_ascii=False, indent=1))
        out.append(rec)
    set_status(base, "batch-plan", batches=len(out), pending_units=len(units))
    return out


def _load_batch(base: Base, name: str) -> dict:
    p = base.batches / f"{name}.json"
    if not p.exists() or not re.fullmatch(r"[be]\d{2,4}", name):
        raise KbError(f"no batch {name}")
    return json.loads(p.read_text(encoding="utf-8"))


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def batch_prompt(base: Base, name: str) -> str:
    """Full prompt for the reader subagent: frame, task, batch context, output contract."""
    b = _load_batch(base, name)
    cfg = base.config()
    ex = {u["id"]: u for u in load_extract(base)["units"]}
    vocab = vocabulary(base)
    defs = {norm_concept(r["concept"]): r.get("definition", "") for _, r in all_markup(base, "concepts")
            if r.get("definition")}
    lines = [_prompt("01-read.md"), "", _prompt("03-concepts.md"), "", "## Batch context " + name, ""]
    cats = cfg.get("categories") or []
    lines.append("Categories (closed list): " + (", ".join(cats) if cats else
                 "not set — propose a short category (1–2 words), the same for similar documents"))
    lines.append("Genres (closed list): " + ", ".join(cfg["genres"]))
    if vocab:
        lines.append(f"Current concept vocabulary ({len(vocab)}; use these spellings, add a new one only if none fits):")
        lines.extend(f"- {c}" + (f" — {defs[c]}" if defs.get(c) else "") for c, _ in sorted(vocab.items()))
    else:
        lines.append("The concept vocabulary is empty — this batch starts it.")
    lines.append("")
    lines.append("Batch units (read each file with the Read tool; the path is absolute):")
    for uid in b["units"]:
        u = ex[uid]
        lines.append(f"- id={uid} · date {u['date']} · {u['chars']} chars · file {base.units_dir / (uid + '.txt')}"
                     f" · title: {u['title']}")
    lines.append("")
    lines.append(f"Answer — only two TSV sections (#units, #concepts) exactly per the contract; {len(b['units'])} rows in #units.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- import
def parse_sections(text: str) -> dict[str, list[list[str]]]:
    """Model output -> sections. ``` code fences are stripped; anything outside a section is an error."""
    secs: dict[str, list[list[str]]] = {}
    cur = None
    for n, line in enumerate(text.splitlines(), 1):
        s = line.rstrip("\r")
        if not s.strip() or s.strip().startswith("```"):
            continue
        if s.startswith("#"):
            key = s[1:].strip().lower()
            if key not in SECTIONS:
                raise KbError(f"line {n}: unknown section {s[:40]!r}")
            cur = key
            secs.setdefault(cur, [])
            continue
        if cur is None:
            raise KbError(f"line {n}: text outside a section — output does not follow the contract")
        secs[cur].append(s.split("\t"))
    return secs


def _rows(secs, key, errors) -> list[dict]:
    cols = SECTIONS[key]
    raw = secs.get(key, [])
    if raw and [c.strip().lower() for c in raw[0]] == cols:
        raw = raw[1:]
    out = []
    for i, cells in enumerate(raw, 1):
        if key == "concepts" and len(cells) == len(cols) - 1:
            cells = cells + [""]                 # models often drop an empty optional definition at the end of the row
        if len(cells) != len(cols):
            errors.append(f"#{key} row {i}: {len(cells)} fields instead of {len(cols)}")
            continue
        row = dict(zip(cols, (c.strip() for c in cells)))
        for c, v in row.items():
            bad = guards.unsafe_markup_field(v)
            if bad:
                errors.append(f"#{key} row {i}: field {c} rejected ({bad})")
        out.append(row)
    return out


def validate_reader(base: Base, batch: dict, text: str) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    cfg = base.config()
    errors: list[str] = []
    try:
        secs = parse_sections(text)
    except KbError as exc:
        return [], [], [], [str(exc)]
    ids = set(batch["units"])
    units = _rows(secs, "units", errors)
    concepts = _rows(secs, "concepts", errors)
    vmap = _rows(secs, "vocab-map", errors)
    if "edges" in secs:
        errors.append("#edges is not expected in the reader output")
    seen = Counter(u["id"] for u in units)
    for uid in ids - set(seen):
        errors.append(f"#units: no row for {uid}")
    for uid, n in seen.items():
        if uid not in ids:
            errors.append(f"#units: foreign id {uid}")
        elif n > 1:
            errors.append(f"#units: id {uid} repeated {n} times")
    cats = set(cfg.get("categories") or [])
    genres = set(cfg["genres"])
    for u in units:
        if cats and u["category"] not in cats:
            errors.append(f"#units {u['id']}: category {u['category']!r} not in the list")
        if not cats and not (1 <= len(u["category"]) <= 40):
            errors.append(f"#units {u['id']}: category empty or longer than 40")
        if len(u["subtopic"]) > 40:
            errors.append(f"#units {u['id']}: subtopic longer than 40")
        if u["genre"] not in genres:
            errors.append(f"#units {u['id']}: genre {u['genre']!r} not in the list")
        if u["practical"] not in ("0", "1"):
            errors.append(f"#units {u['id']}: practical must be 0 or 1")
        if not (20 <= len(u["summary"]) <= 500):
            errors.append(f"#units {u['id']}: summary {len(u['summary'])} chars (need 20–500)")
    per_unit = Counter()
    pairs = set()
    genre_of = {u["id"]: u["genre"] for u in units}
    for c in concepts:
        c["concept"] = norm_concept(c["concept"])
        if c["id"] not in ids:
            errors.append(f"#concepts: foreign id {c['id']}")
        if not (2 <= len(c["concept"]) <= 60):
            errors.append(f"#concepts {c['id']}: concept {c['concept']!r} length not 2–60")
        if c["weight"] not in ("1", "2"):
            errors.append(f"#concepts {c['id']}: weight {c['weight']!r} (need 1 or 2)")
        if len(c["definition"]) > 200:
            errors.append(f"#concepts {c['id']}: definition longer than 200")
        if (c["id"], c["concept"]) in pairs:
            errors.append(f"#concepts {c['id']}: concept {c['concept']!r} repeated")
        pairs.add((c["id"], c["concept"]))
        per_unit[c["id"]] += 1
    for uid in ids:
        n = per_unit[uid]
        if n > 6 or (n == 0 and genre_of.get(uid) != "noise"):
            errors.append(f"#concepts {uid}: {n} concepts (need 1–6; 0 only for noise)")
    return units, concepts, vmap, errors


def validate_edges(base: Base, group: dict, text: str) -> tuple[list[dict], list[dict], list[str]]:
    errors: list[str] = []
    try:
        secs = parse_sections(text)
    except KbError as exc:
        return [], [], [str(exc)]
    allowed = set(group["units"]) | set(group.get("neighbors", []))
    dates = {u["id"]: u["date"] for u in load_extract(base)["units"]}
    edges = _rows(secs, "edges", errors)
    vmap = _rows(secs, "vocab-map", errors)
    if set(secs) - {"edges", "vocab-map"}:
        errors.append("the edge tagger output may contain only #edges (and #vocab-map)")
    seen = set()
    for e in edges:
        key = (e["src"], e["dst"], e["type"])
        for k in ("src", "dst"):
            if e[k] not in allowed:
                errors.append(f"#edges: {k} {e[k]} not in the group")
        if e["src"] == e["dst"]:
            errors.append(f"#edges: self-loop {e['src']}")
        if e["type"] not in EDGE_TYPES:
            errors.append(f"#edges: type {e['type']!r} not in the list")
        if e["confidence"] not in EDGE_CONFIDENCE:
            errors.append(f"#edges: confidence {e['confidence']!r} not in the list")
        if not (10 <= len(e["note"]) <= 300):
            errors.append(f"#edges {e['src']}→{e['dst']}: note {len(e['note'])} chars (need 10–300)")
        if e["type"] in ("develops", "revisits") and dates.get(e["src"]) and dates.get(e["dst"]) \
                and dates[e["src"]] < dates[e["dst"]]:
            errors.append(f"#edges {e['src']}→{e['dst']}: {e['type']} requires src to be no earlier than dst")
        if key in seen:
            errors.append(f"#edges: duplicate {key}")
        seen.add(key)
    return edges, vmap, errors


def _validate_vmap(base: Base, vmap: list[dict], extra_concepts: set[str], errors: list[str]) -> None:
    known = set(vocabulary(base)) | extra_concepts | {norm_concept(r["concept"]) for _, r in all_markup(base, "concepts")}
    for r in vmap:
        r["old"], r["canonical"] = norm_concept(r["old"]), norm_concept(r["canonical"])
        if r["old"] == r["canonical"]:
            errors.append(f"#vocab-map: {r['old']!r} -> maps to itself")
        if r["old"] not in known:
            errors.append(f"#vocab-map: concept {r['old']!r} is not in the markup")
        if not (2 <= len(r["canonical"]) <= 60):
            errors.append(f"#vocab-map: canonical {r['canonical']!r} length not 2–60")


def markup_import(base: Base, name: str, text: str) -> dict:
    """Accept model output for a batch (bNN) or an edge group (eNN). All or nothing (S4)."""
    batch = _load_batch(base, name)
    if name.startswith("b"):
        units, concepts, vmap, errors = validate_reader(base, batch, text)
        _validate_vmap(base, vmap, {c["concept"] for c in concepts}, errors)
        if errors:
            log_run(base, f"import-{name}", units_in=len(batch["units"]), errors=errors)
            raise KbError(f"output for {name} rejected whole ({len(errors)} errors):\n  " + "\n  ".join(errors[:40]))
        write_tsv(base.markup / f"units-{name}.tsv", UNIT_COLS, units)
        write_tsv(base.markup / f"concepts-{name}.tsv", CONCEPT_COLS, concepts)
        res = dict(batch=name, units=len(units), concepts=len(concepts), vocab_map=len(vmap))
    else:
        edges, vmap, errors = validate_edges(base, batch, text)
        _validate_vmap(base, vmap, set(), errors)
        if errors:
            log_run(base, f"import-{name}", units_in=len(batch["units"]), errors=errors)
            raise KbError(f"output for {name} rejected whole ({len(errors)} errors):\n  " + "\n  ".join(errors[:40]))
        write_tsv(base.markup / f"edges-{name}.tsv", EDGE_COLS, edges)
        res = dict(group=name, edges=len(edges), vocab_map=len(vmap))
    if vmap:
        rows = {r["old"]: r for r in read_tsv(base.markup / "vocab-map.tsv")}
        rows.update({r["old"]: r for r in vmap})
        write_tsv(base.markup / "vocab-map.tsv", VMAP_COLS, list(rows.values()))
    log_run(base, f"import-{name}", units_in=len(batch["units"]), units_out=res.get("units", res.get("edges", 0)))
    set_status(base, f"import-{name}", **{k: v for k, v in res.items() if isinstance(v, int)})
    return res


def vocab_import(base: Base, text: str) -> dict:
    """Concept merge table (#vocab-map old->canonical) — the model's/user's decision on the candidates."""
    errors: list[str] = []
    try:
        secs = parse_sections(text)
    except KbError as exc:
        raise KbError(f"merges rejected: {exc}") from None
    if set(secs) - {"vocab-map"}:
        errors.append("only the #vocab-map section is expected")
    vmap = _rows(secs, "vocab-map", errors)
    _validate_vmap(base, vmap, set(), errors)
    if errors:
        raise KbError("merges rejected whole:\n  " + "\n  ".join(errors[:40]))
    rows = {r["old"]: r for r in read_tsv(base.markup / "vocab-map.tsv")}
    rows.update({r["old"]: r for r in vmap})
    write_tsv(base.markup / "vocab-map.tsv", VMAP_COLS, list(rows.values()))
    log_run(base, "vocab-import", units_in=len(vmap), units_out=len(rows))
    return dict(merged=len(vmap), total_map=len(rows), vocabulary=len(vocabulary(base)))


# ---------------------------------------------------------------------------- vocabulary
def _lev(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
        if min(prev) > cap:
            return cap + 1
    return prev[-1]


def _stem(w: str) -> str:
    return w[:max(4, len(w) - 2)]


def vocab_candidates(base: Base) -> dict:
    """Candidate concept merges (code); the model/user decides (05-merge-vocab.md)."""
    voc = vocabulary(base)
    names = sorted(voc)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            fa, fb = fold(a), fold(b)
            why = None
            if fa == fb:
                why = "spelling"
            elif min(len(fa), len(fb)) >= 6 and _lev(fa, fb) <= 2:
                why = "typo/form"
            elif [_stem(w) for w in fa.split()] == [_stem(w) for w in fb.split()]:
                why = "shared stems"
            elif set(fa.split()) < set(fb.split()) or set(fb.split()) < set(fa.split()):
                why = "one contains the other"
            elif {_stem(w) for w in fa.split() if len(w) >= 6} & {_stem(w) for w in fb.split() if len(w) >= 6}:
                why = "shared word"
            if why:
                pairs.append(dict(a=a, a_units=voc[a], b=b, b_units=voc[b], why=why))
    lo, hi = base.config().get("vocab_corridor", [30, 70])
    return dict(size=len(voc), corridor=[lo, hi], in_corridor=lo <= len(voc) <= hi, pairs=pairs,
                singletons=sorted(c for c, n in voc.items() if n == 1))


# ---------------------------------------------------------------------------- edges plan
def cards(base: Base) -> dict[str, dict]:
    ex = {u["id"]: u for u in load_extract(base)["units"]}
    vm = vocab_map(base)
    out = {}
    for _, r in all_markup(base, "units"):
        if r["id"] in ex:
            u = ex[r["id"]]
            out[r["id"]] = dict(id=r["id"], date=u["date"], title=u["title"], category=r["category"],
                                genre=r["genre"], summary=r["summary"], concepts=[])
    for _, r in all_markup(base, "concepts"):
        if r["id"] in out:
            c = norm_concept(r["concept"])
            out[r["id"]]["concepts"].append((vm.get(c, c), int(r["weight"] or 1)))
    return out


def _card_text(c: dict) -> str:
    cs = ", ".join(f"{n}({w})" for n, w in sorted(c["concepts"], key=lambda x: -x[1]))
    return f"- id={c['id']} · {c['date']} · {c['category']}/{c['genre']} · {c['title']}\n  summary: {c['summary']}\n  concepts: {cs}"


def edge_plan(base: Base, neighbors_k: int = 5) -> list[dict]:
    cs = cards(base)
    cap = base.config()["limits"]["batch_chars"]
    order = sorted(cs.values(), key=lambda c: (max(c["concepts"], key=lambda x: x[1])[0] if c["concepts"] else "",
                                                c["date"]))
    groups, cur, size = [], [], 0
    for c in order:
        n = len(_card_text(c))
        if cur and size + n > cap:
            groups.append(cur)
            cur, size = [], 0
        cur.append(c["id"])
        size += n
    if cur:
        groups.append(cur)
    by_concept = defaultdict(set)
    for c in cs.values():
        for name, _ in c["concepts"]:
            by_concept[name].add(c["id"])
    start = _next_name(base, "e")
    out = []
    for i, ids in enumerate(groups):
        inside = set(ids)
        score = Counter()
        for uid in ids:
            for name, w in cs[uid]["concepts"]:
                for other in by_concept[name] - inside:
                    score[other] += w
        nb = [o for o, _ in score.most_common(neighbors_k)] if len(groups) > 1 else []
        rec = dict(name=f"e{start + i:02d}", units=ids, neighbors=nb)
        write_private(base.batches / f"{rec['name']}.json", json.dumps(rec, ensure_ascii=False, indent=1))
        out.append(rec)
    set_status(base, "edge-plan", groups=len(out), cards=len(cs))
    return out


def edge_prompt(base: Base, name: str) -> str:
    g = _load_batch(base, name)
    cs = cards(base)
    lines = [_prompt("04-edges.md"), "", f"## Cards of group {name} ({len(g['units'])})", ""]
    lines += [_card_text(cs[u]) for u in g["units"] if u in cs]
    if g.get("neighbors"):
        lines += ["", "## Neighbours from other groups (edges to them are allowed)", ""]
        lines += [_card_text(cs[u]) for u in g["neighbors"] if u in cs]
    lines += ["", "Answer — only the #edges section exactly per the contract."]
    return "\n".join(lines)


def pending(base: Base) -> list[dict]:
    done = marked_ids(base)
    return [u for u in load_extract(base)["units"] if u["id"] not in done]
