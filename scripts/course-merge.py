#!/usr/bin/env python3
"""Merge course/sections/S*.json into course/course.json and add the bookkeeping fields.

Each section file holds one section object (as in course.json "sections"). A section file
replaces the section with the same id; section order follows the id (S1, S2, ...). The top-level
fields of course.json (id, version, language, changes) are kept from course.json itself.

Generated per step (never written by hand; SCHEMA.md §2.7):
  content_version   sha256 (16 hex) of the step's content: the step without generated fields,
                    the lesson section named by text_ref (text + its sha256), the canonical record
                    of every claim it depends on, and for checks the rubric and the scenarios
  basis, claims, claims_status        from the step -> claims map (claims-map.tsv)
  route, required, eligible, scenarios, rubric_ref   for exercise and quiz steps
Generated at course level: "rubrics" (from rubrics.tsv).

Build inputs that are not shipped (paths default to the development repo, see --help):
  docs/design/claims-p0a.tsv   claims registry
  docs/design/claims-map.tsv   step -> claims map
  docs/design/rubrics.tsv      accepted rubrics

The "changes" journal entry of the current version is checked against the previous course
(course.json of version "from"): added/removed must equal the id difference, every step present in
both versions whose content_version differs must be in "changed", and "important" must be a subset
of added + changed. The previous course is --previous FILE, or --previous-ref REF
(git show REF:<path of course.json>), or by default the newest commit in git history whose
course.json has version == "from" (git log on the course file). A previous course built before
P1 has no content_version: it is computed only from that revision's own inputs taken from git
(lesson files, and claims/map/rubrics tables if they existed then); a dependency without a
historical source makes the step count as changed. A table counts as absent only when git lists
nothing at that path; a failed listing, a listed lesson or table that cannot be read or loaded, or a
table outside the repository fails the build (B-095). With --previous FILE there is no history, so
every step with a dependency counts as changed.

Situations (P2b, SCHEMA.md §2.3, §2.8): a quiz may carry "primary_scenario_id" (default: the step id)
and "situations" (extra situations, each {id, question, options, rubric_ref}). The build checks them,
puts one "scenarios" entry per situation (option_ids sorted by id) and canonicalises content_version:
the options of every situation are hashed sorted by id, so a permutation keeps the version.
Every situation of a quiz has an answer_version (question, options {id, text, correct} sorted by id,
the resolved rubric text or "-"; whitespace normalised; reactions and rubric status excluded). The
append-only registry course/scenario-registry.tsv pins scenario_id -> (step, answer_version) over the
whole released history: an id seen with another answer_version or under another step fails the
build; a new id is appended. --init-registry creates the registry from the released course versions
in git (0.1.0 = ea17f9e, 0.2.0 = the newest commit whose course.json has version 0.2.0) and prints
the coverage report.

Writes atomically. --check validates and reports whether course.json is up to date, writes nothing.
"""
import argparse
import copy
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
COURSE_DIR = SCRIPT_DIR.parent / "course"
DEV_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_CLAIMS = DEV_ROOT / "docs" / "design" / "claims-p0a.tsv"
DEFAULT_MAP = DEV_ROOT / "docs" / "design" / "claims-map.tsv"
DEFAULT_RUBRICS = DEV_ROOT / "docs" / "design" / "rubrics.tsv"
DEFAULT_REGISTRY = COURSE_DIR / "scenario-registry.tsv"
REGISTRY_FIELDS = ("scenario_id", "step", "answer_version", "first_course_version", "note")
# Released course versions read by --init-registry (design p2b-quizzes.md §3). 0.2.0 is resolved as the
# newest commit whose course.json has that version.
RELEASES = (("0.1.0", "ea17f9e"), ("0.2.0", None))

GENERATED = ("content_version", "basis", "claims", "claims_status", "route", "required",
             "eligible", "scenarios", "rubric_ref")
CHECK_TYPES = ("exercise", "quiz")
BASES = ("claims", "normative", "unmapped")
CLAIM_STATUS_ORDER = {"verified": 0, "unverified": 1, "disputed": 2}
CLAIM_FIELDS = ("claim_id", "quote_en", "translation_ru", "our_inference", "scope", "risk",
                "status", "doc_basis", "observed")
RUBRIC_STATUSES = ("accepted", "candidate")


class BuildError(Exception):
    pass


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(text: str, n: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def slug(heading: str) -> str:
    h = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return h.replace(" ", "-")


# ---------- inputs ----------

def read_tsv(path: Path):
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t", quoting=csv.QUOTE_NONE))


def load_claims(path: Path) -> dict:
    claims = {}
    for row in read_tsv(path):
        cid = row.get("claim_id", "").strip()
        if not cid:
            continue
        if cid in claims:
            raise BuildError(f"claims: duplicate {cid}")
        status = row.get("status", "").strip()
        if status not in CLAIM_STATUS_ORDER:
            raise BuildError(f"claims: {cid} has status {status!r}, expected one of {sorted(CLAIM_STATUS_ORDER)}")
        claims[cid] = {k: (row.get(k) or "").strip() for k in CLAIM_FIELDS}
    return claims


def load_rubrics(path: Path) -> dict:
    rubrics = {}
    for row in read_tsv(path):
        rid, step = row["rubric_id"].strip(), row["step_id"].strip()
        if rid in rubrics:
            raise BuildError(f"rubrics: duplicate {rid}")
        if row["status"].strip() not in RUBRIC_STATUSES:
            raise BuildError(f"rubrics: {rid} status {row['status']!r}")
        if not row["text"].strip():
            raise BuildError(f"rubrics: {rid} has no text")
        rubrics[rid] = {"step": step, "status": row["status"].strip(), "text": row["text"].strip()}
    return rubrics


def load_map(path: Path, claims: dict) -> dict:
    rows = {}
    for row in read_tsv(path):
        key, basis = row["step_id"].strip(), row["basis"].strip()
        ids = [c.strip() for c in row["claim_ids"].split(",") if c.strip() and c.strip() != "-"]
        if key in rows:
            raise BuildError(f"claims-map: duplicate row {key}")
        if basis not in BASES:
            raise BuildError(f"claims-map: {key} basis {basis!r}")
        if basis == "claims" and not ids:
            raise BuildError(f"claims-map: {key} basis claims without claim ids")
        if basis != "claims" and ids:
            raise BuildError(f"claims-map: {key} basis {basis} must have claim_ids '-'")
        for c in ids:
            if c not in claims:
                raise BuildError(f"claims-map: {key} unknown claim {c}")
        rows[key] = {"basis": basis, "claims": ids}
    return rows


# ---------- lesson sections ----------

def lesson_section(course_dir: Path, ref: str):
    """Text of the lesson section named by 'lessons/<file>.md#<anchor>'; exactly one heading must match."""
    if "#" not in ref:
        raise BuildError(f"text_ref {ref!r}: no #anchor")
    file_part, anchor = ref.split("#", 1)
    path = course_dir / file_part
    if not path.is_file():
        raise BuildError(f"text_ref {ref!r}: file missing")
    lines = path.read_text(encoding="utf-8").splitlines()
    heads = [(i, len(l) - len(l.lstrip("#"))) for i, l in enumerate(lines)
             if l.startswith("#") and slug(l.lstrip("#")) == anchor]
    if len(heads) != 1:
        raise BuildError(f"text_ref {ref!r}: {len(heads)} matching headings (need exactly 1)")
    start, level = heads[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("#") and len(lines[j]) - len(lines[j].lstrip("#")) <= level:
            end = j
            break
    return "\n".join(lines[start:end]).strip() + "\n"


# ---------- course walking ----------

def iter_steps(course: dict):
    for section in course["sections"]:
        for lesson in section["lessons"]:
            for step in lesson["steps"]:
                yield section, lesson, step


def step_order(course: dict):
    return [s["id"] for _, _, s in iter_steps(course)]


def conditional_steps(course: dict) -> set:
    """Steps that only some paths through a branch visit (symmetric difference before the paths merge)."""
    order = step_order(course)
    pos = {sid: i for i, sid in enumerate(order)}
    steps = {s["id"]: s for _, _, s in iter_steps(course)}

    def walk(start, limit=60):
        out, cur = [], start
        while cur in steps and len(out) < limit:
            out.append(cur)
            st = steps[cur]
            if st["type"] == "branch":
                cur = st["default"]
            elif st.get("next"):
                cur = st["next"]
            elif st["type"] == "checkpoint":
                break
            else:
                i = pos[cur] + 1
                cur = order[i] if i < len(order) else None
        return out

    result = set()
    for st in steps.values():
        if st["type"] != "branch":
            continue
        walks = [walk(c["next"]) for c in st.get("cases", [])] + [walk(st["default"])]
        common = set(walks[0]).intersection(*map(set, walks[1:]))
        for w in walks:
            for sid in w:
                if sid in common:
                    break
                result.add(sid)
    return result


# ---------- annotation ----------

def clean_step(step: dict) -> dict:
    return {k: v for k, v in step.items() if k not in GENERATED}


def by_id(options):
    return sorted(options, key=lambda o: str(o.get("id")))


def canonical_step(step: dict) -> dict:
    """The step as hashed into content_version: options of every situation sorted by id (their order is
    a display layout, not content). The order of the situations list and every other sequence is kept."""
    base = copy.deepcopy(clean_step(step))
    # primary_rubric_ref is how the rubric is referenced, not content: the resolved rubric is hashed
    # through the payload's "rubric" (§12 addendum 1), so writing the inferred choice keeps the version
    base.pop("primary_rubric_ref", None)
    if base.get("type") == "quiz":
        if isinstance(base.get("options"), list):
            base["options"] = by_id(base["options"])
        for sit in base.get("situations") or []:
            if isinstance(sit, dict) and isinstance(sit.get("options"), list):
                sit["options"] = by_id(sit["options"])
    return base


def primary_id(step: dict) -> str:
    return step.get("primary_scenario_id") or step["id"]


def compute_step(step, lesson, course_dir, claims, cmap, rubrics_by_step, conditional, rubrics=None):
    """Return the generated fields of one step (without mutating it)."""
    base = canonical_step(step)
    row = cmap.get(step["id"], {"basis": "unmapped", "claims": []})
    basis, claim_ids = row["basis"], list(row["claims"])
    text_ref = None
    if step.get("text_ref"):
        content = lesson_section(course_dir, step["text_ref"])
        text_ref = {"ref": step["text_ref"], "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}
        sec = cmap.get(step["text_ref"])
        if sec:
            if sec["claims"] and basis == "normative":
                raise BuildError(f"{step['id']}: normative but its text_ref section depends on claims {sec['claims']}")
            claim_ids += [c for c in sec["claims"] if c not in claim_ids]
    claim_ids = sorted(set(claim_ids))
    statuses = [claims[c]["status"] for c in claim_ids]
    claims_status = max(statuses, key=CLAIM_STATUS_ORDER.get) if statuses else "-"
    out = {"basis": basis, "claims": claim_ids, "claims_status": claims_status}
    rubric = None
    if step["type"] in CHECK_TYPES:
        rubric_id, rubric = rubrics_by_step.get(step["id"], (None, None))
        option_ids = sorted(o["id"] for o in step.get("options", [])) if step["type"] == "quiz" else []
        scenarios = [{"id": primary_id(step), "option_ids": option_ids, "rubric_ref": rubric_id or "-"}]
        for sit in step.get("situations") or []:
            scenarios.append({"id": sit["id"], "option_ids": sorted(o["id"] for o in sit.get("options", [])),
                              "rubric_ref": sit.get("rubric_ref", "-")})
        accepted = bool(rubric and rubric["status"] == "accepted")
        if basis == "claims":
            eligible = all(claims[c]["status"] == "verified" for c in claim_ids)
        elif basis == "normative":
            eligible = accepted
        else:
            eligible = False
        lesson_needs = bool(lesson.get("needs"))
        if step.get("optional_practice"):
            route = "optional_practice"
        elif step["id"] in conditional:
            route = "branch"
        else:
            route = "main"
        out.update({"route": route, "required": not (lesson_needs and step["type"] == "exercise"),
                    "eligible": eligible, "rubric_ref": rubric_id or "-", "scenarios": scenarios})
    payload = {"step": base, "text_ref": text_ref,
               "claims": [claims[c] for c in claim_ids],
               "rubric": rubric, "scenarios": out.get("scenarios")}
    sit_rubrics = {}
    for sit in step.get("situations") or []:
        ref = sit.get("rubric_ref", "-")
        if ref != "-":
            sit_rubrics[ref] = (rubrics or {}).get(ref)
    if sit_rubrics:                      # only when present: a step without situations hashes as before P2b
        payload["situation_rubrics"] = sit_rubrics
    out["content_version"] = sha(canon(payload))
    return out


# ---------- situations (P2b) ----------

def validate_situations(course: dict, rubrics: dict):
    """SCHEMA.md §2.3: situation ids unique in the course, option ids unique within a step over all its
    situations, exactly 3 options with one correct and non-empty texts and reactions, rubric_ref '-' or
    an existing rubric. Situations only on quiz steps."""
    errors, seen = [], {}
    for _, _, st in iter_steps(course):
        if st["type"] != "quiz":
            if "situations" in st or "primary_scenario_id" in st:
                errors.append(f"{st['id']}: situations / primary_scenario_id only on quiz steps")
            continue
        sits = st.get("situations") or []
        if not isinstance(sits, list):
            errors.append(f"{st['id']}: situations must be a list")
            continue
        ids = [primary_id(st)] + [x.get("id") for x in sits if isinstance(x, dict)]
        for sid in ids:
            if not isinstance(sid, str) or not sid:
                errors.append(f"{st['id']}: situation without id")
            elif sid in seen:
                errors.append(f"{st['id']}: situation id {sid} already used by {seen[sid]}")
            else:
                seen[sid] = st["id"]
        opt_ids = [o.get("id") for o in st.get("options", [])]
        for x in sits:
            if not isinstance(x, dict):
                errors.append(f"{st['id']}: a situation must be an object")
                continue
            where = f"{st['id']}/{x.get('id')}"
            if not str(x.get("question", "")).strip():
                errors.append(f"{where}: empty question")
            opts = x.get("options") or []
            if len(opts) != 3:
                errors.append(f"{where}: {len(opts)} options, need exactly 3")
            if sum(1 for o in opts if o.get("correct") is True) != 1:
                errors.append(f"{where}: need exactly one correct option")
            for o in opts:
                if not isinstance(o.get("correct"), bool):
                    errors.append(f"{where}.{o.get('id')}: correct must be bool")
                for k in ("id", "text", "reaction"):
                    if not str(o.get(k, "")).strip():
                        errors.append(f"{where}.{o.get('id')}: empty {k}")
            opt_ids += [o.get("id") for o in opts]
            ref = x.get("rubric_ref", "-")
            if ref != "-" and ref not in rubrics:
                errors.append(f"{where}: rubric_ref {ref} is not a rubric")
        dup = sorted({i for i in opt_ids if opt_ids.count(i) > 1}, key=str)
        if dup:
            errors.append(f"{st['id']}: option ids repeat across its situations: {dup}")
    if errors:
        raise BuildError("situations: " + "; ".join(errors))


def norm_ws(text) -> str:
    return " ".join(str(text or "").split())


def answer_version(question, options, rubric_text) -> str:
    """sha256 (16 hex) of the situation's answer: question, options {id, text, correct} sorted by id, the
    normalised text of the resolved rubric or '-'. Whitespace normalised; reactions and rubric status
    are not part of it (design p2b §3)."""
    body = {"question": norm_ws(question),
            "options": [{"id": o.get("id"), "text": norm_ws(o.get("text")), "correct": bool(o.get("correct"))}
                        for o in by_id(options)],
            "rubric": norm_ws(rubric_text) if rubric_text and norm_ws(rubric_text) else "-"}
    return sha(canon(body))


def course_situations(course: dict, rubrics=None):
    """[(scenario_id, step_id, answer_version)] for every situation of every quiz, in course order.
    rubrics: {id: {text, ...}}; default course["rubrics"] (a built course; an old course has none)."""
    rubrics = course.get("rubrics", {}) if rubrics is None else rubrics

    def text_of(ref):
        r = rubrics.get(ref) if ref and ref != "-" else None
        return r.get("text") if r else None

    out = []
    for _, _, st in iter_steps(course):
        if st.get("type") != "quiz":
            continue
        out.append((primary_id(st), st["id"],
                    answer_version(st.get("question"), st.get("options", []), text_of(st.get("rubric_ref", "-")))))
        for x in st.get("situations") or []:
            out.append((x["id"], st["id"],
                        answer_version(x.get("question"), x.get("options", []), text_of(x.get("rubric_ref", "-")))))
    return out


# ---------- scenario registry (P2b) ----------

def read_registry(path: Path):
    if not Path(path).is_file():
        raise BuildError(f"scenario registry {path} is missing: run course-merge.py --init-registry")
    rows = read_tsv(Path(path))
    for r in rows:
        if any(r.get(k) is None for k in REGISTRY_FIELDS):
            raise BuildError(f"scenario registry: malformed row {r}")
    return rows


def registry_line(row) -> str:
    return "\t".join(str(row[k]) for k in REGISTRY_FIELDS)


def check_registry(course: dict, rows):
    """Every situation of the course against the registry. Returns the rows to append (new ids).
    An id whose rows disagree (conflicting history) is forbidden; an id under another step, or with
    another answer_version, fails the build (clarification 1 of the P2b review: the row pins the step)."""
    by = {}
    for r in rows:
        by.setdefault(r["scenario_id"], []).append(r)
    errors, new = [], []
    for scen, step, av in course_situations(course):
        hist = by.get(scen)
        if not hist:
            row = {"scenario_id": scen, "step": step, "answer_version": av,
                   "first_course_version": course["version"], "note": "added by build"}
            new.append(row)
            by[scen] = [row]
            continue
        steps = {r["step"] for r in hist}
        avs = {r["answer_version"] for r in hist}
        if len(avs) > 1 or len(steps) > 1:
            errors.append(f"{scen}: forbidden id (conflicting history in the registry: "
                          f"steps {sorted(steps)}, answer_versions {sorted(avs)}); use a new id")
        elif steps != {step}:
            errors.append(f"{scen}: registered under step {next(iter(steps))}, now under {step}; "
                          "moving a task to another step needs a new id")
        elif avs != {av}:
            errors.append(f"{scen}: registered with answer_version {next(iter(avs))}, now {av}; "
                          "a changed question/option/key/rubric needs a new id")
    if errors:
        raise BuildError("scenario registry: " + "; ".join(errors))
    return new


def registry_superset(base_rows, cand_rows):
    """Errors if the candidate registry is not a line-by-line superset of the base registry."""
    cand = [registry_line(r) for r in cand_rows]
    errors = [f"base row changed or removed: {registry_line(r)}" for r in base_rows if registry_line(r) not in cand]
    base = [registry_line(r) for r in base_rows]
    if cand[:len(base)] != base and not errors:
        errors.append("base rows are not a prefix of the candidate registry (append-only order broken)")
    return errors


def registry_provenance(path: Path):
    """The registry's init provenance (P2b §3, fail closed): the '# Init sources:' header line must name
    every mandatory release (RELEASES) and 'unavailable: none'. A registry initialised from incomplete
    history cannot prove that an absent id is new, so the build does not trust it. Returns the error
    text or None."""
    heads = [l[1:].strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.startswith("#")]
    line = next((h for h in heads if h.startswith("Init sources:")), None)
    if line is None:
        return "no '# Init sources:' provenance line"
    missing = [v for v, _ in RELEASES if f"{v} = " not in line]
    if missing or not line.endswith("unavailable: none"):
        return f"init provenance incomplete ({line!r}; missing releases {missing})"
    return None


def render_registry(rows, header_lines=()):
    out = [f"# {h}" for h in header_lines]
    out.append("\t".join(REGISTRY_FIELDS))
    out += [registry_line(r) for r in rows]
    return "\n".join(out) + "\n"


class HistoryUnavailable(Exception):
    """A git object that should be readable is not (as opposed to a file absent at that commit)."""


def registry_init_rows(course_dir: Path):
    """Rows from the released course versions in git, plus the coverage report (design p2b §3)."""
    rel = git(["rev-parse", "--show-prefix"], course_dir)
    if rel.returncode != 0:
        raise BuildError("--init-registry needs a git checkout")
    path = rel.stdout.strip() + "course.json"
    log = git(["log", "--format=%h", "--", "course.json"], course_dir).stdout.split()
    coverage = {"releases": [], "other_commits": [], "unavailable": []}

    def at(ref):
        shown = git(["show", f"{ref}:{path}"], course_dir)
        if shown.returncode != 0:
            return None
        return json.loads(shown.stdout)["course"]

    # the rubric table's path inside the repository (the same layout in every checkout of it)
    relr = DEFAULT_RUBRICS.relative_to(DEV_ROOT).as_posix()
    toplevel = git(["rev-parse", "--show-toplevel"], course_dir)

    def hist_rubrics(ref):
        # pathspecs of ls-tree are relative to the cwd (unlike `git show ref:path`): list from the
        # repository root with full names and match the path exactly
        if toplevel.returncode != 0:
            raise HistoryUnavailable("git rev-parse --show-toplevel failed")
        top = Path(toplevel.stdout.strip())
        listed = git(["ls-tree", "--full-name", "--name-only", ref, "--", relr], top)
        if listed.returncode != 0:
            raise HistoryUnavailable(f"git ls-tree {ref} failed")
        if relr not in listed.stdout.splitlines():
            return {}                                    # no rubric table at that commit: no rubrics then
        shown = git(["show", f"{ref}:{relr}"], top)
        if shown.returncode != 0:
            raise HistoryUnavailable(f"{relr} at {ref} unreadable")
        with tempfile.TemporaryDirectory(prefix="registry-init-") as w:
            f = Path(w) / "rubrics.tsv"
            f.write_text(shown.stdout, encoding="utf-8")
            return load_rubrics(f)

    def situations_at(ref, course):
        rub = course.get("rubrics")
        if rub is None:                                   # built before P1: the rubric table of that commit
            hr = hist_rubrics(ref)
            by_step = {r["step"]: rid for rid, r in hr.items()}
            for _, _, st in iter_steps(course):
                if st.get("type") == "quiz" and st["id"] in by_step:
                    st["rubric_ref"] = by_step[st["id"]]
            rub = hr
        return course_situations(course, rub)

    releases = []
    for version, ref in RELEASES:
        if ref is None:                  # the newest commit with that version; an unreadable newer commit
            blocked = None               # makes the choice unknowable, never a silent older pick
            for r in log:
                c = at(r)
                if c is None:
                    blocked = r
                    break
                if c.get("version") == version:
                    ref = r
                    break
            if blocked:
                coverage["unavailable"].append({"version": version, "ref": blocked,
                                                "why": f"{blocked} unreadable while finding the newest {version}"})
                continue
        course = at(ref) if ref else None
        if course is None or course.get("version") != version:
            coverage["unavailable"].append({"version": version, "ref": ref,
                                            "why": "not in git" if course is None else f"version {course.get('version')}"})
            continue
        full = git(["rev-parse", ref], course_dir).stdout.strip()
        try:
            sits = situations_at(full, course)
        except HistoryUnavailable as e:
            coverage["unavailable"].append({"version": version, "ref": full[:7], "why": str(e)})
            continue
        releases.append((version, full[:7], sits))
        coverage["releases"].append({"version": version, "ref": full[:7],
                                     "quizzes": sum(1 for _, _, s in iter_steps(course) if s.get("type") == "quiz")})
    rows, by = [], {}
    for version, ref, sits in releases:
        for scen, step, av in sits:
            known = by.get(scen, [])
            if any(r["step"] == step and r["answer_version"] == av for r in known):
                continue
            note = f"init from {version} ({ref})"
            if known:
                note = f"conflict: {version} ({ref}) differs from {known[0]['first_course_version']}; id forbidden"
            row = {"scenario_id": scen, "step": step, "answer_version": av, "first_course_version": version,
                   "note": note}
            rows.append(row)
            by.setdefault(scen, []).append(row)
    release_refs = {r["ref"] for r in coverage["releases"]}
    for ref in log:
        full = git(["rev-parse", ref], course_dir).stdout.strip()
        if full[:7] in release_refs:
            continue
        course = at(full)
        if course is None:
            coverage["unavailable"].append({"version": None, "ref": full[:7], "why": "git show failed"})
            continue
        try:
            sits = situations_at(full, course)
        except HistoryUnavailable as e:
            coverage["unavailable"].append({"version": None, "ref": full[:7], "why": str(e)})
            continue
        differs = sorted(scen for scen, step, av in sits if scen in by
                         and not any(r["step"] == step and r["answer_version"] == av for r in by[scen]))
        absent = sorted(scen for scen, _, _ in sits if scen not in by)
        coverage["other_commits"].append({"ref": full[:7], "version": course.get("version"),
                                          "differs_from_release_rows": differs, "ids_not_in_any_release": absent})
    coverage["rows"] = len(rows)
    coverage["conflicts"] = sorted({r["scenario_id"] for r in rows if r["note"].startswith("conflict")})
    return rows, coverage


def primary_rubrics(course: dict, rubrics: dict) -> dict:
    """{step_id: (rubric_id, rubric)} — the rubric of each check step's primary situation (SCHEMA.md §2.3,
    design p2b §12 addendum 1).
    primary_rubric_ref set: "-" is an explicit absence (no lookup); an id must be a rubric of this step,
    used as is (its status is not changed: a non-accepted rubric gives no scoring).
    Not set: candidates = rubric rows of the step that no extra situation of the step names; exactly one ->
    it; none and exactly one row of the step (shared with a situation) -> it; no rows -> none; anything else
    is a BuildError asking for primary_rubric_ref. Never a silent downgrade or rebinding. The result does
    not depend on the order of the rubric rows."""
    rows = {}
    for rid, r in rubrics.items():
        rows.setdefault(r["step"], []).append(rid)
    out, errors = {}, []
    for _, _, st in iter_steps(course):
        if "primary_rubric_ref" in st:
            ref = st["primary_rubric_ref"]
            if st["type"] not in CHECK_TYPES:
                errors.append(f"{st['id']}: primary_rubric_ref only on exercise and quiz steps")
            elif not isinstance(ref, str) or not ref:
                errors.append(f"{st['id']}: primary_rubric_ref must be a rubric id or '-'")
            elif ref == "-":
                pass
            elif ref not in rubrics:
                errors.append(f"{st['id']}: primary_rubric_ref {ref} is not a rubric")
            elif rubrics[ref]["step"] != st["id"]:
                errors.append(f"{st['id']}: primary_rubric_ref {ref} belongs to {rubrics[ref]['step']}")
            else:
                out[st["id"]] = (ref, rubrics[ref])
            continue
        mine = sorted(rows.get(st["id"], []))
        if not mine:
            continue
        if st["type"] not in CHECK_TYPES:
            if len(mine) > 1:
                errors.append(f"{st['id']}: two rubrics for {st['id']}")
            continue          # a rubric of a non-check step is not used
        named = {x.get("rubric_ref") for x in st.get("situations") or [] if x.get("rubric_ref", "-") != "-"}
        cand = [rid for rid in mine if rid not in named]
        if len(cand) == 1:
            out[st["id"]] = (cand[0], rubrics[cand[0]])
        elif not cand and len(mine) == 1:
            out[st["id"]] = (mine[0], rubrics[mine[0]])
        else:
            errors.append(f"{st['id']}: ambiguous primary rubric: set primary_rubric_ref "
                          f"(rubrics of the step {mine}, named by situations {sorted(named)})")
    if errors:
        raise BuildError("rubrics: " + "; ".join(errors))
    return out


def annotate(course: dict, course_dir: Path, claims: dict, cmap: dict, rubrics: dict) -> dict:
    ids = set(step_order(course))
    for key in cmap:
        if key.startswith("lessons/"):
            lesson_section(course_dir, key)          # the section must resolve to exactly one heading
        elif key not in ids:
            raise BuildError(f"claims-map: step {key} not in the course")
    validate_situations(course, rubrics)
    for rid, r in rubrics.items():
        if r["step"] not in ids:
            raise BuildError(f"rubrics: {rid} step {r['step']} not in the course")
    rubrics_by_step = primary_rubrics(course, rubrics)
    conditional = conditional_steps(course)
    for _, lesson, step in iter_steps(course):
        gen = compute_step(step, lesson, course_dir, claims, cmap, rubrics_by_step, conditional, rubrics)
        for k in GENERATED:
            step.pop(k, None)
        if step["type"] in CHECK_TYPES:
            for k in ("route", "required", "eligible", "rubric_ref", "scenarios"):
                step[k] = gen[k]
        for k in ("basis", "claims", "claims_status", "content_version"):
            step[k] = gen[k]
    course["rubrics"] = {rid: {"step": r["step"], "status": r["status"], "text": r["text"]}
                         for rid, r in sorted(rubrics.items())}
    return course


def content_versions(course: dict, course_dir: Path, claims, cmap, rubrics) -> dict:
    """content_version per step id; stored values if the course was built with them, else computed."""
    steps = list(iter_steps(course))
    if steps and all("content_version" in s for _, _, s in steps):
        return {s["id"]: s["content_version"] for _, _, s in steps}
    tmp = copy.deepcopy(course)
    annotate(tmp, course_dir, claims, {k: v for k, v in cmap.items()
                                       if k.startswith("lessons/") or k in set(step_order(tmp))},
             {rid: r for rid, r in rubrics.items() if r["step"] in set(step_order(tmp))})
    return {s["id"]: s["content_version"] for _, _, s in iter_steps(tmp)}


def historical_versions(previous: dict, hist=None) -> dict:
    """content_version of each step of the previous course, from its own revision's inputs.

    A previous course built with content_version keeps its stored values. For an older course the
    value is computed only from that revision's inputs (hist: course_dir with its lesson files,
    claims, cmap, rubrics as they were; a missing table means the dependency did not exist then).
    Where a dependency has no historical source (a text_ref without the old lesson files, a claim
    the old map names but the old registry lacks) the value is None: unknown, i.e. changed.
    Today's lessons, claims, map or rubrics are never used for the previous course.
    """
    hist = hist or {}
    hdir = hist.get("course_dir")
    hclaims, hcmap, hrub = hist.get("claims") or {}, hist.get("cmap") or {}, hist.get("rubrics") or {}
    by_step = {r["step"]: (rid, r) for rid, r in hrub.items()}
    cond = conditional_steps(previous)
    out = {}
    for _, lesson, st in iter_steps(previous):
        if "content_version" in st:
            out[st["id"]] = st["content_version"]
            continue
        if st.get("text_ref") and hdir is None:
            out[st["id"]] = None
            continue
        try:
            out[st["id"]] = compute_step(st, lesson, Path(hdir or "."), hclaims, hcmap, by_step, cond)["content_version"]
        except (BuildError, KeyError):
            out[st["id"]] = None
    return out


# ---------- changes journal ----------

def validate_journal_shape(course: dict):
    changes = course.get("changes", [])
    if not isinstance(changes, list):
        raise BuildError("changes must be a list")
    seen = set()
    for e in changes:
        for k in ("version", "from", "added", "removed", "changed", "important", "note"):
            if k not in e:
                raise BuildError(f"changes {e.get('version')}: missing {k}")
        if e["version"] in seen:
            raise BuildError(f"changes: two entries for {e['version']}")
        seen.add(e["version"])
        for k in ("added", "removed", "changed", "important"):
            if not isinstance(e[k], list) or len(set(e[k])) != len(e[k]):
                raise BuildError(f"changes {e['version']}: {k} must be a list without duplicates")
        extra = set(e["important"]) - set(e["added"]) - set(e["changed"])
        if extra:
            raise BuildError(f"changes {e['version']}: important not in added/changed: {sorted(extra)}")
        if not isinstance(e["note"], str) or not e["note"].strip():
            raise BuildError(f"changes {e['version']}: empty note")


def validate_changes(course: dict, previous: dict, course_dir: Path, claims, cmap, rubrics, hist=None):
    """The journal entry of course.version must match the difference to the previous course.
    hist: the previous revision's own inputs (see historical_versions); without them every step with
    a dependency counts as changed."""
    validate_journal_shape(course)
    entry = next((e for e in course.get("changes", []) if e["version"] == course["version"]), None)
    if entry is None:
        raise BuildError(f"changes: no entry for version {course['version']}")
    if previous["version"] != entry["from"]:
        raise BuildError(f"changes {entry['version']}: previous course has version {previous['version']}, "
                         f"journal says from {entry['from']}")
    new_ids, old_ids = step_order(course), step_order(previous)
    added = [i for i in new_ids if i not in set(old_ids)]
    removed = [i for i in old_ids if i not in set(new_ids)]
    errors = []
    if set(entry["added"]) != set(added):
        errors.append(f"added: journal {sorted(entry['added'])} != diff {sorted(added)}")
    if set(entry["removed"]) != set(removed):
        errors.append(f"removed: journal {sorted(entry['removed'])} != diff {sorted(removed)}")
    new_cv = content_versions(course, course_dir, claims, cmap, rubrics)
    old_cv = historical_versions(previous, hist)
    both = set(new_ids) & set(old_ids)
    changed = sorted(i for i in both if old_cv[i] is None or new_cv[i] != old_cv[i])
    missing = sorted(set(changed) - set(entry["changed"]))
    if missing:
        errors.append(f"changed: content_version differs but not in journal: {missing}")
    stray = sorted(set(entry["changed"]) - both)
    if stray:
        errors.append(f"changed: not a step of both versions: {stray}")
    if errors:
        raise BuildError(f"changes {entry['version']}: " + "; ".join(errors))
    return {"added": added, "removed": removed, "changed": changed}


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def previous_course(course_dir: Path, from_version: str, ref=None, path=None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))["course"], None
    prefix = git(["rev-parse", "--show-prefix"], course_dir)
    if prefix.returncode != 0:
        raise BuildError("previous course: not a git checkout; pass --previous FILE")
    rel = prefix.stdout.strip() + "course.json"
    refs = [ref] if ref else git(["log", "--format=%H", "--", "course.json"], course_dir).stdout.split()
    for r in refs:
        shown = git(["show", f"{r}:{rel}"], course_dir)
        if shown.returncode != 0:
            continue
        doc = json.loads(shown.stdout)["course"]
        if ref or doc.get("version") == from_version:
            return doc, r
    raise BuildError(f"previous course: no commit with course.json version {from_version}; pass --previous FILE")


def historical_inputs(course_dir: Path, ref: str, workdir: Path, claims_path: Path, map_path: Path,
                      rubrics_path: Path) -> dict:
    """Materialise the previous revision's lesson files and build tables (those that existed) from git.

    Fail closed (B-095): a table counts as absent at ref only when `git ls-tree ref -- <path>` succeeds with
    empty output; then the dependency did not exist then (empty table). A listing that fails or lists
    something other than the exact path, a table or lesson that is listed but cannot be read or loaded, and a
    table outside the repository (its history cannot be established) raise BuildError: a read error is not
    proof of absence. Names are handled as bytes (no newline translation: a CR in a name is kept)."""
    def raw(args, cwd):                               # bytes in, bytes out; the shared git() is text mode
        return subprocess.run(["git", "--literal-pathspecs", *args], cwd=cwd, capture_output=True)

    def line(out: bytes) -> bytes:                    # rev-parse output: drop the one trailing newline only
        return out[:-1] if out.endswith(b"\n") else out

    def why(p) -> str:
        return p.stderr.decode("utf-8", "replace").strip()[:200]

    pre = raw(["rev-parse", "--show-prefix"], course_dir)
    tl = raw(["rev-parse", "--show-toplevel"], course_dir)
    if pre.returncode != 0 or tl.returncode != 0:
        raise BuildError(f"previous course: {course_dir} is not in a git checkout; inputs at {ref} cannot be read")
    prefix = line(pre.stdout)
    top = Path(os.fsdecode(line(tl.stdout)))
    refb = os.fsencode(ref)
    listing = raw(["ls-tree", "-r", "-z", "--name-only", refb, "--", b"lessons/"], course_dir)
    if listing.returncode != 0:
        raise BuildError(f"previous course: cannot list lessons at {ref}")
    hdir = workdir / "course"
    for name in filter(None, listing.stdout.split(b"\0")):
        rel = name[len(prefix):] if name.startswith(prefix) else name
        shown = raw(["show", refb + b":" + prefix + rel], course_dir)
        if shown.returncode != 0:
            raise BuildError(f"previous course: lesson {os.fsdecode(prefix + rel)!r} is listed at {ref} but "
                             f"unreadable: {why(shown)}")
        dest = hdir / os.fsdecode(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(shown.stdout)

    def old_table(path: Path, label: str):
        try:
            rel = Path(path).resolve().relative_to(top.resolve()).as_posix()
        except ValueError:
            raise BuildError(f"previous course: {label} table {path} is outside the repository {top}; "
                             f"its state at {ref} cannot be established") from None
        relb = os.fsencode(rel)
        listed = raw(["ls-tree", "-z", "--full-name", "--name-only", refb, "--", relb], top)
        if listed.returncode != 0:
            raise BuildError(f"previous course: cannot list {label} table {rel!r} at {ref}: {why(listed)}")
        names = [n for n in listed.stdout.split(b"\0") if n]
        if not names:
            return None                                  # proven absent at ref: the dependency did not exist
        if relb not in names:
            raise BuildError(f"previous course: {label} table {rel!r} at {ref}: the listing names "
                             f"{[os.fsdecode(n) for n in names][:3]!r}, not the table itself")
        shown = raw(["show", refb + b":" + relb], top)
        if shown.returncode != 0:
            raise BuildError(f"previous course: {label} table {rel!r} exists at {ref} but is unreadable: "
                             f"{why(shown)}")
        dest = workdir / ("old-" + Path(path).name)
        dest.write_bytes(shown.stdout)
        return dest, rel

    def load(label, found, fn, *args):
        dest, rel = found
        try:
            return fn(dest, *args)
        # ValueError covers UnicodeDecodeError; AttributeError / TypeError / IndexError: a structurally short
        # row (csv gives None for a missing field) in a historical table
        except (BuildError, KeyError, ValueError, csv.Error, AttributeError, TypeError, IndexError) as e:
            raise BuildError(f"previous course: {label} table {rel!r} at {ref} cannot be loaded: "
                             f"{type(e).__name__}: {e}") from e

    out = {"course_dir": hdir if hdir.exists() else None, "claims": {}, "cmap": {}, "rubrics": {}}
    c, m, r = old_table(claims_path, "claims"), old_table(map_path, "claims-map"), old_table(rubrics_path, "rubrics")
    if c:
        out["claims"] = load("claims", c, load_claims)
    if m:
        out["cmap"] = load("claims-map", m, load_map, out["claims"])
    if r:
        out["rubrics"] = load("rubrics", r, load_rubrics)
    return out


# ---------- merge ----------

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


def build(course_dir: Path, claims_path: Path, map_path: Path, rubrics_path: Path,
          previous=None, previous_ref=None, registry_path=None):
    doc = merge(course_dir)
    course = doc["course"]
    claims = load_claims(claims_path)
    cmap = load_map(map_path, claims)
    rubrics = load_rubrics(rubrics_path)
    annotate(course, course_dir, claims, cmap, rubrics)
    validate_journal_shape(course)
    entry = next((e for e in course.get("changes", []) if e["version"] == course["version"]), None)
    if entry is None:
        raise BuildError(f"changes: no entry for version {course['version']}")
    prev, ref = previous_course(course_dir, entry["from"], ref=previous_ref, path=previous)
    with tempfile.TemporaryDirectory(prefix="course-merge-prev-") as work:
        hist = historical_inputs(course_dir, ref, Path(work), claims_path, map_path, rubrics_path) if ref else None
        diff = validate_changes(course, prev, course_dir, claims, cmap, rubrics, hist=hist)
    rpath = registry_path or course_dir / "scenario-registry.tsv"
    rows = read_registry(rpath)
    bad = registry_provenance(rpath)
    if bad:
        raise BuildError(f"scenario registry {rpath}: {bad}; an absent id is not proof of a new one: "
                         "re-run --init-registry with every release available")
    diff["registry_new"] = check_registry(course, rows)
    # top-level key order: id, version, release_id (RC tag, optional), language, changes, rubrics, sections
    ordered = {k: course[k] for k in ("id", "version", "release_id", "language") if k in course}
    for k in ("changes", "rubrics"):
        if k in course:
            ordered[k] = course[k]
    for k, v in course.items():
        if k not in ordered and k != "sections":
            ordered[k] = v
    ordered["sections"] = course["sections"]
    doc["course"] = ordered
    return doc, diff


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge course sections and add bookkeeping fields.")
    ap.add_argument("--check", action="store_true", help="validate only; fail if course.json is not up to date")
    ap.add_argument("--course-dir", type=Path, default=COURSE_DIR)
    ap.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    ap.add_argument("--claims-map", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--rubrics", type=Path, default=DEFAULT_RUBRICS)
    ap.add_argument("--previous", help="course.json of the 'from' version (file)")
    ap.add_argument("--previous-ref", help="git ref whose course.json is the 'from' version")
    ap.add_argument("--registry", type=Path, help="scenario registry (default: <course-dir>/scenario-registry.tsv)")
    ap.add_argument("--init-registry", action="store_true",
                    help="create the scenario registry from the released versions in git; print the coverage report")
    a = ap.parse_args(argv)
    registry = a.registry or a.course_dir / "scenario-registry.tsv"
    if a.init_registry:
        try:
            rows, coverage = registry_init_rows(a.course_dir)
        except BuildError as e:
            print(f"course-merge: ERROR: {e}", file=sys.stderr)
            return 1
        mandatory = {v for v, _ in RELEASES}
        coverage["mandatory_unavailable"] = [u for u in coverage["unavailable"] if u.get("version") in mandatory]
        coverage["complete"] = not coverage["mandatory_unavailable"]
        if not coverage["complete"]:                       # fail closed: no file is created or rewritten
            print(json.dumps({"registry": str(registry), "written": False, **coverage}, ensure_ascii=False, indent=1))
            print("course-merge: ERROR: mandatory release(s) unavailable: "
                  + ", ".join(f"{u['version']} {u['ref']} ({u['why']})" for u in coverage["mandatory_unavailable"])
                  + f"; {registry} not written", file=sys.stderr)
            return 2
        if registry.exists():
            have = [registry_line(r) for r in read_registry(registry)]
            missing = [registry_line(r) for r in rows if registry_line(r) not in have]
            if missing:
                print(f"course-merge: ERROR: {registry} exists and lacks {len(missing)} init rows "
                      f"(append-only: not rewritten): {missing[:3]}", file=sys.stderr)
                return 1
            print(json.dumps({"registry": str(registry), "already_initialised": True, **coverage},
                             ensure_ascii=False, indent=1))
            return 0
        head = ["Scenario registry (P2b): append-only, never edit or delete a row. Written by course-merge.py.",
                "scenario_id -> (step, answer_version); an id seen with another step or answer_version fails the build.",
                "Init sources: " + "; ".join(f"{r['version']} = {r['ref']}" for r in coverage["releases"])
                + ("; unavailable: " + ", ".join(f"{u['version']} {u['ref']} ({u['why']})" for u in coverage["unavailable"])
                   if coverage["unavailable"] else "; unavailable: none"),
                "Other commits of course.json read (not releases, no rows): "
                + ", ".join(f"{o['ref']} ({o['version']})" for o in coverage["other_commits"])]
        fd, tmp = tempfile.mkstemp(dir=registry.parent, suffix=".tsv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(render_registry(rows, head))
        os.replace(tmp, registry)
        print(json.dumps({"registry": str(registry), "already_initialised": False, **coverage},
                         ensure_ascii=False, indent=1))
        return 0
    try:
        doc, diff = build(a.course_dir, a.claims, a.claims_map, a.rubrics, a.previous, a.previous_ref, registry)
    except BuildError as e:
        print(f"course-merge: ERROR: {e}", file=sys.stderr)
        return 1
    course = doc["course"]
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    summary = (f"{len(course['sections'])} sections, "
               f"{sum(len(s['lessons']) for s in course['sections'])} lessons; "
               f"vs previous: +{len(diff['added'])} -{len(diff['removed'])} changed {len(diff['changed'])}; "
               f"registry +{len(diff['registry_new'])}")
    target = a.course_dir / "course.json"
    if a.check:
        if target.read_text(encoding="utf-8") != text:
            print(f"course-merge: course.json is not up to date; run course-merge.py ({summary})", file=sys.stderr)
            return 1
        if diff["registry_new"]:
            print(f"course-merge: scenario registry lacks {len(diff['registry_new'])} new situations; "
                  f"run course-merge.py ({summary})", file=sys.stderr)
            return 1
        print(f"ok: {summary}")
        return 0
    if diff["registry_new"]:
        old_text = registry.read_text(encoding="utf-8")
        new_text = old_text + "".join(registry_line(r) + "\n" for r in diff["registry_new"])
        fd, tmp = tempfile.mkstemp(dir=registry.parent, suffix=".tsv")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.replace(tmp, registry)
    fd, tmp = tempfile.mkstemp(dir=a.course_dir, suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, target)
    print(f"merged: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
