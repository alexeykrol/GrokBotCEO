#!/usr/bin/env python3
"""
P2b candidate 1 — the control matrix of docs/design/p2b-quizzes.md §9 for the course bookkeeping
(course/progress.py), the build (scripts/course-merge.py), the scenario registry and the balancer
(scripts/quiz-balance.py). Analyzer cases 16 and 17: tools/synth/tests/test_p2b.py.

Test names carry the case number and its type: test_cNN_<defect|guard|new>_...
  defect  must FAIL on the base 1b2e857 and PASS on the candidate (fail-first, tools/p2b/fail_first.py)
  guard   must PASS on both
  new     new behaviour: runs on the candidate only (skipped when P2B_SIDE=base, base-r2 or base-r3)
Candidate 1-r2 controls are named test_r2NN_<defect|guard|new>_... and compare d0c609e (P2B_SIDE=base-r2)
with this tree: defect FAILS on d0c609e, guard passes on both, new runs on the candidate only.
Candidate 1-r3 controls (test_r3NN_...) compare 1a4982c (P2B_SIDE=base-r3) with this tree the same way.
B-095 controls (test_r4NN_...) compare 8839d5f (P2B_SIDE=base-r4) with this tree the same way:
historical build inputs fail closed (a read error is not proof of absence).
Defect and guard tests use only calls the base also understands; the one protocol difference is
`--label`, passed only when `open` returned a frozen `display` (the base has none).

Fixture courses are small and synthetic, built through course-merge.annotate in temporary folders;
the course of this release and the P1 progress fixtures are read-only. Stdlib only, no network.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
ROOT = RELEASE_DIR.parent
COURSE_FILE = RELEASE_DIR / "course" / "course.json"
REGISTRY_FILE = RELEASE_DIR / "course" / "scenario-registry.tsv"
FIXTURES = ROOT / "docs" / "design" / "p1-fixtures"
LEARNERS = ["novichok", "oshibayushchiysya", "otlichnik", "sporshchik", "toropyga"]
HAVE_FIXTURES = all((FIXTURES / f"uchenik-{n}-progress.json").is_file() for n in LEARNERS)
HAVE_BUILD_INPUTS = (ROOT / "docs" / "design" / "claims-map.tsv").is_file()
SIDE = os.environ.get("P2B_SIDE", "candidate")
BASE_REF = os.environ.get("P2B_BASE", "1b2e857")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PG = _load("p2b_progress_under_test", RELEASE_DIR / "course" / "progress.py")
CM = _load("p2b_course_merge_under_test", SCRIPT_DIR / "course-merge.py")


def qb():
    return _load("p2b_quiz_balance_under_test", SCRIPT_DIR / "quiz-balance.py")


BASES = ("base", "base-r2", "base-r3", "base-r4")
new = unittest.skipIf(SIDE in BASES, "new behaviour: candidate only")
# candidate 1-r2 controls (test_r2NN_<type>_...): compared against d0c609e (P2B_SIDE=base-r2), not run on 1b2e857
r2 = unittest.skipIf(SIDE == "base", "r2 control: compared against d0c609e")
r2new = unittest.skipIf(SIDE in BASES, "r2 new behaviour: candidate only")
# candidate 1-r3 controls (test_r3NN_<type>_...): compared against 1a4982c (P2B_SIDE=base-r3)
r3 = unittest.skipIf(SIDE in ("base", "base-r2"), "r3 control: compared against 1a4982c")
# B-095 controls (test_r4NN_<type>_...): compared against 8839d5f (P2B_SIDE=base-r4)
r4 = unittest.skipIf(SIDE in ("base", "base-r2", "base-r3"), "r4 control: compared against 8839d5f")


def tree_state(root: Path):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


BEFORE = {"release": tree_state(RELEASE_DIR),
          "fixtures": tree_state(FIXTURES) if FIXTURES.exists() else {}}

# ---------------------------------------------------------------- fixture course

Q = "S1.L01.s02"
RUBRIC = "R-q"


def opts(ids="abc", key="b", texts=None, reaction="r"):
    texts = texts or {}
    return [{"id": i, "text": texts.get(i, f"вариант {i}"), "correct": i == key, "reaction": f"{reaction} {i}"}
            for i in ids]


def situation(sid, key="p2", rubric=RUBRIC, question="Пароль от сервиса попал в чат. Что сделать?", ids=("p1", "p2", "p3")):
    return {"id": sid, "question": question, "rubric_ref": rubric,
            "options": [{"id": i, "text": f"ответ {i}", "correct": i == key, "reaction": f"реакция {i}"} for i in ids]}


def quiz_step(order="abc", key="b", **extra):
    st = {"id": Q, "type": "quiz", "question": "Ключ попал в чат. Что сделать?", "options": opts(order, key)}
    st.update(extra)
    return st


def raw(version, q, changes=(), more_s1=()):
    s1 = [{"id": "S1.L01.s01", "type": "explain", "text": "t", "example": "e"}, q,
          {"id": "S1.L01.s03", "type": "explain", "text": "t3", "example": "e"}, *more_s1,
          {"id": "S1.L01.s09", "type": "checkpoint", "text": "t",
           "options": [{"id": "continue", "label": "l", "target": "S2", "text": "t"},
                       {"id": "pause", "label": "p", "text": "t"}]}]
    s2 = [{"id": "S2.L01.s01", "type": "explain", "text": "t", "example": "e"},
          {"id": "S2.L01.s02", "type": "checkpoint", "text": "t",
           "options": [{"id": "continue", "label": "l", "target": "finish", "text": "t"},
                       {"id": "pause", "label": "p", "text": "t"}]}]
    les = lambda lid, st: {"id": lid, "title": "L" + lid, "competencies": ["P1.01"], "text": "lessons/x.md", "steps": st}
    return {"id": "mentor", "version": version, "language": "ru", "changes": list(changes),
            "sections": [{"id": "S1", "title": "T1", "goal": "g", "lessons": [les("S1.L01", s1)]},
                         {"id": "S2", "title": "T2", "goal": "g", "lessons": [les("S2.L01", s2)]}]}


def change(version, frm, added=(), removed=(), changed=(), important=(), note="Правка."):
    return {"version": version, "from": frm, "added": list(added), "removed": list(removed),
            "changed": list(changed), "important": list(important), "note": note}


def rubrics(extra=None):
    r = {RUBRIC: {"step": Q, "status": "accepted", "text": "Верно только отозвать ключ у источника."}}
    r.update(extra or {})
    return r


def build(version, q, changes=(), rub=None, more_s1=()):
    """A built fixture course (this tree's course-merge.annotate): normative quiz with an accepted rubric."""
    c = raw(version, copy.deepcopy(q), changes, more_s1)
    CM.annotate(c, Path(tempfile.gettempdir()), {}, {Q: {"basis": "normative", "claims": []}},
                rubrics() if rub is None else rub)
    return {"course": c}


def cv_of(doc, sid=Q):
    return next(st["content_version"] for s in doc["course"]["sections"] for l in s["lessons"]
                for st in l["steps"] if st["id"] == sid)


# ---------------------------------------------------------------- progress environment

TMP_ROOTS = []

# Cases that describe release 0.2.0 (the balancer on its 58 quizzes, the synthetic 0.3.0 built from it) read
# that release from git (a06537d, "0.2.0" in the registry header), not the working-tree course.json, which
# moved on to 0.3.0 in P2b candidate 2.
RELEASE_020 = "a06537d"
CANDIDATE1 = "2505a95"                  # accepted P2b candidate 1: the registry before the 0.3.0 build rows


def _dev_history_present():
    """True in the development repository, where the historical release commits exist. The public release
    clone carries none of them (asked of the repository that holds RELEASE_DIR, the one the code under test
    reads), so tests that rebuild or compare historical releases cannot run there; they
    skip with this reason instead of failing. In the development repository they always run."""
    r = subprocess.run(["git", "-C", str(RELEASE_DIR), "cat-file", "-e", RELEASE_020 + "^{commit}"],
                       capture_output=True)
    return r.returncode == 0


needs_dev_history = unittest.skipUnless(
    _dev_history_present(), "historical release commits are not in this repository (public release clone)")
_COURSE_020 = []


def course_020() -> Path:
    if not _COURSE_020:
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{RELEASE_020}:release/course/course.json"],
                           capture_output=True)
        if r.returncode != 0:
            raise unittest.SkipTest(f"release 0.2.0 ({RELEASE_020}) not readable from git")
        d = Path(tempfile.mkdtemp(prefix="p2b-course-020-"))
        TMP_ROOTS.append(d)
        (d / "course.json").write_bytes(r.stdout)
        _COURSE_020.append(d / "course.json")
    return _COURSE_020[0]


_INPUTS_020 = []
HISTORICAL_TABLES = ("claims-p0a.tsv", "claims-map.tsv", "rubrics.tsv")


def inputs_020():
    """Every build input of release 0.2.0 from git (Codex 36b48ec8 p.7): course.json, the lesson files its
    text_refs name, and the claims / claims-map / rubrics tables as they were at RELEASE_020. Returns
    (course_dir, claims, cmap, rubrics) loaded through this tree's course-merge. The working-tree tables have
    moved on (0.3.0 adds R-S1.L14.s13.b-1, which 0.2.0 has no situation for)."""
    if not _INPUTS_020:
        d = Path(tempfile.mkdtemp(prefix="p2b-inputs-020-"))
        TMP_ROOTS.append(d)
        cdir = d / "course"
        cdir.mkdir()
        shutil.copyfile(course_020(), cdir / "course.json")
        ls = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", RELEASE_020,
                             "release/course/lessons/"], capture_output=True, text=True)
        names = [n for n in ls.stdout.splitlines() if n.endswith(".md")]
        if ls.returncode != 0 or not names:
            raise unittest.SkipTest(f"lessons of release 0.2.0 ({RELEASE_020}) not readable from git")
        for n in names:
            r = subprocess.run(["git", "-C", str(ROOT), "show", f"{RELEASE_020}:{n}"], capture_output=True)
            if r.returncode != 0:
                raise unittest.SkipTest(f"{n} at {RELEASE_020} not readable from git")
            out = cdir / Path(n).relative_to("release/course")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.stdout)
        tables = {}
        for name in HISTORICAL_TABLES:
            r = subprocess.run(["git", "-C", str(ROOT), "show", f"{RELEASE_020}:docs/design/{name}"],
                               capture_output=True)
            if r.returncode != 0:
                raise unittest.SkipTest(f"docs/design/{name} at {RELEASE_020} not readable from git")
            (d / name).write_bytes(r.stdout)
            tables[name] = d / name
        claims = CM.load_claims(tables["claims-p0a.tsv"])
        _INPUTS_020.append((cdir, claims, CM.load_map(tables["claims-map.tsv"], claims),
                            CM.load_rubrics(tables["rubrics.tsv"])))
    return _INPUTS_020[0]


BUILD_NOTE = b"\tadded by build"


def registry_init_part():
    """REGISTRY_FILE without the rows the build appended (note "added by build"); those rows may only
    follow the initialised ones. --init-registry reproduces exactly this part."""
    lines = REGISTRY_FILE.read_bytes().splitlines(keepends=True)
    n = next((i for i, x in enumerate(lines) if x.rstrip(b"\n").endswith(BUILD_NOTE)), len(lines))
    assert all(x.rstrip(b"\n").endswith(BUILD_NOTE) for x in lines[n:]), "build rows only at the end"
    return b"".join(lines[:n])


OTHER = b"# Other commits of course.json read (not releases, no rows): "


def same_init(got: bytes, want: bytes):
    """--init-registry output against the registry's initialised part. Every line must be equal except the
    informational list of other commits read: a later re-init also reads commits made after the registry was
    written (P2b candidate 2: the 0.3.0 commits), which may only be prepended (git log is newest first) and
    must not be commits of a released version. Returns a list of problems."""
    g, w = got.splitlines(keepends=True), want.splitlines(keepends=True)
    if len(g) != len(w):
        return [f"{len(g)} lines != {len(w)}"]
    probs = []
    for a, b in zip(g, w):
        if a.startswith(OTHER) and b.startswith(OTHER):
            la = [x.strip() for x in a[len(OTHER):].decode().strip().split(",")]
            lb = [x.strip() for x in b[len(OTHER):].decode().strip().split(",")]
            extra = la[:len(la) - len(lb)]
            if la[len(la) - len(lb):] != lb or any(x.endswith(("(0.1.0)", "(0.2.0)")) for x in extra):
                probs.append(f"other commits {la} do not extend {lb} with later commits only")
        elif a != b:
            probs.append(f"{a!r} != {b!r}")
    return probs


class Env:
    def __init__(self, tc):
        self.dir = Path(tempfile.mkdtemp(prefix="p2b-"))
        TMP_ROOTS.append(self.dir)
        tc.addCleanup(shutil.rmtree, self.dir, True)
        self.home = self.dir / "mentor"
        self.course_path = self.dir / "course.json"

    def set_course(self, doc):
        self.course_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

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
        before = self.raw()
        code, _, err = self.run(*args)
        tc.assertNotEqual(code, 0, f"{args} should fail")
        if contains:
            tc.assertIn(contains, err)
        tc.assertEqual(before, self.raw(), f"{args}: file changed on error")
        return err

    def raw(self):
        p = self.home / "progress.json"
        return p.read_bytes() if p.exists() else None

    def state(self):
        return json.loads(self.raw())

    def put(self, state):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "progress.json").write_bytes((json.dumps(state, ensure_ascii=False, indent=1) + "\n").encode())

    def rev(self):
        return self.state()["revision"]


def label_of(o, option):
    return next((d["label"] for d in o.get("display") or [] if d["option_id"] == option), None)


def record_args(o, attempt, option, *extra):
    args = ["record", "--token", o["token"], "--attempt", attempt]
    lab = label_of(o, option)
    if lab is not None:                      # the base has no display and no --label
        args += ["--label", lab]
    return args + ["--option", option, *extra]


class Base(unittest.TestCase):
    def setUp(self):
        PG.HOOKS.clear()

    def fresh(self, doc):
        env = Env(self)
        env.set_course(doc)
        env.ok(self, "migrate")
        return env

    def to_step(self, env, sid):
        for _ in range(60):
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

    def back_to_quiz(self, env):
        env.ok(self, "lesson", "S1.L01", "--revision", env.rev())
        return self.to_step(env, Q)

    def reveal(self, env, wrong=None):
        """Three wrong answers on the situation open now; returns the closing result."""
        o = env.ok(self, "open", Q)
        self.assertTrue(o["scoring"], o)
        key = None
        ids = o.get("option_ids") or []
        wrong = wrong or [x for x in ids if x not in ("b", "p2")][:1] * 3
        r = None
        for n, opt in enumerate(wrong, 1):
            r = env.ok(self, *record_args(o, n, opt, "--rubric", "incorrect"))
        self.assertTrue(r["revealed"])
        return o

    def confirm(self, env, option):
        o = env.ok(self, "open", Q)
        r = env.ok(self, *record_args(o, o["next_attempt"], option, "--rubric", "correct", "--evidence", "own_answer"))
        self.assertEqual(r["status"], "confirmed")
        return o


# ================================================================ defects (fail on 1b2e857)

class TestDefects(Base):
    def test_c01_defect_permutation_same_cv_no_repeat_no_notice(self):
        c1 = build("1.0.0", quiz_step("abc", key="b"))
        env = self.fresh(c1)
        self.to_step(env, Q)
        self.confirm(env, "b")
        c2 = build("1.1.0", quiz_step("acb", key="b"), changes=[change("1.1.0", "1.0.0")])
        env.set_course(c2)
        rep = env.ok(self, "migrate", "--json")
        st = env.state()
        self.assertEqual(rep["rechecks"], [], "a permutation must not send a passed check to repeat")
        self.assertEqual(st["repeat"], [])
        self.assertEqual(rep["notices"], [])
        self.assertEqual(st["checks"][Q]["best_this_version"]["status"], "confirmed")
        self.assertEqual(cv_of(c1), cv_of(c2), "content_version must not depend on the order of options")

    def test_c03_defect_reaction_edit_changes_cv_keeps_reveal(self):
        c1 = build("1.0.0", quiz_step())
        env = self.fresh(c1)
        self.to_step(env, Q)
        self.reveal(env, ["a", "c", "a"])
        q2 = quiz_step()
        q2["options"][0]["reaction"] = "другая реакция"
        c2 = build("1.1.0", q2, changes=[change("1.1.0", "1.0.0", changed=[Q])])
        self.assertNotEqual(cv_of(c1), cv_of(c2), "a reaction edit changes content_version")
        env.set_course(c2)
        env.ok(self, "migrate")
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertFalse(o["scoring"], "a revealed situation must stay revealed after a reaction edit")
        env.fails(self, *record_args(o, o["next_attempt"], "b", "--rubric", "correct", "--evidence", "own_answer"))

    def test_c06_defect_revealed_primary_new_situation_scored(self):
        c1 = build("1.0.0", quiz_step())
        env = self.fresh(c1)
        self.to_step(env, Q)
        self.reveal(env, ["a", "c", "a"])
        c2 = build("1.1.0", quiz_step(situations=[situation(Q + ".b")]),
                   changes=[change("1.1.0", "1.0.0", changed=[Q])])
        env.set_course(c2)
        env.ok(self, "migrate")
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertEqual(o["scenario_id"], Q + ".b", "the revealed primary must not be offered for a score again")
        self.assertTrue(o["scoring"])
        r = env.ok(self, *record_args(o, o["next_attempt"], "p2", "--rubric", "correct", "--evidence", "new_situation"))
        self.assertEqual(r["status"], "confirmed")
        hist = env.state()["checks"][Q]["history"]
        self.assertEqual([h["scenario_id"] for h in hist if h.get("scored") and h["status"] == "confirmed"], [Q + ".b"])

    def test_c12_defect_open_without_display_superseded(self):
        c1 = build("1.0.0", quiz_step())
        env = self.fresh(c1)
        self.to_step(env, Q)
        o = env.ok(self, "open", Q)
        st = env.state()
        for k in ("display", "question", "options"):          # an expectation opened before P2b
            st["open"].pop(k, None)
        env.put(st)
        before_hist = len(st["checks"][Q]["history"])
        env.set_course(build("1.1.0", quiz_step(), changes=[change("1.1.0", "1.0.0")]))
        rep = env.ok(self, "migrate", "--json")
        o2 = env.ok(self, "open", Q)
        self.assertNotEqual(o2["token"], o["token"], "an open without display must not survive migrate")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--option", "b",
                  "--rubric", "correct", "--evidence", "own_answer")
        st = env.state()
        self.assertEqual(len(st["checks"][Q]["history"]), before_hist, "superseded: no attempt")
        self.assertEqual(st["repeat"], [])
        self.assertEqual(rep["notices"], [])
        self.assertEqual(rep.get("superseded"), [Q])
        self.assertEqual(st["superseded_opens"][0]["token"], o["token"])
        self.assertTrue(o2.get("display"))


# ================================================================ guards (pass on both)

class TestGuards(Base):
    def test_c15_guard_schema1_letter_is_option_id_after_permutation(self):
        c2 = build("1.1.0", quiz_step("cab", key="b"), changes=[change("1.1.0", "1.0.0")])
        env = Env(self)
        env.set_course(c2)
        env.put({"course_version": "1.0.0", "current": "S1.L01.s03", "completed": ["S1.L01.s01", Q],
                 "quiz": {Q: {"option": "b", "attempts": 1}}, "exercises": {}, "skip_reasons": {},
                 "updated": "2026-11-12T10:00:00Z"})
        env.ok(self, "migrate")
        st = env.state()
        h = st["checks"][Q]["history"][0]
        self.assertEqual(h["option_ids"], ["b"])                       # the id b, not the letter at position b
        self.assertEqual(st["legacy"][Q][0]["original"], {"quiz": {"option": "b", "attempts": 1}})
        self.assertEqual(h["origin"], "legacy_unknown")

    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    @needs_dev_history
    def test_c11a_guard_real_course_builds_without_raising_eligible(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            r = CM.main(["--check"])
        self.assertEqual(r, 0, "course 0.2.0 must build unchanged")
        c = PG.Course(COURSE_FILE)
        self.assertEqual([s for s in c.order if c.steps[s].get("eligible")], ["S1.L14.s13"])


# ================================================================ new behaviour (candidate only)

class TestBuildNew(Base):
    @new
    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    def test_c02_new_hash_function_keeps_every_020_cv(self):
        course_dir, claims, cmap, rub = inputs_020()                   # all inputs of 0.2.0, not only course.json
        c = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        CM.annotate(c, course_dir, claims, cmap, rub)
        stored = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        now = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(c)}
        was = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(stored)}
        self.assertEqual(len(was), 307)
        self.assertEqual({k for k in was if now[k] != was[k]}, set())
        # why the pin: the working-tree rubrics of 0.3.0 have a second row for S1.L14.s13 (.b's own rubric) and
        # 0.2.0 has no situation naming it, so with them the 0.2.0 primary is ambiguous; the build says so loudly
        # instead of rebinding (§12 addendum 1). The historical cv above never sees those rows.
        cur = CM.load_rubrics(CM.DEFAULT_RUBRICS)
        if sum(1 for r in cur.values() if r["step"] == "S1.L14.s13") > 1:
            with self.assertRaisesRegex(CM.BuildError, "ambiguous primary rubric"):
                CM.annotate(json.loads(course_020().read_text(encoding="utf-8"))["course"], course_dir,
                            claims, cmap, cur)

    def registry_of(self, doc):
        return [{"scenario_id": s, "step": st, "answer_version": av, "first_course_version": doc["course"]["version"],
                 "note": "t"} for s, st, av in CM.course_situations(doc["course"])]

    @new
    def test_c04_new_same_id_other_answer_fails_build(self):
        base = build("1.0.0", quiz_step(situations=[situation(Q + ".b")]))
        rows = self.registry_of(base)
        self.assertEqual(CM.check_registry(base["course"], rows), [])
        edits = {
            "question": lambda q: q["situations"][0].update(question="Другой вопрос"),
            "option text": lambda q: q["situations"][0]["options"][0].update(text="другой ответ"),
            "key": lambda q: [o.update(correct=o["id"] == "p3") for o in q["situations"][0]["options"]],
            "primary question": lambda q: q.update(question="Совсем другой вопрос"),
            "rubric text": None,
        }
        for name, fn in edits.items():
            q = quiz_step(situations=[situation(Q + ".b")])
            rub = None
            if fn:
                fn(q)
            else:
                rub = rubrics()
                rub[RUBRIC] = dict(rub[RUBRIC], text="Другая рубрика.")
            doc = build("1.1.0", q, rub=rub)
            with self.subTest(edit=name), self.assertRaises(CM.BuildError):
                CM.check_registry(doc["course"], rows)
        # reaction, whitespace, rubric status and option order keep the answer
        for name, fn in {"reaction": lambda q: q["situations"][0]["options"][0].update(reaction="иная"),
                         "spaces": lambda q: q["situations"][0].update(question="  Пароль от сервиса  попал в чат.\nЧто сделать?"),
                         "order": lambda q: q["situations"][0]["options"].reverse()}.items():
            q = quiz_step(situations=[situation(Q + ".b")])
            fn(q)
            with self.subTest(keep=name):
                self.assertEqual(CM.check_registry(build("1.1.0", q)["course"], rows), [])
        rub = rubrics()
        rub[RUBRIC] = dict(rub[RUBRIC], status="candidate")
        self.assertEqual(CM.check_registry(build("1.1.0", quiz_step(situations=[situation(Q + ".b")]), rub=rub)["course"], rows), [])
        # clarification 1: the same id under another step fails; forbidden id fails
        moved = copy.deepcopy(rows)
        for r in moved:
            if r["scenario_id"] == Q + ".b":
                r["step"] = "S1.L01.s07"
        with self.assertRaises(CM.BuildError):
            CM.check_registry(base["course"], moved)
        conflict = rows + [dict(rows[1], answer_version="0" * 16, note="conflict")]
        with self.assertRaises(CM.BuildError):
            CM.check_registry(base["course"], conflict)

    @new
    def test_c09_new_registry_remove_return(self):
        c1 = build("1.0.0", quiz_step(situations=[situation(Q + ".b")]))
        rows = self.registry_of(c1)
        c2 = build("1.1.0", quiz_step())                                  # .b removed: rows stay
        self.assertEqual(CM.check_registry(c2["course"], rows), [])
        c3 = build("1.2.0", quiz_step(situations=[situation(Q + ".b")]))  # same answer back: no new row
        self.assertEqual(CM.check_registry(c3["course"], rows), [])
        with self.assertRaises(CM.BuildError):                            # same id, another answer
            CM.check_registry(build("1.2.0", quiz_step(situations=[situation(Q + ".b", key="p3")]))["course"], rows)
        new_rows = CM.check_registry(build("1.2.0", quiz_step(situations=[situation(Q + ".c", key="p3")]))["course"], rows)
        self.assertEqual([r["scenario_id"] for r in new_rows], [Q + ".c"])
        # progress: the reveal of .b survives remove -> return with the same answer
        env = self.fresh(c1)
        self.to_step(env, Q)
        self.reveal(env, ["a", "c", "a"])
        self.back_to_quiz(env)
        o = self.reveal(env, ["p1", "p3", "p1"])
        self.assertEqual(o["scenario_id"], Q + ".b")
        env.set_course(build("1.1.0", quiz_step(), changes=[change("1.1.0", "1.0.0", changed=[Q])]))
        env.ok(self, "migrate")
        env.set_course(build("1.2.0", quiz_step(situations=[situation(Q + ".b")]),
                             changes=[change("1.1.0", "1.0.0", changed=[Q]), change("1.2.0", "1.1.0", changed=[Q])]))
        env.ok(self, "migrate")
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertFalse(o["scoring"], "both situations revealed: no score")

    @new
    def test_c10_new_registry_superset_of_base(self):
        rows = CM.read_registry(REGISTRY_FILE)
        self.assertEqual(len([r for r in rows if r["note"] != "added by build"]), 63)   # rows initialised from releases
        for ref in (BASE_REF, self.first_registry_commit()):
            shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:release/course/scenario-registry.tsv"],
                                   capture_output=True, text=True) if ref else None
            base_rows = []
            if shown is not None and shown.returncode == 0:
                f = Path(tempfile.mkdtemp(prefix="p2b-reg-")) / "r.tsv"
                TMP_ROOTS.append(f.parent)
                f.write_text(shown.stdout, encoding="utf-8")
                base_rows = CM.read_registry(f)
            with self.subTest(base=ref):
                self.assertEqual(CM.registry_superset(base_rows, rows), [])
        changed = copy.deepcopy(rows)
        changed[3]["answer_version"] = "f" * 16
        self.assertTrue(CM.registry_superset(rows, changed))
        self.assertTrue(CM.registry_superset(rows, rows[:5] + rows[6:]))
        self.assertEqual(CM.registry_superset(rows, rows + [dict(rows[0], scenario_id="X.new")]), [])

    def first_registry_commit(self):
        r = subprocess.run(["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%h", "--",
                            "release/course/scenario-registry.tsv"], capture_output=True, text=True)
        refs = r.stdout.split()
        return refs[-1] if refs else None

    @new
    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    @needs_dev_history
    def test_c10b_new_registry_init_reproducible(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            r = CM.main(["--init-registry"])                # the file exists: verifies, never rewrites
        self.assertEqual(r, 0)
        rep = json.loads(out.getvalue())
        self.assertTrue(rep["already_initialised"])
        self.assertEqual([x["ref"] for x in rep["releases"]], ["ea17f9e", "a06537d"])
        self.assertEqual((rep["rows"], rep["conflicts"], rep["unavailable"]), (63, [], []))

    @new
    def test_c11b_new_situation_rubric_condition_of_scoring(self):
        cand = rubrics({"R-cand": {"step": Q, "status": "candidate", "text": "Кандидат."}})
        for rubric_ref, rub, scored in (("-", None, False), ("R-cand", cand, False), (RUBRIC, None, True)):
            with self.subTest(rubric=rubric_ref):
                doc = build("1.0.0", quiz_step(situations=[situation(Q + ".b", rubric=rubric_ref)]), rub=rub)
                env = self.fresh(doc)
                self.to_step(env, Q)
                self.reveal(env, ["a", "c", "a"])
                self.back_to_quiz(env)
                o = env.ok(self, "open", Q)
                self.assertEqual((o["scenario_id"], o["scoring"]), (Q + ".b", scored))
        with self.assertRaises(CM.BuildError):                               # a missing rubric id
            build("1.0.0", quiz_step(situations=[situation(Q + ".b", rubric="R-none")]))
        doc = build("1.0.0", quiz_step(situations=[situation(Q + ".b", rubric="-")]), rub={})
        st = doc["course"]["sections"][0]["lessons"][0]["steps"][1]
        self.assertFalse(st["eligible"])                                     # no rubric: exists, not eligible


class TestProgressNew(Base):
    @new
    def test_c05_new_primary_edit_new_primary_id(self):
        c1 = build("1.0.0", quiz_step())
        env = self.fresh(c1)
        n_before = env.ok(self, "summary", "all")["N"]
        self.to_step(env, Q)
        self.reveal(env, ["a", "c", "a"])
        q2 = quiz_step(primary_scenario_id=Q + ".v2")
        q2["question"] = "Ключ от сервиса попал в общий чат. Что сделать первым?"
        rows = TestBuildNew.registry_of(self, c1)
        c2 = build("1.1.0", q2, changes=[change("1.1.0", "1.0.0", changed=[Q])])
        self.assertEqual([r["scenario_id"] for r in CM.check_registry(c2["course"], rows)], [Q + ".v2"])
        env.set_course(c2)
        env.ok(self, "migrate")
        self.assertEqual(env.ok(self, "summary", "all")["N"], n_before)
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertEqual((o["step"], o["scenario_id"], o["scoring"]), (Q, Q + ".v2", True))
        self.assertTrue(env.state()["exposure"][Q][Q][0]["revealed"])        # the old reveal is kept under its id

    @new
    def test_c07_new_situation_does_not_inherit_reveal(self):
        doc = build("1.0.0", quiz_step(situations=[situation(Q + ".b")]))
        env = self.fresh(doc)
        self.to_step(env, Q)
        self.reveal(env, ["a", "c", "a"])
        self.back_to_quiz(env)
        self.reveal(env, ["p1", "p3", "p1"])
        c2 = build("1.1.0", quiz_step(situations=[situation(Q + ".b"),
                                                  situation(Q + ".c", ids=("k1", "k2", "k3"), key="k1")]),
                   changes=[change("1.1.0", "1.0.0", changed=[Q])])
        env.set_course(c2)
        env.ok(self, "migrate")
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertEqual((o["scenario_id"], o["scoring"]), (Q + ".c", True))
        self.assertNotIn(Q + ".c", env.state()["exposure"].get(Q, {}))

    @new
    def test_c08_new_keys_of_each_situation(self):
        doc = build("1.0.0", quiz_step(situations=[situation(Q + ".b")]))
        env = self.fresh(doc)
        self.to_step(env, Q)
        o = env.ok(self, "open", Q)
        self.assertEqual(o["scenario_id"], Q)
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "p2",
                  "--rubric", "correct", "--evidence", "own_answer")            # p2 is not an id of the primary
        self.reveal(env, ["a", "c", "a"])
        self.back_to_quiz(env)
        o = env.ok(self, "open", Q)
        self.assertEqual(o["scenario_id"], Q + ".b")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b",
                  "--rubric", "correct", "--evidence", "own_answer", contains="not one of")
        env.fails(self, *record_args(o, 1, "p2", "--rubric", "incorrect"), contains="contradicts the answer key")
        r = env.ok(self, *record_args(o, 1, "p2", "--rubric", "correct", "--evidence", "new_situation"))
        self.assertEqual(r["status"], "confirmed")                            # judged by the key of .b

    @new
    def test_c13_new_frozen_layout_survives_restart_and_permutation(self):
        c1 = build("1.0.0", quiz_step("abc", key="b"))
        env = self.fresh(c1)
        self.to_step(env, Q)
        o = env.ok(self, "open", Q)
        frozen = [o["display"], o["question"], o["options"]]
        self.assertEqual([d["label"] for d in o["display"]], ["a", "b", "c"])
        o2 = env.ok(self, "open", Q)                                          # restart: state only from the file
        self.assertEqual((o2["token"], [o2["display"], o2["question"], o2["options"]]), (o["token"], frozen))
        c2 = build("1.1.0", quiz_step("cab", key="b"), changes=[change("1.1.0", "1.0.0")])
        self.assertEqual(cv_of(c1), cv_of(c2))
        env.set_course(c2)
        env.ok(self, "migrate")
        o3 = env.ok(self, "open", Q)
        self.assertEqual((o3["token"], [o3["display"], o3["question"], o3["options"]]), (o["token"], frozen),
                         "reopen returns the frozen layout, not the current array")
        r = env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b",
                   "--rubric", "correct", "--evidence", "own_answer")
        self.assertEqual(r["status"], "confirmed")
        self.back_to_quiz(env)
        o4 = env.ok(self, "open", Q)                                           # a new show takes the new order
        self.assertEqual([d["option_id"] for d in o4["display"]], ["c", "a", "b"])

    @new
    def test_c14_new_label_option_pair_checked(self):
        doc = build("1.0.0", quiz_step("bac", key="a"))                      # display: a->b, b->a, c->c
        env = self.fresh(doc)
        self.to_step(env, Q)
        o = env.ok(self, "open", Q)
        self.assertEqual({d["label"]: d["option_id"] for d in o["display"]}, {"a": "b", "b": "a", "c": "c"})
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "b",
                  "--rubric", "incorrect", contains="shows option")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--option", "a",
                  "--rubric", "correct", "--evidence", "own_answer", contains="--label is required")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "z", "--option", "a",
                  "--rubric", "correct", "--evidence", "own_answer", contains="not in the display")
        env.fails(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b",
                  "--rubric", "correct", "--evidence", "own_answer")
        r = env.ok(self, "record", "--token", o["token"], "--attempt", 1, "--label", "b", "--option", "a",
                   "--rubric", "correct", "--evidence", "own_answer")
        self.assertEqual(r["status"], "confirmed")
        h = env.state()["checks"][Q]["history"][-1]
        self.assertEqual(h["option_ids"], ["a"])


# ================================================================ balancer and lint

UNITS7 = ["S1.L01.s02", "S1.L01.s02.b", "S1.L01.s05", "S1.L02.s03", "S1.L02.s07", "S2.L01.s04", "S2.L01.s04.b"]
EXPECTED7 = [("S1.L01.s02", "a"), ("S1.L01.s02.b", "a"), ("S1.L01.s05", "b"), ("S1.L02.s03", "c"),
             ("S1.L02.s07", "c"), ("S2.L01.s04", "b"), ("S2.L01.s04.b", "a")]
REAL58 = ("aacbcbabacacbabcacbacbcabcbaabcbaccababcacbacbcabbcabacbac", "9f0a6bb780e9e142")
REAL59 = ("ababcbacabccbabacacbacbcabcbaabcbaccababcacbacbcabbcabacbac", "3d8fc6709a8d3103")


class TestBalance(unittest.TestCase):
    @new
    def test_c18_new_balancer_p2b_balance_1(self):
        B = qb()
        self.assertEqual(B.VERSION, "p2b-balance-1")
        self.assertEqual(B.tie_key("S1.L01.s02.b", "a"),
                         hashlib.sha256("p2b-balance-1|S1.L01.s02.b|a".encode()).hexdigest())
        self.assertEqual(B.assign(UNITS7), (EXPECTED7, []))
        self.assertEqual(B.assign(UNITS7[:1]), ([("S1.L01.s02", "a")], []))
        self.assertEqual(B.assign(UNITS7[:2]), ([("S1.L01.s02", "b"), ("S1.L01.s02.b", "a")], []))
        for n in (1, 2, 4, 7):
            a1, a2 = B.assign(UNITS7[:n]), B.assign(UNITS7[:n])
            self.assertEqual(a1, a2)
            self.assertEqual(len(a1[0]), n)
        course = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        units = [u for u, _, _, _ in B.situations(course)]
        self.assertEqual(len(units), 58)
        i = units.index("S1.L14.s13")
        for us, (seq, digest), counts in ((units, REAL58, {"a": 20, "b": 19, "c": 19}),
                                          (units[:i + 1] + ["S1.L14.s13.b"] + units[i + 1:], REAL59,
                                           {"a": 20, "b": 20, "c": 19})):
            a, w = B.assign(us)
            got = "".join(x for _, x in a)
            self.assertEqual((got, hashlib.sha256(got.encode()).hexdigest()[:16]), (seq, digest))
            self.assertEqual({L: got.count(L) for L in "abc"}, counts)
            self.assertNotIn("aaa", got)
            self.assertNotIn("bbb", got)
            self.assertNotIn("ccc", got)
            self.assertEqual(w, [])
        # permutation: correct to the chosen position, wrong options keep their order; idempotent
        o = [{"id": "a", "correct": False}, {"id": "b", "correct": True}, {"id": "c", "correct": False}]
        self.assertEqual([x["id"] for x in B.permute(o, "a")], ["b", "a", "c"])
        self.assertEqual([x["id"] for x in B.permute(o, "c")], ["a", "c", "b"])
        self.assertEqual(B.permute(B.permute(o, "c"), "c"), B.permute(o, "c"))

    @new
    def test_c18b_new_apply_is_idempotent_on_a_fixture_dir(self):
        B = qb()
        d = Path(tempfile.mkdtemp(prefix="p2b-bal-"))
        TMP_ROOTS.append(d)
        self.addCleanup(shutil.rmtree, d, True)
        (d / "sections").mkdir()
        sec = raw("1.0.0", quiz_step(situations=[situation(Q + ".b")]))["sections"]
        for s in sec:
            (d / "sections" / f"{s['id']}.json").write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        a1, _ = B.apply_to_sections(d)
        once = {f.name: f.read_bytes() for f in (d / "sections").iterdir()}
        a2, _ = B.apply_to_sections(d)
        self.assertEqual(a1, a2)
        self.assertEqual({f.name: f.read_bytes() for f in (d / "sections").iterdir()}, once)

    @new
    def test_c19_new_lint_warnings(self):
        B = qb()

        def course_with(option_sets):
            steps = [{"id": f"S1.L01.s{i:02d}", "type": "quiz", "question": "q", "options": o}
                     for i, o in enumerate(option_sets, 1)]
            return {"sections": [{"id": "S1", "lessons": [{"id": "S1.L01", "steps": steps}]}]}

        def o3(texts, key):
            return [{"id": i, "text": t, "correct": i == key, "reaction": "r"} for i, t in zip("abc", texts)]

        all_b = course_with([o3(["xx", "yy", "zz"], "b")] * 6)
        w, n = B.lint(all_b)
        self.assertTrue(any("position b" in x for x in w))
        self.assertTrue(any("run of 3" in x for x in w))
        self.assertEqual(n["all"]["tie"], 6)
        self.assertEqual(n["all"]["longest"], 0)                           # a tie is not "the longest"
        longest = course_with([o3(["x", "длинный верный", "y"], "b"), o3(["длинный верный", "x", "y"], "a"),
                               o3(["x", "y", "длинный верный"], "c")])
        w, n = B.lint(longest)
        self.assertEqual(n["all"]["longest"], 3)
        self.assertTrue(any("strictly the longest" in x for x in w))
        self.assertFalse(any("position" in x for x in w))
        good = course_with([o3(["aa", "bb", "cc"], k) for k in "abcbca"])
        self.assertEqual(B.lint(good)[0], [])
        # both denominators: all situations and the primaries alone
        sit = course_with([o3(["aa", "bb", "cc"], "a")])
        sit["sections"][0]["lessons"][0]["steps"][0]["situations"] = [
            {"id": "S1.L01.s01.b", "options": o3(["aa", "bb", "cc"], "c")}]
        self.assertEqual((B.lint(sit)[1]["all"]["n"], B.lint(sit)[1]["primaries"]["n"]), (2, 1))

    @new
    @unittest.skipUnless(HAVE_BUILD_INPUTS, "review inputs live only in the development repo")
    def test_c20_new_detectors_and_review_tsv(self):
        QR = _load("p2b_quiz_review_under_test", ROOT / "tools" / "p2b" / "quiz_review.py")
        old = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        cand = json.loads(COURSE_FILE.read_text(encoding="utf-8"))["course"]
        self.assertEqual(cand["version"], "0.3.0")
        # detectors on 0.2.0: 32 strictly longest, 2 ties (not "longest"), 2 + 2 candidates
        s = QR.summary(QR.detect(old))
        self.assertEqual((s["n"], len(s["longest"]), s["tie"]), (58, 32, ["S3.L03.s06", "S3.L05.s02"]))
        self.assertEqual(s["copy_above"], ["S1.L13.s03", "S4.L01.s07"])
        self.assertEqual(s["reaction_hint"], [("S1.L21.s05", "c"), ("S4.L01.s07", "b")])
        # the review TSV: every 0.2.0 primary and S1.L14.s13.b, reasons, code-computed hashes
        rows = QR.read_tsv(ROOT / "docs" / "design" / "p2b-quiz-review.tsv")
        self.assertEqual(QR.check(rows, old, cand), [])
        self.assertEqual(len(rows), 59)
        self.assertEqual(sorted(r["step"] for r in rows if r["entity_hash_before"] != "-"),
                         sorted(st["id"] for _, st, _, p, _ in QR.situations(old) if p))
        self.assertEqual([r["scenario"] for r in rows if r["entity_hash_before"] == "-"], ["S1.L14.s13.b"])
        # an edit of question/option text/key of a primary has a new id <step>.v2; a reaction-only edit keeps it
        for r in rows:
            if r["entity_hash_before"] == "-":
                continue
            eo, en = QR.entity(old, r["step"]), QR.entity(cand, r["scenario"])
            answer = lambda e: (e["question"], [(o["id"], o["text"], o["correct"]) for o in e["options"]], e["rubric"])
            with self.subTest(step=r["step"]):
                self.assertEqual(r["scenario"], r["step"] if answer(eo) == answer(en) else r["step"] + ".v2")
        # S1.L14.s13.b (design §7): p1-p3, one correct, reactions, its own accepted rubric R-S1.L14.s13.b-1
        # (content2-r2 §C, accepted in Codex 36b48ec8); the primary keeps R-S1.L14.s13-1 by the §12 fallback
        st = next(st for _, st, _, p, _ in QR.situations(cand) if st["id"] == "S1.L14.s13")
        b = st["situations"][0]
        self.assertEqual((b["id"], sorted(o["id"] for o in b["options"]), b["rubric_ref"]),
                         ("S1.L14.s13.b", ["p1", "p2", "p3"], "R-S1.L14.s13.b-1"))
        self.assertEqual((cand["rubrics"]["R-S1.L14.s13.b-1"]["step"], cand["rubrics"]["R-S1.L14.s13.b-1"]["status"]),
                         ("S1.L14.s13", "accepted"))
        self.assertNotIn("primary_rubric_ref", st)
        self.assertEqual({x["id"]: x["rubric_ref"] for x in st["scenarios"]},
                         {"S1.L14.s13": "R-S1.L14.s13-1", "S1.L14.s13.b": "R-S1.L14.s13.b-1"})
        self.assertEqual([o["id"] for o in b["options"] if o["correct"]], ["p2"])
        self.assertTrue(all(o["reaction"].strip() for o in b["options"]))
        self.assertEqual((st["eligible"], st["rubric_ref"]), (True, "R-S1.L14.s13-1"))   # the primary keeps its rubric
        # no detector hit is left in the candidate; strictly longest at most half
        s2 = QR.summary(QR.detect(cand))
        self.assertEqual((s2["copy_above"], s2["reaction_hint"]), ([], []))
        self.assertLessEqual(len(s2["longest"]) / s2["n"], 0.5)
        # journal 0.3.0: changed = the edited steps, important among them; registry: only the new ids appended
        entry = next(e for e in cand["changes"] if e["version"] == "0.3.0")
        self.assertEqual(sorted(entry["changed"]), sorted({r["step"] for r in rows if r["decision"] == "edit"}))
        self.assertEqual((entry["added"], entry["removed"]), ([], []))
        self.assertTrue(entry["important"] and set(entry["important"]) <= set(entry["changed"]))
        shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{CANDIDATE1}:release/course/scenario-registry.tsv"],
                               capture_output=True, text=True, check=True).stdout
        f = scratch_dir() / "c1.tsv"
        f.write_text(shown, encoding="utf-8")
        base_rows, rows_now = CM.read_registry(f), CM.read_registry(REGISTRY_FILE)
        self.assertEqual(CM.registry_superset(base_rows, rows_now), [])
        appended = rows_now[len(base_rows):]
        self.assertEqual(rows_now[:len(base_rows)], base_rows)
        self.assertEqual(sorted(r["scenario_id"] for r in appended),
                         sorted(r["scenario"] for r in rows if r["scenario"] != r["step"]))
        self.assertTrue(all((r["first_course_version"], r["note"]) == ("0.3.0", "added by build") for r in appended))


class TestRealSituationB(Base):
    # Real 0.3.0 (content2-r2 §C): the learner revealed the primary S1.L14.s13; open offers .b with scoring;
    # an answer with the label shown for p2 is confirmed; the primary stays revealed.
    @new
    def test_c20b_new_real_b_scored_after_primary_reveal(self):
        S = "S1.L14.s13"
        env = self.fresh(json.loads(COURSE_FILE.read_text(encoding="utf-8")))
        env.ok(self, "lesson", "S1.L14", "--revision", env.rev())
        self.to_step(env, S)
        o = env.ok(self, "open", S)
        self.assertEqual((o["scenario_id"], o["scoring"]), (S, True))
        for n, opt in enumerate(["a", "b", "a"], 1):
            r = env.ok(self, *record_args(o, n, opt, "--rubric", "incorrect"))
        self.assertTrue(r["revealed"])
        env.ok(self, "lesson", "S1.L14", "--revision", env.rev())             # back to the quiz, as a learner would
        self.to_step(env, S)
        o2 = env.ok(self, "open", S)
        self.assertEqual((o2["scenario_id"], o2["scoring"]), (S + ".b", True))
        self.assertIsNotNone(label_of(o2, "p2"))
        r2 = env.ok(self, *record_args(o2, o2["next_attempt"], "p2", "--rubric", "correct", "--evidence", "new_situation"))
        self.assertEqual(r2["status"], "confirmed")
        st = env.state()
        self.assertTrue(any(e.get("revealed") for e in st["exposure"][S][S]), "the primary stays revealed")
        self.assertEqual([h["scenario_id"] for h in st["checks"][S]["history"]
                          if h.get("scored") and h["status"] == "confirmed"], [S + ".b"])


# ================================================================ migrate 0.2.0 -> 0.3.0 on fixtures

@unittest.skipUnless(HAVE_FIXTURES and HAVE_BUILD_INPUTS, "P1 fixtures and build inputs: development repo only")
class TestMigrate030(Base):
    def course_030(self, reaction_edit=None):
        B = qb()
        course_dir, claims, cmap, rub = inputs_020()                   # the synthetic 0.3.0 is 0.2.0 + edits
        c = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        assignment, _ = B.plan(c)
        where = {u: o for u, _, _, o in B.situations(c)}
        for u, letter in assignment:
            where[u][:] = B.permute(list(where[u]), letter)
        if reaction_edit:
            st = next(s for _, _, s in CM.iter_steps(c) if s["id"] == reaction_edit)
            st["options"][0]["reaction"] += " (уточнено)"
        CM.annotate(c, course_dir, claims, cmap, rub)
        old = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(
            json.loads(course_020().read_text(encoding="utf-8"))["course"])}
        changed = sorted(s["id"] for _, _, s in CM.iter_steps(c) if s["content_version"] != old[s["id"]])
        c["version"] = "0.3.0"
        c["changes"] = c["changes"] + [change("0.3.0", "0.2.0", changed=changed, important=changed)]
        moved = sum(1 for u, x in assignment if B.correct_pos(where[u]) == x)
        return {"course": c}, changed, moved

    @new
    def test_c21_new_migrate_020_030_matches_journal(self):
        results = {}
        for edit in (None, "S1.L02.s04"):
            doc030, changed, moved = self.course_030(edit)
            self.assertEqual(changed, [edit] if edit else [], "only the reaction edit changes a version")
            self.assertEqual(moved, 58)
            for name in LEARNERS:
                env = Env(self)
                shutil.copyfile(course_020(), env.course_path)
                env.put(json.loads((FIXTURES / f"uchenik-{name}-progress.json").read_text(encoding="utf-8")))
                env.ok(self, "migrate")
                st020 = env.state()
                did = set(st020["checks"])
                env.set_course(doc030)
                rep = env.ok(self, "migrate", "--json")
                st = env.state()
                new_notices = [n for n in st["notices"] if n["version"] == "0.3.0"]
                expected_rechecks = sorted(s for s in changed if s in did)
                with self.subTest(edit=edit, learner=name):
                    self.assertEqual(sorted(rep["rechecks"]), expected_rechecks)
                    self.assertTrue(set(st["repeat"]) - set(st020["repeat"]) <= set(changed))
                    self.assertTrue(all(set(n["steps"]) <= set(changed) for n in new_notices))
                    self.assertEqual(rep["superseded"], [])
                results[(edit, name)] = (len(rep["rechecks"]), len(new_notices),
                                         len(set(st["repeat"]) - set(st020["repeat"])))
        # the real 0.3.0 of this tree (P2b candidate 2): the fixtures migrated 0.1.0 -> 0.2.0 -> 0.3.0
        real = json.loads(COURSE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(real["course"]["version"], "0.3.0")
        entry = next(e for e in real["course"]["changes"] if e["version"] == "0.3.0")
        for name in LEARNERS:
            env = Env(self)
            shutil.copyfile(course_020(), env.course_path)
            env.put(json.loads((FIXTURES / f"uchenik-{name}-progress.json").read_text(encoding="utf-8")))
            env.ok(self, "migrate")
            st020 = env.state()
            did = set(st020["checks"])
            env.set_course(real)
            rep = env.ok(self, "migrate", "--json")
            st = env.state()
            new_notices = [n for n in st["notices"] if n["version"] == "0.3.0"]
            new_repeats = set(st["repeat"]) - set(st020["repeat"])
            with self.subTest(real="0.3.0", learner=name):
                self.assertEqual(sorted(rep["rechecks"]), sorted(s for s in entry["changed"] if s in did))
                self.assertTrue(new_repeats <= set(entry["changed"]))
                self.assertEqual(sorted(s for n in new_notices for s in n["steps"]),
                                 sorted(s for s in entry["changed"] if s in did))
                self.assertTrue(all(n["important"] == bool(set(n["steps"]) & set(entry["important"])) for n in new_notices))
                self.assertEqual(rep["superseded"], [])
            results[("real 0.3.0", name)] = (len(rep["rechecks"]), len(new_notices), len(new_repeats),
                                             sorted(new_repeats), [(n["kind"], n["important"]) for n in new_notices])
        print("\n  c21 migrate 0.2.0->0.3.0 (rechecks, new notices, new repeats): "
              + "; ".join(f"{e or 'permutation only'}/{n}={v}" for (e, n), v in results.items()), file=sys.stderr)

    @new
    def test_c21b_new_open_expectations_at_030(self):
        doc030, _, _ = self.course_030()
        env = Env(self)
        shutil.copyfile(course_020(), env.course_path)
        env.ok(self, "migrate")
        self.to_step(env, "S1.L01.s03")
        o = env.ok(self, "open", "S1.L01.s03")
        env.set_course(doc030)
        rep = env.ok(self, "migrate", "--json")
        self.assertEqual(rep["superseded"], [])                           # has a display: survives
        o2 = env.ok(self, "open", "S1.L01.s03")
        self.assertEqual((o2["token"], o2["display"]), (o["token"], o["display"]))
        st = env.state()
        for k in ("display", "question", "options"):
            st["open"].pop(k)
        env.put(st)
        rep = env.ok(self, "migrate", "--json")                           # same version: still closes it
        self.assertEqual(rep["superseded"], ["S1.L01.s03"])
        self.assertEqual(env.state()["repeat"], [])


# ================================================================ candidate 1-r2 controls (vs d0c609e)

R_TWO = {"R-two": {"step": Q, "status": "accepted", "text": "Другая ситуация того же навыка."}}


def step_of(doc, sid=Q):
    return next(st for _, _, st in CM.iter_steps(doc["course"]) if st["id"] == sid)


def av_of(doc, scen):
    return next(av for s, _, av in CM.course_situations(doc["course"]) if s == scen)


def two_situations(**extra):
    """Codex 30ab6049 group 2: .b shares the primary's R-q, .c has its own accepted R-two."""
    return quiz_step(situations=[situation(Q + ".b", rubric=RUBRIC),
                                 situation(Q + ".c", rubric="R-two", ids=("z1", "z2", "z3"), key="z2")], **extra)


def reversed_rubrics(rub):
    return dict(reversed(list(rub.items())))


class TestR2PrimaryRubric(Base):
    """Group 2: primary_rubric_ref (design §12 addendum 1). Base fixture: primary R-q, accepted, eligible."""

    def base_rows(self):
        base = build("1.0.0", quiz_step())
        return base, TestBuildNew.registry_of(self, base)

    @r2
    def test_r211_defect_ambiguous_primary_rubric_fails_build(self):
        for order in ("as written", "rows permuted"):
            rub = rubrics(R_TWO) if order == "as written" else reversed_rubrics(rubrics(R_TWO))
            with self.subTest(order=order), self.assertRaisesRegex(CM.BuildError, "ambiguous primary rubric"):
                build("1.1.0", two_situations(), rub=rub)

    @r2
    def test_r212_defect_explicit_primary_rubric_keeps_primary(self):
        base, rows = self.base_rows()
        for order in ("as written", "rows permuted"):
            rub = rubrics(R_TWO) if order == "as written" else reversed_rubrics(rubrics(R_TWO))
            with self.subTest(order=order):
                doc = build("1.1.0", two_situations(primary_rubric_ref=RUBRIC), rub=rub)
                st = step_of(doc)
                self.assertEqual((st["rubric_ref"], st["eligible"]), (RUBRIC, True))
                self.assertEqual(av_of(doc, Q), av_of(base, Q))
                self.assertEqual([r["scenario_id"] for r in CM.check_registry(doc["course"], rows)],
                                 [Q + ".b", Q + ".c"])

    @r2
    def test_r213_guard_new_situation_own_rubric_primary_inferred(self):
        base, rows = self.base_rows()
        for order in ("as written", "rows permuted"):
            rub = rubrics(R_TWO) if order == "as written" else reversed_rubrics(rubrics(R_TWO))
            with self.subTest(order=order):
                doc = build("1.1.0", quiz_step(situations=[situation(Q + ".c", rubric="R-two", ids=("z1", "z2", "z3"),
                                                                     key="z2")]), rub=rub)
                st = step_of(doc)
                self.assertEqual((st["rubric_ref"], st["eligible"]), (RUBRIC, True))
                self.assertEqual([r["scenario_id"] for r in CM.check_registry(doc["course"], rows)], [Q + ".c"])

    @r2
    def test_r214_guard_one_rubric_shared_with_a_situation(self):
        base, rows = self.base_rows()
        doc = build("1.1.0", quiz_step(situations=[situation(Q + ".b", rubric=RUBRIC)]))
        st = step_of(doc)
        self.assertEqual((st["rubric_ref"], st["eligible"]), (RUBRIC, True))
        self.assertEqual([r["scenario_id"] for r in CM.check_registry(doc["course"], rows)], [Q + ".b"])

    @r2new
    def test_r215_new_primary_rubric_ref_validation(self):
        st = step_of(build("1.0.0", quiz_step(primary_rubric_ref="-")))          # explicit absence, no lookup
        self.assertEqual((st["rubric_ref"], st["eligible"]), ("-", False))
        cand = rubrics({"R-cand": {"step": Q, "status": "candidate", "text": "Кандидат."}})
        st = step_of(build("1.0.0", quiz_step(primary_rubric_ref="R-cand"), rub=cand))
        self.assertEqual((st["rubric_ref"], st["eligible"]), ("R-cand", False))   # the field accepts nothing
        other = rubrics({"R-other": {"step": "S1.L01.s03", "status": "accepted", "text": "Чужая."}})
        for name, q, rub in (("unknown id", quiz_step(primary_rubric_ref="R-none"), None),
                             ("rubric of another step", quiz_step(primary_rubric_ref="R-other"), other),
                             ("empty", quiz_step(primary_rubric_ref=""), None)):
            with self.subTest(name), self.assertRaises(CM.BuildError):
                build("1.0.0", q, rub=rub)
        with self.assertRaisesRegex(CM.BuildError, "only on exercise and quiz"):
            build("1.0.0", quiz_step(), more_s1=[{"id": "S1.L01.s04", "type": "explain", "text": "t",
                                                  "example": "e", "primary_rubric_ref": "-"}])
        # two rows, none named by a situation: ambiguous too (no first-row pick)
        with self.assertRaisesRegex(CM.BuildError, "ambiguous primary rubric"):
            build("1.0.0", quiz_step(), rub=rubrics(R_TWO))

    @r2new
    def test_r216_new_reference_is_not_content(self):
        plain, explicit = build("1.0.0", quiz_step()), build("1.0.0", quiz_step(primary_rubric_ref=RUBRIC))
        self.assertEqual(cv_of(plain), cv_of(explicit))                           # writing the inferred choice
        self.assertEqual(av_of(plain, Q), av_of(explicit, Q))
        rub = rubrics()
        rub[RUBRIC] = dict(rub[RUBRIC], status="candidate")
        self.assertEqual(av_of(build("1.0.0", quiz_step(primary_rubric_ref=RUBRIC), rub=rub), Q), av_of(plain, Q))
        rub = rubrics()
        rub[RUBRIC] = dict(rub[RUBRIC], text="Совсем другой критерий.")
        self.assertNotEqual(av_of(build("1.0.0", quiz_step(primary_rubric_ref=RUBRIC), rub=rub), Q), av_of(plain, Q))


def fail_show(*prefixes):
    """CM.git with `git show <ref>:...` failing for the given refs (fault injection; the repo is untouched)."""
    real = CM.git

    def fake(args, cwd):
        if args and args[0] == "show" and any(str(args[1]).startswith(p + ":") for p in prefixes):
            return subprocess.CompletedProcess(args, 128, "", "simulated unavailable release")
        return real(args, cwd)
    return fake


def init_registry(path, git=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as st:
        if git:
            st.enter_context(unittest.mock.patch.object(CM, "git", git))
        st.enter_context(contextlib.redirect_stdout(out))
        st.enter_context(contextlib.redirect_stderr(err))
        rc = CM.main(["--init-registry", "--registry", str(path)])
    return rc, out.getvalue(), err.getvalue()


def scratch_dir():
    d = Path(tempfile.mkdtemp(prefix="p2b-r2-"))
    TMP_ROOTS.append(d)
    return d


@needs_dev_history
class TestR2RegistryInit(unittest.TestCase):
    """Group 3: registry init fails closed when a mandatory release is unavailable."""

    @r2
    def test_r221_defect_unavailable_release_fails_closed(self):
        for name, ref in (("0.1.0", "ea17f9e"), ("0.2.0", "a06537d")):
            with self.subTest(release=name):
                d = scratch_dir()
                f = d / "registry.tsv"
                rc, out, _ = init_registry(f, fail_show(ref))
                self.assertNotEqual(rc, 0)
                self.assertFalse(f.exists(), "no registry may be created from incomplete history")
                rep = json.loads(out)
                self.assertIn(name, [u["version"] for u in rep["unavailable"]])
                existing = d / "existing.tsv"                              # an existing file is not rewritten
                existing.write_bytes(REGISTRY_FILE.read_bytes())
                rc, _, _ = init_registry(existing, fail_show(ref))
                self.assertNotEqual(rc, 0)
                self.assertEqual(existing.read_bytes(), REGISTRY_FILE.read_bytes())

    @r2
    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    def test_r222_defect_partial_registry_cannot_admit_changed_retired_id(self):
        course = json.loads(COURSE_FILE.read_text(encoding="utf-8"))["course"]
        rows = [{"scenario_id": s, "step": st, "answer_version": av, "first_course_version": "0.2.0",
                 "note": "init from 0.2.0 (a06537d)"} for s, st, av in CM.course_situations(course)]
        self.assertNotIn("S1.L05.s04", [r["scenario_id"] for r in rows])
        f = scratch_dir() / "partial.tsv"
        f.write_text(CM.render_registry(rows, [
            "Scenario registry (P2b): append-only, never edit or delete a row. Written by course-merge.py.",
            "Init sources: 0.2.0 = a06537d; unavailable: 0.1.0 ea17f9e (not in git)"]), encoding="utf-8")
        args = (CM.COURSE_DIR, CM.DEFAULT_CLAIMS, CM.DEFAULT_MAP, CM.DEFAULT_RUBRICS)
        with self.assertRaises(CM.BuildError):
            CM.build(*args, registry_path=f)
        CM.build(*args, registry_path=REGISTRY_FILE)                      # the complete registry keeps working
        # with the complete registry the retired id cannot come back with another answer
        back = copy.deepcopy(course)
        q = next(st for _, _, st in CM.iter_steps(back) if st.get("type") == "quiz")
        q.update(id="S1.L05.s04", question="ДРУГОЙ ответ под старым id")
        with self.assertRaises(CM.BuildError):
            CM.check_registry(back, CM.read_registry(REGISTRY_FILE))

    @r2
    def test_r223_guard_all_releases_init_reproduces_registry(self):
        f = scratch_dir() / "registry.tsv"
        rc, out, _ = init_registry(f)
        self.assertEqual(rc, 0)
        self.assertEqual(same_init(f.read_bytes(), registry_init_part()), [])
        self.assertEqual(len(CM.read_registry(f)), 63)
        once = f.read_bytes()
        rc, _, _ = init_registry(f)                                          # re-init: byte-identical
        self.assertEqual(rc, 0)
        self.assertEqual(f.read_bytes(), once)

    @r2new
    def test_r224_new_unreadable_history_rubrics_or_newer_commit_fail_closed(self):
        real = CM.git

        def no_rubrics(args, cwd):                        # course.json readable, rubric table at 0.1.0 not
            if args and args[0] == "ls-tree" and any(str(a).startswith("ea17f9e") for a in args[1:]):
                return subprocess.CompletedProcess(args, 128, "", "simulated")
            return real(args, cwd)
        f = scratch_dir() / "registry.tsv"
        rc, out, _ = init_registry(f, no_rubrics)
        self.assertNotEqual(rc, 0)
        self.assertFalse(f.exists())
        self.assertIn("0.1.0", [u["version"] for u in json.loads(out)["mandatory_unavailable"]])
        # the newest commit of course.json unreadable: 0.2.0 is not silently taken from an older commit
        newest = real(["log", "-1", "--format=%h", "--", "course.json"], CM.COURSE_DIR).stdout.strip()
        rc, out, _ = init_registry(f, fail_show(newest))
        self.assertNotEqual(rc, 0)
        self.assertFalse(f.exists())
        self.assertIn("0.2.0", [u["version"] for u in json.loads(out)["mandatory_unavailable"]])
        # a registry without provenance is refused by the build
        g = scratch_dir() / "bare.tsv"
        g.write_text(CM.render_registry(CM.read_registry(REGISTRY_FILE)), encoding="utf-8")
        self.assertIsNotNone(CM.registry_provenance(g))
        self.assertIsNone(CM.registry_provenance(REGISTRY_FILE))


# ================================================================ candidate 1-r3 controls (vs 1a4982c)

RUBRIC_TABLE = "docs/design/rubrics.tsv"
S13_AV = "b7dd5f73b58ce31c"          # S1.L14.s13 in the registry: 0.2.0 with its rubric text


def external_table(fail_read=False, reads=None):
    """CM.git where the 0.2.0 snapshots carry no embedded rubrics (as a pre-P1 build), so the historical
    rubric table must be read; with fail_read the read of that table is refused (fault injection)."""
    real = CM.git

    def fake(args, cwd):
        if args and args[0] == "show" and str(args[1]).endswith(":" + RUBRIC_TABLE):
            if reads is not None:
                reads.append(str(args[1]))
            if fail_read:
                return subprocess.CompletedProcess(args, 128, "", "simulated refused read")
        r = real(args, cwd)
        if args and args[0] == "show" and str(args[1]).endswith(":release/course/course.json") and r.returncode == 0:
            d = json.loads(r.stdout)
            if d["course"].get("version") == "0.2.0":
                d["course"].pop("rubrics", None)
                r = subprocess.CompletedProcess(args, 0, json.dumps(d), "")
        return r
    return fake


@needs_dev_history
class TestR3HistoricalRubricTable(unittest.TestCase):
    """r3: the historical rubric table is looked up from the repository root, not the course folder."""

    def in_cwd(self, d):
        old = os.getcwd()
        os.chdir(d)
        self.addCleanup(os.chdir, old)

    @r3
    def test_r301_defect_external_table_gives_the_registered_answer(self):
        for cwd in (ROOT, scratch_dir()):
            with self.subTest(cwd=str(cwd)):
                self.in_cwd(cwd)
                reads = []
                with unittest.mock.patch.object(CM, "git", external_table(reads=reads)):
                    rows, cov = CM.registry_init_rows(CM.COURSE_DIR)
                av = next(r["answer_version"] for r in rows if r["scenario_id"] == "S1.L14.s13")
                self.assertEqual(av, S13_AV)
                self.assertTrue(reads, "the rubric table of 0.2.0 was never read")
                self.assertEqual(cov["unavailable"], [])

    @r3
    def test_r302_defect_refused_table_read_fails_closed(self):
        d = scratch_dir()
        f = d / "registry.tsv"
        rc, out, _ = init_registry(f, external_table(fail_read=True))
        self.assertNotEqual(rc, 0)
        self.assertFalse(f.exists())
        self.assertIn("0.2.0", [u["version"] for u in json.loads(out)["unavailable"]])
        existing = d / "existing.tsv"
        existing.write_bytes(REGISTRY_FILE.read_bytes())
        rc, _, _ = init_registry(existing, external_table(fail_read=True))
        self.assertNotEqual(rc, 0)
        self.assertEqual(existing.read_bytes(), REGISTRY_FILE.read_bytes())

    @r3
    def test_r303_guard_absent_table_in_an_old_release_is_absence(self):
        reads = []
        with unittest.mock.patch.object(CM, "git", external_table(reads=reads)):
            rows, cov = CM.registry_init_rows(CM.COURSE_DIR)
        self.assertEqual(cov["unavailable"], [])
        self.assertFalse([r for r in reads if r.startswith("ea17f9e")], "0.1.0 has no rubric table")
        want = [r for r in CM.read_registry(REGISTRY_FILE) if r["first_course_version"] == "0.1.0"]
        self.assertEqual([r for r in rows if r["first_course_version"] == "0.1.0"], want)
        self.assertEqual(len(want), 62)

    @r3
    def test_r304_guard_full_init_byte_identical_from_any_cwd(self):
        d = scratch_dir()
        self.in_cwd(d)
        f = d / "registry.tsv"
        rc, _, _ = init_registry(f)
        self.assertEqual(rc, 0)
        self.assertEqual(same_init(f.read_bytes(), registry_init_part()), [])
        self.assertEqual(len(CM.read_registry(f)), 63)


# ================================================================ B-095 controls (vs 8839d5f)

T_CLAIMS = "claim_id\tquote_en\ttranslation_ru\tour_inference\tscope\trisk\tstatus\tdoc_basis\tobserved\n" \
           "C1\tq\tп\ti\ts\tlow\tverified\td\to\n"
T_MAP = "step_id\tbasis\tclaim_ids\nS1.L01.s01\tclaims\tC1\n"
T_RUB = "rubric_id\tstep_id\tstatus\ttext\nR-x\tS1.L01.s01\taccepted\tКритерий.\n"
H_COURSE = {"version": "0.1.0", "sections": [{"id": "S1", "lessons": [{"id": "S1.L01", "steps": [
    {"id": "S1.L01.s01", "type": "explain", "text_ref": "lessons/a.md#intro"},
    {"id": "S1.L01.s02", "type": "explain", "text_ref": "lessons/b.md#more"}]}]}]}


class HistRepo:
    """A scratch git repository shaped like this one (release/course + docs/design). Commit `a` has the
    course, two lessons, the claims and map tables and no rubric table; commit `b` adds the rubric table.
    The working tree keeps all three tables, as a build at HEAD would see them."""

    def __init__(self):
        self.root = scratch_dir() / "repo"
        self.course = self.root / "release" / "course"
        self.design = self.root / "docs" / "design"
        (self.course / "lessons").mkdir(parents=True)
        self.design.mkdir(parents=True)
        self.run("init", "-q")
        (self.course / "course.json").write_text(json.dumps({"course": H_COURSE}), encoding="utf-8")
        (self.course / "lessons" / "a.md").write_text("# Intro\n\nТекст урока a.\n", encoding="utf-8")
        (self.course / "lessons" / "b.md").write_text("# More\n\nТекст урока b.\n", encoding="utf-8")
        self.claims, self.map, self.rubrics = (self.design / "claims-p0a.tsv", self.design / "claims-map.tsv",
                                               self.design / "rubrics.tsv")
        self.claims.write_text(T_CLAIMS, encoding="utf-8")
        self.map.write_text(T_MAP, encoding="utf-8")
        self.a = self.commit("a")
        self.rubrics.write_text(T_RUB, encoding="utf-8")
        self.b = self.commit("b")

    def run(self, *args):
        r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                            "-c", "user.name=t", "-c", "user.email=t@t", *args],
                           cwd=self.root, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def commit(self, msg):
        self.run("add", "release", "docs")
        self.run("commit", "-q", "-m", msg)
        return self.run("rev-parse", "HEAD")

    def drop_blob(self, ref, rel):
        """Delete the loose object of <ref>:<rel>: the tree still lists the file, reading it fails."""
        oid = self.run("rev-parse", f"{ref}:{rel}")
        (self.root / ".git" / "objects" / oid[:2] / oid[2:]).unlink()

    def inputs(self, ref, claims=None):
        w = scratch_dir()
        return CM.historical_inputs(self.course, ref, w, claims or self.claims, self.map, self.rubrics)


def failing_git(*needles):
    """subprocess.run where every git ls-tree / git show naming one of the needles fails (a repository read
    error on that path); everything else runs for real. Both the base and the candidate read through it."""
    real = subprocess.run

    def fake(cmd, *a, **kw):
        if (isinstance(cmd, list) and cmd[:1] == ["git"] and any(x in ("ls-tree", "show") for x in cmd[1:3])
                and any(n in str(c) for c in cmd for n in needles)):
            text = kw.get("text")
            return subprocess.CompletedProcess(cmd, 128, "" if text else b"",
                                               "fatal: simulated read error" if text else b"fatal: simulated read error")
        return real(cmd, *a, **kw)
    return fake


@needs_dev_history
class TestR4HistoricalInputsFailClosed(unittest.TestCase):
    """B-095 (Codex 568ded6f): an access or read error on an existing historical input is not proof of absence."""

    @r4
    def test_r401_defect_table_listed_but_unreadable_fails_closed(self):
        h = HistRepo()
        h.drop_blob(h.a, "docs/design/claims-map.tsv")
        with self.assertRaisesRegex(CM.BuildError, "claims-map.*" + h.a):
            h.inputs(h.a)

    @r4
    def test_r402_defect_table_listing_failure_fails_closed(self):
        h = HistRepo()
        with unittest.mock.patch.object(subprocess, "run", failing_git("claims-p0a.tsv")):
            with self.assertRaisesRegex(CM.BuildError, "cannot list claims.*" + h.b):
                h.inputs(h.b)

    @r4
    def test_r403_defect_lesson_listed_but_unreadable_fails_closed(self):
        h = HistRepo()
        h.drop_blob(h.b, "release/course/lessons/b.md")
        with self.assertRaisesRegex(CM.BuildError, "lessons/b.md"):
            h.inputs(h.b)

    @r4
    def test_r404_defect_table_outside_repository_fails_closed(self):
        h = HistRepo()
        outside = scratch_dir() / "claims-p0a.tsv"
        outside.write_text(T_CLAIMS, encoding="utf-8")
        with self.assertRaisesRegex(CM.BuildError, "outside the repository"):
            h.inputs(h.b, claims=outside)

    @r4
    def test_r405_guard_absent_table_is_empty_and_history_proceeds(self):
        h = HistRepo()
        hist = h.inputs(h.a)                                # rubrics.tsv did not exist at a: empty, no error
        self.assertEqual(hist["rubrics"], {})
        self.assertEqual(list(hist["claims"]), ["C1"])
        self.assertEqual(hist["cmap"]["S1.L01.s01"]["claims"], ["C1"])
        self.assertEqual(sorted(p.name for p in (hist["course_dir"] / "lessons").iterdir()), ["a.md", "b.md"])
        hv = CM.historical_versions(copy.deepcopy(H_COURSE), hist)
        self.assertEqual(sorted(hv), ["S1.L01.s01", "S1.L01.s02"])
        self.assertNotIn(None, hv.values())
        self.assertEqual(h.inputs(h.b)["rubrics"]["R-x"]["step"], "S1.L01.s01")
        with self.assertRaises(CM.BuildError):              # an unknown ref: the lesson listing itself fails
            h.inputs("0" * 40)
        # real history: 0.1.0 (ea17f9e) has no claims-map and no rubric table -> proven absent, built as before
        hist = CM.historical_inputs(CM.COURSE_DIR, "ea17f9e", scratch_dir(), CM.DEFAULT_CLAIMS, CM.DEFAULT_MAP,
                                    CM.DEFAULT_RUBRICS)
        self.assertEqual((len(hist["claims"]), hist["cmap"], hist["rubrics"]), (28, {}, {}))
        hv = CM.historical_versions(json.loads(subprocess.run(
            ["git", "-C", str(ROOT), "show", "ea17f9e:release/course/course.json"],
            capture_output=True, text=True).stdout)["course"], hist)
        self.assertEqual(len(hv), 302)
        self.assertEqual(hashlib.sha256(json.dumps(hv, sort_keys=True).encode()).hexdigest()[:16], "0c5b60f47c435697")

    @r4
    @unittest.skipUnless(HAVE_BUILD_INPUTS, "build inputs live only in the development repo")
    def test_r406_guard_020_historical_versions_unchanged(self):
        stored = json.loads(course_020().read_text(encoding="utf-8"))["course"]
        bare = copy.deepcopy(stored)
        for _, _, st in CM.iter_steps(bare):
            st.pop("content_version")                        # recompute every step from 0.2.0's own inputs
        hist = CM.historical_inputs(CM.COURSE_DIR, RELEASE_020, scratch_dir(), CM.DEFAULT_CLAIMS, CM.DEFAULT_MAP,
                                    CM.DEFAULT_RUBRICS)
        hv = CM.historical_versions(bare, hist)
        was = {s["id"]: s["content_version"] for _, _, s in CM.iter_steps(stored)}
        self.assertEqual(len(was), 307)
        self.assertEqual({k for k in was if hv[k] != was[k]}, set())

    @r4
    def test_r407_guard_table_name_with_cr_loads_its_rows(self):
        # Codex ce349bd1 p.1: a readable table whose name holds a CR must load (aff2957 lost it to newline
        # translation of a text-mode listing and returned it as absent)
        h = HistRepo()
        odd = h.design / "rubrics\r.tsv"
        odd.write_text(T_RUB, encoding="utf-8")
        c = h.commit("cr")
        hist = CM.historical_inputs(h.course, c, scratch_dir(), h.claims, h.map, odd)
        self.assertEqual(list(hist["rubrics"]), ["R-x"])

    @r4
    def test_r408_defect_short_row_in_historical_table_is_a_build_error(self):
        # Codex ce349bd1 p.2: a valid-UTF-8 row missing its last field gives None from csv -> AttributeError
        h = HistRepo()
        h.rubrics.write_text("rubric_id\tstep_id\tstatus\ttext\nR-x\tS1.L01.s01\taccepted\n", encoding="utf-8")
        c = h.commit("short")
        with self.assertRaisesRegex(CM.BuildError, "rubrics.*" + c + ".*AttributeError"):
            h.inputs(c)

    @r4
    def test_r409_defect_table_listed_readable_invalid_utf8_fails_closed(self):
        h = HistRepo()
        h.rubrics.write_bytes(b"rubric_id\tstep_id\tstatus\ttext\nR-x\tS\taccepted\t\xff\xfe\n")
        c = h.commit("c")                                   # present but not decodable: not an empty table
        with self.assertRaisesRegex(CM.BuildError, "rubrics.*" + c + ".*UnicodeDecodeError"):
            h.inputs(c)

    @r4
    def test_r410_defect_lesson_name_with_cr_restored_byte_exactly(self):
        h = HistRepo()
        body = "# Odd\n\nУрок с CR в имени.\r\n".encode("utf-8")
        (h.course / "lessons" / "c\r.md").write_bytes(body)
        c = h.commit("cr lesson")
        hist = h.inputs(c)
        self.assertEqual(sorted(p.name for p in (hist["course_dir"] / "lessons").iterdir()), ["a.md", "b.md", "c\r.md"])
        self.assertEqual((hist["course_dir"] / "lessons" / "c\r.md").read_bytes(), body)


class TestZzNoWritesOutsideTemp(unittest.TestCase):
    def test_zz_guard_release_and_fixtures_untouched(self):
        self.assertEqual(tree_state(RELEASE_DIR), BEFORE["release"])
        if FIXTURES.exists():
            self.assertEqual(tree_state(FIXTURES), BEFORE["fixtures"])
        tmp = Path(tempfile.gettempdir()).resolve()
        for root in TMP_ROOTS:
            self.assertTrue(str(root.resolve()).startswith(str(tmp)), root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
