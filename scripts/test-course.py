#!/usr/bin/env python3
"""
Tests for the Mentor course (course/course.json, course/lessons/, course/kb/).
Contract: course/SCHEMA.md.

Each check is a function returning a list of error strings. The real course must
produce none (GREEN); small broken fixtures prove each check catches its defect (RED).
Stdlib only, no network.
"""
import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
COURSE_DIR = SCRIPT_DIR.parent / "course"
COURSE_FILE = COURSE_DIR / "course.json"
KB_DIR = COURSE_DIR / "kb"
LESSONS_DIR = COURSE_DIR / "lessons"

STEP_TYPES = {"explain", "exercise", "quiz", "checkpoint", "branch"}
CHECK_METHODS = {"workspace_file", "list_sections", "config_key", "user_confirm_form", "agent_tool"}
COMPETENCY_RE = re.compile(r"^P\d+\.\d{2}$")
SECTION_RE = re.compile(r"^S\d+$")
LESSON_RE = re.compile(r"^S\d+\.L\d{2}$")
LESSON_TEXT_RE = re.compile(r"^lessons/[\w.-]+\.md$")
URL_RE = re.compile(r"^https?://\S+$")

# U4: words a beginner must not see. Latin words with word boundaries, Russian stems, file names.
FORBIDDEN_RE = re.compile(
    r"(?i)(?<![\w.])(?:repo\w*|commit\w*|git|github|config\.json|payload)(?![\w])"
    r"|репозитор\w*|коммит\w*"
    r"|\b[\w-]+\.(?:json|md|py|sh)\b"
)
USER_FACING_STEP_KEYS = ("text", "example", "task", "expected_result", "on_success", "question")


def load_course(path=COURSE_FILE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def iter_lessons(course):
    for section in course["course"]["sections"]:
        for lesson in section["lessons"]:
            yield section, lesson


def iter_steps(course):
    for section, lesson in iter_lessons(course):
        for step in lesson["steps"]:
            yield section, lesson, step


def all_step_ids(course):
    return [s["id"] for _, _, s in iter_steps(course)]


def user_facing_strings(course):
    """(where, text) pairs for every user-facing field (SCHEMA.md §2.6)."""
    for section in course["course"]["sections"]:
        yield section["id"] + ".title", section.get("title", "")
        yield section["id"] + ".goal", section.get("goal", "")
        for lesson in section["lessons"]:
            yield lesson["id"] + ".title", lesson.get("title", "")
    for _, _, step in iter_steps(course):
        for key in USER_FACING_STEP_KEYS:
            if isinstance(step.get(key), str):
                yield f"{step['id']}.{key}", step[key]
        if isinstance(step.get("on_fail"), dict):
            yield f"{step['id']}.on_fail.hint", step["on_fail"].get("hint", "")
        for opt in step.get("options", []):
            for key in ("text", "reaction", "label"):
                if isinstance(opt.get(key), str):
                    yield f"{step['id']}.{opt.get('id')}.{key}", opt[key]
        for sit in step.get("situations") or []:
            if isinstance(sit.get("question"), str):
                yield f"{sit.get('id')}.question", sit["question"]
            for opt in sit.get("options", []):
                for key in ("text", "reaction"):
                    if isinstance(opt.get(key), str):
                        yield f"{sit.get('id')}.{opt.get('id')}.{key}", opt[key]


# ---------- checks ----------

def check_structure(course):
    errors = []
    c = course.get("course", {})
    for key in ("id", "version", "language", "sections"):
        if key not in c:
            errors.append(f"course: missing {key}")
    if c.get("language") != "ru":
        errors.append("course: language must be 'ru'")
    for section in c.get("sections", []):
        if not SECTION_RE.match(section.get("id", "")):
            errors.append(f"section id {section.get('id')!r} not S<n>")
        for key in ("title", "goal"):
            if not section.get(key):
                errors.append(f"{section.get('id')}: empty {key}")
        if not section.get("lessons"):
            errors.append(f"{section.get('id')}: no lessons")
        for lesson in section.get("lessons", []):
            if not LESSON_RE.match(lesson.get("id", "")):
                errors.append(f"lesson id {lesson.get('id')!r} not S<n>.L<nn>")
            if not lesson.get("title"):
                errors.append(f"{lesson.get('id')}: empty title")
            if not lesson.get("steps"):
                errors.append(f"{lesson.get('id')}: no steps")
            for step in lesson.get("steps", []):
                if step.get("type") not in STEP_TYPES:
                    errors.append(f"{step.get('id')}: unknown type {step.get('type')!r}")
    return errors


def check_unique_ids(course):
    seen, errors = set(), []
    ids = [s["id"] for s in course["course"]["sections"]]
    ids += [l["id"] for _, l in iter_lessons(course)]
    ids += all_step_ids(course)
    for i in ids:
        if i in seen:
            errors.append(f"duplicate id {i}")
        seen.add(i)
    return errors


def check_lesson_texts(course, base=COURSE_DIR):
    errors = []
    for _, lesson in iter_lessons(course):
        text = lesson.get("text", "")
        if not LESSON_TEXT_RE.match(text):
            errors.append(f"{lesson['id']}: text {text!r} not lessons/<file>.md")
        elif not (base / text).is_file():
            errors.append(f"{lesson['id']}: missing {text}")
    for _, _, step in iter_steps(course):
        ref = step.get("text_ref")
        if ref:
            file_part = ref.split("#", 1)[0]
            if not (base / file_part).is_file():
                errors.append(f"{step['id']}: text_ref file missing {file_part}")
    return errors


def check_competencies(course):
    errors = []
    for _, lesson in iter_lessons(course):
        comps = lesson.get("competencies")
        if not comps:
            errors.append(f"{lesson['id']}: no competencies")
            continue
        for comp in comps:
            if not isinstance(comp, str) or not COMPETENCY_RE.match(comp):
                errors.append(f"{lesson['id']}: bad competency id {comp!r}")
    return errors


def check_explains(course):
    errors = []
    for _, _, step in iter_steps(course):
        if step["type"] != "explain":
            continue
        if not (step.get("text") or step.get("text_ref")):
            errors.append(f"{step['id']}: explain needs text or text_ref")
        if not str(step.get("example", "")).strip():
            errors.append(f"{step['id']}: explain without example")
    return errors


def check_quizzes(course):
    errors = []
    for _, _, step in iter_steps(course):
        if step["type"] != "quiz":
            continue
        if not str(step.get("question", "")).strip():
            errors.append(f"{step['id']}: empty question")
        opts = step.get("options", [])
        if len(opts) != 3:
            errors.append(f"{step['id']}: {len(opts)} options, need exactly 3")
        if sum(1 for o in opts if o.get("correct") is True) != 1:
            errors.append(f"{step['id']}: need exactly one correct option")
        if len({o.get("id") for o in opts}) != len(opts):
            errors.append(f"{step['id']}: duplicate option ids")
        for o in opts:
            if not isinstance(o.get("correct"), bool):
                errors.append(f"{step['id']}.{o.get('id')}: correct must be bool")
            for key in ("id", "text", "reaction"):
                if not str(o.get(key, "")).strip():
                    errors.append(f"{step['id']}.{o.get('id')}: empty {key}")
    return errors


def check_exercises(course):
    errors = []
    for _, _, step in iter_steps(course):
        if step["type"] != "exercise":
            continue
        for key in ("task", "expected_result", "on_success"):
            if not str(step.get(key, "")).strip():
                errors.append(f"{step['id']}: empty {key}")
        check = step.get("check")
        if not isinstance(check, dict) or check.get("method") not in CHECK_METHODS:
            errors.append(f"{step['id']}: check.method must be one of {sorted(CHECK_METHODS)}")
        elif not str(check.get("detail", "")).strip():
            errors.append(f"{step['id']}: empty check.detail")
        on_fail = step.get("on_fail")
        if not isinstance(on_fail, dict) or not str(on_fail.get("hint", "")).strip() \
                or not isinstance(on_fail.get("retry"), bool):
            errors.append(f"{step['id']}: on_fail needs hint and bool retry")
        if not isinstance(step.get("only_human"), bool):
            errors.append(f"{step['id']}: only_human must be bool")
    return errors


def check_checkpoints(course):
    errors = []
    sections = course["course"]["sections"]
    section_ids = [s["id"] for s in sections]
    for idx, section in enumerate(sections):
        last = section["lessons"][-1]["steps"][-1] if section["lessons"] and section["lessons"][-1]["steps"] else {}
        if last.get("type") != "checkpoint":
            errors.append(f"{section['id']}: does not end with a checkpoint")
            continue
        opts = {o.get("id"): o for o in last.get("options", [])}
        if set(opts) != {"continue", "pause"} or len(last.get("options", [])) != 2:
            errors.append(f"{last['id']}: options must be exactly continue + pause")
            continue
        expected = section_ids[idx + 1] if idx + 1 < len(sections) else "finish"
        if opts["continue"].get("target") != expected:
            errors.append(f"{last['id']}: continue target {opts['continue'].get('target')!r}, want {expected!r}")
        for o in opts.values():
            for key in ("label", "text"):
                if not str(o.get(key, "")).strip():
                    errors.append(f"{last['id']}.{o.get('id')}: empty {key}")
    # a checkpoint anywhere but the section end is a defect
    for section in sections:
        steps = [s for l in section["lessons"] for s in l["steps"]]
        for s in steps[:-1]:
            if s["type"] == "checkpoint":
                errors.append(f"{s['id']}: checkpoint not at section end")
    return errors


def check_references(course):
    errors = []
    ids = set(all_step_ids(course))
    order = all_step_ids(course)
    for _, _, step in iter_steps(course):
        if "next" in step and step["next"] not in ids:
            errors.append(f"{step['id']}: next {step['next']!r} does not exist")
        if step["type"] != "branch":
            continue
        if step.get("default") not in ids:
            errors.append(f"{step['id']}: default {step.get('default')!r} does not exist")
        if not step.get("cases"):
            errors.append(f"{step['id']}: branch without cases")
        for case in step.get("cases", []):
            when = case.get("when", {})
            if case.get("next") not in ids:
                errors.append(f"{step['id']}: case next {case.get('next')!r} does not exist")
            ref = when.get("step")
            if ref not in ids:
                errors.append(f"{step['id']}: when.step {ref!r} does not exist")
            elif order.index(ref) >= order.index(step["id"]):
                errors.append(f"{step['id']}: when.step {ref!r} is not a previous step")
            conds = [k for k in ("answer", "attempts_min", "result") if k in when]
            if len(conds) != 1:
                errors.append(f"{step['id']}: when needs exactly one of answer/attempts_min/result")
            if "result" in when and when["result"] not in ("passed", "skipped"):
                errors.append(f"{step['id']}: when.result must be passed or skipped")
    return errors


def check_beginner_language(course, lessons_dir=LESSONS_DIR):
    errors = []
    for where, text in user_facing_strings(course):
        m = FORBIDDEN_RE.search(text)
        if m:
            errors.append(f"{where}: {m.group(0)!r}")
    if lessons_dir.is_dir():
        for path in sorted(lessons_dir.glob("*.md")):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                m = FORBIDDEN_RE.search(line)
                if m:
                    errors.append(f"lessons/{path.name}:{n}: {m.group(0)!r}")
    return errors


def parse_front_matter(text):
    """Minimal front matter parser: scalars and one-level '- item' lists."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    data, key = {}, None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") or line.startswith("- "):
            if key is None or not isinstance(data.get(key), list):
                return None
            data[key].append(line.split("- ", 1)[1].strip())
        elif ":" in line:
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            data[key] = val if val else []
        else:
            return None
    return data


def check_kb(kb_dir=KB_DIR):
    errors, ids = [], set()
    files = sorted(kb_dir.glob("*.md")) if kb_dir.is_dir() else []
    if not files:
        errors.append("kb: no articles")
    for path in files:
        fm = parse_front_matter(path.read_text(encoding="utf-8"))
        if fm is None:
            errors.append(f"kb/{path.name}: no front matter")
            continue
        for key in ("id", "title", "updated"):
            if not isinstance(fm.get(key), str) or not fm.get(key):
                errors.append(f"kb/{path.name}: missing {key}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(fm.get("updated", ""))):
            errors.append(f"kb/{path.name}: updated must be YYYY-MM-DD")
        sources = fm.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"kb/{path.name}: needs at least one source")
        else:
            for s in sources:
                if not URL_RE.match(s):
                    errors.append(f"kb/{path.name}: source {s!r} is not a URL")
        if fm.get("id") in ids:
            errors.append(f"kb/{path.name}: duplicate id {fm.get('id')}")
        ids.add(fm.get("id"))
    return errors


def check_dialog_tree(course):
    """Walk the dialog tree over every answer: every step is reachable from the start,
    and from every step every path can still reach the finish (no dead ends, no traps).
    A wrong quiz answer is a short loop back to the same question, so it is not an edge."""
    sections = course["course"]["sections"]
    order = [s["id"] for _, _, s in iter_steps(course)]
    steps = {s["id"]: s for _, _, s in iter_steps(course)}
    first_of = {sec["id"]: sec["lessons"][0]["steps"][0]["id"]
                for sec in sections if sec.get("lessons") and sec["lessons"][0].get("steps")}
    errors, edges = [], {}
    for i, sid in enumerate(order):
        s = steps[sid]
        follow = s.get("next") or (order[i + 1] if i + 1 < len(order) else "finish")
        if s["type"] == "branch":
            out = [c.get("next") for c in s.get("cases", [])] + [s.get("default")]
        elif s["type"] == "checkpoint":
            out = []
            resume = next((o.get("target") for o in s.get("options", []) if o.get("target")), None)
            for o in s.get("options", []):
                # pause has no target: after the break the user resumes where continue leads
                tgt = o.get("target") or resume
                out.append("finish" if tgt == "finish" else first_of.get(tgt, f"?{tgt}"))
        else:
            out = [follow]
        for o in out:
            if o != "finish" and o not in steps:
                errors.append(f"{sid}: leads to unknown step {o!r}")
        edges[sid] = [o for o in out if o == "finish" or o in steps]
    if not order:
        return ["course has no steps"]
    seen, stack = set(), [order[0]]
    while stack:
        n = stack.pop()
        if n in seen or n == "finish":
            continue
        seen.add(n)
        stack.extend(edges.get(n, []))
    errors += [f"{sid}: unreachable from the start" for sid in order if sid not in seen]
    rev = {}
    for a, outs in edges.items():
        for b in outs:
            rev.setdefault(b, []).append(a)
    ok, stack = set(), ["finish"]
    while stack:
        n = stack.pop()
        for a in rev.get(n, []):
            if a not in ok:
                ok.add(a)
                stack.append(a)
    errors += [f"{sid}: no path to the finish (dead end or trap)" for sid in order if sid not in ok]
    return errors


def check_situations(course):
    """P2b §2: situation ids unique in the course; option ids unique in a step over all its situations;
    3 options, one correct, non-empty texts and reactions; rubric_ref '-' or an existing rubric; a scored
    (eligible) check rests only on verified claims or normative with an accepted rubric."""
    errors, seen = [], {}
    rubrics = course["course"].get("rubrics", {})
    for _, _, step in iter_steps(course):
        if step["type"] != "quiz":
            if "situations" in step or "primary_scenario_id" in step:
                errors.append(f"{step['id']}: situations only on quiz steps")
            continue
        sits = step.get("situations") or []
        ids = [step.get("primary_scenario_id") or step["id"]] + [x.get("id") for x in sits]
        for i in ids:
            if i in seen:
                errors.append(f"{step['id']}: situation id {i} already used by {seen[i]}")
            seen[i] = step["id"]
        opt_ids = [o.get("id") for o in step.get("options", [])]
        for x in sits:
            where = f"{step['id']}/{x.get('id')}"
            opts = x.get("options", [])
            if not str(x.get("question", "")).strip():
                errors.append(f"{where}: empty question")
            if len(opts) != 3:
                errors.append(f"{where}: {len(opts)} options, need exactly 3")
            if sum(1 for o in opts if o.get("correct") is True) != 1:
                errors.append(f"{where}: need exactly one correct option")
            for o in opts:
                for key in ("id", "text", "reaction"):
                    if not str(o.get(key, "")).strip():
                        errors.append(f"{where}.{o.get('id')}: empty {key}")
            opt_ids += [o.get("id") for o in opts]
            ref = x.get("rubric_ref", "-")
            if ref != "-" and ref not in rubrics:
                errors.append(f"{where}: rubric_ref {ref} does not exist")
        if len(set(opt_ids)) != len(opt_ids):
            errors.append(f"{step['id']}: option ids repeat across its situations")
        built = [sc.get("id") for sc in step.get("scenarios", [])]
        if built and built != ids:
            errors.append(f"{step['id']}: scenarios {built} do not follow the situations {ids}")
    for _, _, step in iter_steps(course):
        if step["type"] in ("quiz", "exercise") and step.get("eligible"):
            ok_claims = step.get("basis") == "claims" and step.get("claims_status") == "verified"
            rub = rubrics.get(step.get("rubric_ref", "-")) or {}
            ok_norm = step.get("basis") == "normative" and rub.get("status") == "accepted"
            if not (ok_claims or ok_norm):
                errors.append(f"{step['id']}: eligible without verified claims or an accepted normative rubric")
    return errors


def balance_lint(course):
    """Warnings only (P2b §5, §8): position share outside [0.25; 0.42], runs of 3, correct = strictly
    the longest above 0.5. Implemented in scripts/quiz-balance.py."""
    path = SCRIPT_DIR / "quiz-balance.py"
    spec = importlib.util.spec_from_file_location("quiz_balance_lint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.lint(course["course"])


ALL_CHECKS = (check_structure, check_unique_ids, check_lesson_texts, check_competencies,
              check_explains, check_quizzes, check_exercises, check_checkpoints,
              check_references, check_beginner_language, check_dialog_tree)


# ---------- GREEN: the real course ----------

class TestRealCourse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = load_course()

    def assertClean(self, errors):
        self.assertEqual(errors, [], "\n" + "\n".join(errors))

    def test_json_loads(self):
        self.assertIn("course", self.course)

    def test_structure(self):
        self.assertClean(check_structure(self.course))

    def test_four_sections(self):
        self.assertEqual([s["id"] for s in self.course["course"]["sections"]], ["S1", "S2", "S3", "S4"])

    def test_unique_ids(self):
        self.assertClean(check_unique_ids(self.course))

    def test_lesson_texts_exist(self):
        self.assertClean(check_lesson_texts(self.course))

    def test_competency_ids(self):
        self.assertClean(check_competencies(self.course))

    def test_explain_has_example(self):
        self.assertClean(check_explains(self.course))

    def test_quiz_three_options_one_correct(self):
        self.assertClean(check_quizzes(self.course))

    def test_dialog_tree_every_path_reaches_finish(self):
        self.assertClean(check_dialog_tree(self.course))

    def test_exercises(self):
        self.assertClean(check_exercises(self.course))

    def test_sections_end_with_checkpoint(self):
        self.assertClean(check_checkpoints(self.course))

    def test_branch_and_next_targets_exist(self):
        self.assertClean(check_references(self.course))

    def test_beginner_language_u4(self):
        self.assertClean(check_beginner_language(self.course))

    def test_kb_front_matter(self):
        self.assertClean(check_kb())

    def test_situations(self):
        self.assertClean(check_situations(self.course))

    def test_balance_lint_warnings_only(self):
        warnings, numbers = balance_lint(self.course)
        # a warning, never a failure: printed for the reader with both denominators
        print(f"\n  balance lint: {len(warnings)} warnings; all situations {numbers['all']['n']} "
              f"{numbers['all']['counts']}, primaries {numbers['primaries']['n']} {numbers['primaries']['counts']}; "
              f"strictly longest {numbers['all']['longest']}, ties {numbers['all']['tie']}", file=sys.stderr)
        for w in warnings[:5]:
            print(f"  warning: {w}", file=sys.stderr)
        self.assertIsInstance(warnings, list)


# ---------- RED: each check catches its defect ----------

class TestChecksCatchDefects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = load_course()

    def mutate(self):
        return copy.deepcopy(self.base)

    def find(self, course, type_):
        return next(s for _, _, s in iter_steps(course) if s["type"] == type_)

    def test_dialog_tree_trap(self):
        c = self.mutate()
        b = self.find(c, "branch")
        b["default"] = b["id"]
        for case in b.get("cases", []):
            case["next"] = b["id"]
        self.assertTrue(check_dialog_tree(c))

    def test_dialog_tree_unreachable(self):
        c = self.mutate()
        steps = c["course"]["sections"][0]["lessons"][0]["steps"]
        steps[0]["next"] = "finish"
        self.assertTrue(check_dialog_tree(c))

    def test_duplicate_id(self):
        c = self.mutate()
        steps = c["course"]["sections"][0]["lessons"][0]["steps"]
        steps[1]["id"] = steps[0]["id"]
        self.assertTrue(check_unique_ids(c))

    def test_missing_lesson_file(self):
        c = self.mutate()
        c["course"]["sections"][0]["lessons"][0]["text"] = "lessons/no-such-file.md"
        self.assertTrue(check_lesson_texts(c))

    def test_quiz_two_options(self):
        c = self.mutate()
        self.find(c, "quiz")["options"].pop()
        self.assertTrue(check_quizzes(c))

    def test_quiz_two_correct(self):
        c = self.mutate()
        for o in self.find(c, "quiz")["options"]:
            o["correct"] = True
        self.assertTrue(check_quizzes(c))

    def test_quiz_empty_reaction(self):
        c = self.mutate()
        self.find(c, "quiz")["options"][0]["reaction"] = " "
        self.assertTrue(check_quizzes(c))

    def test_exercise_bad_method(self):
        c = self.mutate()
        self.find(c, "exercise")["check"]["method"] = "guess"
        self.assertTrue(check_exercises(c))

    def test_exercise_no_expected_result(self):
        c = self.mutate()
        del self.find(c, "exercise")["expected_result"]
        self.assertTrue(check_exercises(c))

    def test_section_without_checkpoint(self):
        c = self.mutate()
        c["course"]["sections"][1]["lessons"][-1]["steps"].pop()
        self.assertTrue(check_checkpoints(c))

    def test_wrong_continue_target(self):
        c = self.mutate()
        last = c["course"]["sections"][-1]["lessons"][-1]["steps"][-1]
        last["options"][0]["target"] = "S5"
        self.assertTrue(check_checkpoints(c))

    def test_branch_target_missing(self):
        c = self.mutate()
        self.find(c, "branch")["cases"][0]["next"] = "S9.L01.s01"
        self.assertTrue(check_references(c))

    def test_bad_competency(self):
        c = self.mutate()
        c["course"]["sections"][0]["lessons"][0]["competencies"] = ["1.3"]
        self.assertTrue(check_competencies(c))

    def test_explain_without_example(self):
        c = self.mutate()
        del self.find(c, "explain")["example"]
        self.assertTrue(check_explains(c))

    def test_u4_words_caught(self):
        for bad in ("Сохрани в repo", "сделай commit", "открой config.json", "это git", "Залей на GitHub",
                    "лежит в репозитории", "коммит готов", "открой progress.json"):
            c = self.mutate()
            self.find(c, "explain")["example"] = bad
            self.assertTrue(check_beginner_language(c, lessons_dir=Path("/nonexistent")), bad)

    def test_u4_plain_words_pass(self):
        c = self.mutate()
        self.find(c, "explain")["example"] = "Зайди в #Улучшения и подтверди — короткий репортаж"
        self.assertEqual(check_beginner_language(c, lessons_dir=Path("/nonexistent")), [])

    def situation_course(self):
        c = self.mutate()
        q = self.find(c, "quiz")
        q["situations"] = [{"id": q["id"] + ".b", "question": "q2", "rubric_ref": "-",
                            "options": [{"id": f"p{i}", "text": f"t{i}", "correct": i == 2, "reaction": "r"}
                                        for i in (1, 2, 3)]}]
        q["scenarios"] = [{"id": q["id"]}, {"id": q["id"] + ".b"}]
        return c, q

    def test_situations_good_fixture_passes(self):
        c, _ = self.situation_course()
        self.assertEqual(check_situations(c), [])

    def test_situation_option_id_reused(self):
        c, q = self.situation_course()
        q["situations"][0]["options"][0]["id"] = q["options"][0]["id"]
        self.assertTrue(check_situations(c))

    def test_situation_id_reused(self):
        c, q = self.situation_course()
        q["situations"][0]["id"] = q["id"]
        self.assertTrue(check_situations(c))

    def test_situation_two_correct_or_empty_reaction(self):
        c, q = self.situation_course()
        q["situations"][0]["options"][0]["correct"] = True
        self.assertTrue(check_situations(c))
        c, q = self.situation_course()
        q["situations"][0]["options"][1]["reaction"] = ""
        self.assertTrue(check_situations(c))

    def test_situation_unknown_rubric(self):
        c, q = self.situation_course()
        q["situations"][0]["rubric_ref"] = "R-none"
        self.assertTrue(check_situations(c))

    def test_eligible_without_accepted_rubric(self):
        c = self.mutate()
        q = self.find(c, "quiz")
        q.update(eligible=True, basis="unmapped")
        self.assertTrue(check_situations(c))

    def test_kb_front_matter_parser(self):
        self.assertIsNone(parse_front_matter("no front matter"))
        fm = parse_front_matter("---\nid: a\ntitle: B\nsources:\n  - https://x.example\nupdated: 2026-11-10\n---\nx")
        self.assertEqual(fm["sources"], ["https://x.example"])
        fm = parse_front_matter("---\nid: a\ntitle: B\nsources:\nupdated: 2026-11-10\n---\nx")
        self.assertEqual(fm["sources"], [])


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stderr)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
