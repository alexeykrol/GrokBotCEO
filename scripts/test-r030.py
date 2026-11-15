#!/usr/bin/env python3
"""
Tests for course release 0.3.0, student side (plan C1-C5; contract course/EVENT-SCHEMA.md, course-feedback-v1):
version stamped on new history entries (C3), answer and remark events, consent, flush to a local stub
receiver, export, doctor, migrate's changed_done line (C5), the static runtime line (C1).

Synthetic courses and progress files live in temporary folders; the only network is a local http.server
stub on 127.0.0.1 started by the tests. Stdlib only, no bots, nothing outside the temp folders is written
(last test). These tests check the script, not Mentor's behaviour (C1 level 2 is not_run here).
"""
import contextlib
import copy
import hashlib
import http.server
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
ROOT = RELEASE_DIR.parent
COURSE_FILE = RELEASE_DIR / "course" / "course.json"
RUNTIME_FILE = RELEASE_DIR / "course" / "MENTOR-RUNTIME.md"
PROGRESS = RELEASE_DIR / "course" / "progress.py"
B095 = "candidate/b095"
RC_RELEASE_ID = "course-0.3.0-rc4"      # the frozen RC this tree is (rc1 tag stays on its own commit)
INVITE = "Если что-то непонятно или кажется неверным — напиши, разберёмся. Пароли и ключи сюда не пиши."


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PG = _load("progress_r030_under_test", PROGRESS)
TMP_ROOTS = []


def tree_state(root: Path):
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


BEFORE = tree_state(RELEASE_DIR)

Q, QB, EX, E1, E4 = "S1.L01.s02", "S1.L01.s02.b", "S1.L01.s03", "S1.L01.s01", "S1.L01.s04"
KEY = {Q: "b", QB: "q"}


def course_doc(version, quiz_cv="cv-q1", changes=(), release_id=None):
    opts = lambda ids, key: [{"id": x, "text": "t-" + x, "correct": x == key, "reaction": "r-" + x} for x in ids]
    steps = [
        {"id": E1, "type": "explain", "text": "t", "example": "e", "content_version": "cv-e1"},
        {"id": Q, "type": "quiz", "question": "q1", "options": opts("abc", "b"), "content_version": quiz_cv,
         "eligible": True, "rubric_ref": "R1", "route": "main", "required": True,
         "scenarios": [{"id": Q, "option_ids": ["a", "b", "c"], "rubric_ref": "R1"},
                       {"id": QB, "option_ids": ["p", "q", "r"], "rubric_ref": "R1b"}],
         "situations": [{"id": QB, "question": "q2", "options": opts("pqr", "q"), "rubric_ref": "R1b"}]},
        {"id": EX, "type": "exercise", "task": "do", "expected_result": "x", "check": {"method": "user_confirm_form"},
         "content_version": "cv-x1", "eligible": False, "route": "main", "required": True},
        {"id": E4, "type": "explain", "text": "t4", "example": "e", "content_version": "cv-e4"},
    ]
    c = {"id": "c", "version": version, "language": "ru", "changes": list(changes),
         "rubrics": {"R1": {"status": "accepted"}, "R1b": {"status": "accepted"}},
         "sections": [{"id": "S1", "title": "Раздел", "lessons": [{"id": "S1.L01", "title": "Урок", "steps": steps}]}]}
    if release_id:
        c["release_id"] = release_id
    return {"course": c}


CHANGE_03 = {"from": "0.2.0", "version": "0.3.0", "added": [], "removed": [], "changed": [Q], "important": [],
             "note": "Правка."}


# ---------------------------------------------------------------- local receiver stub

class Stub:
    def __init__(self):
        self.modes = []                 # per course-event request: ok | 500 | drop | 403 | redirect
        self.requests = []              # (path, headers, body bytes)
        self.rows = {}                  # (install, id) -> canonical payload
        self.installs = {}              # token -> install_id
        self.reject = set()             # ids answered rejected/schema
        stub = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj=None, headers=()):
                data = json.dumps(obj).encode() if obj is not None else b""
                self.send_response(code)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                stub.requests.append((self.path, dict(self.headers), body))
                if self.path == "/v1/register":
                    iid, tok = str(uuid.uuid4()), uuid.uuid4().hex + uuid.uuid4().hex
                    stub.installs[tok] = iid
                    return self._send(201, {"install_id": iid, "send_token": tok, "ref_code": "X", "ref_accepted": False})
                if self.path != "/v1/course-event":
                    return self._send(404, {"error": "not_found"})
                mode = stub.modes.pop(0) if stub.modes else "ok"
                if mode == "500":
                    return self._send(500, {"error": "internal"})
                if mode == "403":
                    return self._send(403, {"error": "forbidden"})
                if mode == "redirect":
                    return self._send(307, {}, [("Location", "/v1/elsewhere")])
                auth = self.headers.get("Authorization", "")
                tok = auth[7:] if auth.startswith("Bearer ") else None
                env = json.loads(body.decode("utf-8"))
                if stub.installs.get(tok) != env.get("install_id"):
                    return self._send(403, {"error": "install_mismatch"})
                out = {"accepted": [], "duplicate": [], "rejected": []}
                for e in env["events"]:
                    k, canon = (env["install_id"], e["id"]), json.dumps(e, sort_keys=True, ensure_ascii=False)
                    if e["id"] in stub.reject:
                        out["rejected"].append({"id": e["id"], "reason": "schema"})
                    elif k in stub.rows:
                        if stub.rows[k] == canon:
                            out["duplicate"].append(e["id"])
                        else:
                            out["rejected"].append({"id": e["id"], "reason": "conflict"})
                    else:
                        stub.rows[k] = canon
                        out["accepted"].append(e["id"])
                if mode == "drop":                            # committed, answer lost
                    self.close_connection = True
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                return self._send(200, out)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def course_event_calls(self):
        return [r for r in self.requests if r[0] == "/v1/course-event"]


def closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


class Crash(BaseException):
    pass


# ---------------------------------------------------------------- base

class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="r030-"))
        TMP_ROOTS.append(self.dir)
        self.home = self.dir / "mentor"
        self.course = self.dir / "course.json"
        self.set_course(course_doc("0.2.0"))
        self.env = {k: v for k, v in os.environ.items() if k != "GROKBOT_FEEDBACK_URL"}
        self.stub = None
        PG.HOOKS.clear()

    def tearDown(self):
        PG.HOOKS.clear()
        if self.stub:
            self.stub.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def set_course(self, doc):
        self.course.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    def serve(self):
        self.stub = Stub()
        self.env["GROKBOT_FEEDBACK_URL"] = self.stub.url
        return self.stub

    def run_pg(self, *args, stdin=None, auto_endpoint=True):
        if auto_endpoint and args and args[0] == "flush" and "--endpoint" not in args:
            base = PG.normalise_endpoint(self.env["GROKBOT_FEEDBACK_URL"])[0] if self.env.get("GROKBOT_FEEDBACK_URL") else None
            if base:                                       # the Mentor copies where.feedback.endpoint verbatim
                args = (*args, "--endpoint", base)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin or "")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = PG.main(["--kb-home", str(self.home), "--course", str(self.course), *args])
        return code, out.getvalue(), err.getvalue()

    def ok(self, *args, stdin=None):
        code, out, err = self.run_pg(*args, stdin=stdin)
        self.assertEqual(code, 0, err)
        return json.loads(out) if out.strip().startswith("{") else out

    def fail(self, *args, stdin=None):
        code, out, err = self.run_pg(*args, stdin=stdin)
        self.assertEqual(code, 2, out)
        self.assertIn("progress: ERROR", err)
        return err

    # course driving
    def to_quiz(self):
        self.ok("migrate")
        w = self.ok("where")
        if w["step"] == E1:
            self.ok("advance", "--revision", str(w["revision"]))
        return self.ok("open", Q)

    def answer(self, o, option, extra=()):
        lab = next(d["label"] for d in o["display"] if d["option_id"] == option)
        args = ["record", "--token", o["token"], "--attempt", str(o["next_attempt"]), "--label", lab, "--option", option]
        if o["scoring"]:
            if option == KEY[o["scenario_id"]]:
                args += ["--rubric", "correct", "--evidence", "own_answer"]
            else:
                args += ["--rubric", "incorrect"]
        return self.ok(*args, *extra)

    def remark(self, **kw):
        d = {"source_msg": None, "kind": "unclear", "text": "Непонятно", "scope": "step", "step": Q,
             "scenario_id": None, "parent_id": None}
        d.update(kw)
        return self.ok("remark", stdin=json.dumps(d, ensure_ascii=False))

    def export(self):
        code, out, err = self.run_pg("export-feedback")
        self.assertEqual(code, 0, err)
        return [json.loads(x) for x in out.splitlines()]

    def events(self):
        return PG.read_jsonl(self.home / "events.jsonl")[0]

    def progress(self):
        return json.loads((self.home / "progress.json").read_text(encoding="utf-8"))

    def outbox(self):
        return json.loads((self.home / "outbox-state.json").read_text(encoding="utf-8"))

    def identity(self):
        return json.loads((self.home / "identity.json").read_text(encoding="utf-8"))

    def consent(self):
        return self.ok("consent", "--decision", "granted", "--recipient", "127.0.0.1")

    def sent_ids(self):
        return [e["id"] for r in self.stub.course_event_calls() for e in json.loads(r[2])["events"]]


# ---------------------------------------------------------------- C2: remark identity and data

class TestRemark(Base):
    def test_same_source_msg_two_calls_two_events(self):
        self.ok("migrate")
        a = self.remark(source_msg="m1")
        b = self.remark(source_msg="m1")
        self.assertTrue(a["written"] and b["written"])
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual([e["source_msg"] for e in self.events()], ["m1", "m1"])

    def test_same_text_two_calls_two_events(self):
        self.ok("migrate")
        a, b = self.remark(), self.remark()
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual(len(self.events()), 2)

    def test_retry_with_event_id_after_minute_change_and_restart_one_event(self):
        self.ok("migrate")
        with mock.patch.object(PG, "now", lambda: "2026-11-14T10:00:00Z"):
            a = self.remark(source_msg="m7")
        with mock.patch.object(PG, "now", lambda: "2026-11-14T10:01:00Z"):
            b = self.remark(source_msg="m7", event_id=a["id"])
        d = {"source_msg": "m7", "kind": "unclear", "text": "Непонятно", "scope": "step", "step": Q,
             "scenario_id": None, "parent_id": None, "event_id": a["id"]}
        r = subprocess.run([sys.executable, "-B", str(PROGRESS), "--kb-home", str(self.home), "--course",
                            str(self.course), "remark"], input=json.dumps(d), capture_output=True, text=True,
                           env=dict(self.env, PYTHONDONTWRITEBYTECODE="1"))      # restart: a new process
        self.assertEqual(r.returncode, 0, r.stderr)
        c = json.loads(r.stdout)
        self.assertEqual((b["id"], c["id"]), (a["id"], a["id"]))
        self.assertEqual((a["written"], b["written"], c["written"]), (True, False, False))
        self.assertEqual(len(self.events()), 1)

    def test_retry_with_event_id_different_payload_conflict(self):
        self.ok("migrate")
        a = self.remark()
        before = (self.home / "events.jsonl").read_bytes()
        err = self.fail("remark", stdin=json.dumps({"kind": "unclear", "text": "другой текст", "scope": "step",
                                                    "step": Q, "event_id": a["id"]}))
        self.assertIn("conflict", err)
        self.fail("remark", stdin=json.dumps({"kind": "unclear", "text": "x", "scope": "course",
                                              "event_id": "f" * 32}))
        self.assertEqual((self.home / "events.jsonl").read_bytes(), before)

    def test_quotes_newlines_shell_text_are_data(self):
        self.ok("migrate")
        text = 'Он сказал "нет"; it\'s $(rm -rf ~) `id` \\n\nвторая строка\tтаб'
        self.remark(text=text, kind="wrong")
        ev = self.events()[0]
        self.assertEqual(ev["text"], text.strip())
        self.assertEqual(ev["kind"], "wrong")
        self.assertTrue((self.home / "events.jsonl").read_bytes().count(b"\n") == 1)

    def test_remark_does_not_change_progress_json_bytes(self):
        o = self.to_quiz()
        self.answer(o, "a", ["--message-id", "u1"])            # an attempt, open stays (wrong answer)
        before = (self.home / "progress.json").read_bytes()
        r = self.remark(source_msg="m1", scenario_id=o["scenario_id"])
        self.remark(kind="other", text="ещё", parent_id=r["id"])
        self.remark(scope="course", step=None, text="весь курс скучный")
        self.assertEqual((self.home / "progress.json").read_bytes(), before)
        p = self.progress()
        self.assertEqual(p["open"]["token"], o["token"])
        self.assertEqual(p["consumed_messages"], ["u1"])

    def test_remark_validation(self):
        self.ok("migrate")
        self.fail("remark", stdin="not json")
        self.fail("remark", stdin=json.dumps({"kind": "unclear", "text": "x", "scope": "step", "step": None}))
        self.fail("remark", stdin=json.dumps({"kind": "bad", "text": "x", "scope": "course"}))
        self.fail("remark", stdin=json.dumps({"kind": "other", "text": "x", "scope": "course", "extra": 1}))
        self.fail("remark", stdin=json.dumps({"kind": "other", "text": "x", "scope": "course", "parent_id": "0" * 32}))
        self.fail("remark", stdin=json.dumps({"kind": "other", "text": "я" * 1001, "scope": "course"}))
        self.fail("remark", stdin=json.dumps({"kind": "other", "text": "x", "scope": "step", "step": "S9.L99.s99"}))
        self.assertEqual(self.events(), [])

    def test_remark_event_fields_follow_contract(self):
        self.set_course(course_doc("0.2.0", release_id="course-test-rc"))
        self.ok("migrate")
        self.remark(source_msg="m1")
        ev = self.events()[0]
        self.assertEqual(set(ev), {"id", "type", "course_version", "release_id", "version_origin", "at", "source_msg",
                                   "scope", "step", "scenario_id", "kind", "text", "parent_id"})
        self.assertEqual((ev["course_version"], ev["release_id"], ev["version_origin"]),
                         ("0.2.0", "course-test-rc", "recorded"))
        cid = self.identity()["collector_id"]
        self.assertTrue(PG.HEX32.fullmatch(ev["id"]))
        self.assertNotEqual(ev["id"], hashlib.sha256(f"{cid}|remark:m1|remark".encode()).hexdigest()[:32])


class TestMasking(unittest.TestCase):
    # Fake secrets are split into parts so the public tree never contains a secret-shaped literal
    # (leak gate, INVARIANTS R3); the joined strings are what the masking code sees.
    CASES = {
        "provider sk-": "мой ключ sk" + "-proj-abcDEF1234567890xyz",
        "provider xai-": "xai" + "-AbCdEf1234567890QwErTy",
        "github ghp_": "gh" + "p_ABCDEFGHIJKLMNOPQRSTUVWX1234",
        "github_pat_": "github" + "_pat_11ABCDEFG0123456789_abcdefghij",
        "aws AKIA": "AK" + "IAIOSFODNN7EXAMPLE",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "hex>=32": "da39a3ee5e6b4b0d3255bfef95601890afd80709",
        "base64>=32": "QWxhZGRpbjpvcGVuIHNlc2FtZQQWxhZGRpbjpvcGVuIHNlc2FtZQ==",
        "email": "ivan.petrov+bot@example.com",
        "phone formatted": "+7 (912) 345-67-89",
        "phone plain": "89123456789",
    }

    def test_each_known_format_masked(self):
        for name, secret in self.CASES.items():
            with self.subTest(name):
                got = PG.mask_text(f"вот: {secret} конец")
                self.assertNotIn(secret, got)
                self.assertIn(PG.MASK, got)
                self.assertTrue(got.startswith("вот: ") and got.endswith(" конец"), got)

    def test_ordinary_text_kept(self):
        for t in ("Шаг S1.L01.s02 непонятен", "2026-11-14 в 10:00", "код 12345", "вариант b"):
            self.assertEqual(PG.mask_text(t), t)

    def test_declared_limitation_unrecognised_secret_passes(self):
        # Documented limitation (EVENT-SCHEMA §4): a plain password is not a known format and is NOT masked.
        t = "пароль от бота Qwerty!2024"
        self.assertEqual(PG.mask_text(t), t)


# ---------------------------------------------------------------- C3 + answer events

class TestAnswerEvents(Base):
    def test_record_stamps_version_and_writes_one_event(self):
        self.set_course(course_doc("0.2.0", release_id="rc-x"))
        o = self.to_quiz()
        out = self.answer(o, "b")
        self.assertEqual(out["status"], "confirmed")
        h = self.progress()["checks"][Q]["history"][-1]
        self.assertEqual((h["course_version"], h["release_id"]), ("0.2.0", "rc-x"))
        self.assertEqual(h["shown_order"], [d["option_id"] for d in o["display"]])
        uuid.UUID(h["attempt_uid"])
        evs = self.events()
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual(set(ev), {"id", "type", "course_version", "release_id", "version_origin", "at", "step",
                                   "scenario_id", "option_ids", "shown_order", "status", "attempt", "revealed",
                                   "evidence_class"})
        cid = self.identity()["collector_id"]
        self.assertEqual(ev["id"], hashlib.sha256(f"{cid}|answer-uid:{h['attempt_uid']}|answer".encode()).hexdigest()[:32])
        self.assertEqual((ev["option_ids"], ev["status"], ev["attempt"], ev["at"], ev["evidence_class"]),
                         (["b"], "confirmed", 1, h["at"], None))
        for k in ("install_id", "send_token", "collector_id"):
            self.assertNotIn(k, ev)

    def test_exercise_and_skip_events(self):
        o = self.to_quiz()
        self.answer(o, "b")
        oe = self.ok("open", EX)
        self.ok("record", "--token", oe["token"], "--said-done")
        evs = self.events()
        self.assertEqual([e["step"] for e in evs], [Q, EX])
        self.assertEqual((evs[1]["option_ids"], evs[1]["shown_order"], evs[1]["status"]), ([], None, "said_done"))

    def test_primary_and_b_attempt1_have_different_ids(self):
        o = self.to_quiz()
        for _ in range(3):
            o2 = self.answer(o, "a")
            o["next_attempt"] = o2.get("next_attempt")
        self.assertTrue(o2["revealed"])
        w = self.ok("where")
        self.ok("lesson", "S1.L01", "--revision", str(w["revision"]))
        w = self.ok("where")
        self.ok("advance", "--revision", str(w["revision"]))
        ob = self.ok("open", Q)
        self.assertEqual((ob["scenario_id"], ob["next_attempt"]), (QB, 1))
        self.answer(ob, "q")
        evs = self.events()
        first = [e for e in evs if e["attempt"] == 1]
        self.assertEqual({e["scenario_id"] for e in first}, {Q, QB})
        self.assertEqual(len({e["id"] for e in first}), 2)
        self.assertEqual(len({e["id"] for e in evs}), len(evs))

    def test_two_versions_attempt1_different_ids_and_version_kept(self):
        o = self.to_quiz()
        self.answer(o, "b")
        self.set_course(course_doc("0.3.0", quiz_cv="cv-q2", changes=[CHANGE_03]))
        m = self.ok("migrate", "--json")
        self.assertTrue(m["version_changed"])
        self.assertEqual((m["changed_done"], m["changed_done_steps"]), (1, [Q]))
        w = self.ok("where")
        self.ok("lesson", "S1.L01", "--revision", str(w["revision"]))
        w = self.ok("where")
        self.ok("advance", "--revision", str(w["revision"]))
        o2 = self.ok("open", Q)
        self.assertEqual(o2["next_attempt"], 1)
        self.answer(o2, "b")
        evs = self.events()
        self.assertEqual([(e["attempt"], e["course_version"]) for e in evs], [(1, "0.2.0"), (1, "0.3.0")])
        self.assertNotEqual(evs[0]["id"], evs[1]["id"])
        # a later migration does not change a recorded version (event lines and history are immutable)
        self.set_course(course_doc("0.4.0", quiz_cv="cv-q3",
                                   changes=[CHANGE_03, dict(CHANGE_03, **{"from": "0.3.0", "version": "0.4.0"})]))
        self.ok("migrate")
        hist = self.progress()["checks"][Q]["history"]
        self.assertEqual([h["course_version"] for h in hist], ["0.2.0", "0.3.0"])
        exp = self.export()
        self.assertEqual([(e["course_version"], e["version_origin"]) for e in exp],
                         [("0.2.0", "recorded"), ("0.3.0", "recorded")])

    def test_old_entry_on_02_migrate_03_export_reconstructed_never_sent(self):
        o = self.to_quiz()
        self.answer(o, "a")
        # make it a pre-0.3.0 entry: no version, no uid, no event line
        p = self.progress()
        h = p["checks"][Q]["history"][0]
        for k in ("course_version", "release_id", "shown_order", "attempt_uid"):
            h.pop(k)
        h["at"] = "2026-11-01T10:00:00Z"
        (self.home / "progress.json").write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (self.home / "events.jsonl").unlink()
        old = copy.deepcopy(h)
        self.set_course(course_doc("0.3.0", quiz_cv="cv-q2", changes=[CHANGE_03]))
        self.ok("migrate")
        self.assertEqual(self.progress()["checks"][Q]["history"][0], old)        # old history not rewritten
        self.assertEqual(self.events(), [])                                       # never written as sendable
        exp = self.export()
        self.assertEqual(len(exp), 1)
        self.assertEqual((exp[0]["course_version"], exp[0]["version_origin"], exp[0]["export_only"]),
                         ("0.2.0", "reconstructed", True))

    def test_reconstruct_rules(self):
        p = {"migrations": [{"id": "m1", "from": "0.1.0", "to": "0.2.0", "at": "2026-11-10T00:00:00Z"},
                            {"id": "m2", "from": "0.2.0", "to": "0.3.0", "at": "2026-11-12T00:00:00Z"}]}
        self.assertEqual(PG.reconstruct_version(p, "2026-11-09T00:00:00Z"), ("0.1.0", "reconstructed"))
        self.assertEqual(PG.reconstruct_version(p, "2026-11-11T00:00:00Z"), ("0.2.0", "reconstructed"))
        self.assertEqual(PG.reconstruct_version(p, "2026-11-13T00:00:00Z"), (None, "unknown"))
        self.assertEqual(PG.reconstruct_version(p, "2026-11-12T00:00:00Z"), (None, "unknown"))
        self.assertEqual(PG.reconstruct_version(p, None), (None, "unknown"))
        self.assertEqual(PG.reconstruct_version({"migrations": []}, "2026-11-09T00:00:00Z"), (None, "unknown"))

    def test_old_history_untouched_by_new_record(self):
        o = self.to_quiz()
        self.answer(o, "a")
        p = self.progress()
        h = p["checks"][Q]["history"][0]
        for k in ("course_version", "release_id", "shown_order", "attempt_uid"):
            h.pop(k)
        (self.home / "progress.json").write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        old = copy.deepcopy(h)
        o = self.ok("open", Q)
        self.answer(o, "b")
        hist = self.progress()["checks"][Q]["history"]
        self.assertEqual(hist[0], old)
        self.assertIn("attempt_uid", hist[1])

    def test_crash_between_commit_and_append_rebuilt_once(self):
        o = self.to_quiz()

        def boom():
            raise Crash()
        PG.HOOKS["before_event_append"] = boom
        with self.assertRaises(Crash):
            self.answer(o, "b")
        PG.HOOKS.clear()
        self.assertEqual(self.progress()["checks"][Q]["history"][-1]["status"], "confirmed")
        self.assertEqual(self.events(), [])
        d1 = self.ok("doctor")
        d2 = self.ok("doctor")
        self.ok("flush")
        self.assertEqual((d1["rebuilt"], d2["rebuilt"]), (1, 0))
        self.assertEqual(len(self.events()), 1)

    def test_rebuilt_event_identical_payload(self):
        o = self.to_quiz()
        self.answer(o, "a")
        original = self.events()[0]
        (self.home / "events.jsonl").write_bytes(b"")
        with mock.patch.object(PG, "now", lambda: "2030-01-01T00:00:00Z"):
            self.assertEqual(self.ok("doctor")["rebuilt"], 1)
        self.assertEqual(json.dumps(self.events()[0], sort_keys=True), json.dumps(original, sort_keys=True))

    def test_failed_record_no_event(self):
        o = self.to_quiz()
        self.fail("record", "--token", "bad", "--attempt", "1", "--label", "a", "--option", "a",
                  "--rubric", "incorrect")
        self.fail("record", "--token", o["token"], "--attempt", "1", "--label", "a", "--option", "b",
                  "--rubric", "incorrect")
        self.ok("doctor")
        self.assertEqual(self.events(), [])

    def test_rerun_does_not_regrade_or_reconsume(self):
        o = self.to_quiz()
        self.answer(o, "a", ["--message-id", "u1"])
        before = self.progress()
        lab = next(d["label"] for d in o["display"] if d["option_id"] == "a")
        self.fail("record", "--token", o["token"], "--attempt", "2", "--label", lab, "--option", "a",
                  "--rubric", "incorrect", "--message-id", "u1")
        self.ok("doctor")
        self.assertEqual(self.progress()["checks"][Q]["history"], before["checks"][Q]["history"])
        self.assertEqual(self.progress()["consumed_messages"], ["u1"])
        self.assertEqual(len(self.events()), 1)


# ---------------------------------------------------------------- C4: consent and flush

class TestFlush(Base):
    def test_no_consent_no_request(self):
        stub = self.serve()
        o = self.to_quiz()
        self.answer(o, "b")
        self.remark()
        r = self.ok("flush")
        self.assertEqual(r["action"], "no_consent")
        self.assertEqual(stub.requests, [])

    def test_no_endpoint_noop(self):
        self.consent()
        o = self.to_quiz()
        self.answer(o, "b")
        self.assertEqual(self.ok("flush")["action"], "no_endpoint")

    def test_events_before_consent_then_register_then_same_ids_sent(self):
        stub = self.serve()
        o = self.to_quiz()
        self.answer(o, "a")
        self.remark(source_msg="m1")
        ids = [e["id"] for e in self.events()]
        self.consent()                                       # local: no request
        self.assertEqual(stub.requests, [])
        self.assertEqual(self.ok("flush")["status"], "registered")      # one request
        self.assertEqual([r[0] for r in stub.requests], ["/v1/register"])
        ident = self.identity()
        self.assertTrue(ident["install_id"] and ident["send_token"])
        self.assertEqual(json.loads((self.home / "identity.json.bak").read_text()), ident)
        r = self.ok("flush")
        self.assertEqual((r["accepted"], r["pending"]), (2, 0))
        self.assertEqual(self.sent_ids(), ids)
        call = stub.course_event_calls()[0]
        self.assertEqual(call[1]["Authorization"], "Bearer " + ident["send_token"])
        body = json.loads(call[2])
        self.assertEqual(set(body), {"install_id", "events"})
        for e in body["events"]:
            for k in ("install_id", "send_token", "collector_id"):
                self.assertNotIn(k, e)
        self.assertEqual(set(self.outbox()["delivered"]), set(ids))
        self.assertEqual(self.ok("flush")["action"], "nothing_pending")

    def test_revoked_nothing_sent_including_old_queue(self):
        stub = self.serve()
        self.consent()
        o = self.to_quiz()
        self.answer(o, "b")
        self.ok("flush")                                      # registers
        self.assertEqual(self.ok("flush")["status"], "delivered")
        n = len(stub.course_event_calls())
        self.ok("consent", "--decision", "revoked", "--recipient", "127.0.0.1")
        self.remark()
        self.ok("flush")
        oe = self.ok("open", EX)
        self.ok("record", "--token", oe["token"], "--said-done")
        self.assertEqual(len(stub.course_event_calls()), n)
        self.assertEqual(self.ok("flush")["action"], "no_consent")

    def test_api_failure_keeps_pending_then_explicit_retry(self):
        stub = self.serve()
        self.consent()
        self.ok("flush")                                      # registers
        o = self.to_quiz()
        self.assertEqual(self.answer(o, "b")["status"], "confirmed")
        stub.modes = ["500"]
        r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"], r["http_status"], r["pending"]), ("pending", "http", 500, 1))
        eid = self.events()[0]["id"]
        self.assertEqual(len(stub.course_event_calls()), 1)
        self.assertFalse((self.home / "outbox-state.json").exists())
        r = self.ok("flush")                                  # a later explicit flush
        self.assertEqual((r["accepted"], r["pending"]), (1, 0))
        self.assertIn(eid, self.outbox()["delivered"])

    def test_network_failure_keeps_grade_event_pending(self):
        self.env["GROKBOT_FEEDBACK_URL"] = closed_port_url()
        self.consent()
        o = self.to_quiz()
        code, out, err = self.run_pg("record", "--token", o["token"], "--attempt", "1",
                                     "--label", next(d["label"] for d in o["display"] if d["option_id"] == "b"),
                                     "--option", "b", "--rubric", "correct", "--evidence", "own_answer")
        self.assertEqual((code, err), (0, ""))
        out = json.loads(out)
        self.assertEqual((out["status"], out["current"]), ("confirmed", EX))
        before = self.progress()
        r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"]), ("pending", "transport"))
        self.assertEqual(self.progress(), before)
        self.assertEqual(self.progress()["nav"]["cursor"], EX)
        self.assertEqual(len(self.events()), 1)
        self.assertFalse((self.home / "outbox-state.json").exists())

    def test_lost_response_then_duplicate(self):
        stub = self.serve()
        self.consent()
        self.ok("flush")                                      # registers
        o = self.to_quiz()
        self.answer(o, "b")
        stub.modes = ["drop"]
        self.assertEqual(self.ok("flush")["status"], "pending")
        eid = self.events()[0]["id"]
        self.assertNotIn(eid, self.outbox().get("delivered", {}) if (self.home / "outbox-state.json").exists() else {})
        r = self.ok("flush")
        self.assertEqual((r["duplicate"], r["accepted"]), (1, 0))
        self.assertEqual(self.outbox()["delivered"][eid]["result"], "duplicate")
        self.assertEqual(len(stub.rows), 1)

    def test_corrupted_cache_resends_same_ids_same_identity(self):
        stub = self.serve()
        self.consent()
        o = self.to_quiz()
        self.answer(o, "b")
        self.ok("flush")                                      # registers
        self.assertEqual(self.ok("flush")["accepted"], 1)
        ident = self.identity()
        (self.home / "outbox-state.json").write_text("{garbage", encoding="utf-8")
        r = self.ok("flush")
        self.assertEqual(r["duplicate"], 1)
        self.assertEqual(self.identity(), ident)
        self.assertEqual([r[0] for r in stub.requests].count("/v1/register"), 1)
        self.assertEqual(len(set(self.sent_ids())), 1)

    def test_identity_lost_no_registration_flush_noop_doctor_reports(self):
        stub = self.serve()
        self.consent()
        o = self.to_quiz()
        self.answer(o, "a")
        (self.home / "identity.json").unlink()
        (self.home / "identity.json.bak").unlink()
        n = len(stub.requests)
        self.assertEqual(self.ok("flush")["action"], "identity_lost")
        o = self.ok("where")["open"]
        out = self.answer(o, "b")                            # grading unaffected
        self.assertEqual(out["status"], "confirmed")
        self.assertEqual(len(stub.requests), n)
        self.assertFalse((self.home / "identity.json").exists())
        self.assertEqual(self.ok("doctor")["identity"], "identity_lost")
        self.fail("remark", stdin=json.dumps({"kind": "other", "text": "x", "scope": "course"}))

    def _pre_r030(self):
        """A schema-2 progress with history written before r030 and no r030 file."""
        o = self.to_quiz()
        self.answer(o, "a")
        p = self.progress()
        for h in p["checks"][Q]["history"]:
            for k in ("course_version", "release_id", "shown_order", "attempt_uid"):
                h.pop(k)
        (self.home / "progress.json").write_text(json.dumps(p, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for f in ("events.jsonl", "identity.json", "identity.json.bak", "outbox-state.json", "consent.jsonl"):
            (self.home / f).unlink(missing_ok=True)
        return self.ok("where")["open"]

    def test_bootstrap_pre_r030_history_initialises_identity(self):
        o = self._pre_r030()
        self.assertEqual(self.answer(o, "b")["status"], "confirmed")
        self.assertTrue(PG.HEX32.fullmatch(self.identity()["collector_id"]))
        self.assertEqual(len(self.events()), 1)                     # the new attempt only; old one never sent
        self.assertEqual(self.ok("doctor")["identity"], "ok")

    def test_bootstrap_events_present_identity_missing_is_lost(self):
        stub = self.serve()
        o = self._pre_r030()
        (self.home / "events.jsonl").write_text(json.dumps({"id": "a" * 32, "type": "remark"}) + "\n")
        self.assertEqual(self.answer(o, "b")["status"], "confirmed")     # grading OK
        self.assertFalse((self.home / "identity.json").exists())
        self.assertEqual(self.ok("flush")["action"], "identity_lost")
        self.assertEqual(self.ok("doctor")["identity"], "identity_lost")
        self.assertEqual(stub.requests, [])
        self.assertFalse((self.home / "identity.json").exists())

    def test_restore_bak_same_installation_continues(self):
        stub = self.serve()
        self.consent()
        o = self.to_quiz()
        self.answer(o, "a")
        self.ok("flush")                                      # registers
        self.ok("flush")
        ident = self.identity()
        (self.home / "identity.json").unlink()
        self.assertEqual(self.ok("doctor")["identity"], "ok")
        self.assertEqual(self.identity(), ident)
        self.answer(self.ok("where")["open"], "b")
        self.assertEqual(self.ok("flush")["accepted"], 1)
        self.assertEqual([r[0] for r in stub.requests].count("/v1/register"), 1)
        bodies = [json.loads(r[2]) for r in stub.course_event_calls()]
        self.assertTrue(bodies and all(b["install_id"] == ident["install_id"] for b in bodies))
        self.assertEqual(len(self.outbox()["delivered"]), 2)

    def test_http_refused_for_non_localhost(self):
        self.env["GROKBOT_FEEDBACK_URL"] = "http://feedback.example.com"
        calls = []
        PG.HOOKS["before_network"] = lambda: calls.append(1)
        self.ok("consent", "--decision", "granted", "--recipient", "feedback.example.com")
        r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"], r["action"]), ("skipped", "endpoint_refused", "refused"))
        self.assertEqual(calls, [])
        for url, ok in (("https://h.example/x/", True), ("http://localhost:9", True), ("http://10.0.0.1", False),
                        ("ftp://h.example", False), ("https://u:" + "p@h.example", False), ("https://h.example?a=1", False)):
            with mock.patch.dict(os.environ, {"GROKBOT_FEEDBACK_URL": url}):
                base, host, refused = PG.endpoint_of(type("C", (), {"path": self.course})())
                self.assertEqual(base is not None, ok, url)

    def test_403_and_redirect_keep_pending_one_request(self):
        stub = self.serve()
        self.consent()
        self.ok("migrate")
        self.ok("flush")                                         # registers
        a = self.remark()
        for mode in ("403", "redirect"):
            stub.modes = [mode]
            n = len(stub.requests)
            r = self.ok("flush")
            self.assertIn("error", r)
            self.assertEqual(len(stub.requests), n + 1)             # one request, the redirect not followed
            self.assertNotIn("/v1/elsewhere", [x[0] for x in stub.requests])
        self.assertFalse((self.home / "outbox-state.json").exists())
        self.assertEqual(self.ok("flush")["accepted"], 1)
        self.assertIn(a["id"], self.outbox()["delivered"])

    def test_rejected_and_conflict_recorded_never_resent(self):
        stub = self.serve()
        self.consent()
        self.ok("migrate")
        self.ok("flush")                                         # registers
        a = self.remark(text="первое")
        b = self.remark(text="второе")
        stub.reject.add(a["id"])
        r = self.ok("flush")
        self.assertEqual((r["accepted"], r["rejected"]), (1, 1))
        self.assertEqual(self.outbox()["rejected"][a["id"]]["reason"], "schema")
        self.assertIn(b["id"], self.outbox()["delivered"])
        c = self.remark(text="третье")
        stub.rows[(self.identity()["install_id"], c["id"])] = "other payload"     # same key, other payload
        n = len(stub.course_event_calls())
        self.assertEqual(self.ok("flush")["rejected"], 1)
        self.assertEqual(self.outbox()["rejected"][c["id"]]["reason"], "conflict")
        self.assertNotIn(c["id"], self.outbox()["delivered"])
        self.assertEqual(self.ok("flush")["action"], "nothing_pending")
        self.assertEqual(len(stub.course_event_calls()), n + 1)

    def _foreign_lock(self):
        (self.home / ".progress.lock").write_text(json.dumps({"owner_token": "other"}))

    def test_busy_lock_after_network_waits_and_saves(self):
        stub = self.serve()
        self.consent()
        self.ok("migrate")
        self.ok("flush")                                         # registers
        a = self.remark()

        def hold():
            self._foreign_lock()
            threading.Timer(0.4, lambda: (self.home / ".progress.lock").unlink()).start()
        PG.HOOKS["after_network"] = hold
        r = self.ok("flush")
        self.assertEqual(r["accepted"], 1)
        self.assertIn(a["id"], self.outbox()["delivered"])

    def test_busy_lock_timeout_drops_answer_then_recovers(self):
        stub = self.serve()
        self.ok("migrate")
        self.remark()
        self.consent()
        PG.HOOKS["after_network"] = self._foreign_lock
        with mock.patch.object(PG, "LOCK_WAIT", 0.2):
            code, out, err = self.run_pg("flush")
        self.assertEqual((code, json.loads(out)["status"], json.loads(out)["reason"]), (0, "pending", "busy"))
        self.assertIn("not saved", err)                                         # the register answer is dropped
        self.assertIsNone(self.identity()["install_id"])
        PG.HOOKS.clear()
        (self.home / ".progress.lock").unlink()
        self.assertEqual(self.ok("flush")["action"], "registered")  # registers again, no identity_lost
        self.assertEqual([x[0] for x in stub.requests].count("/v1/register"), 2)
        self.assertEqual(self.ok("flush")["accepted"], 1)

    def test_50_cyrillic_remarks_batches_under_cap(self):
        stub = self.serve()
        self.ok("migrate")
        for i in range(50):
            self.remark(source_msg=f"m{i}", text="ж" * 1000)
        self.ok("migrate")
        self.ok("consent", "--decision", "granted", "--recipient", "127.0.0.1")
        self.assertEqual(self.ok("flush")["status"], "registered")
        for _ in range(5):
            self.ok("flush")
        calls = stub.course_event_calls()
        self.assertGreaterEqual(len(calls), 2)                 # 50 x ~2 KB + envelope does not fit one body
        for c in calls:
            self.assertLessEqual(len(c[2]), 131072)
            self.assertLessEqual(len(json.loads(c[2])["events"]), 50)
            self.assertIn("ж".encode("utf-8"), c[2])         # UTF-8, not \\u escapes
        self.assertEqual(len(set(self.sent_ids())), 50)
        self.assertEqual(len(self.outbox()["delivered"]), 50)


# ---------------------------------------------------------------- explicit flush only (Codex 0d965747, Grok 3cc27fd4)

class NoNetwork:
    """Every local command runs under this: a request child (the only way progress.py reaches the network)
    fails the test at once; the stub must also see no request."""

    def __enter__(self):
        self.p = mock.patch.object(PG.subprocess, "Popen", side_effect=AssertionError("network child spawned"))
        self.p.start()
        PG.LAST_CHILD_PID = None
        return self

    def __exit__(self, *exc):
        self.p.stop()
        return False


class TestExplicitFlush(Base):
    def granted_registered(self):
        stub = self.serve()
        self.ok("migrate")
        self.consent()
        self.assertEqual(self.ok("flush")["status"], "registered")
        stub.requests.clear()
        return stub

    def test_every_local_command_zero_network(self):
        stub = self.granted_registered()
        done = set()

        def run(*args, stdin=None):
            with NoNetwork():
                code, out, err = self.run_pg(*args, stdin=stdin)
            self.assertEqual(code, 0, (args, err))
            self.assertIsNone(PG.LAST_CHILD_PID, args)
            self.assertEqual(stub.requests, [], args)
            done.add(args[0])
            return json.loads(out)

        run("migrate")
        w = run("where")
        run("advance", "--revision", str(w["revision"]))
        o = run("open", Q)
        lab = lambda o, x: next(d["label"] for d in o["display"] if d["option_id"] == x)
        r = run("record", "--token", o["token"], "--attempt", "1", "--label", lab(o, "a"), "--option", "a",
                "--rubric", "incorrect")
        run("remark", stdin=json.dumps({"kind": "unclear", "text": "x", "scope": "step", "step": Q}))
        run("record", "--token", o["token"], "--attempt", str(r["next_attempt"]), "--label", lab(o, "b"),
            "--option", "b", "--rubric", "correct", "--evidence", "own_answer")
        oe = run("open", EX)
        run("skip", "--token", oe["token"], "--reason", "later")
        run("consent", "--decision", "revoked", "--recipient", "127.0.0.1")
        run("consent", "--decision", "granted", "--recipient", "127.0.0.1")
        w = run("where")
        run("lesson", "S1.L01", "--revision", str(w["revision"]))
        # notice: a changed done step after an update
        self.set_course(course_doc("0.3.0", quiz_cv="cv-q2",
                                   changes=[dict(CHANGE_03, important=[Q])]))
        run("migrate")
        w = run("where")
        self.assertTrue(w["notices"], w)
        run("notice", w["notices"][0]["id"], "--later", "--revision", str(w["revision"]))
        # checkpoint pause + resume on the real course
        self.home = self.dir / "real-home"
        self.course = Path(shutil.copyfile(COURSE_FILE, self.dir / "real-course.json"))
        run("migrate")
        run("consent", "--decision", "granted", "--recipient", "127.0.0.1")
        for _ in range(400):
            w = run("where")
            typ, sid, rev = w["content"]["type"], w["step"], str(w["revision"])
            if typ == "checkpoint":
                run("checkpoint", "--revision", rev, "--choice", "pause")
                run("resume", "--revision", str(run("where")["revision"]))
                break
            if typ == "explain":
                run("advance", "--revision", rev)
            else:
                run("skip", "--token", run("open", sid)["token"], "--reason", "test")
        self.assertEqual(done, {"migrate", "where", "advance", "open", "record", "remark", "skip", "consent",
                                "lesson", "notice", "checkpoint", "resume"})
        self.assertTrue(self.events())                 # the data is on disk, waiting for an explicit flush

    def test_only_cmd_flush_reaches_the_request_child(self):
        import ast
        tree = ast.parse(PROGRESS.read_text(encoding="utf-8"))
        callers = {}
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for c in ast.walk(fn):
                if isinstance(c, ast.Call):
                    name = c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None)
                    if name in ("_post", "Popen", "urlopen", "create_connection"):
                        callers.setdefault(name, set()).add(fn.name)
        self.assertEqual(callers, {"_post": {"cmd_flush"}, "Popen": {"_post"}})
        self.assertFalse(hasattr(PG, "FLUSH_AFTER") or hasattr(PG, "flush_quietly"))

    def test_record_output_correlates_and_data_on_disk_before_flush(self):
        stub = self.granted_registered()
        o = self.to_quiz()
        with NoNetwork():
            r = self.answer(o, "b")
        h = self.progress()["checks"][Q]["history"][-1]
        self.assertEqual((r["status"], h["status"]), ("confirmed", "confirmed"))
        self.assertEqual(r["attempt_uid"], h["attempt_uid"])
        cid = self.identity()["collector_id"]
        self.assertEqual(r["event_id"], PG.event_id(cid, "answer-uid:" + h["attempt_uid"], "answer"))
        self.assertEqual([e["id"] for e in self.events()], [r["event_id"]])
        with NoNetwork():
            m = self.remark()
        self.assertEqual([e["id"] for e in self.events()], [r["event_id"], m["id"]])
        self.assertEqual(stub.requests, [])
        self.assertFalse((self.home / "outbox-state.json").exists())
        f = self.ok("flush")
        self.assertEqual((f["status"], f["sent"], f["accepted"], f["pending"]), ("delivered", 2, 2, 0))
        self.assertEqual(self.sent_ids(), [r["event_id"], m["id"]])
        self.assertEqual(self.ok("flush")["status"], "nothing_pending")

    def test_skip_record_has_ids_and_identity_lost_gives_null_event_id(self):
        self.ok("migrate")
        w = self.ok("where")
        self.ok("advance", "--revision", str(w["revision"]))
        o = self.ok("open", Q)
        r = self.ok("skip", "--token", o["token"], "--reason", "x")
        self.assertEqual(r["attempt_uid"], self.progress()["checks"][Q]["history"][-1]["attempt_uid"])
        self.assertEqual(r["event_id"], self.events()[0]["id"])
        for f in ("identity.json", "identity.json.bak"):
            (self.home / f).unlink()
        oe = self.ok("open", EX)
        r = self.ok("record", "--token", oe["token"], "--said-done")
        self.assertTrue(r["attempt_uid"])
        self.assertIsNone(r["event_id"])

    def snapshot(self):
        return {f: (self.home / f).read_bytes() for f in ("progress.json", "events.jsonl", "identity.json")
                if (self.home / f).exists()} | {"outbox": (self.home / "outbox-state.json").exists()}

    def test_endpoint_missing_or_mismatch_refused_exit3_nothing_touched(self):
        stub = self.serve()
        o = self.to_quiz()
        self.answer(o, "a")
        self.consent()
        before = self.snapshot()
        cases = [((), "endpoint_required"),
                 (("--endpoint", "https://other.example"), "endpoint_mismatch"),
                 (("--endpoint", stub.url + "/v2"), "endpoint_mismatch"),
                 (("--endpoint", stub.url.replace("http:", "https:")), "endpoint_mismatch"),
                 (("--endpoint", "not a url"), "endpoint_mismatch")]
        for extra, reason in cases:
            with NoNetwork():
                code, out, err = self.run_pg("flush", *extra, auto_endpoint=False)
            r = json.loads(out)
            self.assertEqual((code, r["status"], r["reason"]), (3, "refused", reason), extra)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(stub.requests, [])
        # spelling variants of the same endpoint are accepted
        port = stub.url.rsplit(":", 1)[1]
        for same in (stub.url + "/", f"HTTP://127.0.0.1:{port}"):
            code, out, _ = self.run_pg("flush", "--endpoint", same, auto_endpoint=False)
            self.assertEqual((code, json.loads(out)["status"]), (0, "registered") if same.endswith("/") else
                             (0, "delivered"))
        # no endpoint configured: --endpoint is a mismatch, no flag is a plain skip
        self.env.pop("GROKBOT_FEEDBACK_URL")
        code, out, _ = self.run_pg("flush", "--endpoint", stub.url, auto_endpoint=False)
        self.assertEqual((code, json.loads(out)["reason"]), (3, "endpoint_mismatch"))
        code, out, _ = self.run_pg("flush", auto_endpoint=False)
        self.assertEqual((code, json.loads(out)["status"], json.loads(out)["reason"]), (0, "skipped", "no_endpoint"))

    def test_skipped_flush_changes_nothing_none_and_revoked_send_nothing(self):
        stub = self.serve()
        o = self.to_quiz()
        self.answer(o, "a")
        before = self.snapshot()
        with NoNetwork():
            r = self.ok("flush")                                    # consent none
        self.assertEqual((r["status"], r["reason"], r["pending"]), ("skipped", "no_consent", 1))
        self.assertEqual(self.snapshot(), before)
        self.ok("consent", "--decision", "revoked", "--recipient", "127.0.0.1")
        before = self.snapshot()
        with NoNetwork():
            r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"]), ("skipped", "no_consent"))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(stub.requests, [])

    def test_403_and_timeout_pending_then_same_ids_once(self):
        stub = self.granted_registered()
        o = self.to_quiz()
        a = self.answer(o, "a")
        m = self.remark()
        before = self.progress()
        stub.modes = ["403"]
        r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"], r["http_status"], r["pending"]), ("pending", "http", 403, 2))
        self.env["GROKBOT_FEEDBACK_URL"] = closed_port_url()
        r = self.ok("flush")
        self.assertEqual((r["status"], r["reason"]), ("pending", "transport"))
        self.env["GROKBOT_FEEDBACK_URL"] = stub.url
        stub.modes = ["drop"]                                         # stored, answer lost
        self.assertEqual(self.ok("flush")["status"], "pending")
        r = self.ok("flush")
        self.assertEqual((r["status"], r["duplicate"], r["pending"]), ("delivered", 2, 0))
        self.assertEqual(self.progress(), before)
        self.assertEqual(sorted(k[1] for k in stub.rows), sorted([a["event_id"], m["id"]]))
        self.assertEqual(self.ok("flush")["status"], "nothing_pending")


# ---------------------------------------------------------------- one hard deadline per request (Codex 715b3920)

class DripServer:
    """Loopback server that answers register / course-event slowly: mode "headers" drips the whole raw response
    byte by byte, mode "body" sends the headers at once and drips the body; one write every `every` seconds.
    A handler stops at the first failed write (the client closed). server_close() joins every handler thread."""

    def __init__(self, mode, every=1.0):
        import socketserver

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = False
            block_on_close = True

        drip = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                drip.paths.append(self.path)
                if self.path == "/v1/register":
                    code, obj = 201, {"install_id": str(uuid.uuid4()), "send_token": "t" * 43}
                else:
                    code, obj = 200, {"accepted": [e["id"] for e in json.loads(body)["events"]],
                                      "duplicate": [], "rejected": []}
                data = json.dumps(obj).encode()
                head = (f"HTTP/1.1 {code} X\r\nContent-Type: application/json\r\n"
                        f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode()
                if mode == "headers":
                    pieces = [head[i:i + 1] for i in range(len(head))] + [data]
                else:
                    self.wfile.write(head)
                    self.wfile.flush()
                    pieces = [data[i:i + 1] for i in range(len(data))]
                try:
                    for i, piece in enumerate(pieces):
                        if i:
                            time.sleep(every)
                        self.wfile.write(piece)
                        self.wfile.flush()
                except OSError:
                    return
                self.close_connection = True

        self.paths = []
        self.server = S(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class SilentServer:
    """Raw loopback server: reads one request, waits `header_delay`, answers HTTP/1.0 200 with
    Connection: close and a Content-Length it never sends (the body stays silent). Records arrival times."""

    def __init__(self, header_delay):
        self.paths, self.arrivals, self.stop = [], [], threading.Event()
        self.t0 = time.monotonic()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.sock.settimeout(0.1)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}"
        self.header_delay = header_delay
        self.thread = threading.Thread(target=self._serve)
        self.thread.start()

    def _serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(5)
                data = b""
                try:
                    while b"\r\n\r\n" not in data:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                except OSError:
                    continue
                if not data:
                    continue
                self.paths.append(data.split(b" ")[1].decode())
                self.arrivals.append(time.monotonic() - self.t0)
                if self.stop.wait(self.header_delay):
                    continue
                try:
                    conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n"
                                 b"Connection: close\r\n\r\n")
                except OSError:
                    continue
                self.stop.wait(60)

    def close(self):
        self.stop.set()
        self.thread.join()
        self.sock.close()


class TestDeadline(Base):
    DEADLINE = 2.0

    def setUp(self):
        super().setUp()
        self.baseline = threading.active_count()

    def _prepare(self, registered):
        """Consent and identity without network; registered=True adds an install so the flush posts events."""
        o = self.to_quiz()
        self.consent()                                   # no endpoint: no request, identity bootstrapped
        if registered:
            ident = self.identity()
            ident.update(install_id=str(uuid.uuid4()), send_token="s" * 43)
            for f in ("identity.json", "identity.json.bak"):
                (self.home / f).write_text(json.dumps(ident))
        return o

    def _record_args(self, o):
        lab = next(d["label"] for d in o["display"] if d["option_id"] == "b")
        return ("record", "--token", o["token"], "--attempt", "1", "--label", lab, "--option", "b",
                "--rubric", "correct", "--evidence", "own_answer")

    def _run(self, mode, registered, deadline=DEADLINE, server=None, env=None, quiet_until=None):
        o = self._prepare(registered)
        drip = server or DripServer(mode)
        self.env["GROKBOT_FEEDBACK_URL"] = drip.url
        self.env.update(env or {})
        PG.LAST_CHILD_PID = None
        try:
            code, out, err = self.run_pg(*self._record_args(o))   # local: instant, no child, no request
            self.assertEqual((code, err, PG.LAST_CHILD_PID), (0, "", None))
            self.assertEqual(json.loads(out)["status"], "confirmed")
            before = self.progress()
            t0 = time.monotonic()
            with mock.patch.object(PG, "TIMEOUT", deadline):
                code, out, err = self.run_pg("flush")
            elapsed = time.monotonic() - t0
            if quiet_until:                                   # watch the server past the point a late send would land
                time.sleep(max(0.0, quiet_until - (time.monotonic() - t0)))
        finally:
            drip.close()
        self.assertLess(elapsed, deadline + 1.5, elapsed)
        self.assertGreaterEqual(elapsed, deadline - 0.2, elapsed)      # it did wait for the slow server
        r = json.loads(out)
        self.assertEqual((code, r["status"], r["reason"]), (0, "pending", "deadline"))
        self.assertIn("stays pending", err)
        self.assertEqual(self.progress(), before)                       # grade, open, verdict untouched
        pid = PG.LAST_CHILD_PID
        self.assertIsNotNone(pid)
        with self.assertRaises(ProcessLookupError):                     # the request child is gone (reaped)
            os.kill(pid, 0)
        self.assertEqual(drip.paths, [] if quiet_until else ["/v1/course-event" if registered else "/v1/register"])
        self.assertEqual(threading.active_count(), self.baseline)       # no reader, watchdog or handler left
        self.assertEqual(len(self.events()), 1)
        if (self.home / "outbox-state.json").exists():
            self.assertEqual((self.outbox()["delivered"], self.outbox()["rejected"]), ({}, {}))
        if not registered:
            self.assertIsNone(self.identity()["install_id"])            # nothing stored from a partial answer

    def test_register_headers_drip(self):
        self._run("headers", registered=False)

    def test_register_body_drip(self):
        self._run("body", registered=False)

    def test_course_event_headers_drip(self):
        self._run("headers", registered=True)

    def test_course_event_body_drip(self):
        self._run("body", registered=True)

    def test_register_http10_close_late_headers_silent_body(self):
        self._run(None, registered=False, server=SilentServer(header_delay=1.2))

    def test_course_event_http10_close_late_headers_silent_body(self):
        self._run(None, registered=True, server=SilentServer(header_delay=1.2))

    def test_slow_dns_bounded_and_nothing_sent_after_deadline(self):
        srv = SilentServer(header_delay=0)
        self._run(None, registered=True, deadline=1.0, server=srv, quiet_until=4.0,
                  env={"GROKBOT_TEST_HOOKS": "1", "GROKBOT_TEST_DNS_DELAY": "3"})
        self.assertEqual(srv.arrivals, [])

    def test_dns_hook_ignored_without_test_flag(self):
        self.env.update(GROKBOT_TEST_DNS_DELAY="30")
        self.serve()
        self.consent()
        self.ok("migrate")
        self.ok("flush")                                  # registers
        self.remark()
        t0 = time.monotonic()
        self.ok("flush")
        self.assertLess(time.monotonic() - t0, 5)
        self.assertEqual(len(self.stub.course_event_calls()), 1)

    def test_production_default_deadline_10s(self):
        self.assertEqual(PG.TIMEOUT, 10)
        self._run(None, registered=False, deadline=PG.TIMEOUT, server=SilentServer(header_delay=7))


# ---------------------------------------------------------------- jsonl, doctor

class TestJsonlAndDoctor(Base):
    def test_torn_line_reported_truncated_saved(self):
        self.ok("migrate")
        self.remark(source_msg="m1")
        good = (self.home / "events.jsonl").read_bytes()
        with open(self.home / "events.jsonl", "ab") as fh:
            fh.write(b'{"id": "half')
        self.assertEqual(len(self.events()), 1)               # ignored on read
        d = self.ok("doctor")
        self.assertEqual(d["files"]["events.jsonl"]["torn_bytes"], len(b'{"id": "half'))
        self.assertEqual(len(d["repaired"]), 1)
        self.assertEqual((self.home / "events.jsonl").read_bytes(), good)
        self.assertEqual((self.home / d["repaired"][0]).read_bytes(), b'{"id": "half')
        self.assertEqual(self.ok("doctor")["files"]["events.jsonl"]["torn_bytes"], 0)

    def test_append_after_torn_keeps_complete_lines(self):
        self.ok("migrate")
        self.remark(source_msg="m1")
        with open(self.home / "events.jsonl", "ab") as fh:
            fh.write(b'{"torn')
        self.remark(source_msg="m2")
        self.assertEqual(len(self.events()), 2)
        self.assertEqual(len(list(self.home.glob("events.torn-*"))), 1)

    def test_where_reports_feedback_consent(self):
        self.ok("migrate")
        self.assertEqual(self.ok("where")["feedback"], {"recipient": None, "endpoint": None, "consent": None})
        self.env["GROKBOT_FEEDBACK_URL"] = "https://FB.example.org:443/"
        self.assertEqual(self.ok("where")["feedback"], {"recipient": "fb.example.org",
                                                        "endpoint": "https://fb.example.org", "consent": "none"})
        self.ok("consent", "--decision", "revoked", "--recipient", "fb.example.org")
        self.assertEqual(self.ok("where")["feedback"]["consent"], "revoked")
        line = PG.read_jsonl(self.home / "consent.jsonl")[0][0]
        self.assertEqual(line["scope"], {"data_set": "course-feedback-v1", "recipient": "fb.example.org",
                                         "course_major": "0"})


# ---------------------------------------------------------------- C1, C5 static; content versions

def content_versions(doc):
    out = {}
    for s in doc["course"]["sections"]:
        for l in s["lessons"]:
            for st in l["steps"]:
                out[st["id"]] = st.get("content_version")
    return out


class TestStatic(unittest.TestCase):
    def test_c1_invitation_line_in_shared_check_block(self):
        text = RUNTIME_FILE.read_text(encoding="utf-8")
        self.assertEqual(text.count(INVITE), 1)
        i = text.index("**quiz** and **exercise**: first `P open")
        self.assertLess(i, text.index(INVITE))
        self.assertLess(text.index(INVITE), text.index("**branch**"))
        self.assertIn("remark <<'REMARK_JSON_END'", text)
        self.assertIn("Курс обновился: изменено N шагов, которые ты проходил", text)

    def test_explicit_flush_in_runtime(self):
        text = RUNTIME_FILE.read_text(encoding="utf-8")
        cmd = ("cd <WORKSPACE_PATH> && python3 -B grokbotceo/course/progress.py --kb-home mentor flush "
               "--endpoint <ENDPOINT>")
        self.assertEqual(text.count(cmd), 1)
        self.assertIn("`feedback.endpoint` from the latest `P where`", text)
        self.assertIn("«Сохранено, отправка позже.»", text)
        self.assertIn("never joined to another command with `&&` or `;`", text)
        self.assertIn("never work around it", text)
        self.assertLess(text.index("## 3a. Sending feedback"), text.index("## 4."))
        self.assertNotIn("$(", text.split("## 3a.")[1].split("## 4.")[0])

    def test_course_equals_b095_except_release_id_and_cvs_unchanged(self):
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{B095}:release/course/course.json"], capture_output=True)
        if r.returncode != 0:
            self.skipTest(f"{B095} not readable from git")
        old = json.loads(r.stdout.decode("utf-8"))
        new = json.loads(COURSE_FILE.read_text(encoding="utf-8"))
        self.assertEqual(new["course"]["version"], "0.3.0")
        self.assertEqual(new["course"]["release_id"], RC_RELEASE_ID)
        self.assertNotIn("release_id", old["course"])
        stripped = copy.deepcopy(new)
        del stripped["course"]["release_id"]
        self.assertEqual(stripped, old)                                  # the single added key, nothing else
        self.assertEqual(content_versions(old), content_versions(new))    # every step's content_version
        self.assertGreaterEqual(sum(1 for s in PG.Course(COURSE_FILE).steps.values() if s["type"] in ("quiz", "exercise")), 128)
        # byte level: b095 plus exactly one line after "version"
        added = [x for x in COURSE_FILE.read_text(encoding="utf-8").splitlines()
                 if x not in r.stdout.decode("utf-8").splitlines()]
        self.assertEqual(added, [f'    "release_id": "{RC_RELEASE_ID}",'])

    def test_build_recomputes_course_json_with_release_id(self):
        # course-merge --check rebuilds every generated field (content_version included) from the step inputs and
        # compares the whole text: passing proves release_id does not enter any step's content_version.
        if not (ROOT / "docs" / "design" / "claims-map.tsv").is_file():
            self.skipTest("build inputs are only in the development repo")
        if subprocess.run(["git", "-C", str(SCRIPT_DIR), "cat-file", "-e", "a06537d^{commit}"],
                          capture_output=True).returncode != 0:
            self.skipTest("historical release commits are not in this repository (public release clone)")
        cm = _load("r030_course_merge", SCRIPT_DIR / "course-merge.py")
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cm.main(["--check"]), 0, err.getvalue())
        doc = json.loads(COURSE_FILE.read_text(encoding="utf-8"))
        for sid, st in ((s["id"], s) for sec in doc["course"]["sections"] for l in sec["lessons"] for s in l["steps"]):
            self.assertNotIn("release_id", json.dumps(st, ensure_ascii=False), sid)


class TestRealCourseRelease(Base):
    def test_answer_event_carries_release_id(self):
        self.course = Path(shutil.copyfile(COURSE_FILE, self.dir / "real-course.json"))
        self.ok("migrate")
        for _ in range(50):
            w = self.ok("where")
            if w["content"]["type"] == "explain":
                self.ok("advance", "--revision", str(w["revision"]))
                continue
            break
        o = self.ok("open", w["step"])
        opt = o["option_ids"][0]
        lab = next(d["label"] for d in o["display"] if d["option_id"] == opt)
        args = ["record", "--token", o["token"], "--attempt", "1", "--label", lab, "--option", opt]
        if o["scoring"]:
            args += ["--rubric", "incorrect"]
        self.ok(*args)
        ev = self.events()[0]
        self.assertEqual((ev["type"], ev["course_version"], ev["release_id"]), ("answer", "0.3.0", RC_RELEASE_ID))
        self.assertEqual(self.progress()["checks"][w["step"]]["history"][0]["release_id"], RC_RELEASE_ID)


# ---------------------------------------------------------------- plan §3.2: migrations on copies (RC)

FIXTURES = ROOT / "docs" / "design" / "p1-fixtures"
LEARNERS = ["novichok", "oshibayushchiysya", "sporshchik", "toropyga", "otlichnik"]
# owner-decision-p2b-2026-11-14.md §2: 0.2.0 -> 0.3.0 on copies of the five archived learners
BASE_RECHECKS = {"novichok": 14, "oshibayushchiysya": 23, "sporshchik": 24, "toropyga": 36, "otlichnik": 48}
BASE_NEW_REPEATS = {"novichok": 14, "oshibayushchiysya": 22, "sporshchik": 23, "toropyga": 35, "otlichnik": 47}
RELEASE_020 = "a06537d"


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@unittest.skipUnless(all((FIXTURES / f"uchenik-{n}-progress.json").is_file() for n in LEARNERS),
                     "archived learner fixtures are only in the development repo")
class TestMigrationRC(Base):
    COUNTS = {}

    def setUp(self):
        super().setUp()
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{RELEASE_020}:release/course/course.json"],
                           capture_output=True)
        if r.returncode != 0:
            self.skipTest("release 0.2.0 not readable from git")
        self.c020 = self.dir / "course-020.json"
        self.c020.write_bytes(r.stdout)
        self.rc = self.dir / "course-rc.json"
        shutil.copyfile(COURSE_FILE, self.rc)

    def learner(self, name):
        self.home = self.dir / name
        self.home.mkdir()
        (self.home / "progress.json").write_bytes((FIXTURES / f"uchenik-{name}-progress.json").read_bytes())

    def test_schema1_to_rc_direct_and_rerun_noop(self):
        for name in LEARNERS:
            with self.subTest(learner=name):
                self.learner(name)
                self.course = self.rc
                orig = json.loads((FIXTURES / f"uchenik-{name}-progress.json").read_text(encoding="utf-8"))
                rep = self.ok("migrate", "--json")
                st = self.progress()
                self.assertTrue(rep["changed"])
                self.assertEqual((st["schema"], st["course_version"]), (2, "0.3.0"))
                self.assertEqual(st["migrations"][-1]["from"], orig["course_version"])
                once = (self.home / "progress.json").read_bytes()
                again = self.ok("migrate", "--json")                          # re-run: no-op, byte-identical
                self.assertFalse(again["changed"])
                self.assertEqual((self.home / "progress.json").read_bytes(), once)
                TestMigrationRC.COUNTS[("schema1->RC", name)] = (len(rep["rechecks"]), len(st["repeat"]))

    def test_schema2_020_to_rc_base_numbers_hold_history_and_legacy_unchanged(self):
        for name in LEARNERS:
            with self.subTest(learner=name):
                self.learner(name)
                self.course = self.c020
                self.ok("migrate")
                st020 = self.progress()
                hist = {sid: [digest(h) for h in c["history"]] for sid, c in st020["checks"].items()}
                legacy = {k: [digest(e) for e in v] for k, v in st020["legacy"].items()}
                self.course = self.rc
                rep = self.ok("migrate", "--json")
                st = self.progress()
                new_repeats = set(st["repeat"]) - set(st020["repeat"])
                self.assertEqual(len(rep["rechecks"]), BASE_RECHECKS[name])
                self.assertEqual(len(new_repeats), BASE_NEW_REPEATS[name])
                self.assertEqual(rep["changed_done"], len(rep["changed_done_steps"]))
                for sid, ds in hist.items():                                  # old history entries untouched
                    live = st["checks"].get(sid)
                    got = live["history"] if live else next(
                        e["original"]["check"]["history"] for e in st["legacy"][sid] if "check" in e.get("original", {}))
                    self.assertEqual([digest(h) for h in got[:len(ds)]], ds, sid)
                for k, ds in legacy.items():                                  # legacy is append-only
                    self.assertEqual([digest(e) for e in st["legacy"][k][:len(ds)]], ds, k)
                again = self.ok("migrate", "--json")
                self.assertFalse(again["changed"])
                TestMigrationRC.COUNTS[("0.2.0->RC", name)] = (len(rep["rechecks"]), len(new_repeats),
                                                                rep["changed_done"])

    def walk_and_answer(self):
        for _ in range(300):
            w = self.ok("where")
            typ, sid, rev = w["content"]["type"], w["step"], str(w["revision"])
            if typ == "explain":
                self.ok("advance", "--revision", rev)
            elif typ == "checkpoint":
                self.ok("checkpoint", "--revision", rev, "--choice", "continue")
            elif typ == "exercise":
                o = self.ok("open", sid)
                self.ok("skip", "--token", o["token"], "--reason", "test")
            else:
                o = self.ok("open", sid)
                opt = o["option_ids"][0]
                lab = next(d["label"] for d in o["display"] if d["option_id"] == opt)
                args = ["record", "--token", o["token"], "--attempt", str(o["next_attempt"]), "--label", lab,
                        "--option", opt]
                if o["scoring"]:
                    args += ["--rubric", "incorrect"]
                self.ok(*args)
                return sid
        self.fail("no quiz reached")

    def test_mixed_version_history(self):
        self.learner("novichok")
        self.course = self.c020
        self.ok("migrate")
        s020 = self.walk_and_answer()                                         # recorded at 0.2.0
        before = self.progress()
        old = {sid: [digest(h) for h in c["history"]] for sid, c in before["checks"].items()}
        self.course = self.rc
        self.ok("migrate")
        s030 = self.walk_and_answer()                                         # recorded at 0.3.0
        st = self.progress()
        for sid, ds in old.items():
            if sid in st["checks"]:
                self.assertEqual([digest(h) for h in st["checks"][sid]["history"][:len(ds)]], ds, sid)
        origins = {(h.get("origin"), h.get("course_version", "absent")) for c in st["checks"].values() for h in c["history"]}
        self.assertIn(("legacy_unknown", None), origins)                      # schema-1 record (0.1.0)
        self.assertIn(("runtime", "0.2.0"), origins)
        self.assertIn(("runtime", "0.3.0"), origins)
        exp = {(e["step"], e["course_version"], e["version_origin"]) for e in self.export() if e["type"] == "answer"}
        self.assertIn((s020, "0.2.0", "recorded"), exp)
        self.assertIn((s030, "0.3.0", "recorded"), exp)
        self.assertEqual({e["course_version"] for e in self.events()}, {"0.2.0", "0.3.0"})

    @classmethod
    def tearDownClass(cls):
        if cls.COUNTS:
            print("\n  RC migration (rechecks, new repeats[, changed_done]): "
                  + "; ".join(f"{k[0]} {k[1]}={v}" for k, v in sorted(cls.COUNTS.items())), file=sys.stderr)


class TestZzNoWritesOutsideTemp(unittest.TestCase):
    def test_zz_guard_release_untouched(self):
        self.assertEqual(tree_state(RELEASE_DIR), BEFORE)
        tmp = Path(tempfile.gettempdir()).resolve()
        for root in TMP_ROOTS:
            self.assertTrue(str(root.resolve()).startswith(str(tmp)), root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
