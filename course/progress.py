#!/usr/bin/env python3
"""Mentor's course bookkeeping: where the learner is, what they answered, what changed.

Standard library only (Python 3.9+), no network. Mentor judges (is the answer right by the rubric,
what kind of evidence); this script keeps the books (order, cursors, expectations, attempt numbers,
revealed answers, versions, history, migration, backups, totals). Contract: course/SCHEMA.md §4.

    progress.py migrate [--json]                         first call of every course session
    progress.py where                                    current step, open expectation, notices
    progress.py open STEP                                show a check: opens (or returns) its expectation
    progress.py record --token T --attempt N --label L --option ID [--rubric R --evidence E]   quiz answer
    progress.py record --token T --attempt N --rubric R --evidence E                     free check
    progress.py record --token T --artifact-ref JSON                                     exercise, auto-check
    progress.py record --token T --artifact-stdin <<'REF'                                exercise, auto-check, no quoting:
        method: M / detail: D / observed: O   (three lines on stdin, values as they are)
    progress.py record --token T --said-done                                             exercise, [Сделал]
    progress.py skip (--token T | --revision R) --reason TEXT
    progress.py advance --revision R                     after an explain step
    progress.py checkpoint --revision R --choice continue|pause
    progress.py resume --revision R                      after a pause
    progress.py notice ID (--now | --later) --revision R
    progress.py lesson LESSON_ID --revision R            take a lesson out of order (detour)
    progress.py summary LEVEL                            LEVEL = all | S<n> | S<n>.L<nn>
    progress.py rollback --to MIGRATION_ID               operator only: back to the copy before a migration
    progress.py remark < JSON                            a learner's remark about the course (stdin, one object)
    progress.py consent --decision D [--recipient HOST] [--participant-key K]    the learner's sending decision;
                                                         D = granted | revoked (v1, or v2 stop/resume),
                                                         granted_at_install | acknowledged (v2); HOST defaults
                                                         to the configured endpoint's host
    progress.py flush [--endpoint URL]                   the ONLY network command: send pending feedback events
                                                         (needs consent; --endpoint required when one is configured)
    progress.py queue                                    v2: remarks waiting to be sent (ids only, read-only)
    progress.py whoami                                   the installation ID only (never the token or the key)
    progress.py export-feedback                          print feedback events as JSON lines (read-only)
    progress.py doctor                                   torn .jsonl lines, missing answer events

    --kb-home DIR   Mentor's folder, relative to the current folder (default: mentor). Files:
                    DIR/progress.json, DIR/.progress.lock, DIR/progress-backups/.
    --course FILE   course.json (default: grokbotceo/course/course.json)
    --message-id ID (record, skip) a platform message id; each id is consumed once.

Feedback events (course/EVENT-SCHEMA.md, course-feedback-v1 and v2): DIR/events.jsonl, DIR/consent.jsonl,
DIR/outbox-state.json; v2 also the key file (env GROKBOT_COURSE_ENV, default ~/.grokbotceo/course.env,
mode 600: install_id, send_token, participant key; never printed). The contract in force is the data set of
the last consent line for the recipient: v2 sends remarks only. Every other command is local: it never opens a connection, whatever the endpoint and
consent. `flush` is called explicitly (its own tool call), makes at most one request and prints a JSON
summary (status delivered | nothing_pending | registered | pending | skipped | refused; see cmd_flush).
Exit 0 for every summary except `refused` (exit 3: --endpoint missing or not the configured endpoint, nothing
done). `record` and `skip` print `attempt_uid` and `event_id` of the committed attempt. Endpoint: env
GROKBOT_FEEDBACK_URL, else "endpoint" in feedback.json next to course.json; https only (http only for
127.0.0.1/localhost); `where` shows it as feedback.endpoint. Network only with the learner's recorded consent.

Output is JSON on stdout. A contract error prints "progress: ERROR: ..." on stderr, exits 2 and
changes nothing. A busy lock is an error too (no retry, no unlock by age: a person removes a stuck
lock). Every write goes through a temporary file and os.replace, after checking that this process
still owns the lock and that progress.json did not change since it was read.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

sys.dont_write_bytecode = True

SCHEMA = 2
FINISH = "finish"
CHECK_TYPES = ("quiz", "exercise")
NO_FRAME_TYPES = ("branch", "checkpoint")
RUBRICS = ("correct", "incorrect", "invalid")
EVIDENCE = ("own_answer", "new_situation", "explanation", "verified_artifact")
RANK = {"shown": 1, "skipped": 2, "said_done": 3, "confirmed": 4}
MAX_WRONG = 3
MAX_LATER = 3
LABELS = "abcdefghij"     # display label = position in the situation's options array (P2b §4)
LEGACY_LETTER_BASIS = ("schema-1 letter read as option id: in course 0.1.0-0.2.0 every quiz lists its "
                       "options in the order a, b, c (checked on the snapshots of those versions)")
V1_KEYS = ("course_version", "current", "completed", "quiz", "exercises", "skip_reasons",
           "paused_at", "updated")
PROCESS_START = time.time()
HOOKS = {}          # tests only: name -> callable, see _hook()


class ContractError(Exception):
    pass


def _hook(name):
    fn = HOOKS.get(name)
    if fn:
        fn()


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha8(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:8]


def semver(v):
    if not isinstance(v, str) or not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise ContractError(f"unknown course version {v!r}")
    return tuple(int(x) for x in v.split("."))


def dump(state) -> bytes:
    return (json.dumps(state, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---------------------------------------------------------------- course

class Course:
    def __init__(self, path: Path):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ContractError(f"course file not found: {path}")
        except ValueError as e:
            raise ContractError(f"course file is not valid JSON: {e}")
        c = doc["course"]
        self.version = c["version"]
        self.release_id = c.get("release_id")
        self.path = path
        self.changes = c.get("changes", [])
        self.rubrics = c.get("rubrics", {})
        self.sections = c["sections"]
        self.order, self.steps, self.lesson, self.section = [], {}, {}, {}
        for s in self.sections:
            for l in s["lessons"]:
                for st in l["steps"]:
                    self.order.append(st["id"])
                    self.steps[st["id"]] = st
                    self.lesson[st["id"]] = l
                    self.section[st["id"]] = s
        self.pos = {sid: i for i, sid in enumerate(self.order)}

    def __contains__(self, sid):
        return sid in self.steps

    def type(self, sid):
        return self.steps[sid]["type"]

    def cv(self, sid):
        return self.steps[sid].get("content_version")

    def following(self, sid):
        i = self.pos[sid] + 1
        return self.order[i] if i < len(self.order) else FINISH

    def succ(self, sid):
        return self.steps[sid].get("next") or self.following(sid)

    def section_start(self, target):
        if target == FINISH:
            return FINISH
        for s in self.sections:
            if s["id"] == target:
                return s["lessons"][0]["steps"][0]["id"]
        raise ContractError(f"checkpoint target {target!r} is not a section")

    def checkpoint_target(self, sid):
        opts = {o["id"]: o for o in self.steps[sid].get("options", [])}
        return self.section_start(opts["continue"]["target"])

    def primary_id(self, sid):
        return self.steps[sid].get("primary_scenario_id") or sid

    def scenarios(self, sid):
        """The situations of a check, in show priority: the built list, else the primary followed by the
        step's extra situations."""
        st = self.steps[sid]
        if st.get("scenarios"):
            return st["scenarios"]
        out = [{"id": self.primary_id(sid),
                "option_ids": sorted(o["id"] for o in st.get("options", [])) if st["type"] == "quiz" else [],
                "rubric_ref": st.get("rubric_ref", "-")}]
        for x in st.get("situations") or []:
            out.append({"id": x["id"], "option_ids": sorted(o["id"] for o in x.get("options", [])),
                        "rubric_ref": x.get("rubric_ref", "-")})
        return out

    def situation(self, sid, scenario_id):
        """The one resolver of a situation: {id, question, options, key, rubric_ref}. Every reader (open,
        record, scoring) takes the question, options, key and rubric from here, never from the step."""
        st = self.steps[sid]
        entry = next((x for x in self.scenarios(sid) if x["id"] == scenario_id), None)
        if entry is None:
            raise ContractError(f"{scenario_id} is not a situation of {sid}")
        if scenario_id == self.primary_id(sid):
            src = st
            ref = entry.get("rubric_ref", st.get("rubric_ref", "-"))
        else:
            src = next((x for x in st.get("situations") or [] if x.get("id") == scenario_id), None)
            if src is None:
                raise ContractError(f"situation {scenario_id} of {sid} has no content in the course")
            ref = src.get("rubric_ref", entry.get("rubric_ref", "-"))
        opts = list(src.get("options", [])) if st["type"] == "quiz" else []
        return {"id": scenario_id, "question": src.get("question"), "options": opts,
                "key": [o["id"] for o in opts if o.get("correct")], "rubric_ref": ref or "-"}

    def scoring(self, sid, scenario_id):
        """eligible step AND the situation's own rubric exists and is accepted (not revealed: see open/record)."""
        st = self.steps[sid]
        rub = self.rubrics.get(self.situation(sid, scenario_id)["rubric_ref"])
        return bool(st.get("eligible")) and bool(rub) and rub.get("status") == "accepted"


# ---------------------------------------------------------------- files and lock

class Store:
    def __init__(self, home_arg: str):
        self.home_arg = home_arg.rstrip("/") or "."
        self.home = Path(home_arg)
        self.path = self.home / "progress.json"
        self.lock = self.home / ".progress.lock"
        self.backups = self.home / "progress-backups"
        self.events = self.home / "events.jsonl"
        self.consent = self.home / "consent.jsonl"
        self.outbox = self.home / "outbox-state.json"
        self.identity = self.home / "identity.json"
        self.identity_bak = self.home / "identity.json.bak"
        self.token = None

    def read(self):
        try:
            return self.path.read_bytes()
        except FileNotFoundError:
            return None

    def acquire(self):
        self.home.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise ContractError(f"{self.lock} exists: another writer holds the lock. Not retrying; "
                                "if no writer is running, a person removes the lock file")
        self.token = secrets.token_hex(16)
        with os.fdopen(fd, "w") as fh:
            json.dump({"owner_token": self.token, "pid": os.getpid(), "process_start": PROCESS_START,
                       "at": now()}, fh)

    def acquire_wait(self, timeout):
        """Only for saving a flush result after the network call: wait (bounded) for a busy lock instead of
        failing at once. Commands keep the no-wait rule of acquire()."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.acquire()
            except ContractError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    def owns(self):
        try:
            return json.loads(self.lock.read_text()).get("owner_token") == self.token
        except (OSError, ValueError):
            return False

    def release(self):
        if self.token and self.owns():
            os.remove(self.lock)
        self.token = None

    def write_atomic(self, path: Path, data: bytes, mode=None):
        tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass

    def commit(self, data: bytes, original):
        _hook("before_commit")
        if not self.owns():
            raise ContractError("the lock is no longer ours; nothing written")
        if self.read() != original:
            raise ContractError("progress.json changed since it was read (another writer); nothing written")
        self.write_atomic(self.path, data)

    def backup(self, raw: bytes, version: str):
        """Immutable byte copy; an existing copy is reused only if it is byte-identical."""
        self.backups.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(raw).hexdigest()
        safe = re.sub(r"[^\w.-]", "_", str(version))
        for name in (f"{safe}-{digest[:8]}.json", f"{safe}-{digest}.json"):
            p = self.backups / name
            if p.exists():
                if p.read_bytes() == raw:
                    return f"{self.home_arg}/progress-backups/{name}", digest
                continue
            self.write_atomic(p, raw, mode=0o444)
            return f"{self.home_arg}/progress-backups/{name}", digest
        raise ContractError("both backup names are taken by different content; nothing written")


def parse(raw):
    try:
        state = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ContractError(f"progress.json is not valid JSON ({e}); nothing written")
    if not isinstance(state, dict):
        raise ContractError("progress.json is not a JSON object; nothing written")
    schema = state.get("schema", 1)
    if schema not in (1, SCHEMA):
        raise ContractError(f"progress.json has schema {schema!r}, this script knows 1 and 2; nothing written")
    return state


def need_current(state, course):
    if state is None:
        raise ContractError("no progress.json: run migrate first")
    if state.get("schema", 1) != SCHEMA or state.get("course_version") != course.version:
        raise ContractError("progress.json is not migrated to this course version: run migrate first")


def need_revision(state, rev):
    if rev is None:
        raise ContractError("--revision is required")
    if rev != state.get("revision"):
        raise ContractError(f"revision {rev} is not current ({state.get('revision')}): call where again")


# ---------------------------------------------------------------- state helpers

def skeleton(course_version, cursor):
    return {"schema": SCHEMA, "revision": 0, "course_version": course_version,
            "nav": {"cursor": cursor, "stack": [], "paused": None},
            "completed": [], "skip_reasons": {}, "open": None, "checks": {}, "notices": [],
            "repeat": [], "legacy": {}, "exposure": {}, "consumed_messages": [], "migrations": [],
            "updated": None}


def new_check(cv):
    return {"lifecycle": "active", "content_version": cv, "current": None, "best_this_version": None,
            "exposure": {}, "history": []}


def current_step(p):
    stack = p["nav"]["stack"]
    if stack:
        fr = stack[-1]
        return fr["steps"][fr["index"]]
    return p["nav"]["cursor"]


def add_completed(p, sid):
    if sid not in p["completed"]:
        p["completed"].append(sid)


def add_repeat(p, sid):
    if sid not in p["repeat"]:
        p["repeat"].append(sid)


def attempts(chk, cv, scenario=None):
    return [h for h in chk.get("history", []) if h.get("content_version") == cv
            and (scenario is None or h.get("scenario_id") == scenario) and h.get("origin") != "legacy_unknown"]


def _hits(e):
    return bool(e and e.get("revealed"))


def revealed(p, sid, scenario, cv=None):
    """Exposure identity is (step, scenario_id), without a version (P2b §3): a revealed situation is never
    scored again while its id is the same, whatever happens to the step's content_version. A changed
    answer gets a new id (the build's scenario registry enforces it). The ledger p["exposure"] outlives
    removal and return of the step. cv is accepted for callers and ignored."""
    chk = p["checks"].get(sid) or {}
    if _hits(chk.get("exposure", {}).get(scenario)):
        return True
    return any(_hits(e) for e in p.get("exposure", {}).get(sid, {}).get(scenario, []))


def note_exposure(p, sid, scenario, entry):
    lst = p.setdefault("exposure", {}).setdefault(sid, {}).setdefault(scenario, [])
    if entry not in lst:
        lst.append(entry)


def rebuild_exposure(p):
    """Collect every known reveal into the ledger: live checks and checks archived in legacy."""
    p.setdefault("exposure", {})
    for sid, chk in p["checks"].items():
        for scen, e in chk.get("exposure", {}).items():
            if e.get("revealed"):
                note_exposure(p, sid, scen, e)
    for sid, entries in p["legacy"].items():
        if sid == "_file":
            continue
        for ent in entries:
            chk = (ent.get("original") or {}).get("check") or {}
            for scen, e in chk.get("exposure", {}).items():
                if e.get("revealed"):
                    note_exposure(p, sid, scen, e)
            if "quiz" in (ent.get("original") or {}):
                note_exposure(p, sid, sid, {"revealed": True, "content_version": None, "source": "legacy"})


def eval_branch(p, course, sid):
    st = course.steps[sid]
    for case in st.get("cases", []):
        cond = case["when"]
        chk = p["checks"].get(cond["step"])
        hist = attempts(chk, chk.get("content_version")) if chk else []
        best = (chk or {}).get("best_this_version") or {}
        if "answer" in cond:
            opts = [h["option_ids"][-1] for h in hist if h.get("option_ids")]
            hit = bool(opts) and opts[-1] == cond["answer"]
        elif "attempts_min" in cond:
            hit = len(hist) >= cond["attempts_min"]
        elif "result" in cond:
            if cond["result"] == "skipped":
                hit = best.get("status") == "skipped"
            else:
                hit = best.get("status") in ("confirmed", "said_done")
        else:
            hit = False
        if hit:
            return case["next"]
    return st["default"]


def resolve(p, course, sid):
    guard = 0
    while sid != FINISH and sid in course and course.type(sid) == "branch":
        add_completed(p, sid)
        sid = eval_branch(p, course, sid)
        guard += 1
        if guard > 100:
            raise ContractError("branch loop")
    return sid


def advance_from(p, course, sid):
    """sid is finished: mark it, move the current frame or the cursor. Returns notices finished."""
    add_completed(p, sid)
    stack = p["nav"]["stack"]
    done = []
    if stack:
        fr = stack[-1]
        fr["index"] += 1
        if fr["index"] >= len(fr["steps"]):
            stack.pop()
            if fr["kind"] == "notice":
                for n in p["notices"]:
                    if n["id"] == fr["notice_id"]:
                        n["state"] = "done"
                        done.append(n["id"])
        return done
    p["nav"]["cursor"] = resolve(p, course, course.succ(sid))
    return done


def following_ids(course, sid):
    """All ids after sid in course order (no cutoff): a later migration picks the nearest one that still exists."""
    if sid == FINISH or sid not in course:
        return []
    return list(course.order[course.pos[sid] + 1:])


def frame_steps(course, steps):
    return [s for s in steps if s in course and course.type(s) not in NO_FRAME_TYPES]


def offered_notices(p):
    return [n for n in p["notices"] if n["state"] in ("new", "later")]


def step_view(course, sid):
    if sid == FINISH:
        return {"step": FINISH}
    sec, les = course.section[sid], course.lesson[sid]
    return {"step": sid, "section": {"id": sec["id"], "title": sec["title"]},
            "lesson": {"id": les["id"], "title": les["title"]}, "content": course.steps[sid]}


# ---------------------------------------------------------------- migrate

def chain(course, a, b):
    out, cur = [], a
    for _ in range(len(course.changes) + 1):
        if cur == b:
            return out
        e = next((x for x in course.changes if x.get("from") == cur), None)
        if e is None:
            return None
        out.append(e)
        cur = e["version"]
    return None


def legacy_append(p, key, mid, from_version, original, origin="legacy_unknown", reason=None):
    entry = {"migration_id": mid, "from_version": from_version, "original": original, "origin": origin}
    if reason:
        entry["reason"] = reason
    p["legacy"].setdefault(key, []).append(entry)


def from_v1(old, mid, course):
    """Schema 1 -> 2. Every original record is kept whole in legacy."""
    for k, typ in (("quiz", dict), ("exercises", dict), ("skip_reasons", dict), ("completed", list)):
        if k in old and old[k] is not None and not isinstance(old[k], typ):
            raise ContractError(f"progress.json field {k} has an unexpected type; nothing written")
    a = old.get("course_version")
    p = skeleton(a, old.get("current") or (FINISH if old.get("completed") else course.order[0]))
    legacy_append(p, "_file", mid, a, {k: v for k, v in old.items() if k not in ("quiz", "exercises")})
    p["completed"] = list(old.get("completed") or [])
    p["skip_reasons"] = dict(old.get("skip_reasons") or {})
    at = old.get("updated")
    for sid, rec in (old.get("quiz") or {}).items():
        legacy_append(p, sid, mid, a, {"quiz": rec})
        p["legacy"][sid][-1]["option_basis"] = LEGACY_LETTER_BASIS
        chk = p["checks"].setdefault(sid, new_check(None))
        chk["lifecycle"] = "needs_recheck"
        r = rec if isinstance(rec, dict) else {}
        opt = r.get("option")
        chk["history"].append({"attempt": r.get("attempts"), "content_version": None, "scenario_id": sid,
                               "option_ids": [opt] if opt is not None else [], "rubric_verdict": "-",
                               "status": "-", "evidence": "-", "revealed": bool(r.get("revealed")),
                               "scored": False, "origin": "legacy_unknown", "at": at,
                               "note": "old result without confirmation"})
        chk["exposure"][sid] = {"revealed": True, "content_version": None, "source": "legacy"}
    for sid, val in (old.get("exercises") or {}).items():
        legacy_append(p, sid, mid, a, {"exercises": val})
        chk = p["checks"].setdefault(sid, new_check(None))
        chk["lifecycle"] = "needs_recheck"
        skipped = val == "skipped"
        chk["history"].append({"attempt": 1, "content_version": None, "scenario_id": sid, "option_ids": [],
                               "rubric_verdict": "-", "status": "skipped" if skipped else "-", "evidence": "-",
                               "revealed": False, "scored": False, "origin": "legacy_unknown", "at": at,
                               "note": "skip known exactly" if skipped else "old result without confirmation"})
        if skipped:
            chk["current"] = {"status": "skipped", "evidence": "-", "attempt": 1}
            chk["best_this_version"] = {"status": "skipped", "evidence": "-", "attempt": 1}
    pa = old.get("paused_at")
    if isinstance(pa, str) and pa in course:   # a timestamp or unknown value is not a pause target (kept in legacy)
        p["nav"]["paused"] = {"at": pa, "resume_target": None}
    return p


def fix_cursor(p, course):
    cur = p["nav"]["cursor"]
    if cur == FINISH or (cur in course):
        return resolve(p, course, cur) if cur != FINISH else cur
    done = [course.pos[s] for s in p["completed"] if s in course]
    nxt = course.order[max(done) + 1] if done and max(done) + 1 < len(course.order) else (
        FINISH if done else course.order[0])
    return resolve(p, course, nxt)


def migrate_state(p, course, mid, a, b, old_completed, report):
    """Fit a schema-2 state recorded against version a to the course b (also used when a == b)."""
    reason = f"removed_in_{b}"
    rebuild_exposure(p)
    for sid in list(p["checks"]):
        if sid not in course:
            chk = p["checks"].pop(sid)
            origin = "legacy_unknown" if all(h.get("origin") == "legacy_unknown" for h in chk["history"]) else "runtime"
            legacy_append(p, sid, mid, a, {"check": chk, "completed": sid in p["completed"],
                                           "skip_reason": p["skip_reasons"].pop(sid, None)}, origin, reason)
            report["legacy_added"].append(sid)
    for sid in list(dict.fromkeys(p["completed"])):
        if sid not in course and sid not in report["legacy_added"]:
            legacy_append(p, sid, mid, a, {"completed": True, "skip_reason": p["skip_reasons"].pop(sid, None)},
                          reason=reason)
            report["legacy_added"].append(sid)
    for sid in list(p["skip_reasons"]):
        if sid not in course:
            legacy_append(p, sid, mid, a, {"skip_reason": p["skip_reasons"].pop(sid)}, reason=reason)
            report["legacy_added"].append(sid)
    p["completed"] = [s for s in dict.fromkeys(p["completed"]) if s in course]
    p["repeat"] = [s for s in p["repeat"] if s in course]
    for n in p["notices"]:
        n["steps"] = [s for s in n["steps"] if s in course]
    stack = []
    for fr in p["nav"]["stack"]:
        before = fr["steps"][:fr["index"]]
        fr["steps"] = [s for s in fr["steps"] if s in course]
        fr["index"] = len([s for s in before if s in course])
        if fr["index"] < len(fr["steps"]):
            stack.append(fr)
        elif fr["kind"] == "notice":
            for n in p["notices"]:
                if n["id"] == fr["notice_id"]:
                    n["state"] = "done"
    p["nav"]["stack"] = stack
    o = p.get("open")
    if o and "display" not in o:
        # opened before P2b: no frozen layout. Closed without an attempt, repeat or notice; its token dies.
        p.setdefault("superseded_opens", []).append(
            {"token": o.get("token"), "step": o.get("step"), "content_version": o.get("content_version"),
             "scenario_id": o.get("scenario_id"), "opened_at": o.get("opened_at"), "migration_id": mid,
             "reason": "open without a frozen display"})
        report.setdefault("superseded", []).append(o.get("step"))
        p["open"] = None
    elif o and (o["step"] not in course or o["content_version"] != course.cv(o["step"])):
        p["open"] = None

    # cursor and pause
    paused = p["nav"]["paused"]
    old_cursor = p["nav"]["cursor"]
    p["nav"]["cursor"] = fix_cursor(p, course)
    if paused is not None:
        at, target = paused.get("at"), paused.get("resume_target")
        at_cp = isinstance(at, str) and at in course and course.type(at) == "checkpoint"
        if target is not None and (target == FINISH or target in course):
            new_target = target                              # a stored target that still exists is kept
        elif target is not None:                             # removed: nearest following step that exists
            nxt = next((s for s in paused.get("following", []) if s in course), None)
            if nxt is not None:
                new_target = resolve(p, course, nxt)
            elif at_cp:
                new_target = resolve(p, course, course.checkpoint_target(at))
            else:
                new_target = p["nav"]["cursor"]
        elif at_cp:
            new_target = resolve(p, course, course.checkpoint_target(at))
        elif isinstance(at, str) and at in course:
            new_target = resolve(p, course, at)              # schema-1 pause at a plain step: resume there
        else:
            new_target = p["nav"]["cursor"]
        if target is not None and old_cursor == target:
            p["nav"]["cursor"] = new_target
        paused["resume_target"] = new_target
        paused["following"] = following_ids(course, new_target)

    # changed content
    links = chain(course, a, b) if a != b else []
    changed = set()
    if links:
        for e in links:
            changed |= set(e.get("changed", []))
    for sid, chk in p["checks"].items():
        cv = course.cv(sid)
        if chk.get("content_version") is not None and chk["content_version"] != cv:
            chk["content_version"] = cv
            chk["best_this_version"] = None
            chk["current"] = None
            chk["lifecycle"] = "needs_recheck"
            add_repeat(p, sid)
            report["rechecks"].append(sid)
        elif chk.get("content_version") is None and sid in changed:
            add_repeat(p, sid)
            report["rechecks"].append(sid)
    if a != b:
        did = set(old_completed) | {s for s, c in p["checks"].items() if c.get("history")}
        steps = [s for s in course.order if s in did and (s in changed or s in report["rechecks"])]
        report["changed_done_steps"] = steps
        report["changed_done"] = len(steps)

    # notices for steps the learner would otherwise never see
    if a != b:
        cursor = p["nav"]["stack"][0]["return_to"] if p["nav"]["stack"] else p["nav"]["cursor"]
        limit = len(course.order) if cursor == FINISH or cursor not in course else course.pos[cursor]
        before = [s for s in course.order[:limit] if course.type(s) not in NO_FRAME_TYPES]
        done = set(p["completed"])
        if links is None:
            groups = [("added", [s for s in before if s not in done], True, "")]
        else:
            added = set().union(*[set(e["added"]) for e in links]) if links else set()
            important = set().union(*[set(e["important"]) for e in links]) if links else set()
            note = " ".join(e["note"] for e in links if e.get("note"))
            add_steps = [s for s in before if s in added and s not in done]
            cor_steps = [s for s in before if s in changed and s in set(old_completed)]
            groups = [("added", add_steps, bool(important & set(add_steps)), note),
                      ("correction", cor_steps, bool(important & set(cor_steps)), note)]
        known = {n["id"] for n in p["notices"]}
        for kind, steps, imp, note in groups:
            if not steps:
                continue
            nid = f"{b}#{kind}-{sha8(steps)}"
            if nid in known:
                continue
            p["notices"].append({"id": nid, "kind": kind, "version": b, "steps": steps, "important": imp,
                                 "state": "new", "later_count": 0, "note": note})
            report["notices"].append(nid)


def cmd_migrate(args, course, store):
    store.acquire()
    try:
        raw = store.read()
        report = {"changed": False, "migration_id": None, "notices": [], "legacy_added": [],
                  "rechecks": [], "backup": None, "superseded": [], "version_changed": False,
                  "changed_done": 0, "changed_done_steps": []}
        if raw is None:
            p = skeleton(course.version, None)
            p["nav"]["cursor"] = resolve(p, course, course.order[0])
            p["revision"] = 1
            p["updated"] = now()
            store.commit(dump(p), None)
            report["changed"] = True
            report["notices"] = [n["id"] for n in offered_notices(p)]
            return report
        state = parse(raw)
        schema_from = state.get("schema", 1)
        a = state.get("course_version")
        b = course.version
        if semver(a) > semver(b):
            raise ContractError(f"progress.json is for course {a}, newer than this course {b} "
                                "(unknown downgrade); nothing written")
        mid = f"m{len(state.get('migrations', [])) + 1}" if schema_from == SCHEMA else "m1"
        if schema_from == 1:
            p = from_v1(state, mid, course)
            old_completed = list(p["completed"])
        else:
            p = copy.deepcopy(state)
            old_completed = list(p["completed"])
        migrate_state(p, course, mid, a, b, old_completed, report)
        report["version_changed"] = a != b
        p["course_version"] = b
        cmp_old = {k: v for k, v in state.items() if k not in ("revision", "updated")}
        cmp_new = {k: v for k, v in p.items() if k not in ("revision", "updated")}
        if schema_from == SCHEMA and cmp_old == cmp_new:
            report["notices"] = [n["id"] for n in offered_notices(p)]
            return report
        backup, digest = store.backup(raw, a)
        _hook("after_backup")
        p.setdefault("migrations", []).append({"id": mid, "from": a, "to": b, "schema_from": schema_from,
                                               "source_sha256": digest, "backup": backup, "at": now()})
        p["revision"] = int(state.get("revision", 0) or 0) + 1
        p["updated"] = now()
        store.commit(dump(p), raw)
        report.update({"changed": True, "migration_id": mid, "backup": backup,
                       "notices": [n["id"] for n in offered_notices(p)]})
        return report
    finally:
        store.release()


# ---------------------------------------------------------------- mutations

def mutate(store, course, fn, events=False):
    store.acquire()
    try:
        raw = store.read()
        p = parse(raw) if raw is not None else None
        need_current(p, course)
        if events:
            try:
                ensure_identity(store, p)                   # the collector exists before the first event
            except ContractError as e:                      # identity_lost: grading goes on, nothing is sent
                note(str(e))
        out = fn(p)
        p["revision"] = int(p.get("revision", 0)) + 1
        p["updated"] = now()
        store.commit(dump(p), raw)
        out["revision"] = p["revision"]
        if events and out.get("attempt_uid"):
            try:                                            # the answer is committed: never fail after it
                ident = load_identity(store)                # None under identity_lost: no id, nothing is sent
            except Exception:                               # noqa: BLE001
                ident = None
            out["event_id"] = (event_id(ident["collector_id"], "answer-uid:" + out["attempt_uid"], "answer")
                               if ident else None)
        if events:
            # EVENT-SCHEMA §3a: progress.json is committed first; the answer line follows. A failure here does
            # not undo or hide the committed answer: the event is rebuilt from history before the next flush.
            _hook("before_event_append")
            try:
                rebuild_missing(store, p, course)
            except Exception as e:                          # noqa: BLE001 - the record itself succeeded
                note(f"answer event not written now, it will be rebuilt from history ({e})")
        return out
    finally:
        store.release()


def consume_message(p, mid):
    if mid is None:
        return
    if mid in p["consumed_messages"]:
        raise ContractError(f"message {mid} was already recorded")
    p["consumed_messages"].append(mid)          # kept for the life of the file: an id is never accepted twice


def cmd_open(args, course, store):
    store.acquire()
    try:
        raw = store.read()
        p = parse(raw) if raw is not None else None
        need_current(p, course)
        sid = args.step
        if sid != current_step(p):
            raise ContractError(f"{sid} is not the current step ({current_step(p)})")
        if sid not in course or course.type(sid) not in CHECK_TYPES:
            raise ContractError(f"{sid} is not a check (quiz or exercise)")
        cv = course.cv(sid)
        o = p.get("open")
        if o and o["step"] == sid and o["content_version"] == cv and "display" in o:
            return dict(o, revision=p["revision"])              # the frozen layout, never recomputed
        chk = p["checks"].get(sid)
        if chk is None:
            chk = p["checks"][sid] = new_check(cv)
        elif chk.get("content_version") is None:
            chk["content_version"] = cv
        pick, free = pick_situation(p, course, sid)
        sit = course.situation(sid, pick)
        scoring = free and course.scoring(sid, pick)
        o = {"token": secrets.token_hex(8), "step": sid, "content_version": cv, "scenario_id": pick,
             "option_ids": [x["id"] for x in sit["options"]], "scoring": scoring,
             "next_attempt": len(attempts(chk, cv, pick)) + 1, "opened_at": now(),
             "display": [{"label": LABELS[i], "option_id": x["id"]} for i, x in enumerate(sit["options"])]}
        if course.type(sid) == "quiz":
            o["question"] = sit["question"]
            o["options"] = [{"id": x["id"], "text": x.get("text"), "reaction": x.get("reaction")}
                            for x in sit["options"]]
        p["open"] = o
        p["revision"] = int(p.get("revision", 0)) + 1
        p["updated"] = now()
        store.commit(dump(p), raw)
        return dict(o, revision=p["revision"])
    finally:
        store.release()


def pick_situation(p, course, sid):
    """First situation in show priority that is not revealed; all revealed -> the first one, not free."""
    ids = [x["id"] for x in course.scenarios(sid)]
    free = [x for x in ids if not revealed(p, sid, x)]
    return (free or ids)[0], bool(free)


def check_labels(o, options, labels):
    """--label and --option go together under a frozen display; every pair must agree with it. This proves
    the pair is consistent, not which button the learner pressed (SCHEMA §4)."""
    display = o.get("display") or []
    if labels and not options:
        raise ContractError("--label goes with --option")
    if not display:
        if labels:
            raise ContractError("this expectation has no display: --label is not accepted")
        return
    if options and not labels:
        raise ContractError("--label is required with --option (the label the learner chose in the frozen display)")
    if len(labels) != len(options):
        raise ContractError("give one --label per --option, in the same order")
    shown = {d["label"]: d["option_id"] for d in display}
    for lab, opt in zip(labels, options):
        if lab not in shown:
            raise ContractError(f"label {lab!r} is not in the display {sorted(shown)}")
        if shown[lab] != opt:
            raise ContractError(f"label {lab!r} shows option {shown[lab]!r}, not {opt!r}; nothing written")


def parse_artifact(ref, step):
    try:
        art = json.loads(ref)
    except ValueError:
        raise ContractError("--artifact-ref must be JSON: {\"method\", \"detail\", \"observed\"}")
    if not isinstance(art, dict):
        raise ContractError("--artifact-ref must be a JSON object")
    check = step.get("check") or {}
    if check.get("method") in (None, "user_confirm_form"):
        raise ContractError("this exercise has no automatic check: use --said-done")
    if art.get("method") != check.get("method"):
        raise ContractError(f"artifact method {art.get('method')!r} is not this step's check method {check.get('method')!r}")
    if art.get("detail") != check.get("detail"):
        raise ContractError("artifact detail does not match this step's check detail")
    obs = art.get("observed")
    if not isinstance(obs, str) or not obs.strip():
        raise ContractError("artifact needs 'observed': what was found (path + sha256, section id, key + value hash, tool + result digest)")
    return {"method": art["method"], "detail": art["detail"], "observed": obs.strip()}


ARTIFACT_KEYS = ("method", "detail", "observed")


def read_artifact_lines(stream):
    """--artifact-stdin: the artifact as three lines `method: …`, `detail: …`, `observed: …` (any order, each
    once). A value is the rest of its line after `key: `, taken as it is: no shell quoting, no JSON escaping,
    so an apostrophe or a double quote is just itself. Returns the same JSON text --artifact-ref takes, so
    parse_artifact applies the very same checks (method, detail character for character, observed)."""
    buf = getattr(stream, "buffer", None)
    raw = buf.read(16 * 1024 + 1) if buf is not None else stream.read(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        raise ContractError("--artifact-stdin: input is larger than 16 KiB")
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ContractError("--artifact-stdin: input is not UTF-8")
    art = {}
    for line in raw.split("\n"):
        line = line.rstrip("\r")
        if not line.strip():
            continue
        key, sep, value = line.lstrip().partition(": ")
        if not sep or key not in ARTIFACT_KEYS:
            raise ContractError("--artifact-stdin: each line is `method: …`, `detail: …` or `observed: …`; "
                                f"got {line[:60]!r}")
        if key in art:
            raise ContractError(f"--artifact-stdin: {key!r} given twice")
        art[key] = value
    missing = [k for k in ARTIFACT_KEYS if k not in art]
    if missing:
        raise ContractError(f"--artifact-stdin: missing {missing}")
    return json.dumps(art, ensure_ascii=False)


def finish_attempt(p, course, chk, sid, entry, close):
    chk["history"].append(entry)
    cur = {"status": entry["status"], "evidence": entry["evidence"], "attempt": entry["attempt"]}
    chk["current"] = cur
    best = chk.get("best_this_version")
    if best is None or RANK[entry["status"]] > RANK.get(best.get("status"), 0):
        chk["best_this_version"] = dict(cur)
    chk["lifecycle"] = "active"
    if entry["status"] in ("confirmed", "said_done") and sid in p["repeat"]:
        p["repeat"].remove(sid)
    out = {"step": sid, "attempt": entry["attempt"], "status": entry["status"], "revealed": entry["revealed"],
           "scored": entry["scored"], "closed": close}
    if entry.get("attempt_uid"):
        out["attempt_uid"] = entry["attempt_uid"]          # correlation id of the committed attempt
    if close:
        p["open"] = None
        out["notices_done"] = advance_from(p, course, sid)
    out["current"] = current_step(p)
    return out


def cmd_record(args, course, store):
    if getattr(args, "artifact_stdin", False):
        if args.artifact_ref:
            raise ContractError("give the artifact once: --artifact-ref or --artifact-stdin, not both")
        args.artifact_ref = read_artifact_lines(sys.stdin)   # read before the lock; same checks as --artifact-ref

    def fn(p):
        o = p.get("open")
        if not o or args.token != o["token"]:
            raise ContractError("token is not the open expectation (repeated, stale or foreign); nothing written")
        sid = o["step"]
        if sid != current_step(p) or o["content_version"] != course.cv(sid):
            raise ContractError("the expectation is stale (step or content changed); call open again")
        st = course.steps[sid]
        chk = p["checks"].setdefault(sid, new_check(o["content_version"]))
        cv, scen = o["content_version"], o["scenario_id"]
        options = args.option or []
        for opt in options:
            if opt not in o["option_ids"]:
                raise ContractError(f"option {opt!r} is not one of {o['option_ids']}")
        if args.attempt is not None and args.attempt != o["next_attempt"]:
            raise ContractError(f"attempt {args.attempt} is not the next attempt ({o['next_attempt']}); nothing written")
        if args.evidence and args.evidence not in EVIDENCE + ("-",):
            raise ContractError(f"--evidence must be one of {EVIDENCE}")
        if args.rubric and args.rubric not in RUBRICS:
            raise ContractError(f"--rubric must be one of {RUBRICS}")
        check_labels(o, options, args.label or [])
        scoring = o["scoring"] and not revealed(p, sid, scen)
        consume_message(p, args.message_id)
        entry = {"attempt": o["next_attempt"], "content_version": cv, "scenario_id": scen, "option_ids": options,
                 "rubric_verdict": "-", "status": "shown", "evidence": "-", "revealed": False, "scored": scoring,
                 "origin": "runtime", "at": now()}
        stamp_entry(entry, course, sid, o)
        if args.message_id is not None:
            entry["message_id"] = args.message_id

        if st["type"] == "quiz":
            if args.said_done or args.artifact_ref:
                raise ContractError("a quiz takes --option (and --rubric when scoring), not --said-done/--artifact-ref")
            if not options:
                raise ContractError("a quiz answer needs --option")
            if args.attempt is None:
                raise ContractError("a quiz answer needs --attempt")
            if not scoring:
                if args.rubric:
                    raise ContractError("this check is not scored (scoring=false): --rubric is not accepted")
                return finish_attempt(p, course, chk, sid, entry, close=True)
            if not args.rubric:
                raise ContractError("scored quiz: --rubric is required")
            key = course.situation(sid, scen)["key"]             # the key of THIS situation
            entry["rubric_verdict"] = args.rubric
            if args.rubric == "correct":
                if len(options) != 1 or options != key:
                    raise ContractError("--rubric correct does not match the answer key")
                ev = args.evidence or "-"
                if ev in ("-", "verified_artifact"):
                    raise ContractError("confirmed needs --evidence own_answer|new_situation|explanation")
                entry.update(status="confirmed", evidence=ev)
                return finish_attempt(p, course, chk, sid, entry, close=True)
            if len(options) == 1 and options == key and args.rubric == "incorrect":
                raise ContractError("--rubric incorrect contradicts the answer key")
            return wrong(p, course, chk, sid, entry, cv, scen)

        # exercise
        if options:
            raise ContractError("an exercise takes no --option")
        if args.said_done:
            if args.rubric or args.evidence or args.artifact_ref:
                raise ContractError("--said-done takes no --rubric, --evidence or --artifact-ref")
            entry.update(status="said_done", origin="user_form", scored=False)
            return finish_attempt(p, course, chk, sid, entry, close=True)
        if args.artifact_ref:
            art = parse_artifact(args.artifact_ref, st)
            if args.evidence not in (None, "verified_artifact"):
                raise ContractError("--artifact-ref goes with --evidence verified_artifact")
            if args.rubric not in (None, "correct"):
                raise ContractError("a found artifact is a correct result; record a failed check by not recording")
            entry.update(evidence="verified_artifact", artifact=art)
            if scoring:
                entry.update(status="confirmed", rubric_verdict="correct")
            return finish_attempt(p, course, chk, sid, entry, close=True)
        if args.evidence == "verified_artifact":
            raise ContractError("--evidence verified_artifact needs --artifact-ref")
        if args.attempt is None:
            raise ContractError("a free check needs --attempt")
        if not scoring:
            if args.rubric:
                raise ContractError("this check is not scored (scoring=false): --rubric is not accepted")
            return finish_attempt(p, course, chk, sid, entry, close=True)
        if not args.rubric:
            raise ContractError("scored check: --rubric is required")
        entry["rubric_verdict"] = args.rubric
        if args.rubric == "correct":
            ev = args.evidence or "-"
            if ev == "-":
                raise ContractError("confirmed needs --evidence")
            entry.update(status="confirmed", evidence=ev)
            return finish_attempt(p, course, chk, sid, entry, close=True)
        return wrong(p, course, chk, sid, entry, cv, scen)

    return mutate(store, course, fn, events=True)


def wrong(p, course, chk, sid, entry, cv, scen):
    n_wrong = 1 + len([h for h in attempts(chk, cv, scen) if h.get("rubric_verdict") in ("incorrect", "invalid")])
    if n_wrong >= MAX_WRONG:
        entry["revealed"] = True
        chk["exposure"][scen] = {"revealed": True, "content_version": cv, "source": "runtime"}
        note_exposure(p, sid, scen, dict(chk["exposure"][scen]))
        return finish_attempt(p, course, chk, sid, entry, close=True)
    out = finish_attempt(p, course, chk, sid, entry, close=False)
    p["open"]["next_attempt"] += 1
    out["next_attempt"] = p["open"]["next_attempt"]
    return out


def cmd_skip(args, course, store):
    def fn(p):
        if not args.reason or not args.reason.strip():
            raise ContractError("--reason is required")
        o = p.get("open")
        if args.token is not None:
            if not o or args.token != o["token"] or o["step"] != current_step(p):
                raise ContractError("token is not the open expectation; nothing written")
            sid, cv, scen, n = o["step"], o["content_version"], o["scenario_id"], o["next_attempt"]
        else:
            need_revision(p, args.revision)
            sid = current_step(p)
            if sid == FINISH or course.type(sid) not in CHECK_TYPES:
                raise ContractError("only a check (quiz or exercise) can be skipped")
            cv = course.cv(sid)
            scen = pick_situation(p, course, sid)[0]
            chk0 = p["checks"].get(sid)
            n = len(attempts(chk0, cv, scen)) + 1 if chk0 else 1
        consume_message(p, args.message_id)
        chk = p["checks"].setdefault(sid, new_check(cv))
        if chk.get("content_version") is None:
            chk["content_version"] = cv
        p["skip_reasons"][sid] = args.reason.strip()
        entry = {"attempt": n, "content_version": cv, "scenario_id": scen, "option_ids": [], "rubric_verdict": "-",
                 "status": "skipped", "evidence": "-", "revealed": False, "scored": False, "origin": "runtime",
                 "at": now(), "reason": args.reason.strip()}
        stamp_entry(entry, course, sid, o if args.token is not None else None)
        return finish_attempt(p, course, chk, sid, entry, close=True)
    return mutate(store, course, fn, events=True)


def cmd_advance(args, course, store):
    def fn(p):
        need_revision(p, args.revision)
        sid = current_step(p)
        if sid == FINISH:
            raise ContractError("the course is finished")
        if course.type(sid) != "explain":
            raise ContractError(f"{sid} is a {course.type(sid)}: use open/record/skip or checkpoint")
        done = advance_from(p, course, sid)
        return {"step": sid, "current": current_step(p), "notices_done": done}
    return mutate(store, course, fn)


def cmd_checkpoint(args, course, store):
    def fn(p):
        need_revision(p, args.revision)
        sid = current_step(p)
        if sid == FINISH or course.type(sid) != "checkpoint":
            raise ContractError("the current step is not a checkpoint")
        add_completed(p, sid)
        target = resolve(p, course, course.checkpoint_target(sid))
        if args.choice == "pause":
            p["nav"]["paused"] = {"at": sid, "resume_target": target, "following": following_ids(course, target)}
        else:
            p["nav"]["paused"] = None
        p["nav"]["cursor"] = target
        return {"step": sid, "choice": args.choice, "current": current_step(p), "paused": p["nav"]["paused"]}
    return mutate(store, course, fn)


def cmd_resume(args, course, store):
    def fn(p):
        need_revision(p, args.revision)
        if p["nav"]["paused"] is None:
            raise ContractError("not paused")
        target = p["nav"]["paused"].get("resume_target") or p["nav"]["cursor"]
        p["nav"]["paused"] = None
        if not p["nav"]["stack"]:
            p["nav"]["cursor"] = target
        return {"current": current_step(p)}
    return mutate(store, course, fn)


def cmd_notice(args, course, store):
    def fn(p):
        need_revision(p, args.revision)
        n = next((x for x in p["notices"] if x["id"] == args.id), None)
        if n is None:
            raise ContractError(f"no notice {args.id}")
        if n["state"] not in ("new", "later"):
            raise ContractError(f"notice {args.id} is {n['state']}")
        if args.now:
            steps = frame_steps(course, n["steps"])
            if not steps:
                n["state"] = "done"
            else:
                p["nav"]["stack"].append({"kind": "notice", "notice_id": n["id"], "steps": steps, "index": 0,
                                          "return_to": current_step(p), "started_at": now()})
                n["state"] = "started"
        else:
            n["later_count"] += 1
            if n["later_count"] >= MAX_LATER:
                n["state"] = "in_repeat"
                for s in n["steps"]:
                    add_repeat(p, s)
            else:
                n["state"] = "later"
        return {"notice": n["id"], "state": n["state"], "current": current_step(p)}
    return mutate(store, course, fn)


def cmd_lesson(args, course, store):
    def fn(p):
        need_revision(p, args.revision)
        steps = [sid for sid in course.order if course.lesson[sid]["id"] == args.lesson_id]
        steps = frame_steps(course, steps)
        if not steps:
            raise ContractError(f"no lesson {args.lesson_id}")
        p["nav"]["stack"].append({"kind": "lesson", "lesson_id": args.lesson_id, "steps": steps, "index": 0,
                                  "return_to": current_step(p), "started_at": now()})
        return {"current": current_step(p)}
    return mutate(store, course, fn)


# ---------------------------------------------------------------- read-only

def load_ro(store, course):
    raw = store.read()
    p = parse(raw) if raw is not None else None
    need_current(p, course)
    return p


def cmd_where(args, course, store):
    p = load_ro(store, course)
    sid = current_step(p)
    out = {"revision": p["revision"], "course_version": p["course_version"], "finished": sid == FINISH,
           "mode": p["nav"]["stack"][-1]["kind"] if p["nav"]["stack"] else "main",
           "paused": p["nav"]["paused"], **step_view(course, sid)}
    o = p.get("open")
    out["open"] = o if o and o["step"] == sid else None
    out["notices"] = [{"id": n["id"], "kind": n["kind"], "important": n["important"], "note": n["note"],
                       "later_count": n["later_count"],
                       "lessons": list(dict.fromkeys(course.lesson[s]["title"] for s in n["steps"] if s in course))}
                      for n in offered_notices(p)]
    out["repeat"] = list(p["repeat"])
    base, host, _ = endpoint_of(course)
    out["feedback"] = {"recipient": host, "endpoint": base,
                       "consent": consent_state(store, host) if host else None}
    if host:
        decision, ds, answered = consent_info(store, host)
        if ds == DATA_SET_V2:                               # v2 adds what the runtime needs (EVENT-SCHEMA §5)
            out["feedback"].update(data_set=ds, notice_due=not answered and decision in SENDING,
                                   queued=len(queued_remarks(store)))
    return out


def cmd_summary(args, course, store):
    p = load_ro(store, course)
    lvl = args.level
    if lvl == "all":
        ids = course.order
    elif re.fullmatch(r"S\d+", lvl):
        ids = [s for s in course.order if course.section[s]["id"] == lvl]
    elif re.fullmatch(r"S\d+\.L\d+", lvl):
        ids = [s for s in course.order if course.lesson[s]["id"] == lvl]
    else:
        raise ContractError("LEVEL is all, S<n> or S<n>.L<nn>")
    if not ids:
        raise ContractError(f"no such level {lvl}")
    taken = set(p["completed"]) | set(p["checks"])
    eligible_set, practice, disputed = [], [], []
    for sid in ids:
        st = course.steps[sid]
        if st["type"] not in CHECK_TYPES:
            continue
        if st.get("claims_status") == "disputed":
            disputed.append(sid)
        route = st.get("route", "main")
        if route == "optional_practice":
            practice.append(sid)
            continue
        active = route == "main" or (route == "branch" and sid in taken)
        if st.get("required", True) and active and st.get("eligible"):
            eligible_set.append(sid)

    def best(sid):
        chk = p["checks"].get(sid) or {}
        return (chk.get("best_this_version") or {}).get("status")

    x = [s for s in eligible_set if best(s) == "confirmed"]
    y = [s for s in eligible_set if best(s) == "said_done"]
    z = [s for s in eligible_set if best(s) == "skipped"]
    level_ids = set(ids)
    repeat = [s for s in p["repeat"] if s in level_ids]
    lines = []
    if eligible_set:
        lines.append(f"confirmed {len(x)} of {len(eligible_set)}")
    lines.append(f"said done {len(y)}")
    lines.append(f"skipped {len(z)}")
    pr = [s for s in practice if best(s) == "confirmed"]
    if practice:
        lines.append(f"practice {len(pr)}")
    if repeat:
        lines.append("repeat: " + ", ".join(repeat))
    details = []
    for sid in ids:
        if course.steps[sid]["type"] in CHECK_TYPES and sid in p["checks"]:
            chk = p["checks"][sid]
            details.append({"step": sid, "lifecycle": chk["lifecycle"], "last": chk.get("current"),
                            "best": chk.get("best_this_version")})
    return {"level": lvl, "X": len(x), "N": len(eligible_set), "Y": len(y), "Z": len(z),
            "show_confirmed_line": bool(eligible_set), "confirmed": x, "practice": pr, "repeat": repeat,
            "disputed": disputed, "lines": lines, "checks": details}


# ---------------------------------------------------------------- rollback (operator)

def cmd_rollback(args, course, store):
    store.acquire()
    try:
        raw = store.read()
        if raw is None:
            raise ContractError("no progress.json")
        p = parse(raw)
        m = next((x for x in p.get("migrations", []) if x["id"] == args.to), None)
        if m is None:
            raise ContractError(f"no migration {args.to}")
        path = store.backups / Path(m["backup"]).name
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != m["source_sha256"]:
            raise ContractError("backup does not match its recorded sha256; nothing written")
        saved, _ = store.backup(raw, f"pre-rollback-{p.get('course_version')}-r{p.get('revision')}")
        after = [h for c in p.get("checks", {}).values() for h in c.get("history", [])
                 if h.get("origin") != "legacy_unknown"]
        _hook("before_rollback_write")
        if not store.owns():
            raise ContractError("the lock is no longer ours; nothing written")
        if store.read() != raw:
            raise ContractError("progress.json changed since it was read; nothing written")
        store.write_atomic(store.path, data)
        return {"restored": m["backup"], "current_state_saved_to": saved,
                "lost_from_live_file": {"runtime_attempts": len(after), "completed_now": len(p.get("completed", [])),
                                        "revision": p.get("revision")}}
    finally:
        store.release()


# ---------------------------------------------------------------- feedback events (EVENT-SCHEMA.md)

DATA_SET = "course-feedback-v1"
DATA_SET_V2 = "course-feedback-v2"         # EVENT-SCHEMA §5: remarks only, consent at install, key file
V1_DECISIONS = ("granted", "revoked")
V2_DECISIONS = ("granted_at_install", "acknowledged", "granted", "revoked")
SENDING = ("granted", "granted_at_install", "acknowledged")   # decisions under which flush may send
NOTICE_ANSWERS = ("acknowledged", "granted", "revoked")       # v2: the course-start notice was answered
KEY_FILE_ENV = "GROKBOT_COURSE_ENV"
KEY_FILE_DEFAULT = os.path.expanduser("~/.grokbotceo/course.env")
KEY_RES = {"GROKBOT_INSTALL_ID": re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
           "GROKBOT_SEND_TOKEN": re.compile(r"[A-Za-z0-9_-]{16,256}"),
           "GROKBOT_PARTICIPANT_KEY": re.compile(r"[A-Za-z0-9_-]{16,64}")}
REMARK_KINDS = ("unclear", "wrong", "other")
REMARK_FIELDS = ("source_msg", "kind", "text", "scope", "step", "scenario_id", "parent_id")
REMARK_KEYS = REMARK_FIELDS + ("event_id",)
MASK = "[скрыто]"
BATCH = 50
BODY_MAX = 128 * 1024
TIMEOUT = 10            # ONE hard deadline (s) for the whole request of a flush: connect, TLS, headers, body
LOCK_WAIT = 10          # seconds flush waits for the lock to save the server's answer
LOCAL_HOSTS = ("127.0.0.1", "localhost")
HEX32 = re.compile(r"[0-9a-f]{32}")
ISO = "%Y-%m-%dT%H:%M:%SZ"


def note(msg):
    print(f"progress: note: {msg}", file=sys.stderr)


def stamp_entry(entry, course, sid, o):
    """C3 + EVENT-SCHEMA §3a: everything needed to rebuild the answer event goes into the committed history
    entry: the course version and release at this moment, the shown option order and the event source."""
    entry["course_version"] = course.version
    entry["release_id"] = course.release_id
    disp = (o or {}).get("display") or []
    entry["shown_order"] = [d["option_id"] for d in disp] if disp and course.type(sid) == "quiz" else None
    entry["attempt_uid"] = str(uuid.uuid4())            # the answer identity, generated once, never recomputed


def answer_source(sid, h):
    """EVENT-SCHEMA §2: "answer-uid:" + the stored attempt_uid. The displayed attempt counter is not an identity
    (it restarts per content_version and per situation). Entries written before 0.3.0 have no uid: they get an
    export-only source and are never written to events.jsonl or sent."""
    if h.get("attempt_uid"):
        return "answer-uid:" + h["attempt_uid"]
    return f"answer-legacy:{sid}:{h.get('scenario_id')}:{h.get('content_version')}:{h.get('attempt')}:{h.get('at')}"


def event_id(collector_id, source, kind):
    return hashlib.sha256(f"{collector_id}|{source}|{kind}".encode("utf-8")).hexdigest()[:32]


def jsonl_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def read_jsonl(path: Path):
    """-> (objects of complete lines, torn trailing bytes or b"", number of unreadable complete lines)."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return [], b"", 0
    cut = data.rfind(b"\n") + 1
    torn = data[cut:]
    out, bad = [], 0
    for line in data[:cut].split(b"\n"):
        if not line.strip():
            continue
        try:
            obj = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            bad += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        else:
            bad += 1
    return out, torn, bad


def repair_torn(store, path: Path):
    """Under the lock: cut a torn trailing line back to the last complete line; its bytes go to
    <stem>.torn-<ts> for inspection. Complete lines are never touched. Returns the saved file name or None."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    cut = data.rfind(b"\n") + 1
    if cut == len(data):
        return None
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    saved = path.with_name(f"{path.stem}.torn-{stamp}-{secrets.token_hex(3)}")
    store.write_atomic(saved, data[cut:])
    with open(path, "r+b") as fh:
        fh.truncate(cut)
        fh.flush()
        os.fsync(fh.fileno())
    return saved.name


def append_lines(store, path: Path, objs):
    if not objs:
        return
    store.home.mkdir(parents=True, exist_ok=True)
    repair_torn(store, path)
    with open(path, "ab") as fh:
        for o in objs:
            fh.write(jsonl_bytes(o))
        fh.flush()
        os.fsync(fh.fileno())


def load_outbox(store):
    """The delivery cache. Missing or unreadable -> empty: events are re-sent under the same identity and the
    server answers duplicate."""
    try:
        st = json.loads(store.outbox.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        st = None
    if not isinstance(st, dict):
        st = {}
    out = {"version": 1, "delivered": {}, "rejected": {}}
    for k in ("delivered", "rejected"):
        if isinstance(st.get(k), dict):
            out[k] = st[k]
    return out


def save_outbox(store, st):
    if not store.owns():
        raise ContractError("the lock is no longer ours; outbox-state.json not written")
    store.write_atomic(store.outbox, (json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode(),
                       mode=0o600)


def _identity_from(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict) or d.get("version") != 1 or not HEX32.fullmatch(str(d.get("collector_id"))):
        return None
    for k in ("install_id", "send_token"):
        if d.get(k) is not None and not isinstance(d.get(k), str):
            return None
    if (d.get("install_id") is None) != (d.get("send_token") is None):
        return None
    return d


def _write_identity(store, ident):
    if not store.owns():
        raise ContractError("the lock is no longer ours; identity.json not written")
    data = (json.dumps(ident, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode()
    store.write_atomic(store.identity, data, mode=0o600)
    store.write_atomic(store.identity_bak, data, mode=0o600)


def load_identity(store):
    """identity.json, else a valid identity.json.bak (restored in place, under the lock), else None."""
    ident = _identity_from(store.identity)
    if ident is not None:
        return ident
    ident = _identity_from(store.identity_bak)
    if ident is not None and store.token and store.owns():
        store.write_atomic(store.identity, (json.dumps(ident, ensure_ascii=False, indent=1, sort_keys=True)
                                            + "\n").encode(), mode=0o600)
    return ident


def identity_lost(store, p=None):
    """No valid identity while there is evidence of an earlier r030 identity (EVENT-SCHEMA §1, Bootstrap):
    events.jsonl, consent.jsonl, outbox-state.json, identity.json(.bak) present, or an attempt_uid in the
    history. Pre-r030 history alone is not evidence."""
    if load_identity(store) is not None:
        return False
    if any(f.exists() for f in (store.events, store.consent, store.outbox, store.identity, store.identity_bak)):
        return True
    return p is not None and any(h.get("attempt_uid") for _, h in answer_candidates(p))


def ensure_identity(store, p=None):
    """Under the lock. Created once before the first event; never regenerated while events exist."""
    ident = load_identity(store)
    if ident is not None:
        return ident
    if identity_lost(store, p):
        raise ContractError("identity_lost: identity.json and its .bak are missing or invalid while events "
                            "exist; restore a verified snapshot of identity.json (no new identity is created)")
    ident = {"version": 1, "collector_id": secrets.token_hex(16), "install_id": None, "send_token": None,
             "created_at": now()}
    _write_identity(store, ident)
    return ident


def parse_at(at):
    try:
        return _dt.datetime.strptime(at, ISO)
    except (TypeError, ValueError):
        return None


def reconstruct_version(p, at):
    """Course version of a history entry written without one (before 0.3.0): only from the migrations
    journal, when the entry is strictly earlier than a migration that names its from-version. The nearest
    such migration wins. Anything else (no time, equal times, no later migration) is unknown."""
    t = parse_at(at)
    if t is None:
        return None, "unknown"
    later = []
    for m in p.get("migrations") or []:
        mt = parse_at((m or {}).get("at"))
        if mt is None or mt == t:
            return None, "unknown"
        if mt > t:
            later.append((mt, m))
    if not later:
        return None, "unknown"
    frm = min(later, key=lambda x: x[0])[1].get("from")
    if not isinstance(frm, str) or not re.fullmatch(r"\d+\.\d+\.\d+", frm):
        return None, "unknown"
    return frm, "reconstructed"


def history_entries(p):
    """Every runtime attempt in the file: live checks and checks archived in legacy (removed steps).
    Schema-1 records (origin legacy_unknown) are not attempts and give no event."""
    for sid, chk in (p.get("checks") or {}).items():
        for h in chk.get("history") or []:
            yield sid, h
    for sid, ents in (p.get("legacy") or {}).items():
        if sid == "_file":
            continue
        for ent in ents or []:
            chk = (ent.get("original") or {}).get("check") or {}
            for h in chk.get("history") or []:
                yield sid, h


def answer_event(cid, p, sid, h, course):
    if "course_version" in h:
        cv, rid, origin = h.get("course_version"), h.get("release_id"), "recorded"
    else:
        (cv, origin), rid = reconstruct_version(p, h.get("at")), None
    # every field comes from the stored entry (never from "now" or the current course), so a rebuilt event is
    # the same payload as the original; for 0.3.0 entries a quiz is the one with a frozen shown_order
    ev = h.get("evidence")
    if h.get("attempt_uid"):
        is_ex = h.get("shown_order") is None
    else:
        is_ex = course is not None and sid in course and course.type(sid) == "exercise"
    ev_class = ev if (is_ex or ev == "verified_artifact") and ev not in (None, "-") else None
    src = answer_source(sid, h)
    return {"id": event_id(cid, src, "answer") if cid else None, "type": "answer", "course_version": cv, "release_id": rid,
            "version_origin": origin, "at": h.get("at"), "step": sid, "scenario_id": h.get("scenario_id"),
            "option_ids": list(h.get("option_ids") or []), "shown_order": h.get("shown_order"),
            "status": h.get("status"), "attempt": h.get("attempt"), "revealed": bool(h.get("revealed")),
            "evidence_class": ev_class}


def answer_candidates(p, sendable=False):
    """Runtime attempts; sendable=True keeps only those with an attempt_uid (recorded by 0.3.0 or later)."""
    return [(sid, h) for sid, h in history_entries(p)
            if isinstance(h, dict) and h.get("origin") != "legacy_unknown"
            and isinstance(h.get("attempt"), int) and h["attempt"] >= 1
            and (not sendable or isinstance(h.get("attempt_uid"), str))]


def rebuild_missing(store, p, course):
    """Under the lock: append the answer event of every committed attempt with an attempt_uid that has no
    line yet (EVENT-SCHEMA §3a). Idempotent; uses the stored uid only."""
    if p is None:
        return 0
    cands = answer_candidates(p, sendable=True)
    if not cands:
        return 0
    cid = ensure_identity(store, p)["collector_id"]
    have = {e.get("id") for e in read_jsonl(store.events)[0]}
    new = []
    for sid, h in cands:
        ev = answer_event(cid, p, sid, h, course)
        if ev["id"] not in have:
            have.add(ev["id"])
            new.append(ev)
    append_lines(store, store.events, new)
    return len(new)


_MASKS = [
    re.compile(r"(?<![\w-])(?:sk-(?:proj-|ant-)?|xai-)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?<!\w)(?:ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|AKIA[0-9A-Z]{12,})"),
    re.compile(r"(?<![\w.-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?![\w.-])"),   # JWT-like
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),                                                    # e-mail
    re.compile(r"(?<![\w+/=-])[A-Za-z0-9+/_-]{32,}={0,2}(?![\w+/=-])"),                              # hex/base64 >=32
]
_PHONE = re.compile(r"\+?\d[\d \t().-]{7,}\d")


def mask_text(text: str) -> str:
    """EVENT-SCHEMA §4. Known formats only; free text may hold secrets this filter does not recognise."""
    for rx in _MASKS:
        text = rx.sub(MASK, text)
    return _PHONE.sub(lambda m: MASK if len(re.sub(r"\D", "", m.group())) >= 9 else m.group(), text)


def _str_or_null(d, key, limit, required=False):
    v = d.get(key)
    if v is None:
        if required:
            raise ContractError(f"remark: {key} is required")
        return None
    if not isinstance(v, str) or not v or len(v) > limit:
        raise ContractError(f"remark: {key} must be a non-empty string of at most {limit} characters, or null")
    return v


def read_remark(stream):
    raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ContractError("remark: input is larger than 64 KiB")
    try:
        d = json.loads(raw)
    except ValueError:
        raise ContractError("remark: stdin must be one JSON object")
    if not isinstance(d, dict):
        raise ContractError("remark: stdin must be one JSON object")
    extra = sorted(set(d) - set(REMARK_KEYS))
    if extra:
        raise ContractError(f"remark: unknown fields {extra}")
    if d.get("kind") not in REMARK_KINDS:
        raise ContractError(f"remark: kind must be one of {REMARK_KINDS}")
    if d.get("scope") not in ("step", "course"):
        raise ContractError("remark: scope must be step or course")
    text = d.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ContractError("remark: text must be a non-empty string")
    text = mask_text(text.strip())
    if len(text) > 1000:
        raise ContractError("remark: text is longer than 1000 characters after masking; shorten it")
    pid = d.get("parent_id")
    if pid is not None and (not isinstance(pid, str) or not HEX32.fullmatch(pid)):
        raise ContractError("remark: parent_id must be the 32-hex id of an earlier remark, or null")
    eid = d.get("event_id")
    if eid is not None and (not isinstance(eid, str) or not HEX32.fullmatch(eid)):
        raise ContractError("remark: event_id must be the 32-hex id printed by an earlier remark, or absent")
    return eid, {"source_msg": _str_or_null(d, "source_msg", 128), "kind": d["kind"], "text": text,
            "scope": d["scope"], "step": _str_or_null(d, "step", 64, required=d["scope"] == "step"),
            "scenario_id": _str_or_null(d, "scenario_id", 96), "parent_id": pid}


def cmd_remark(args, course, store):
    """A learner's remark: one immutable event. Never reads or writes progress.json."""
    retry_id, r = read_remark(sys.stdin)
    if r["step"] is not None and r["step"] not in course:
        raise ContractError(f"remark: {r['step']} is not a step of course {course.version}")
    store.acquire()
    try:
        raw = store.read()
        try:
            p = parse(raw) if raw is not None else None
        except ContractError:
            p = None
        cid = ensure_identity(store, p)["collector_id"]
        events = read_jsonl(store.events)[0]
        if r["parent_id"] and r["parent_id"] not in {e.get("id") for e in events if e.get("type") == "remark"}:
            raise ContractError("remark: parent_id is not an earlier remark")
        if retry_id is not None:
            # retry of an earlier call (EVENT-SCHEMA §2): same id + same payload -> nothing new; else conflict
            old = next((e for e in events if e.get("id") == retry_id), None)
            if old is None or old.get("type") != "remark":
                raise ContractError("remark: event_id is not a recorded remark; call remark without event_id")
            if {k: old.get(k) for k in REMARK_FIELDS} != r:
                raise ContractError("conflict: event_id exists with a different payload; nothing written")
            return {"id": retry_id, "written": False}
        # identity is always a fresh client uuid; source_msg is metadata only (it may repeat across chats)
        eid = event_id(cid, "remark-uuid:" + str(uuid.uuid4()), "remark")
        ev = {"id": eid, "type": "remark", "course_version": course.version, "release_id": course.release_id,
              "version_origin": "recorded", "at": now(), **r}
        held = held_now(store, course)
        if held:
            ev["held"] = True               # written while stopped (v2 revoked): never sent, even after resume
        append_lines(store, store.events, [ev])
        out = {"id": eid, "written": True}
        if held:
            out["held"] = True
        return out
    finally:
        store.release()


def held_now(store, course):
    """True when the effective v2 consent is `revoked` (tech-requirements 22d): a remark written now stays local
    for good. The recipient is the configured endpoint's host; with no endpoint, any recipient whose last line
    is a v2 stop counts."""
    host = endpoint_of(course)[1]
    hosts = {host} if host else {(c.get("scope") or {}).get("recipient") for c in read_jsonl(store.consent)[0]
                                 if isinstance(c.get("scope"), dict)}
    for h in hosts:
        if isinstance(h, str):
            decision, ds, _ = consent_info(store, h)
            if decision == "revoked" and ds == DATA_SET_V2:
                return True
    return False


def recipient_ok(host):
    return isinstance(host, str) and 0 < len(host) <= 253 and re.fullmatch(r"[a-z0-9.-]+", host) is not None


def consent_lines(store, host):
    """Complete consent lines for this recipient of a known data set and decision, oldest first."""
    out = []
    for c in read_jsonl(store.consent)[0]:
        sc = c.get("scope") or {}
        if not isinstance(sc, dict) or sc.get("recipient") != host:
            continue
        ds, dec = sc.get("data_set"), c.get("decision")
        if (ds == DATA_SET and dec in V1_DECISIONS) or (ds == DATA_SET_V2 and dec in V2_DECISIONS):
            out.append((ds, dec))
    return out


def consent_info(store, host):
    """-> (decision or "none", data set of the last line or None, v2 notice answered?)."""
    lines = consent_lines(store, host)
    if not lines:
        return "none", None, False
    answered = any(ds == DATA_SET_V2 and dec in NOTICE_ANSWERS for ds, dec in lines)
    return lines[-1][1], lines[-1][0], answered


def cmd_consent(args, course, store):
    """The learner's sending decision, one appended line. v1: granted | revoked. v2 (EVENT-SCHEMA §5):
    granted_at_install (written by the install, once: never over an earlier decision), acknowledged (the
    course-start notice answered; never re-grants after a stop), and the stop / resume words as revoked /
    granted, which keep the data set already in force (none yet -> v1, as before)."""
    host = (args.recipient or "").strip().lower()
    if not host:
        host = endpoint_of(course)[1] or ""
    if not recipient_ok(host):
        raise ContractError("--recipient must be a host name (the course author's server); "
                            "none given and no endpoint configured")
    pkey = getattr(args, "participant_key", None)
    if pkey is not None:
        if args.decision != "granted_at_install":
            raise ContractError("--participant-key goes only with --decision granted_at_install")
        if not KEY_RES["GROKBOT_PARTICIPANT_KEY"].fullmatch(pkey):
            raise ContractError("--participant-key has an invalid format")
    store.acquire()
    try:
        raw = store.read()
        try:
            p = parse(raw) if raw is not None else None
        except ContractError:
            p = None
        decision, ds, answered = consent_info(store, host)
        if args.decision in ("granted_at_install", "acknowledged"):
            data_set = DATA_SET_V2
        else:
            data_set = ds or DATA_SET
        write = True
        if args.decision == "granted_at_install":
            write = decision == "none"                      # a re-install or update never overrides a decision
        elif args.decision == "acknowledged":
            if ds != DATA_SET_V2:
                raise ContractError("acknowledged needs the consent recorded at install (course-feedback-v2)")
            write = not answered and decision in SENDING     # after «не отправляй» it stays stopped
        ensure_identity(store, p)                           # bootstrap before the first r030 file is written
        if write:
            line = {"at": now(), "decision": args.decision,
                    "scope": {"data_set": data_set, "recipient": host,
                              "course_major": str(semver(course.version)[0])},
                    "course_version": course.version}
            append_lines(store, store.consent, [line])
        key_file = None
        if pkey is not None:
            key_file = "written" if write_key_file({"GROKBOT_PARTICIPANT_KEY": pkey}) else "failed"
        decision, ds, answered = consent_info(store, host)
    finally:
        store.release()
    if data_set == DATA_SET and ds == DATA_SET:
        return {"decision": args.decision, "recipient": host, "data_set": DATA_SET}
    out = {"decision": decision, "recipient": host, "data_set": ds, "written": write,
           "notice_due": ds == DATA_SET_V2 and not answered and decision in SENDING,
           "endpoint": endpoint_of(course)[0]}             # for the install's flush --endpoint
    if key_file:
        out["key_file"] = key_file
    return out


def consent_state(store, host):
    """The decision of the last complete consent line for this recipient (v1 or v2 data set): granted | revoked |
    granted_at_install | acknowledged | none."""
    return consent_info(store, host)[0]


def effective_consent(store, host):
    return consent_state(store, host) in SENDING


def key_file_path():
    return Path(os.environ.get(KEY_FILE_ENV) or KEY_FILE_DEFAULT)


def read_key_file():
    """-> {name: value} of the valid known lines of the key file; missing or unreadable -> {}."""
    try:
        text = key_file_path().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    out = {}
    for line in text.splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name in KEY_RES and KEY_RES[name].fullmatch(value):
            out[name] = value
    return out


def write_key_file(updates):
    """Merge into the key file: created 0600 from the start (parent 0700), tmp + fsync + rename. Never printed.
    -> True, or False (with a note) when it cannot be written; the caller goes on."""
    path = key_file_path()
    data = read_key_file()
    data.update(updates)
    body = "".join(f"{k}={data[k]}\n" for k in sorted(data)).encode("utf-8")
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError as e:
        note(f"key file not written ({type(e).__name__})")
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


def key_file_credentials():
    k = read_key_file()
    if k.get("GROKBOT_INSTALL_ID") and k.get("GROKBOT_SEND_TOKEN"):
        return k["GROKBOT_INSTALL_ID"], k["GROKBOT_SEND_TOKEN"]
    return None


def endpoint_of(course):
    """-> (base url or None, host or None, refusal reason or None)."""
    url = os.environ.get("GROKBOT_FEEDBACK_URL")
    if not url:
        try:
            cfg = json.loads((course.path.parent / "feedback.json").read_text(encoding="utf-8"))
            url = cfg.get("endpoint") if isinstance(cfg, dict) else None
        except (OSError, ValueError, UnicodeDecodeError):
            url = None
    if not url:
        return None, None, None
    return normalise_endpoint(url)


DEFAULT_PORTS = {"https": 443, "http": 80}


def normalise_endpoint(url):
    """-> (scheme://host[:port][/path] or None, host or None, refusal reason or None). The default port and a
    trailing slash are dropped and scheme/host lower-cased, so two spellings of one endpoint compare equal."""
    try:
        u = urllib.parse.urlsplit(str(url).strip())
        host = (u.hostname or "").lower()
        port = u.port
    except ValueError:
        return None, None, "endpoint is not a URL"
    if u.username or u.password or u.query or u.fragment or not host:
        return None, None, "endpoint must be scheme://host[:port][/path] without credentials, query or fragment"
    scheme = u.scheme.lower()
    if scheme == "https" or (scheme == "http" and host in LOCAL_HOSTS):
        netloc = host + (f":{port}" if port and port != DEFAULT_PORTS[scheme] else "")
        return urllib.parse.urlunsplit((scheme, netloc, u.path.rstrip("/"), "", "")), host, None
    return None, None, f"plain {scheme} is refused for {host} (https only)"


class DeadlineExceeded(OSError):
    """The overall request deadline passed; treated as a transport failure (events stay pending)."""


def encode_body(body) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


# The network call runs in ONE short-lived child process (python -I -B -c, stdlib only, no extra file to ship).
# The child gets everything on stdin (url, body, token - never in argv) and writes "<status>\n<body>" (body
# capped) to stdout. The parent owns the deadline: it waits for the child at most until the deadline and then
# terminates (0.5 s grace) and kills it. This bounds every phase - DNS, connect, TLS, send, headers, a response
# that outlives its connection object - by construction, and nothing can be sent after the child is gone.
# http.client follows no redirects and uses no proxy. GROKBOT_TEST_DNS_DELAY is a test-only fault injection,
# ignored unless GROKBOT_TEST_HOOKS=1.
_CHILD = r"""
import http.client, json, os, socket, ssl, sys, time, urllib.parse
req = json.loads(sys.stdin.buffer.read().decode("utf-8"))
end = time.monotonic() + req["seconds"]
if os.environ.get("GROKBOT_TEST_HOOKS") == "1" and os.environ.get("GROKBOT_TEST_DNS_DELAY"):
    _real = socket.getaddrinfo
    def _slow(*a, **k):
        time.sleep(float(os.environ["GROKBOT_TEST_DNS_DELAY"]))
        return _real(*a, **k)
    socket.getaddrinfo = _slow
left = lambda: max(0.01, end - time.monotonic())
u = urllib.parse.urlsplit(req["url"])
if u.scheme == "https":
    conn = http.client.HTTPSConnection(u.hostname, u.port, timeout=left(), context=ssl.create_default_context())
else:
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=left())
conn.connect()
if time.monotonic() >= end:
    sys.exit(3)
conn.sock.settimeout(left())
data = req["body"].encode("utf-8")
headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
if req.get("token"):
    headers["Authorization"] = "Bearer " + req["token"]
conn.request("POST", u.path or "/", body=data, headers=headers)
resp = conn.getresponse()
body = resp.read(req["cap"] + 1)
sys.stdout.buffer.write(str(resp.status).encode() + b"\n" + body)
sys.stdout.buffer.flush()
"""
LAST_CHILD_PID = None   # tests only: the pid of the last request child


def _reap(proc):
    """Bounded cleanup: terminate, 0.5 s grace, kill, wait; close the pipes."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(0.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    for f in (proc.stdin, proc.stdout, proc.stderr):
        try:
            if f:
                f.close()
        except OSError:
            pass


def _post(url, body, token=None, deadline=None):
    """POST JSON under ONE hard overall deadline (TIMEOUT seconds unless given), counted from this call and
    covering every phase. Returns (status, parsed JSON) or raises OSError / ValueError; on the deadline raises
    DeadlineExceeded with the child already gone and no partial answer used."""
    global LAST_CHILD_PID
    seconds = TIMEOUT if deadline is None else deadline
    end = time.monotonic() + seconds
    payload = json.dumps({"url": url, "body": encode_body(body).decode("utf-8"), "token": token,
                          "seconds": seconds, "cap": BODY_MAX}).encode("utf-8")
    proc = subprocess.Popen([sys.executable, "-I", "-B", "-c", _CHILD], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    LAST_CHILD_PID = proc.pid
    try:
        out, err = proc.communicate(payload, timeout=max(0.01, end - time.monotonic()))
    except subprocess.TimeoutExpired:
        raise DeadlineExceeded("request deadline passed")
    finally:
        _reap(proc)
    if time.monotonic() > end:
        raise DeadlineExceeded("request deadline passed")             # a late answer is never used
    if proc.returncode != 0:
        lines = [x for x in err.decode("utf-8", "replace").strip().splitlines() if x.strip()]
        raise OSError("request failed: " + (lines[-1][:160] if lines else f"exit {proc.returncode}"))
    status_line, _, data = out.partition(b"\n")
    if len(data) > BODY_MAX:
        raise ValueError("answer larger than the body cap")
    return int(status_line), json.loads(data.decode("utf-8"))


def _envelope(install_id, events, contract=None):
    body = {"install_id": install_id, "events": events}
    if contract:
        body["contract"] = contract
    return body


def _batch(events, install_id, contract=None):
    """At most BATCH events and an encoded body of at most BODY_MAX bytes; stop before exceeding."""
    out = []
    for e in events[:BATCH]:
        if len(encode_body(_envelope(install_id, out + [e], contract))) > BODY_MAX:
            break
        out.append(e)
    return out


def _pending(store, types=None):
    """Events not yet delivered or rejected, in file order. types=("remark",) under v2."""
    st = load_outbox(store)
    done = set(st["delivered"]) | set(st["rejected"])
    return [e for e in read_jsonl(store.events)[0] if HEX32.fullmatch(str(e.get("id"))) and e["id"] not in done
            and (types is None or e.get("type") in types) and e.get("held") is not True]   # held: never sent


def _pending_count(store, types=None):
    return len(_pending(store, types))


def queued_remarks(store):
    """v2 queue (EVENT-SCHEMA §5): remark lines of events.jsonl not yet delivered or rejected. The queue is not a
    second file: events.jsonl holds every remark before any send, outbox-state.json marks what went."""
    return [e["id"] for e in _pending(store, ("remark",))]


def cmd_queue(args, course, store):
    """Read-only: the remarks waiting to be sent (ids only, never text)."""
    ids = queued_remarks(store)
    return {"queued": len(ids), "ids": ids}


def cmd_whoami(args, course, store):
    """Read-only (tech-requirements 22h, «покажи мой ID»): the installation ID from the key file, else from
    identity.json; null before registration. Never the send token or the participant key."""
    iid = read_key_file().get("GROKBOT_INSTALL_ID")
    if not iid:
        ident = _identity_from(store.identity) or _identity_from(store.identity_bak)
        iid = ident.get("install_id") if ident else None
    return {"install_id": iid if isinstance(iid, str) and iid else None}


def cmd_flush(args, course, store):
    """EVENT-SCHEMA §3: the ONLY command that touches the network, called explicitly. At most one request:
    register when there is no install, else one batch. No retry inside. Always prints one JSON summary;
    exit 0, except `refused` (exit 3); a broken installation is exit 2 (ContractError on stderr, no summary).
    v2 (EVENT-SCHEMA §5): remarks only, envelope "contract", credentials from the key file, plus `data_set` and
    `delivered_ids` in the summary; `registered` also reports `key_file`.

      status          meaning for the caller
      delivered       one batch went and was answered; `pending` may still be > 0 (the next flush sends more)
      nothing_pending nothing to send
      registered      the install was registered (one request); events go with the next flush
      pending         nothing delivered now, everything stays on disk for a later flush;
                      reason: deadline | transport | http | busy | oversize | register_discarded
      skipped         not configured or not allowed, no request was made;
                      reason: no_endpoint | endpoint_refused | no_consent | identity_lost
      refused         the command itself is wrong, nothing was read, written or sent; EXIT 3;
                      reason: endpoint_required (an endpoint is configured, --endpoint missing) |
                      endpoint_mismatch (--endpoint differs from the configured one, or none is configured)
    """
    res = {"status": None, "reason": None, "rebuilt": 0, "action": None, "sent": 0, "accepted": 0,
           "duplicate": 0, "rejected": 0, "pending": 0}

    def done(status, reason=None, action=None):
        res["status"], res["reason"] = status, reason
        res["action"] = action or reason or status
        return res

    base, host, refused = endpoint_of(course)
    # The command names its destination (--endpoint) so a reviewer of the tool call sees where data goes. It
    # must equal the configured endpoint after normalisation; otherwise nothing at all is done.
    given = getattr(args, "endpoint", None)
    if given is not None or base is not None:
        if given is None:
            res["detail"] = "--endpoint is required when an endpoint is configured; copy where.feedback.endpoint"
            return done("refused", "endpoint_required")
        if normalise_endpoint(given)[0] is None or normalise_endpoint(given)[0] != base:
            res["detail"] = "--endpoint differs from the configured endpoint; nothing was sent"
            return done("refused", "endpoint_mismatch")
    try:
        store.acquire()
    except ContractError as e:
        note(f"feedback not sent now, the course file is busy ({e})"[:300])
        return done("pending", "busy")
    try:
        raw = store.read()
        try:
            p = parse(raw) if raw is not None else None
        except ContractError as e:
            p = None
            note(f"progress.json unreadable, answer events not rebuilt ({e})")
        try:
            res["rebuilt"] = rebuild_missing(store, p, course)
        except ContractError as e:
            if not str(e).startswith("identity_lost"):
                raise
            note("identity_lost: nothing is sent and no new identity is created; run doctor")
            return done("skipped", "identity_lost")
        res["pending"] = _pending_count(store)
        v2 = bool(host) and consent_info(store, host)[1] == DATA_SET_V2
        types, contract = (("remark",), DATA_SET_V2) if v2 else (None, None)
        if v2:
            res["data_set"], res["delivered_ids"] = DATA_SET_V2, []
            res["pending"] = _pending_count(store, types)
        if refused:
            res["detail"] = refused
            return done("skipped", "endpoint_refused", "refused")
        if base is None:
            return done("skipped", "no_endpoint")
        if not effective_consent(store, host):
            return done("skipped", "no_consent")
        if identity_lost(store, p):
            note("identity_lost: nothing is sent and no new identity is created; run doctor")
            return done("skipped", "identity_lost")
        ident = ensure_identity(store, p)
        creds = None
        if v2:
            # v2: the key file (outside mentor/, survives updates) is the credential store; an earlier
            # registration kept only in identity.json is copied there once
            creds = key_file_credentials()
            if creds is None and ident["install_id"] and ident["send_token"]:
                creds = (ident["install_id"], ident["send_token"])
                write_key_file({"GROKBOT_INSTALL_ID": creds[0], "GROKBOT_SEND_TOKEN": creds[1]})
        elif ident["install_id"] and ident["send_token"]:
            creds = (ident["install_id"], ident["send_token"])
        if creds is None:
            res["action"] = "register"
            batch = None
        else:
            pending = _pending(store, types)
            res["pending"] = len(pending)
            if not pending:
                return done("nothing_pending")
            install_id, token = creds
            batch = _batch(pending, install_id, contract)
            if not batch:
                note("the first pending event does not fit one request; it stays pending")
                return done("pending", "oversize")
            res["action"] = "send"
    finally:
        if store.token:
            store.release()

    _hook("before_network")
    try:
        if batch is None:
            status, body = _post(base + "/v1/register", {})
            if status not in (200, 201) or not isinstance(body, dict) or not isinstance(body.get("install_id"), str) \
                    or not isinstance(body.get("send_token"), str):
                res["http_status"] = status
                raise ValueError(f"register answered {status} without install_id/send_token")
        else:
            status, body = _post(base + "/v1/course-event", _envelope(install_id, batch, contract), token)
            if status != 200 or not isinstance(body, dict):
                res["http_status"] = status
                raise ValueError(f"course-event answered {status}")
    except (OSError, ValueError) as e:      # deadline, child failure, 3xx (not followed), 4xx, 5xx
        res["error"] = f"{type(e).__name__}: {e}"[:200]
        note(f"feedback not sent, stays pending ({res['error']})")
        reason = ("deadline" if isinstance(e, DeadlineExceeded) else "http" if "http_status" in res
                  else "transport")
        return done("pending", reason, res["action"])
    _hook("after_network")

    try:
        store.acquire_wait(LOCK_WAIT)
    except ContractError as e:
        # Events stay pending and are re-sent (the server answers duplicate). A lost registration answer
        # leaves identity.json without install_id, so the next flush simply registers again; the unused
        # server installation holds no events and is harmless. identity_lost is not triggered.
        res["error"] = "lock busy, answer not saved"
        note(f"feedback answer not saved after {LOCK_WAIT}s, events stay pending ({e})")
        return done("pending", "busy", res["action"])
    try:
        if batch is None:
            ident = load_identity(store)
            if ident is not None and not ident["install_id"]:        # the registration is added once
                ident.update(install_id=body["install_id"], send_token=body["send_token"])
                _write_identity(store, ident)
                if v2:
                    res["key_file"] = "written" if write_key_file(
                        {"GROKBOT_INSTALL_ID": body["install_id"], "GROKBOT_SEND_TOKEN": body["send_token"]}) \
                        else "failed"
                return done("registered", None, "registered")
            return done("pending", "register_discarded")
        st = load_outbox(store)
        sent = {e["id"] for e in batch}
        at = now()
        for key in ("accepted", "duplicate"):
            for eid in body.get(key) or []:
                if eid in sent:
                    st["delivered"][eid] = {"at": at, "result": key}
                    res[key] += 1
                    if v2:
                        res["delivered_ids"].append(eid)
        for r in body.get("rejected") or []:
            if isinstance(r, dict) and r.get("id") in sent and r["id"] not in st["delivered"]:
                st["rejected"][r["id"]] = {"at": at, "reason": str(r.get("reason"))[:64]}
                res["rejected"] += 1
        save_outbox(store, st)
        res["sent"] = len(batch)
        res["pending"] -= res["accepted"] + res["duplicate"] + res["rejected"]
        return done("delivered", None, "send")
    finally:
        store.release()


def cmd_export_feedback(args, course, store):
    """Read-only: every event as one JSON line; committed answers without a line yet are shown as they will
    be written (rebuilt by the next record, flush or doctor)."""
    events = read_jsonl(store.events)[0]
    raw = store.read()
    p = parse(raw) if raw is not None else None
    ident = _identity_from(store.identity) or _identity_from(store.identity_bak)
    cid = ident["collector_id"] if ident else None
    have = {e.get("id") for e in events}
    if p is not None:
        for sid, h in answer_candidates(p):
            ev = answer_event(cid, p, sid, h, course)
            if cid is None:
                ev["id"] = None                             # no identity yet: shown, not identifiable
            elif not h.get("attempt_uid"):
                ev["export_only"] = True                    # written before 0.3.0: never sent
            if ev["id"] is None or ev["id"] not in have:
                have.add(ev["id"])
                events.append(ev)
    for e in events:
        sys.stdout.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    return None


def cmd_doctor(args, course, store):
    out = {"files": {}, "repaired": [], "rebuilt": 0, "identity": None}
    for path in (store.events, store.consent):
        objs, torn, bad = read_jsonl(path)
        out["files"][path.name] = {"lines": len(objs), "torn_bytes": len(torn), "bad_lines": bad,
                                   "torn_saved": sorted(x.name for x in store.home.glob(path.stem + ".torn-*"))}
    store.acquire()
    try:
        for path in (store.events, store.consent):
            saved = repair_torn(store, path)
            if saved:
                out["repaired"].append(saved)
        raw = store.read()
        try:
            p = parse(raw) if raw is not None else None
        except ContractError as e:
            p = None
            out["progress_error"] = str(e)
        out["identity"] = ("identity_lost" if identity_lost(store, p)
                           else "ok" if load_identity(store) is not None else "absent")
        if out["identity"] != "identity_lost":
            out["rebuilt"] = rebuild_missing(store, p, course)
    finally:
        store.release()
    return out


# ---------------------------------------------------------------- CLI

def build_parser():
    ap = argparse.ArgumentParser(prog="progress.py", description="Mentor course bookkeeping (see module doc).")
    ap.add_argument("--kb-home", default="mentor")
    ap.add_argument("--course", default="grokbotceo/course/course.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--json", action="store_true", help="output is always JSON; accepted for symmetry")
        sp.add_argument("--kb-home", default=argparse.SUPPRESS)
        sp.add_argument("--course", default=argparse.SUPPRESS)
        return sp

    common(sub.add_parser("migrate"))
    common(sub.add_parser("where"))
    sp = common(sub.add_parser("open"))
    sp.add_argument("step")
    sp = common(sub.add_parser("record"))
    sp.add_argument("--token", required=True)
    sp.add_argument("--attempt", type=int)
    sp.add_argument("--option", action="append")
    sp.add_argument("--label", action="append", help="the display label the learner chose (with --option)")
    sp.add_argument("--rubric")
    sp.add_argument("--evidence")
    sp.add_argument("--artifact-ref")
    sp.add_argument("--artifact-stdin", action="store_true",
                    help="read the artifact from stdin as lines method: / detail: / observed: (no quoting)")
    sp.add_argument("--said-done", action="store_true")
    sp.add_argument("--message-id")
    sp = common(sub.add_parser("skip"))
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--token")
    g.add_argument("--revision", type=int)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--message-id")
    sp = common(sub.add_parser("advance"))
    sp.add_argument("--revision", type=int, required=True)
    sp = common(sub.add_parser("checkpoint"))
    sp.add_argument("--revision", type=int, required=True)
    sp.add_argument("--choice", choices=("continue", "pause"), required=True)
    sp = common(sub.add_parser("resume"))
    sp.add_argument("--revision", type=int, required=True)
    sp = common(sub.add_parser("notice"))
    sp.add_argument("id")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--now", action="store_true")
    g.add_argument("--later", action="store_true")
    sp.add_argument("--revision", type=int, required=True)
    sp = common(sub.add_parser("lesson"))
    sp.add_argument("lesson_id")
    sp.add_argument("--revision", type=int, required=True)
    sp = common(sub.add_parser("summary"))
    sp.add_argument("level")
    sp = common(sub.add_parser("rollback"))
    sp.add_argument("--to", required=True)
    common(sub.add_parser("remark"))
    sp = common(sub.add_parser("consent"))
    sp.add_argument("--decision", choices=V2_DECISIONS, required=True)
    sp.add_argument("--recipient", help="the course author's host; default: the configured endpoint's host")
    sp.add_argument("--participant-key", help="v2, with granted_at_install: the key from the personal install link")
    sp = common(sub.add_parser("flush"))
    sp.add_argument("--endpoint", help="the configured endpoint, verbatim from where.feedback.endpoint")
    common(sub.add_parser("queue"))
    common(sub.add_parser("whoami"))
    common(sub.add_parser("export-feedback"))
    common(sub.add_parser("doctor"))
    return ap


COMMANDS = {"migrate": cmd_migrate, "where": cmd_where, "open": cmd_open, "record": cmd_record,
            "skip": cmd_skip, "advance": cmd_advance, "checkpoint": cmd_checkpoint, "resume": cmd_resume,
            "notice": cmd_notice, "lesson": cmd_lesson, "summary": cmd_summary, "rollback": cmd_rollback,
            "remark": cmd_remark, "consent": cmd_consent, "flush": cmd_flush, "queue": cmd_queue,
            "whoami": cmd_whoami,
            "export-feedback": cmd_export_feedback,
            "doctor": cmd_doctor}
# Only `flush` touches the network (EVENT-SCHEMA §3). Every other command is local, whatever the endpoint and
# consent: it never spawns the request child and never opens a socket.


def main(argv=None) -> int:
    ap = build_parser()
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        course = Course(Path(args.course))
        store = Store(args.kb_home)
        out = COMMANDS[args.cmd](args, course, store)
    except ContractError as e:
        print(f"progress: ERROR: {e}", file=sys.stderr)
        return 2
    if out is not None:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.stdout.flush()
    if args.cmd == "flush" and out.get("status") == "refused":
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
