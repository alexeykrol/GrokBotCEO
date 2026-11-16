#!/usr/bin/env python3
"""
Tests for Mentor's course bookkeeping (course/progress.py) and the build fields it relies on
(scripts/course-merge.py). Contract: course/SCHEMA.md §2.7, §4; course/MENTOR-RUNTIME.md §1-3.

Acceptance items 1-27 of the P1 design are named in the test names (t01 ... t27). Synthetic,
fictional courses and progress files are built in temporary folders; the course of this release is
used read-only. The five real schema-1 progress files of the 2026-11-12 synthetic run and course
0.1.0 live only in the development repo (../docs/design/p1-fixtures/); tests that need them are
skipped in a release clone. Every write goes to a tempfile folder; the last test proves that nothing
in the release tree or the fixtures changed. Stdlib only, no network, no bots.
These tests check the script, not the platform: they do not show that Mentor calls it.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
COURSE_FILE = RELEASE_DIR / "course" / "course.json"
FIXTURES = RELEASE_DIR.parent / "docs" / "design" / "p1-fixtures"
LEARNERS = ["novichok", "oshibayushchiysya", "otlichnik", "sporshchik", "toropyga"]
HAVE_FIXTURES = all((FIXTURES / f"uchenik-{n}-progress.json").is_file() for n in LEARNERS)
HAVE_BUILD_INPUTS = (RELEASE_DIR.parent / "docs" / "design" / "claims-map.tsv").is_file()
# The P1 fixture tests and the journal check describe release 0.2.0 (migration 0.1.0 -> 0.2.0). They read
# that release's course.json from git (commit a06537d, "0.2.0" in the scenario registry header), not the
# working-tree course.json, which moves on with later releases (P2b candidate 2: 0.3.0).
RELEASE_020 = "a06537d"
_COURSE_020 = []


def course_020() -> Path:
    """Path of a temp copy of release 0.2.0's course.json (dev repo only: needs git history)."""
    if not _COURSE_020:
        import subprocess
        r = subprocess.run(["git", "-C", str(RELEASE_DIR.parent), "show", f"{RELEASE_020}:release/course/course.json"],
                           capture_output=True)
        if r.returncode != 0:
            raise unittest.SkipTest(f"release 0.2.0 ({RELEASE_020}) not readable from git")
        d = Path(tempfile.mkdtemp(prefix="p1-course-020-"))
        TMP_ROOTS.append(d)
        (d / "course.json").write_bytes(r.stdout)
        _COURSE_020.append(d / "course.json")
    return _COURSE_020[0]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PG = _load("progress_under_test", RELEASE_DIR / "course" / "progress.py")
CM = _load("course_merge_under_test", SCRIPT_DIR / "course-merge.py")
TMP_ROOTS = []


def tree_state(root: Path):
    if not root.exists():
        return {}
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


BEFORE = {"release": tree_state(RELEASE_DIR), "fixtures": tree_state(FIXTURES)}


# ---------------------------------------------------------------- synthetic course

def ex(sid, text="t"):
    return {"id": sid, "type": "explain", "text": text, "example": "e", "content_version": "cv-" + sid + "-" + text}


def quiz(sid, eligible=True, rubric=True, route="main", key="b", cv=None, claims_status="-", basis="normative"):
    return {"id": sid, "type": "quiz", "question": "q",
            "options": [{"id": o, "text": o, "correct": o == key, "reaction": "r"} for o in "abc"],
            "content_version": cv or "cv-" + sid, "basis": basis, "claims_status": claims_status,
            "route": route, "required": True, "eligible": eligible,
            "rubric_ref": ("R-" + sid) if rubric else "-",
            "scenarios": [{"id": sid, "option_ids": ["a", "b", "c"], "rubric_ref": ("R-" + sid) if rubric else "-"}]}


def exercise(sid, method="workspace_file", detail="notes/plan.md contains a plan", eligible=True, rubric=True):
    return {"id": sid, "type": "exercise", "task": "t", "expected_result": "r",
            "check": {"method": method, "detail": detail}, "on_success": "ok",
            "on_fail": {"hint": "h", "retry": True}, "only_human": False,
            "content_version": "cv-" + sid, "basis": "normative", "claims_status": "-", "route": "main",
            "required": True, "eligible": eligible, "rubric_ref": ("R-" + sid) if rubric else "-",
            "scenarios": [{"id": sid, "option_ids": [], "rubric_ref": ("R-" + sid) if rubric else "-"}]}


def checkpoint(sid, target):
    return {"id": sid, "type": "checkpoint", "text": "t", "content_version": "cv-" + sid,
            "options": [{"id": "continue", "label": "l", "target": target, "text": "t"},
                        {"id": "pause", "label": "p", "text": "t"}]}


def course(version, sections, changes=()):
    """sections: [(sid, [(lesson_id, [steps])])]"""
    secs = [{"id": s, "title": "T" + s, "goal": "g",
             "lessons": [{"id": lid, "title": "L" + lid, "competencies": [], "text": "lessons/x.md", "steps": st}
                         for lid, st in lessons]} for s, lessons in sections]
    rubrics = {}
    for s in secs:
        for l in s["lessons"]:
            for st in l["steps"]:
                if st.get("rubric_ref", "-") != "-":
                    rubrics[st["rubric_ref"]] = {"step": st["id"], "status": "accepted", "text": "key"}
    return {"course": {"id": "mentor", "version": version, "language": "ru", "changes": list(changes),
                       "rubrics": rubrics, "sections": secs}}


def change(version, frm, added=(), removed=(), changed=(), important=(), note="Новое."):
    return {"version": version, "from": frm, "added": list(added), "removed": list(removed),
            "changed": list(changed), "important": list(important), "note": note}


BASE_STEPS = [ex("S1.L01.s01"), quiz("S1.L01.s02"), ex("S1.L01.s03"), exercise("S1.L01.s04"),
              exercise("S1.L01.s05", method="user_confirm_form", detail="did it", eligible=False, rubric=False),
              quiz("S1.L01.s06", eligible=False, rubric=False), checkpoint("S1.L01.s07", "S2")]
S2_STEPS = [ex("S2.L01.s01"), ex("S2.L01.s02"), checkpoint("S2.L01.s03", "finish")]


def base_course(version="1.0.0", s1=None, s2=None, changes=()):
    return course(version, [("S1", [("S1.L01", s1 if s1 is not None else copy.deepcopy(BASE_STEPS))]),
                            ("S2", [("S2.L01", s2 if s2 is not None else copy.deepcopy(S2_STEPS))])], changes)


class Env:
    def __init__(self, tc):
        self.dir = Path(tempfile.mkdtemp(prefix="p1-progress-"))
        TMP_ROOTS.append(self.dir)
        tc.addCleanup(shutil.rmtree, self.dir, True)
        self.home = self.dir / "mentor"
        self.course_path = self.dir / "course.json"

    def set_course(self, doc):
        self.course_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def use_real_course(self, path=None):
        shutil.copyfile(path or COURSE_FILE, self.course_path)

    def put(self, data):
        self.home.mkdir(parents=True, exist_ok=True)
        raw = data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False, indent=1) + "\n").encode()
        (self.home / "progress.json").write_bytes(raw)
        return raw

    def raw(self):
        return (self.home / "progress.json").read_bytes()

    def state(self):
        return json.loads(self.raw())

    def run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = PG.main(["--kb-home", str(self.home), "--course", str(self.course_path), *map(str, args)])
        text = out.getvalue()
        return code, (json.loads(text) if code == 0 and text.strip() else None), err.getvalue()

    def ok(self, tc, *args):
        code, out, err = self.run(*args)
        tc.assertEqual(code, 0, f"{args}: {err}")
        return out

    def fails(self, tc, *args, contains=None):
        before = self.raw() if (self.home / "progress.json").exists() else None
        code, _, err = self.run(*args)
        tc.assertNotEqual(code, 0, f"{args} should fail")
        if contains:
            tc.assertIn(contains, err)
        after = self.raw() if (self.home / "progress.json").exists() else None
        tc.assertEqual(before, after, f"{args}: file changed on error")
        return err

    def rev(self):
        return self.state()["revision"]


class Base(unittest.TestCase):
    def setUp(self):
        PG.HOOKS.clear()
        self.addCleanup(PG.HOOKS.clear)

    def fresh(self, doc=None):
        env = Env(self)
        env.set_course(doc or base_course())
        env.ok(self, "migrate")
        return env

    def to_step(self, env, sid):
        """Walk the main path to sid using the API (explains advanced, checks skipped)."""
        for _ in range(50):
            w = env.ok(self, "where")
            if w["step"] == sid:
                return w
            t = w["content"]["type"]
            if t == "explain":
                env.ok(self, "advance", "--revision", w["revision"])
            elif t in ("quiz", "exercise"):
                env.ok(self, "skip", "--revision", w["revision"], "--reason", "test")
            elif t == "checkpoint":
                env.ok(self, "checkpoint", "--revision", w["revision"], "--choice", "continue")
        self.fail(f"did not reach {sid}")


# ---------------------------------------------------------------- real fixtures

def v1_of(state):
    """Rebuild a schema-1 file from legacy entries of migration m1 (values, not ids)."""
    leg = state["legacy"]
    out = dict(leg["_file"][0]["original"])
    quiz_, exe = {}, {}
    for key, entries in leg.items():
        if key == "_file":
            continue
        for e in entries:
            if e["migration_id"] == "m1" and "quiz" in e["original"] and "check" not in e["original"]:
                quiz_[key] = e["original"]["quiz"]
            if e["migration_id"] == "m1" and "exercises" in e["original"]:
                exe[key] = e["original"]["exercises"]
    out["quiz"], out["exercises"] = quiz_, exe
    return out


@unittest.skipUnless(HAVE_FIXTURES, "real progress fixtures live only in the development repo")
class TestRealFixtures(Base):
    def migrated(self, name):
        env = Env(self)
        env.use_real_course(course_020())
        original = env.put((FIXTURES / f"uchenik-{name}-progress.json").read_bytes())
        report = env.ok(self, "migrate", "--json")
        return env, original, report

    def test_t01_nothing_lost_backup_idempotent(self):
        for name in LEARNERS:
            with self.subTest(learner=name):
                env, original, report = self.migrated(name)
                self.assertTrue(report["changed"])
                st = env.state()
                orig = json.loads(original)
                rebuilt = v1_of(st)
                expected = dict(orig)
                expected.setdefault("quiz", {})
                expected.setdefault("exercises", {})
                self.assertEqual(rebuilt, expected)                     # by values, not only ids
                path = env.home / "progress-backups" / Path(st["migrations"][0]["backup"]).name
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(st["migrations"][0]["source_sha256"], hashlib.sha256(original).hexdigest())
                ids_before = set(orig["completed"]) | set(orig.get("quiz", {})) | set(orig.get("exercises", {}))
                ids_after = set(st["completed"]) | set(st["checks"]) | set(st["legacy"])
                self.assertLessEqual(ids_before, ids_after)
                once = env.raw()
                again = env.ok(self, "migrate", "--json")
                self.assertFalse(again["changed"])
                self.assertEqual(env.raw(), once)

    def test_t02_new_secret_steps_notice(self):
        env, _, _ = self.migrated("novichok")
        st = env.state()
        added = [n for n in st["notices"] if n["kind"] == "added"]
        self.assertEqual(len(added), 1)
        for s in ["S1.L14.s09", "S1.L14.s10", "S1.L14.s11", "S1.L14.s12", "S1.L14.s13"]:
            self.assertIn(s, added[0]["steps"])
        self.assertTrue(added[0]["important"])
        for early in ("uchenik-otlichnik-progress.run1.json", "uchenik-otlichnik-progress.run2.json"):
            e = Env(self)
            e.use_real_course(course_020())
            e.put((FIXTURES / early).read_bytes())
            e.ok(self, "migrate")
            self.assertEqual(e.state()["notices"], [], early)

    def test_t03_removed_cursor(self):
        env, original, _ = self.migrated("oshibayushchiysya")
        orig = json.loads(original)
        self.assertEqual(orig["current"], "S1.L26.s05")
        c = PG.Course(course_020())
        last = max(c.pos[s] for s in env.state()["completed"] if s in c)
        self.assertEqual(env.state()["nav"]["cursor"], c.order[last + 1])
        self.assertEqual(env.state()["nav"]["cursor"], "S1.L27.s01")

    def test_t04_legacy_gives_no_x_no_y(self):
        for name in LEARNERS:
            env, _, _ = self.migrated(name)
            s = env.ok(self, "summary", "all")
            self.assertEqual((s["X"], s["Y"]), (0, 0), name)
            for sid, chk in env.state()["checks"].items():
                self.assertNotEqual((chk.get("best_this_version") or {}).get("status"), "confirmed")
                self.assertNotEqual((chk.get("best_this_version") or {}).get("status"), "said_done")

    def test_t14_revealed_legacy_quiz_kept_and_blocked(self):
        env, original, _ = self.migrated("oshibayushchiysya")
        orig = json.loads(original)
        rec = orig["quiz"]["S1.L24.s03"]
        self.assertTrue(rec.get("revealed"))
        st = env.state()
        self.assertEqual(st["legacy"]["S1.L24.s03"][0]["original"], {"quiz": rec})
        self.assertTrue(st["checks"]["S1.L24.s03"]["exposure"]["S1.L24.s03"]["revealed"])
        env.ok(self, "lesson", "S1.L24", "--revision", env.rev())
        self.to_step(env, "S1.L24.s03")
        o = env.ok(self, "open", "S1.L24.s03")
        self.assertFalse(o["scoring"])
        env.fails(self, "record", "--token", o["token"], "--attempt", o["next_attempt"], "--label", "b", "--option", "b",
                  "--rubric", "correct", "--evidence", "own_answer")

    def test_codex_a_paused_at_heterogeneous(self):
        for name in LEARNERS:
            env, original, _ = self.migrated(name)
            orig, st = json.loads(original), env.state()
            self.assertEqual(st["legacy"]["_file"][0]["original"]["paused_at"], orig["paused_at"])
            if name == "sporshchik":
                pz = st["nav"]["paused"]
                self.assertEqual((pz["at"], pz["resume_target"]), ("S2.L01.s02", "S2.L01.s02"))
            else:
                self.assertIsNone(st["nav"]["paused"], name)       # a timestamp is not a pause target
            if orig["current"] in PG.Course(course_020()):
                self.assertEqual(st["nav"]["cursor"], orig["current"])

    def test_codex_b_c_unknown_values_verbatim(self):
        env, original, _ = self.migrated("otlichnik")
        orig, st = json.loads(original), env.state()
        self.assertEqual(st["legacy"]["S4.L05.s03"][0]["original"], {"exercises": "done"})
        self.assertEqual(st["legacy"]["_file"][0]["original"]["notes"], orig["notes"])
        self.assertIsInstance(orig["notes"], list)
        env, original, _ = self.migrated("toropyga")
        self.assertIsInstance(json.loads(original)["notes"], dict)
        self.assertEqual(env.state()["legacy"]["_file"][0]["original"]["notes"], json.loads(original)["notes"])
        env, original, _ = self.migrated("sporshchik")
        orig, st = json.loads(original), env.state()
        withdrawn = [k for k, v in orig["quiz"].items() if v.get("status") == "withdrawn"]
        self.assertEqual(len(withdrawn), 1)
        for k in withdrawn:
            self.assertEqual(st["legacy"][k][0]["original"], {"quiz": orig["quiz"][k]})
        c = PG.Course(course_020())
        wrong_c = [k for k, v in orig["quiz"].items() if v.get("option") == "c" and "c" in (v.get("wrong") or [])]
        self.assertTrue(wrong_c)
        for k in wrong_c:
            self.assertEqual(st["legacy"][k][0]["original"]["quiz"], orig["quiz"][k])
            if k in st["checks"]:
                self.assertEqual(st["checks"][k]["history"][0]["option_ids"], ["c"])   # never corrected by the key

    def test_codex_f_rollback_keeps_new_work(self):
        env, original, _ = self.migrated("novichok")
        w = env.ok(self, "where")
        env.ok(self, "advance", "--revision", w["revision"]) if w["content"]["type"] == "explain" else \
            env.ok(self, "skip", "--revision", w["revision"], "--reason", "x")
        live = env.raw()
        out = env.ok(self, "rollback", "--to", "m1")
        self.assertEqual(env.raw(), original)
        saved = env.home / "progress-backups" / Path(out["current_state_saved_to"]).name
        self.assertEqual(saved.read_bytes(), live)


# ---------------------------------------------------------------- synthetic

class TestRecord(Base):
    def test_t05_reveal_confirm_rubric_said_done(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        self.assertTrue(o["scoring"])
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b",
                  "--evidence", "own_answer", contains="--rubric")             # confirmed without rubric
        for n, opt in enumerate(["a", "c", "a"], 1):
            r = env.ok(self, "record", "--token", o["token"], "--attempt", n, "--label", opt, "--option", opt, "--rubric", "incorrect")
        self.assertTrue(r["revealed"])
        self.assertTrue(r["closed"])
        self.assertEqual(r["status"], "shown")
        # come back to the same scenario: no confirmed
        env.ok(self, "lesson", "S1.L01", "--revision", env.rev())
        self.to_step(env, "S1.L01.s02")
        o2 = env.ok(self, "open", "S1.L01.s02")
        self.assertFalse(o2["scoring"])
        env.fails(self, "record", "--token", o2["token"], "--attempt", o2["next_attempt"], "--label", "b", "--option", "b",
                  "--rubric", "correct", "--evidence", "own_answer")
        # [Сделал]
        env2 = self.fresh()
        self.to_step(env2, "S1.L01.s05")
        o = env2.ok(self, "open", "S1.L01.s05")
        r = env2.ok(self, "record", "--token", o["token"], "--said-done")
        self.assertEqual(r["status"], "said_done")
        chk = env2.state()["checks"]["S1.L01.s05"]
        self.assertEqual(chk["history"][-1]["origin"], "user_form")
        self.assertEqual(chk["best_this_version"]["status"], "said_done")

    def test_confirmed_quiz_counts(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "correct",
                  "--evidence", "own_answer", contains="answer key")
        r = env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b", "--rubric", "correct",
                   "--evidence", "own_answer")
        self.assertEqual(r["status"], "confirmed")
        self.assertEqual(r["current"], "S1.L01.s03")
        s = env.ok(self, "summary", "S1")
        self.assertEqual((s["X"], s["N"]), (1, 2))

    def test_t10_repeat_stale_foreign_unknown(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "incorrect")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "incorrect")
        env.fails(self, "record", "--token", "deadbeef", "--attempt", 2, "--label", "a", "--option", "a", "--rubric", "incorrect")
        env.fails(self, "record", "--token", o["token"], "--attempt", 2, "--label", "z", "--option", "z", "--rubric", "incorrect")
        env.fails(self, "open", "S1.L01.s04", contains="not the current step")
        r = env.ok(self, "record", "--token", o["token"], "--attempt", 2, "--label", "b", "--option", "b", "--rubric", "correct",
                   "--evidence", "own_answer")
        env.fails(self, "record", "--token", o["token"], "--attempt", 3, "--label", "b", "--option", "b", "--rubric", "correct",
                  "--evidence", "own_answer")                                 # closed: stale token

    def test_t11_no_scenario_parameter(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b", "--rubric", "correct",
                  "--evidence", "own_answer", "--scenario", "S1.L01.s02-new")

    def test_t24_not_scoring_check(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s06")
        o = env.ok(self, "open", "S1.L01.s06")
        self.assertFalse(o["scoring"])
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b", "--rubric", "correct",
                  "--evidence", "own_answer", contains="not scored")
        r = env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b")
        self.assertEqual((r["status"], r["scored"], r["revealed"], r["closed"]), ("shown", False, False, True))
        chk = env.state()["checks"]["S1.L01.s06"]
        self.assertEqual(chk["exposure"], {})
        self.assertEqual(len(chk["history"]), 1)
        self.assertNotEqual(chk["best_this_version"]["status"], "confirmed")

    def test_t25_message_id_single_use(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "incorrect",
               "--message-id", "m-1")
        env.fails(self, "record", "--token", o["token"], "--attempt", 2, "--label", "b", "--option", "b", "--rubric", "correct",
                  "--evidence", "own_answer", "--message-id", "m-1", contains="already recorded")
        env.ok(self, "record", "--token", o["token"], "--attempt", 2, "--label", "b", "--option", "b", "--rubric", "correct",
               "--evidence", "own_answer", "--message-id", "m-2")
        # another step, a new expectation, after a "restart" (state only from the file)
        self.to_step(env, "S1.L01.s04")
        o = env.ok(self, "open", "S1.L01.s04")
        env.fails(self, "skip", "--token", o["token"], "--reason", "x", "--message-id", "m-2", contains="already recorded")
        self.assertIn("m-1", env.state()["consumed_messages"])

    def test_t27_repeated_revision_and_option_rules(self):
        env = self.fresh()
        r = env.rev()
        env.ok(self, "advance", "--revision", r)
        env.fails(self, "advance", "--revision", r)
        o = env.ok(self, "open", "S1.L01.s02")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--rubric", "incorrect", contains="--option")
        r = env.rev()
        env.ok(self, "skip", "--revision", r, "--reason", "x")
        env.fails(self, "skip", "--revision", r, "--reason", "x")
        env.ok(self, "advance", "--revision", env.rev())
        o = env.ok(self, "open", "S1.L01.s04")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "correct",
                  "--evidence", "explanation", contains="not one of []")
        r = env.rev()
        env.ok(self, "skip", "--token", o["token"], "--reason", "x")
        self.to_step(env, "S1.L01.s07")
        r = env.rev()
        env.ok(self, "checkpoint", "--revision", r, "--choice", "pause")
        env.fails(self, "checkpoint", "--revision", r, "--choice", "pause")
        r = env.rev()
        env.ok(self, "resume", "--revision", r)
        env.fails(self, "resume", "--revision", r)
        # notice with the same revision twice
        e = self.notice_env()
        n = e.state()["notices"][0]["id"]
        r = e.rev()
        e.ok(self, "notice", n, "--later", "--revision", r)
        e.fails(self, "notice", n, "--later", "--revision", r)

    def notice_env(self):
        e = Env(self)
        e.set_course(base_course("1.0.0"))
        e.ok(self, "migrate")
        self.to_step(e, "S2.L01.s01")
        s1 = copy.deepcopy(BASE_STEPS)
        s1.insert(1, ex("S1.L01.s08"))
        e.set_course(base_course("1.1.0", s1=s1, changes=[change("1.1.0", "1.0.0", added=["S1.L01.s08"],
                                                                 important=["S1.L01.s08"])]))
        e.ok(self, "migrate")
        return e

    def test_artifact_ref_structured(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s04")
        o = env.ok(self, "open", "S1.L01.s04")
        self.assertTrue(o["scoring"])
        tok = o["token"]
        detail = "notes/plan.md contains a plan"
        env.fails(self, "record", "--token", tok, "--artifact-ref", "found it")
        env.fails(self, "record", "--token", tok, "--artifact-ref",
                  json.dumps({"method": "config_key", "detail": detail, "observed": "x"}), contains="method")
        env.fails(self, "record", "--token", tok, "--artifact-ref",
                  json.dumps({"method": "workspace_file", "detail": "other", "observed": "x"}), contains="detail")
        env.fails(self, "record", "--token", tok, "--artifact-ref",
                  json.dumps({"method": "workspace_file", "detail": detail, "observed": " "}), contains="observed")
        env.fails(self, "record", "--token", tok, "--attempt", 1, "--rubric", "correct", "--evidence",
                  "verified_artifact", contains="--artifact-ref")
        art = {"method": "workspace_file", "detail": detail, "observed": "notes/plan.md sha256:0123abcd"}
        r = env.ok(self, "record", "--token", tok, "--artifact-ref", json.dumps(art))
        self.assertEqual(r["status"], "confirmed")
        h = env.state()["checks"]["S1.L01.s04"]["history"][-1]
        self.assertEqual(h["artifact"], art)
        self.assertEqual((h["rubric_verdict"], h["evidence"]), ("correct", "verified_artifact"))
        # a [Сделал]-only exercise cannot take an artifact
        self.to_step(env, "S1.L01.s05")
        o = env.ok(self, "open", "S1.L01.s05")
        env.fails(self, "record", "--token", o["token"], "--artifact-ref",
                  json.dumps({"method": "user_confirm_form", "detail": "did it", "observed": "yes"}))

    # --artifact-stdin: the same artifact as plain lines on stdin, no shell or JSON quoting (Codex 40d78214 P3:
    # 22 of 28 refused records broke on inline '{...}' quoting, 6 on a double-escaped '). Same checks.
    DETAIL_Q = "No tool call: the user's latest message in Mentor's chat; ends with (yes: \"…\") and 'Bot: Bot Maker'"

    def stdin_env(self):
        s1 = copy.deepcopy(BASE_STEPS)
        s1[3] = exercise("S1.L01.s04", method="agent_tool", detail=self.DETAIL_Q)
        env = self.fresh(base_course(s1=s1))
        self.to_step(env, "S1.L01.s04")
        return env, env.ok(self, "open", "S1.L01.s04")["token"]

    def run_stdin(self, env, text, *args, ok=True, contains=None):
        old = sys.stdin
        sys.stdin = io.StringIO(text)
        try:
            return env.ok(self, *args) if ok else env.fails(self, *args, contains=contains)
        finally:
            sys.stdin = old

    def test_artifact_stdin_apostrophes_and_quotes(self):
        env, tok = self.stdin_env()
        good = f"method: agent_tool\ndetail: {self.DETAIL_Q}\nobserved: latest user message: Привет, it's me\n"
        rec = ("record", "--token", tok, "--artifact-stdin")
        # a detail that differs (retyped, or the old ' escape written literally) is refused, nothing written
        self.run_stdin(env, good.replace("user's", "users"), *rec, ok=False, contains="detail")
        self.run_stdin(env, good.replace("user's", "user\\u0027s"), *rec, ok=False, contains="detail")
        self.run_stdin(env, good.replace("agent_tool", "workspace_file"), *rec, ok=False, contains="method")
        self.run_stdin(env, good.replace("observed: latest user message: Привет, it's me", "observed:  "), *rec,
                       ok=False, contains="observed")
        # malformed input: missing key, repeated key, foreign line, both flags at once
        self.run_stdin(env, good.split("observed")[0], *rec, ok=False, contains="missing")
        self.run_stdin(env, good + "detail: x\n", *rec, ok=False, contains="twice")
        self.run_stdin(env, "note: hi\n" + good, *rec, ok=False, contains="each line")
        self.run_stdin(env, '{"method": "agent_tool"}', *rec, ok=False, contains="each line")
        self.run_stdin(env, good, *rec, "--artifact-ref", "{}", ok=False, contains="not both")
        self.run_stdin(env, good, *rec, "--evidence", "own_answer", ok=False, contains="verified_artifact")
        # the right lines (apostrophes, double quotes, Cyrillic as they are; indented or CRLF lines too)
        r = self.run_stdin(env, "\n  " + good.replace("\n", "\r\n"), *rec)
        self.assertEqual(r["status"], "confirmed")
        h = env.state()["checks"]["S1.L01.s04"]["history"][-1]
        self.assertEqual(h["artifact"], {"method": "agent_tool", "detail": self.DETAIL_Q,
                                         "observed": "latest user message: Привет, it's me"})
        self.assertEqual((h["rubric_verdict"], h["evidence"]), ("correct", "verified_artifact"))
        # the token is consumed: the same lines again are refused like any repeated record
        self.run_stdin(env, good, *rec, ok=False, contains="token")

    def test_artifact_stdin_quiz_refused(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        tok = env.ok(self, "open", "S1.L01.s02")["token"]
        self.run_stdin(env, "method: a\ndetail: b\nobserved: c\n", "record", "--token", tok, "--attempt", 1,
                       "--label", "a", "--option", "a", "--rubric", "incorrect", "--artifact-stdin",
                       ok=False, contains="quiz")

    def test_artifact_stdin_real_shell_heredoc(self):
        """The exact form MENTOR-RUNTIME tells Mentor to write, through a real bash: a quoted heredoc keeps
        every apostrophe and double quote of the detail as it is."""
        import subprocess
        env, tok = self.stdin_env()
        script = (f"python3 -B {shlex.quote(str(RELEASE_DIR / "course" / "progress.py"))} --kb-home {shlex.quote(str(env.home))} "
                  f"--course {shlex.quote(str(env.course_path))} record --token {tok} --artifact-stdin <<'REF'\n"
                  f"method: agent_tool\ndetail: {self.DETAIL_Q}\nobserved: tool none; message «Привет» it's\nREF\n")
        r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["status"], "confirmed")
        self.assertEqual(env.state()["checks"]["S1.L01.s04"]["history"][-1]["artifact"]["detail"], self.DETAIL_Q)


class TestSummary(Base):
    def test_t07_t12_eligibility_and_n_zero(self):
        s1 = [quiz("S1.L01.s01"),                                                  # normative + rubric
              quiz("S1.L01.s02", eligible=False, rubric=False, basis="unmapped"),
              quiz("S1.L01.s03", eligible=False, basis="claims", claims_status="unverified"),
              quiz("S1.L01.s04", eligible=False, basis="claims", claims_status="disputed"),
              quiz("S1.L01.s05", route="optional_practice"),
              checkpoint("S1.L01.s06", "S2")]
        env = self.fresh(base_course(s1=s1))
        s = env.ok(self, "summary", "S1")
        self.assertEqual(s["N"], 1)
        self.assertEqual(s["disputed"], ["S1.L01.s04"])
        self.assertTrue(s["show_confirmed_line"])
        s1b = [quiz("S1.L01.s01", eligible=False, rubric=False, basis="unmapped"), checkpoint("S1.L01.s02", "S2")]
        env2 = self.fresh(base_course(s1=s1b))
        s = env2.ok(self, "summary", "S1")
        self.assertEqual(s["N"], 0)
        self.assertFalse(s["show_confirmed_line"])
        self.assertFalse(any(l.startswith("confirmed") for l in s["lines"]))

    def test_t07_real_course_only_normative_rubric_check_counts(self):
        env = Env(self)
        env.use_real_course()
        env.ok(self, "migrate")
        s = env.ok(self, "summary", "all")
        self.assertEqual(s["N"], 1)
        c = PG.Course(COURSE_FILE)
        elig = [sid for sid in c.order if c.steps[sid].get("eligible")]
        self.assertEqual(elig, ["S1.L14.s13"])
        self.assertEqual(c.steps["S1.L14.s13"]["basis"], "normative")
        self.assertEqual(env.ok(self, "summary", "S2")["N"], 0)


class TestMigrate(Base):
    def test_t06_content_change_rechecks(self):
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b", "--rubric", "correct",
               "--evidence", "own_answer")
        s1 = copy.deepcopy(BASE_STEPS)
        s1[1]["content_version"] = "cv-new"
        env.set_course(base_course("1.1.0", s1=s1, changes=[change("1.1.0", "1.0.0", changed=["S1.L01.s02"])]))
        rep = env.ok(self, "migrate", "--json")
        self.assertIn("S1.L01.s02", rep["rechecks"])
        chk = env.state()["checks"]["S1.L01.s02"]
        self.assertEqual(chk["lifecycle"], "needs_recheck")
        self.assertIsNone(chk["best_this_version"])
        self.assertEqual(len(chk["history"]), 1)
        self.assertIn("S1.L01.s02", env.state()["repeat"])
        self.assertEqual(env.ok(self, "summary", "S1")["X"], 0)

    def test_t13_observed_or_scope_changes_content_version(self):
        claims = {"C1": {"claim_id": "C1", "quote_en": "q", "translation_ru": "т", "our_inference": "-",
                         "scope": "s", "risk": "r", "status": "verified", "doc_basis": "a.md:1 sha256:1",
                         "observed": "-"}}
        step = {"id": "S1.L01.s01", "type": "quiz", "question": "q",
                "options": [{"id": o, "text": o, "correct": o == "a", "reaction": "r"} for o in "abc"]}
        cmap = {"S1.L01.s01": {"basis": "claims", "claims": ["C1"]}}

        def cv(cl):
            return CM.compute_step(step, {"id": "S1.L01"}, Path("."), cl, cmap, {}, set())["content_version"]

        base = cv(claims)
        for field, value in (("observed", "run-1 sha256:9"), ("scope", "other scope"), ("doc_basis", "a.md:2 sha256:1")):
            c2 = copy.deepcopy(claims)
            c2["C1"][field] = value
            self.assertNotEqual(cv(c2), base, field)
        c3 = copy.deepcopy(claims)
        c3["C1"]["status"] = "disputed"
        gen = CM.compute_step(step, {"id": "S1.L01"}, Path("."), c3, cmap, {}, set())
        self.assertEqual((gen["claims_status"], gen["eligible"]), ("disputed", False))
        unm = CM.compute_step(step, {"id": "S1.L01"}, Path("."), claims, {}, {}, set())
        self.assertEqual((unm["basis"], unm["eligible"]), ("unmapped", False))

    def test_t15_remove_return_remove_appends(self):
        def doc(version, with_x, changes):
            s1 = copy.deepcopy(BASE_STEPS)
            if not with_x:
                s1 = [s for s in s1 if s["id"] != "S1.L01.s02"]
            return base_course(version, s1=s1, changes=changes)
        ch = [change("1.1.0", "1.0.0", removed=["S1.L01.s02"]), change("1.2.0", "1.1.0", added=["S1.L01.s02"]),
              change("1.3.0", "1.2.0", removed=["S1.L01.s02"])]
        env = self.fresh(doc("1.0.0", True, []))
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "incorrect")
        env.set_course(doc("1.1.0", False, ch[:1]))
        env.ok(self, "migrate")
        first = copy.deepcopy(env.state()["legacy"]["S1.L01.s02"])
        self.assertEqual(len(first), 1)
        env.set_course(doc("1.2.0", True, ch[:2]))
        env.ok(self, "migrate")
        env.ok(self, "lesson", "S1.L01", "--revision", env.rev())
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "c", "--option", "c", "--rubric", "incorrect")
        env.set_course(doc("1.3.0", False, ch))
        env.ok(self, "migrate")
        leg = env.state()["legacy"]["S1.L01.s02"]
        self.assertEqual(len(leg), 2)
        self.assertEqual(leg[0], first[0])
        self.assertNotEqual(leg[0]["migration_id"], leg[1]["migration_id"])

    def test_t16_codex_e_detour_interrupted(self):
        e = Env(self)
        e.set_course(base_course("1.0.0"))
        e.ok(self, "migrate")
        self.to_step(e, "S2.L01.s01")
        s1 = copy.deepcopy(BASE_STEPS)
        s1.insert(0, ex("S1.L01.s08"))
        s1.insert(1, quiz("S1.L01.s09"))
        e.set_course(base_course("1.1.0", s1=s1, changes=[change("1.1.0", "1.0.0", added=["S1.L01.s08", "S1.L01.s09"],
                                                                 important=["S1.L01.s09"])]))
        e.ok(self, "migrate")
        nid = e.state()["notices"][0]["id"]
        for _ in range(2):                                   # where/migrate never spend later_count
            e.ok(self, "where")
            e.ok(self, "migrate")
        self.assertEqual(e.state()["notices"][0]["later_count"], 0)
        e.ok(self, "notice", nid, "--now", "--revision", e.rev())
        w = e.ok(self, "where")
        self.assertEqual((w["step"], w["mode"]), ("S1.L01.s08", "notice"))
        e.ok(self, "advance", "--revision", w["revision"])
        o1 = e.ok(self, "open", "S1.L01.s09")
        # the process stops here; a new session reads only the file
        w = e.ok(self, "where")
        self.assertEqual(w["step"], "S1.L01.s09")
        o2 = e.ok(self, "open", "S1.L01.s09")
        self.assertEqual((o1["token"], o1["next_attempt"]), (o2["token"], o2["next_attempt"]))
        r = e.ok(self, "record", "--token", o2["token"], "--attempt", 1, "--label", "b", "--option", "b", "--rubric", "correct",
                 "--evidence", "own_answer")
        self.assertEqual(r["current"], "S2.L01.s01")
        self.assertEqual(e.state()["notices"][0]["state"], "done")
        self.assertEqual(e.state()["nav"]["stack"], [])

    def test_notice_later_three_times_goes_to_repeat(self):
        e = TestRecord.notice_env(self)
        nid = e.state()["notices"][0]["id"]
        for _ in range(3):
            e.ok(self, "notice", nid, "--later", "--revision", e.rev())
        n = e.state()["notices"][0]
        self.assertEqual((n["state"], n["later_count"]), ("in_repeat", 3))
        self.assertIn("S1.L01.s08", e.state()["repeat"])

    def test_t17_paused_checkpoint_moved_and_removed(self):
        """R4 (Codex 99e83e76 #4): a stored resume_target that still exists is kept."""
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S1.L01.s07")
        env.ok(self, "checkpoint", "--revision", env.rev(), "--choice", "pause")
        self.assertEqual(env.state()["nav"]["paused"]["resume_target"], "S2.L01.s01")
        # a new step Y is inserted before the target X: X stays the target, Y comes as a notice
        s2 = [ex("S2.L01.s00")] + copy.deepcopy(S2_STEPS)
        ch1 = change("1.1.0", "1.0.0", added=["S2.L01.s00"], important=["S2.L01.s00"])
        env.set_course(base_course("1.1.0", s2=s2, changes=[ch1]))
        env.ok(self, "migrate")
        self.assertEqual(env.state()["nav"]["paused"]["resume_target"], "S2.L01.s01")
        self.assertEqual(env.state()["nav"]["cursor"], "S2.L01.s01")
        self.assertIn("S2.L01.s00", [s for n in env.state()["notices"] for s in n["steps"]])
        # removed: the checkpoint and the target X disappear -> nearest following existing step
        s1 = [s for s in copy.deepcopy(BASE_STEPS) if s["id"] != "S1.L01.s07"]
        s2b = [s for s in s2 if s["id"] != "S2.L01.s01"]
        env.set_course(base_course("1.2.0", s1=s1, s2=s2b, changes=[
            ch1, change("1.2.0", "1.1.0", removed=["S1.L01.s07", "S2.L01.s01"])]))
        env.ok(self, "migrate")
        self.assertEqual(env.state()["nav"]["paused"]["resume_target"], "S2.L01.s02")
        self.assertIn("S1.L01.s07", env.state()["legacy"])
        env.ok(self, "resume", "--revision", env.rev())
        self.assertEqual(env.ok(self, "where")["step"], "S2.L01.s02")

    def test_r8_long_pause_nearest_surviving_successor(self):
        """R8 (Codex 39a06593 #1): no cutoff on paused.following; the nearest surviving successor wins."""
        long_s2 = [ex(f"S2.L01.s{i:02d}") for i in range(1, 33)]
        env = self.fresh(base_course("1.0.0", s2=long_s2))
        self.to_step(env, "S1.L01.s07")
        env.ok(self, "checkpoint", "--revision", env.rev(), "--choice", "pause")
        self.assertEqual(env.state()["nav"]["paused"]["resume_target"], "S2.L01.s01")
        removed = [f"S2.L01.s{i:02d}" for i in range(1, 32)]
        env.set_course(base_course("1.1.0", s2=[ex("S2.L01.s00"), ex("S2.L01.s32")], changes=[
            change("1.1.0", "1.0.0", added=["S2.L01.s00"], removed=removed)]))
        env.ok(self, "migrate")
        self.assertEqual(env.state()["nav"]["paused"]["resume_target"], "S2.L01.s32")

    def test_t18_changed_explain_correction(self):
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S2.L01.s01")
        s1 = copy.deepcopy(BASE_STEPS)
        s1[0] = ex("S1.L01.s01", text="fixed")
        env.set_course(base_course("1.1.0", s1=s1, changes=[change("1.1.0", "1.0.0", changed=["S1.L01.s01"],
                                                                 important=["S1.L01.s01"])]))
        env.ok(self, "migrate")
        n = env.state()["notices"]
        self.assertEqual([(x["kind"], x["steps"], x["important"]) for x in n], [("correction", ["S1.L01.s01"], True)])

    def test_t22_finished_course_gets_notices(self):
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S2.L01.s03")
        env.ok(self, "checkpoint", "--revision", env.rev(), "--choice", "continue")
        self.assertEqual(env.ok(self, "where")["step"], "finish")
        s2 = copy.deepcopy(S2_STEPS)
        s2.insert(2, ex("S2.L01.s09"))
        env.set_course(base_course("1.1.0", s2=s2, changes=[change("1.1.0", "1.0.0", added=["S2.L01.s09"],
                                                                 important=["S2.L01.s09"])]))
        env.ok(self, "migrate")
        n = env.state()["notices"]
        self.assertEqual([(x["kind"], x["steps"], x["important"]) for x in n], [("added", ["S2.L01.s09"], True)])

    def test_no_chain_shows_all_missed_steps(self):
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S2.L01.s01")
        s1 = copy.deepcopy(BASE_STEPS)
        s1.insert(1, ex("S1.L01.s08"))
        env.set_course(base_course("2.0.0", s1=s1))           # no changes journal at all
        env.ok(self, "migrate")
        n = env.state()["notices"]
        self.assertEqual(len(n), 1)
        self.assertIn("S1.L01.s08", n[0]["steps"])
        self.assertTrue(n[0]["important"])

    def test_t23_corrupt_newer_downgrade(self):
        env = Env(self)
        env.set_course(base_course("1.0.0"))
        env.put(b"{not json")
        env.fails(self, "migrate", contains="not valid JSON")
        env.put({"schema": 3, "course_version": "1.0.0"})
        env.fails(self, "migrate", contains="schema")
        env.put({"course_version": "2.0.0", "current": "S1.L01.s01", "completed": []})
        env.fails(self, "migrate", contains="downgrade")
        self.assertFalse((env.home / "progress-backups").exists())


class TestFilesAndLock(Base):
    def v1_env(self):
        env = Env(self)
        env.set_course(base_course("1.1.0", changes=[change("1.1.0", "1.0.0")]))
        raw = env.put({"course_version": "1.0.0", "current": "S1.L01.s03", "completed": ["S1.L01.s01", "S1.L01.s02"],
                       "quiz": {"S1.L01.s02": {"option": "b", "attempts": 1}}, "exercises": {}, "skip_reasons": {},
                       "paused_at": None, "updated": "2026-01-01T00:00:00Z"})
        return env, raw

    def test_t09_rollback_byte_for_byte(self):
        env, raw = self.v1_env()
        env.ok(self, "migrate")
        env.ok(self, "advance", "--revision", env.rev())
        live = env.raw()
        out = env.ok(self, "rollback", "--to", "m1")
        self.assertEqual(env.raw(), raw)
        self.assertEqual((env.home / "progress-backups" / Path(out["current_state_saved_to"]).name).read_bytes(), live)

    def test_t19_stale_backup_not_reused(self):
        env, raw = self.v1_env()
        digest = hashlib.sha256(raw).hexdigest()
        bdir = env.home / "progress-backups"
        bdir.mkdir(parents=True)
        squatter = bdir / f"1.0.0-{digest[:8]}.json"
        squatter.write_bytes(b'{"older": true}\n')
        (bdir / "1.0.0-00000000.json").write_bytes(b'{"other": true}\n')
        rep = env.ok(self, "migrate", "--json")
        self.assertEqual(Path(rep["backup"]).name, f"1.0.0-{digest}.json")
        self.assertEqual((bdir / f"1.0.0-{digest}.json").read_bytes(), raw)
        self.assertEqual(squatter.read_bytes(), b'{"older": true}\n')

    def test_t20_crash_between_backup_and_write(self):
        env, raw = self.v1_env()

        def boom():
            raise PG.ContractError("simulated crash after backup")
        PG.HOOKS["after_backup"] = boom
        env.fails(self, "migrate", contains="simulated crash")
        self.assertEqual(env.raw(), raw)
        self.assertEqual(len(list((env.home / "progress-backups").iterdir())), 1)
        self.assertFalse((env.home / ".progress.lock").exists())
        PG.HOOKS.clear()
        rep = env.ok(self, "migrate", "--json")
        self.assertTrue(rep["changed"])
        self.assertEqual(len(list((env.home / "progress-backups").iterdir())), 1)   # the copy is reused

    def test_t21_two_writers(self):
        env = self.fresh()
        lock = env.home / ".progress.lock"
        lock.write_text(json.dumps({"owner_token": "other", "pid": os.getpid(), "at": "2020-01-01T00:00:00Z"}))
        env.fails(self, "advance", "--revision", env.rev(), contains="lock")
        lock.unlink()
        rev = env.rev()

        def other_writer():
            st = env.state()
            st["revision"] += 1
            env.put(st)
        PG.HOOKS["before_commit"] = other_writer
        code, _, err = env.run("advance", "--revision", rev)
        self.assertNotEqual(code, 0)
        self.assertIn("changed since it was read", err)
        self.assertEqual(env.state()["nav"]["cursor"], "S1.L01.s01")

    def test_t26_old_lock_not_removed_takeover_not_deleted(self):
        env = self.fresh()
        lock = env.home / ".progress.lock"
        stale = json.dumps({"owner_token": "alive", "pid": os.getpid(), "process_start": 0, "at": "2000-01-01T00:00:00Z"})
        lock.write_text(stale)
        os.utime(lock, (0, 0))
        env.fails(self, "advance", "--revision", env.rev(), contains="lock")
        env.fails(self, "migrate", contains="lock")
        self.assertEqual(lock.read_text(), stale)
        code, _, _ = env.run("unlock", "--stale")
        self.assertNotEqual(code, 0)                                   # no unlock command exists
        lock.unlink()
        takeover = json.dumps({"owner_token": "newcomer", "pid": 1, "process_start": 0, "at": "x"})

        def steal():
            lock.write_text(takeover)
        PG.HOOKS["before_commit"] = steal
        before = env.raw()
        code, _, err = env.run("advance", "--revision", env.rev())
        self.assertNotEqual(code, 0)
        self.assertIn("lock is no longer ours", err)
        self.assertEqual(env.raw(), before)
        self.assertEqual(lock.read_text(), takeover)                  # not deleted by the old writer


class TestBuild(unittest.TestCase):
    def test_t08_journal_must_match(self):
        # the 0.2.0 course is only the shape here (no claims, no rubrics are passed); the working-tree course
        # moved on and names a rubric in a situation (S1.L14.s13.b), which an empty rubric table cannot resolve
        doc = json.loads(course_020().read_text(encoding="utf-8"))
        cur = doc["course"]
        claims = {}
        cmap = {}
        prev = copy.deepcopy(cur)
        for s in prev["sections"]:
            for l in s["lessons"]:
                for st in l["steps"]:
                    for k in CM.GENERATED:
                        st.pop(k, None)
        # previous version: one step fewer (added now), one extra step (removed now), one explain edited
        les = prev["sections"][0]["lessons"][0]
        added = les["steps"].pop(1)["id"]
        les["steps"].append({"id": "S1.L01.s99", "type": "explain", "text": "x", "example": "y"})
        edited = les["steps"][0]
        edited["text"] = edited["text"] + " old"
        prev["version"] = "9.0.0"
        cur = copy.deepcopy(cur)
        for s in cur["sections"]:
            for l in s["lessons"]:
                for st in l["steps"]:
                    for k in CM.GENERATED:
                        st.pop(k, None)
        CM.annotate(cur, RELEASE_DIR / "course", claims, cmap, {})
        cur["version"] = "9.1.0"
        good = {"version": "9.1.0", "from": "9.0.0", "added": [added], "removed": ["S1.L01.s99"],
                "changed": [edited["id"]], "important": [added], "note": "Новое."}
        cur["changes"] = [good]
        CM.validate_changes(cur, prev, RELEASE_DIR / "course", claims, cmap, {})
        for bad in ({"added": []}, {"removed": []}, {"changed": []}, {"important": ["S1.L02.s01"]},
                    {"added": [added, "S1.L02.s01"]}, {"from": "8.0.0"}):
            c2 = copy.deepcopy(cur)
            c2["changes"] = [dict(good, **bad)]
            with self.subTest(bad=bad), self.assertRaises(CM.BuildError):
                CM.validate_changes(c2, prev, RELEASE_DIR / "course", claims, cmap, {})

    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    def test_t08_real_course_is_built_and_journal_checked(self):
        # course-merge --check rebuilds against the previous release read from git; the public release clone has
        # no release history, so the check can only run in the development repository (there it always runs)
        import subprocess
        if subprocess.run(["git", "-C", str(RELEASE_DIR), "cat-file", "-e", "a06537d^{commit}"],
                          capture_output=True).returncode != 0:
            self.skipTest("historical release commits are not in this repository (public release clone)")
        with contextlib.redirect_stdout(io.StringIO()):
            r = CM.main(["--check"])
        self.assertEqual(r, 0)

    def test_real_course_fields(self):
        c = PG.Course(course_020())
        self.assertTrue(all(c.steps[s].get("content_version") for s in c.order))
        entry = next(e for e in c.changes if e["version"] == c.version)
        for s in ["S1.L14.s09", "S1.L14.s10", "S1.L14.s11", "S1.L14.s12", "S1.L14.s13"]:
            self.assertIn(s, entry["important"])
        rub = c.rubrics[c.steps["S1.L14.s13"]["rubric_ref"]]
        self.assertEqual(rub["status"], "accepted")


class TestCodexRegressions(Base):
    """Codex review of 7624096 (99e83e76): each test failed on 7624096 before its fix."""

    def test_r1_exposure_survives_remove_and_return(self):
        def doc(version, with_q, changes):
            s1 = copy.deepcopy(BASE_STEPS)
            if not with_q:
                s1 = [s for s in s1 if s["id"] != "S1.L01.s02"]
            return base_course(version, s1=s1, changes=changes)
        ch = [change("1.1.0", "1.0.0", removed=["S1.L01.s02"]), change("1.2.0", "1.1.0", added=["S1.L01.s02"])]
        env = self.fresh(doc("1.0.0", True, []))
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        for n, opt in enumerate("aca", 1):
            r = env.ok(self, "record", "--token", o["token"], "--attempt", n, "--label", opt, "--option", opt, "--rubric", "incorrect")
        self.assertTrue(r["revealed"])
        env.set_course(doc("1.1.0", False, ch[:1]))
        env.ok(self, "migrate")
        env.set_course(doc("1.2.0", True, ch))                    # same step, same content, same scenario
        env.ok(self, "migrate")
        env.ok(self, "lesson", "S1.L01", "--revision", env.rev())
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        self.assertFalse(o["scoring"], "a revealed answer must not be scored again after remove -> return")
        env.fails(self, "record", "--token", o["token"], "--attempt", o["next_attempt"], "--label", "b", "--option", "b",
                  "--rubric", "correct", "--evidence", "own_answer")

    def test_r2_message_id_single_use_for_life(self):
        env = self.fresh()
        self.to_step(env, "S1.L01.s02")
        o = env.ok(self, "open", "S1.L01.s02")
        env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "a", "--option", "a", "--rubric", "incorrect",
               "--message-id", "M")
        st = env.state()
        for i in range(600):
            PG.consume_message(st, f"other-{i}")
        env.put(st)
        env.fails(self, "record", "--token", o["token"], "--attempt", 2, "--label", "b", "--option", "b", "--rubric", "correct",
                  "--evidence", "own_answer", "--message-id", "M", contains="already recorded")

    def test_r3_detour_keeps_main_pause(self):
        env = self.fresh(base_course("1.0.0"))
        self.to_step(env, "S1.L01.s07")
        env.ok(self, "checkpoint", "--revision", env.rev(), "--choice", "pause")
        paused = env.state()["nav"]["paused"]
        s1 = copy.deepcopy(BASE_STEPS)
        s1.insert(1, ex("S1.L01.s08"))
        env.set_course(base_course("1.1.0", s1=s1, changes=[change("1.1.0", "1.0.0", added=["S1.L01.s08"],
                                                                 important=["S1.L01.s08"])]))
        env.ok(self, "migrate")
        nid = env.state()["notices"][0]["id"]
        env.ok(self, "notice", nid, "--now", "--revision", env.rev())
        w = env.ok(self, "where")
        self.assertEqual(w["step"], "S1.L01.s08")
        env.ok(self, "advance", "--revision", w["revision"])
        self.assertEqual(env.state()["nav"]["paused"], paused)
        env.ok(self, "resume", "--revision", env.rev())
        self.assertEqual(env.ok(self, "where")["step"], "S2.L01.s01")

    def test_r5_previous_without_content_version_uses_history(self):
        tmp = Path(tempfile.mkdtemp(prefix="p1-r5-"))
        TMP_ROOTS.append(tmp)
        self.addCleanup(shutil.rmtree, tmp, True)
        olddir, newdir = tmp / "old", tmp / "new"
        for d, text in ((olddir, "Old lesson rule"), (newdir, "Corrected lesson rule")):
            (d / "lessons").mkdir(parents=True)
            (d / "lessons/rule.md").write_text("## Rule\n\n" + text + "\n", encoding="utf-8")
        previous = {"version": "0.1.0", "sections": [{"id": "S1", "lessons": [{"id": "S1.L01", "steps": [
            {"id": "S1.L01.s01", "type": "explain", "text_ref": "lessons/rule.md#rule"}]}]}]}
        current = copy.deepcopy(previous)
        current["version"] = "0.2.0"
        current["changes"] = [{"version": "0.2.0", "from": "0.1.0", "added": [], "removed": [], "changed": [],
                               "important": [], "note": "Lesson correction omitted from journal"}]
        CM.annotate(current, newdir, {}, {}, {})
        with self.assertRaises(CM.BuildError):                     # no historical source: conservative
            CM.validate_changes(current, copy.deepcopy(previous), newdir, {}, {}, {})
        with self.assertRaises(CM.BuildError):                     # historical lesson differs
            CM.validate_changes(current, copy.deepcopy(previous), newdir, {}, {}, {},
                                hist={"course_dir": olddir, "claims": {}, "cmap": {}, "rubrics": {}})
        same = tmp / "same"
        shutil.copytree(newdir, same)
        CM.validate_changes(current, copy.deepcopy(previous), newdir, {}, {}, {},
                            hist={"course_dir": same, "claims": {}, "cmap": {}, "rubrics": {}})

    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    def test_r6_observed_change_reaches_mapped_steps(self):
        claims = CM.load_claims(CM.DEFAULT_CLAIMS)
        cmap = CM.load_map(CM.DEFAULT_MAP, claims)
        rubrics = CM.load_rubrics(CM.DEFAULT_RUBRICS)
        base = CM.merge(CM.COURSE_DIR)["course"]
        CM.annotate(base, CM.COURSE_DIR, claims, cmap, rubrics)
        before = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(base)}
        for cid, sid in (("C4a", "S1.L14.s02"), ("C4b", "S1.L14.s02"), ("C2c", "S1.L24.s06"),
                         ("C4a", "S1.L25.s02"), ("C2c", "S1.L24.s04")):
            edited = copy.deepcopy(claims)
            edited[cid]["observed"] = "audit observation sha256:changed"
            c = CM.merge(CM.COURSE_DIR)["course"]
            CM.annotate(c, CM.COURSE_DIR, edited, cmap, rubrics)
            after = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(c)}
            self.assertNotEqual(after[sid], before[sid], f"{cid} observed -> {sid}")


class TestRuntimeOrder(unittest.TestCase):
    """r7: MENTOR-RUNTIME §2 — record first, speak only from a successful result (static check)."""

    @classmethod
    def setUpClass(cls):
        text = (RELEASE_DIR / "course" / "MENTOR-RUNTIME.md").read_text(encoding="utf-8")
        cls.s2 = text[text.index("## 2. Showing a step"):text.index("## 3. Saving")]
        cls.flat = " ".join(cls.s2.split())

    def bullet(self, start, stop):
        i = self.flat.index(start)
        return self.flat[i:self.flat.index(stop, i)]

    def test_r7_order_rule_stated(self):
        self.assertIn("decide → `P record` → speak", self.flat)
        self.assertIn("only from its successful JSON", self.flat)
        self.assertNotIn("Say the chosen option's `reaction`; then", self.flat)

    def test_r7_quiz_record_before_reaction(self):
        q = self.bullet("**quiz**, `scoring: true`", "**exercise**:")
        self.assertLess(q.index("P record"), q.index("reaction"), "quiz: record must come before the reaction")
        self.assertIn("revealed: true", q)
        self.assertLess(q.index("P record"), q.index("revealed: true"))

    def test_r7_artifact_record_before_on_success(self):
        e = self.bullet("`workspace_file`, `list_sections`", "`user_confirm_form`")
        self.assertLess(e.index("P record"), e.index("on_success"))
        self.assertIn("only for a confirmed artifact", e)

    def test_r7_said_done_no_on_success(self):
        e = self.bullet("`user_confirm_form`: a form", "Not found / [Не получилось]")
        self.assertIn("P record --token T --said-done", e)
        self.assertIn("отмечу с твоих слов", e)
        self.assertLess(e.index("--said-done"), e.index("отмечу с твоих слов"))
        self.assertIn("Never say `on_success` here", e)

    def test_r7_scoring_false_no_checked_claim(self):
        e = self.bullet("`scoring: false`", "**quiz**, `scoring: true`")
        self.assertIn("no «проверено»", e)
        # r9 (Codex 39a06593 #2): the reason may be a revealed answer, so the wording stays neutral
        self.assertIn("«сейчас без зачёта»", e)
        self.assertIn("ответ уже был показан", e)
        self.assertIn("never claim the source is unverified as the only reason", e)
        self.assertNotIn("the source is not verified yet. Record", e)

    def test_r7_refusal_example_without_verdict(self):
        self.assertIn("If the call is refused", self.flat)
        ex = self.bullet("Example of a refused call", "`only_human: true`")
        self.assertIn("saying nothing yet", ex)
        self.assertIn("progress: ERROR: token is not the open expectation", ex)
        self.assertIn("does not say «Верно!»", ex)
        self.assertIn("P where", ex)
        self.assertIn("not graded again", ex)
        # the quoted error is the script's real message
        src = (RELEASE_DIR / "course" / "progress.py").read_text(encoding="utf-8")
        self.assertIn("token is not the open expectation (repeated, stale or foreign); nothing written", src)


class TestZzNoWritesOutsideTemp(unittest.TestCase):
    def test_release_and_fixtures_untouched(self):
        self.assertEqual(tree_state(RELEASE_DIR), BEFORE["release"])
        self.assertEqual(tree_state(FIXTURES), BEFORE["fixtures"])
        tmp = Path(tempfile.gettempdir()).resolve()
        for root in TMP_ROOTS:
            self.assertTrue(str(root.resolve()).startswith(str(tmp)), root)


if __name__ == "__main__":
    unittest.main(verbosity=1)
