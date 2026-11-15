#!/usr/bin/env python3
"""
Local end-to-end test of course feedback (release 0.3.0, plan C2-C4; contract course/EVENT-SCHEMA.md):
the REAL receiver (services/feedback-receiver, started as a subprocess on 127.0.0.1 with a free port, a
temporary SQLite DB and an admin password from the environment) and the REAL course/progress.py (run as a
subprocess) on a temporary copy of this release's course.json and a fresh student's progress.

Scenario (Codex acceptance): consent -> open a quiz -> remark «непонятно» while it is open -> the attempt is
not spent and the open question is kept -> the answer is recorded (no request: only an explicit
`flush --endpoint <configured>` touches the network) -> flush -> remark and answer are in
/admin/summary with course_version and step. Then: receiver killed -> events pending, grade kept; receiver
restarted on the same DB -> delivered, no duplicate rows; corrupted outbox-state.json -> resent as
duplicate, still one row each; two remarks with identical text -> two rows; consent revoked -> no request
reaches the receiver (DB count unchanged).

Stdlib only. No network beyond 127.0.0.1. Every file is written under a temporary folder. Skipped when the
receiver is not in this tree (a release clone).
"""
import base64
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
ROOT = RELEASE_DIR.parent
PROGRESS = RELEASE_DIR / "course" / "progress.py"
COURSE_FILE = RELEASE_DIR / "course" / "course.json"
RECEIVER = ROOT / "services" / "feedback-receiver"
HAVE_RECEIVER = (RECEIVER / "feedback_receiver" / "__main__.py").is_file()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Receiver:
    def __init__(self, tmp: Path):
        self.port = free_port()
        self.db = tmp / "receiver" / "feedback.db"
        self.db.parent.mkdir(parents=True)
        self.password = secrets.token_urlsafe(16)
        self.log = tmp / "receiver" / "log.txt"
        self.env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
                    "FR_HOST": "127.0.0.1", "FR_PORT": str(self.port), "FR_DB_PATH": str(self.db),
                    "FR_OUTBOX_DIR": str(tmp / "receiver" / "outbox"), "FR_ADMIN_PASSWORD": self.password,
                    "FR_MAILER": "log"}
        self.proc = None
        self.url = f"http://127.0.0.1:{self.port}"

    def start(self):
        fh = open(self.log, "ab")
        self.proc = subprocess.Popen([sys.executable, "-B", "-m", "feedback_receiver"], cwd=str(RECEIVER),
                                     env=self.env, stdout=fh, stderr=subprocess.STDOUT)
        fh.close()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.url + "/healthz", timeout=1) as r:
                    if r.status == 200:
                        return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("receiver did not start: " + self.log.read_text(errors="replace")[-2000:])

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
        self.proc = None

    def summary(self):
        req = urllib.request.Request(self.url + "/admin/summary")
        auth = base64.b64encode(f"admin:{self.password}".encode()).decode()
        req.add_header("Authorization", "Basic " + auth)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))["course"]

    def rows(self):
        with sqlite3.connect(str(self.db)) as c:
            return [tuple(r) for r in c.execute("SELECT install_id, id, type, course_version, step FROM course_events")]


@unittest.skipUnless(HAVE_RECEIVER, "services/feedback-receiver is not in this tree")
class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="r030-e2e-"))
        self.course = self.tmp / "course" / "course.json"
        self.course.parent.mkdir()
        shutil.copyfile(COURSE_FILE, self.course)
        self.doc = json.loads(self.course.read_text(encoding="utf-8"))["course"]
        self.version = self.doc["version"]
        self.home = self.tmp / "mentor"
        self.rx = Receiver(self.tmp)
        self.rx.start()

    def tearDown(self):
        self.rx.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ the real progress.py
    def flush(self, expect=0):
        """What the Mentor runs as its own tool call: the fixed command naming the configured endpoint."""
        return self.pg("flush", "--endpoint", self.endpoint, expect=expect)

    def pg(self, *args, stdin=None, expect=0):
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1",
               "GROKBOT_FEEDBACK_URL": self.rx.url}
        r = subprocess.run([sys.executable, "-B", str(PROGRESS), "--kb-home", str(self.home), "--course",
                            str(self.course), *args], input=stdin, capture_output=True, text=True, env=env,
                           timeout=60)
        self.assertEqual(r.returncode, expect, r.stderr)
        self.last_err = r.stderr
        return json.loads(r.stdout) if r.stdout.strip().startswith("{") and expect == 0 else r.stdout

    def key_of(self, o):
        for s in self.doc["sections"]:
            for l in s["lessons"]:
                for st in l["steps"]:
                    if st["id"] != o["step"]:
                        continue
                    srcs = [st] + list(st.get("situations") or [])
                    src = next((x for x in srcs if x.get("id", st["id"]) == o["scenario_id"]), st)
                    if o["scenario_id"] == (st.get("primary_scenario_id") or st["id"]):
                        src = st
                    return next(x["id"] for x in src["options"] if x.get("correct"))
        raise AssertionError(o["step"])

    def next_quiz(self):
        """Walk the course from the cursor to the next quiz and open it (exercises are skipped)."""
        for _ in range(200):
            w = self.pg("where")
            typ, sid, rev = w["content"]["type"], w["step"], str(w["revision"])
            if typ == "explain":
                self.pg("advance", "--revision", rev)
            elif typ == "checkpoint":
                self.pg("checkpoint", "--revision", rev, "--choice", "continue")
            elif typ == "exercise":
                o = self.pg("open", sid)
                self.pg("skip", "--token", o["token"], "--reason", "e2e")
            elif typ == "quiz":
                return self.pg("open", sid)
            else:
                self.fail(f"unexpected step type {typ}")
        self.fail("no quiz found")

    def answer(self, o):
        opt = self.key_of(o)
        lab = next(d["label"] for d in o["display"] if d["option_id"] == opt)
        args = ["record", "--token", o["token"], "--attempt", str(o["next_attempt"]), "--label", lab, "--option", opt]
        if o["scoring"]:
            args += ["--rubric", "correct", "--evidence", "own_answer"]
        return self.pg(*args)

    def remark(self, **kw):
        d = {"source_msg": None, "kind": "unclear", "text": "непонятно", "scope": "course", "step": None,
             "scenario_id": None, "parent_id": None}
        d.update(kw)
        return self.pg("remark", stdin=json.dumps(d, ensure_ascii=False))

    def events(self):
        return [json.loads(x) for x in (self.home / "events.jsonl").read_text(encoding="utf-8").splitlines()]

    def delivered(self):
        return json.loads((self.home / "outbox-state.json").read_text(encoding="utf-8"))["delivered"]

    def flush_all(self):
        for _ in range(10):
            r = self.flush()
            if r["status"] in ("nothing_pending", "skipped"):
                return r
        return r

    # ------------------------------------------------------------ scenario
    def test_e2e_acceptance(self):
        self.pg("migrate", "--json")
        fb = self.pg("where")["feedback"]
        self.assertEqual((fb["recipient"], fb["consent"]), ("127.0.0.1", "none"))
        self.endpoint = fb["endpoint"]                                  # copied verbatim, as the Mentor does
        self.assertEqual(self.endpoint, self.rx.url)
        self.pg("consent", "--decision", "granted", "--recipient", "127.0.0.1")       # local only
        self.assertEqual(self.flush()["status"], "registered")
        self.assertEqual(self.pg("flush", expect=3), self.pg("flush", expect=3))      # no --endpoint: refused
        o = self.next_quiz()
        before = (self.home / "progress.json").read_bytes()

        # remark while the quiz is open: no attempt spent, the open question kept
        r = self.remark(scope="step", step=o["step"], scenario_id=o["scenario_id"])
        self.assertTrue(r["written"])
        self.assertEqual((self.home / "progress.json").read_bytes(), before)
        w = self.pg("where")
        self.assertEqual((w["open"]["token"], w["open"]["next_attempt"], w["open"]["display"]),
                         (o["token"], o["next_attempt"], o["display"]))
        self.assertNotIn(o["step"], {s for s in json.loads(before)["checks"] if json.loads(before)["checks"][s]["history"]})

        # the clarification (Mentor asked what exactly is unclear): a follow-up remark linked to the first one
        c = self.remark(scope="step", step=o["step"], scenario_id=o["scenario_id"], parent_id=r["id"],
                        text="не понял, что значит «ключ»")
        self.assertTrue(c["written"])
        self.assertEqual((self.home / "progress.json").read_bytes(), before)
        self.assertEqual(self.pg("where")["open"]["token"], o["token"])
        history_before = {k: v["history"] for k, v in json.loads(before)["checks"].items()}

        # return to the answer: it is recorded as attempt 1 of the same open question
        a = self.answer(o)
        self.assertEqual(a["attempt"], 1)
        self.assertIn(a["status"], ("confirmed", "shown"))
        st = json.loads((self.home / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(len(st["checks"][o["step"]]["history"]), 1)            # one attempt, remarks spent none
        for k, h in history_before.items():                                    # earlier history intact
            self.assertEqual(st["checks"][k]["history"][:len(h)], h)
            self.assertEqual(len(st["checks"][k]["history"]), len(h) + (k == o["step"]))
        self.assertEqual(self.rx.rows(), [])                                   # writes are local
        self.assertTrue(a["attempt_uid"] and a["event_id"])
        self.flush_all()
        rows = self.rx.rows()
        self.assertEqual(sorted(x[2] for x in rows), ["answer", "remark", "remark"])
        self.assertEqual(len(rows), len(set(rows)))
        s = self.rx.summary()
        self.assertIn({"course_version": self.version, "step": o["step"]},
                      [{"course_version": x["course_version"], "step": x["step"]} for x in s["remarks_by_version_step"]])
        self.assertEqual(s["remarks_by_version_step"][0]["kinds"], {"unclear": 2})
        self.assertIn(o["step"], [x["step"] for x in s["answers_by_step"]])
        self.assertEqual(sorted(x["text_escaped"] for x in s["recent_remarks"]),
                         sorted(["непонятно", "не понял, что значит «ключ»"]))
        self.assertTrue(all(x[3] == self.version for x in rows))
        self.assertEqual(set(self.delivered()), {e["id"] for e in self.events()})
        follow = next(e for e in self.events() if e["id"] == c["id"])
        self.assertEqual(follow["parent_id"], r["id"])
        answer_ev = next(e for e in self.events() if e["type"] == "answer" and e["step"] == o["step"])
        self.assertEqual(answer_ev["release_id"], self.doc.get("release_id"))

        # receiver killed: the grade is kept, the event stays pending
        self.rx.stop()
        n_before = len(self.events())
        o2 = self.next_quiz()
        a2 = self.answer(o2)
        self.assertEqual((a2["attempt"], self.last_err), (1, ""))
        r = self.flush()
        self.assertEqual((r["status"], r["reason"]), ("pending", "transport"))
        self.assertIn("stays pending", self.last_err)
        self.assertIn(a2["event_id"], [e["id"] for e in self.events()])
        self.assertEqual(self.pg("where")["step"], a2["current"])
        pending = [e for e in self.events() if e["id"] not in self.delivered()]
        self.assertEqual(pending, self.events()[n_before:])          # everything since the stop (skips, answer)
        self.assertIn((o2["step"], 1, "answer"), [(e["step"], e["attempt"], e["type"]) for e in pending])

        # restarted on the same DB: delivered, no duplicate rows
        self.rx.start()
        self.flush_all()
        self.assertEqual(set(self.delivered()), {e["id"] for e in self.events()})
        rows = self.rx.rows()
        self.assertEqual(len(rows), len(set(rows)))
        self.assertEqual(len(rows), len(self.events()))

        # corrupted delivery cache: everything re-sent, answered duplicate, still one row each
        (self.home / "outbox-state.json").write_text("{broken", encoding="utf-8")
        r = self.flush()
        self.assertEqual((r["accepted"], r["duplicate"], r["rejected"]), (0, len(self.events()), 0))
        self.assertEqual(len(self.rx.rows()), len(self.events()))
        self.assertEqual({x[1] for x in self.rx.rows()}, {e["id"] for e in self.events()})

        # two remarks with identical text: two rows
        n = len(self.rx.rows())
        r1, r2 = self.remark(text="одинаковый текст"), self.remark(text="одинаковый текст")
        self.assertNotEqual(r1["id"], r2["id"])
        self.flush_all()
        self.assertEqual(len(self.rx.rows()), n + 2)

        # consent revoked: nothing reaches the receiver
        n = len(self.rx.rows())
        self.pg("consent", "--decision", "revoked", "--recipient", "127.0.0.1")
        self.remark(text="после отзыва")
        o3 = self.next_quiz()
        self.answer(o3)
        r = self.flush()
        self.assertEqual((r["status"], r["reason"]), ("skipped", "no_consent"))
        self.assertEqual(len(self.rx.rows()), n)
        self.assertEqual(len(self.events()), n + 2)                 # kept locally, not sent


if __name__ == "__main__":
    unittest.main(verbosity=2)
