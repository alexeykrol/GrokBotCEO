#!/usr/bin/env python3
"""
Tests for course feedback contract v2 (course/EVENT-SCHEMA.md §5; design docs/design/feedback-protocol-v2.md):
consent recorded at install, the course-start notice answered once, stop / resume, remarks only on the wire,
flush right after a remark with the delivered ids, the local queue (events.jsonl + outbox-state.json) resent on
the next flush, registration at install into the key file (mode 600, path from GROKBOT_COURSE_ENV), the token
never printed; the update path (UPDATE.md step 11: gate, consent at update, never over an earlier decision);
plus static guards on MENTOR-RUNTIME (thanks instruction, U20 wording).

Reuses the harness of test-r030.py (local http.server stub on 127.0.0.1, temp folders only). Stdlib only.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True          # loading test-r030.py must not leave a .pyc in the release tree
SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
RUNTIME_FILE = RELEASE_DIR / "course" / "MENTOR-RUNTIME.md"
INVARIANTS = RELEASE_DIR.parent / ".claude" / "INVARIANTS.md"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("r030_harness_for_v2", SCRIPT_DIR / "test-r030.py")
UP = _load("update_plan_for_v2", SCRIPT_DIR / "update-plan.py")
PG = R.PG
PKEY = "pk_" + "A1b2C3d4" * 3
THANKS = ('"After the server returns 2xx for a remark (and only then), thank the person in one short line in '
          'Russian. Make it fresh every time: change the image, the joke, the angle. Never repeat a wording or '
          'structure you used in this conversation, and never two thanks of the same kind in a row. It can be '
          'playful, warm, a little absurd, but not sugary and not longer than about 15 words. Mention that the '
          'remark reached the author. If the send failed, don\'t thank; say it is saved and will go out later."')


class V2(R.Base):
    def setUp(self):
        super().setUp()
        self.key_path = self.dir / "box" / ".grokbotceo" / "course.env"
        self.env["GROKBOT_COURSE_ENV"] = str(self.key_path)

    # helpers
    def install(self, pkey=PKEY):
        """What the install does: consent at install (+ participant key), then one flush that registers."""
        self.serve()
        args = ["consent", "--decision", "granted_at_install"] + (["--participant-key", pkey] if pkey else [])
        c = self.ok(*args)
        r = self.ok("flush")
        return c, r

    def key(self):
        return dict(line.split("=", 1) for line in self.key_path.read_text(encoding="utf-8").splitlines())

    def bodies(self):
        return [json.loads(r[2]) for r in self.stub.course_event_calls()]

    def all_output(self, *args, stdin=None):
        code, out, err = self.run_pg(*args, stdin=stdin)
        return code, out + err


class TestInstall(V2):
    def test_install_records_consent_and_registers_into_key_file(self):
        c, r = self.install()
        self.assertEqual((c["decision"], c["data_set"], c["written"], c["notice_due"], c["key_file"]),
                         ("granted_at_install", "course-feedback-v2", True, True, "written"))
        self.assertEqual(c["recipient"], "127.0.0.1")              # default: the configured endpoint's host
        self.assertNotIn(PKEY, json.dumps(c))
        self.assertEqual((r["status"], r["key_file"]), ("registered", "written"))
        self.assertEqual([x[0] for x in self.stub.requests], ["/v1/register"])
        k = self.key()
        token = next(iter(self.stub.installs))
        self.assertEqual(k, {"GROKBOT_INSTALL_ID": self.stub.installs[token], "GROKBOT_SEND_TOKEN": token,
                             "GROKBOT_PARTICIPANT_KEY": PKEY})
        self.assertEqual(stat.S_IMODE(self.key_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.key_path.parent.stat().st_mode), 0o700)
        self.assertEqual(PG.read_jsonl(self.home / "consent.jsonl")[0][-1]["scope"]["data_set"], "course-feedback-v2")
        # the token is never printed by any command
        for args in (("where",), ("queue",), ("flush",), ("doctor",)):
            if args == ("where",):
                self.ok("migrate")
            code, text = self.all_output(*args)
            self.assertNotIn(token, text, args)
            self.assertNotIn(PKEY, text, args)

    def test_reinstall_never_overrides_a_decision(self):
        self.install()
        self.ok("consent", "--decision", "revoked")
        again = self.ok("consent", "--decision", "granted_at_install")
        self.assertEqual((again["written"], again["decision"]), (False, "revoked"))

    def test_participant_key_only_with_install_and_valid(self):
        self.serve()
        self.fail("consent", "--decision", "granted", "--participant-key", PKEY)
        self.fail("consent", "--decision", "granted_at_install", "--participant-key", "bad key")
        self.assertFalse(self.key_path.exists())

    def test_no_endpoint_and_no_recipient_is_an_error(self):
        self.fail("consent", "--decision", "granted_at_install")

    def test_key_file_unwritable_is_a_note_not_a_failure(self):
        self.key_path.parent.parent.mkdir(parents=True)
        self.key_path.parent.parent.chmod(0o500)                  # parent of .grokbotceo not writable
        try:
            c, r = self.install()
        finally:
            self.key_path.parent.parent.chmod(0o700)
        self.assertEqual((c["key_file"], r["status"], r["key_file"]), ("failed", "registered", "failed"))
        self.assertTrue(self.identity()["send_token"])            # sending still works from identity.json
        m = self.remark()
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"]), ("delivered", [m["id"]]))


class TestNoticeAndStop(V2):
    def test_notice_due_until_answered_once(self):
        self.install()
        self.ok("migrate")
        fb = self.ok("where")["feedback"]
        self.assertEqual((fb["consent"], fb["data_set"], fb["notice_due"], fb["queued"]),
                         ("granted_at_install", "course-feedback-v2", True, 0))
        a = self.ok("consent", "--decision", "acknowledged")
        self.assertEqual((a["written"], a["notice_due"]), (True, False))
        self.assertFalse(self.ok("where")["feedback"]["notice_due"])
        self.assertFalse(self.ok("consent", "--decision", "acknowledged")["written"])   # once

    def test_stop_at_notice_then_acknowledged_does_not_resume(self):
        self.install()
        self.ok("consent", "--decision", "revoked")
        a = self.ok("consent", "--decision", "acknowledged")
        self.assertEqual((a["written"], a["decision"], a["notice_due"]), (False, "revoked", False))

    def test_acknowledged_without_v2_consent_is_an_error(self):
        self.serve()
        self.fail("consent", "--decision", "acknowledged")
        self.consent()                                              # v1 grant
        self.fail("consent", "--decision", "acknowledged")

    def test_stop_remark_resume_remark(self):
        """22d: a remark written while stopped is held for good; resume covers new remarks only."""
        self.install()
        self.ok("consent", "--decision", "revoked")                 # «не отправляй»
        held = self.remark(text="написано во время остановки")
        self.assertTrue(held.get("held"))
        line = next(e for e in self.events() if e["id"] == held["id"])
        self.assertIs(line["held"], True)                            # marked when written, in the local line
        n = len(self.stub.requests)
        f = self.ok("flush")
        self.assertEqual((f["status"], f["reason"]), ("skipped", "no_consent"))
        self.assertEqual(len(self.stub.requests), n)                # no request at all
        self.assertEqual(self.ok("queue"), {"queued": 0, "ids": []})  # a held remark is not sendable
        self.ok("migrate")
        self.assertEqual(self.ok("where")["feedback"]["queued"], 0)
        r = self.ok("consent", "--decision", "granted")             # «снова отправляй»
        self.assertEqual((r["decision"], r["data_set"]), ("granted", "course-feedback-v2"))
        self.assertEqual(self.ok("flush")["status"], "nothing_pending")
        self.assertEqual(len(self.stub.requests), n)
        new = self.remark(text="после возобновления")
        self.assertNotIn("held", new)
        self.assertEqual(self.ok("queue"), {"queued": 1, "ids": [new["id"]]})
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"], f["pending"]), ("delivered", [new["id"]], 0))
        sent = [e["id"] for b in self.bodies() for e in b["events"]]
        self.assertEqual(sent, [new["id"]])
        self.assertNotIn(held["id"], sent)
        self.ok("consent", "--decision", "revoked")                 # stop again, then resume again
        self.ok("consent", "--decision", "granted")
        self.assertEqual(self.ok("flush")["status"], "nothing_pending")

    def test_remark_before_any_stop_is_not_held(self):
        self.install()
        m = self.remark()
        self.assertNotIn("held", m)
        self.assertNotIn("held", next(e for e in self.events() if e["id"] == m["id"]))

    def test_whoami_shows_the_install_id_only(self):
        self.assertEqual(self.ok("whoami"), {"install_id": None})   # before registration
        self.install()
        token = next(iter(self.stub.installs))
        code, out, err = self.run_pg("whoami")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"install_id": self.stub.installs[token]})
        self.assertNotIn(token, out + err)
        self.assertNotIn(PKEY, out + err)
        self.key_path.unlink()                                      # key file gone: identity.json still knows
        self.assertEqual(self.ok("whoami"), {"install_id": self.stub.installs[token]})


class TestSending(V2):
    def test_remark_only_on_the_wire_with_contract(self):
        self.install()
        o = self.to_quiz()
        self.answer(o, "b")                                         # a quiz answer: recorded locally only
        self.assertEqual([e["type"] for e in self.events()], ["answer"])
        texts = ["Непонятно, что тут выбрать", "Ошибка в вопросе 🙂 — проверь «вариант б»", "длинно " * 140]
        ids = []
        for t in texts:
            m = self.remark(text=t[:1000])
            f = self.ok("flush")                                    # right after each remark
            self.assertEqual((f["status"], f["delivered_ids"], f["data_set"]), ("delivered", [m["id"]],
                                                                                   "course-feedback-v2"))
            ids.append(m["id"])
        bodies = self.bodies()
        self.assertEqual(len(bodies), 3)
        for b in bodies:
            self.assertEqual(set(b), {"install_id", "events", "contract"})
            self.assertEqual(b["contract"], "course-feedback-v2")
            self.assertEqual({e["type"] for e in b["events"]}, {"remark"})
        self.assertEqual([e["id"] for b in bodies for e in b["events"]], ids)
        self.assertEqual(self.ok("flush")["status"], "nothing_pending")   # the answer is never pending in v2

    def test_failed_send_is_queued_and_resent_next_flush(self):
        self.install()
        self.stub.modes = ["500"]
        a = self.remark(text="первое")
        f = self.ok("flush")
        self.assertEqual((f["status"], f["reason"], f["http_status"], f["delivered_ids"]),
                         ("pending", "http", 500, []))
        self.assertEqual(self.ok("queue"), {"queued": 1, "ids": [a["id"]]})
        self.ok("migrate")
        self.assertEqual(self.ok("where")["feedback"]["queued"], 1)
        b = self.remark(text="второе")
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"], f["pending"]), ("delivered", [a["id"], b["id"]], 0))
        self.assertEqual(self.ok("queue"), {"queued": 0, "ids": []})

    def test_server_down_then_back(self):
        self.install()
        url = self.env["GROKBOT_FEEDBACK_URL"]
        self.env["GROKBOT_FEEDBACK_URL"] = R.closed_port_url()
        m = self.remark()
        f = self.ok("flush")
        self.assertEqual((f["status"], f["reason"]), ("pending", "transport"))
        self.env["GROKBOT_FEEDBACK_URL"] = url
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"]), ("delivered", [m["id"]]))

    def test_key_file_is_the_credential_store(self):
        self.install()
        ident = self.identity()
        ident.update(install_id=None, send_token=None)              # e.g. mentor/ rebuilt; key file survived
        for f in ("identity.json", "identity.json.bak"):
            (self.home / f).write_text(json.dumps(ident), encoding="utf-8")
        m = self.remark()
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"]), ("delivered", [m["id"]]))
        self.assertEqual([x[0] for x in self.stub.requests].count("/v1/register"), 1)   # no second registration

    def test_earlier_registration_is_copied_to_the_key_file(self):
        self.serve()
        self.consent()                                              # v1 install, registered by a v1 flush
        self.ok("flush")
        self.assertFalse(self.key_path.exists())                    # v1 never touches the key file
        self.ok("consent", "--decision", "revoked")
        self.ok("consent", "--decision", "granted")                 # still v1: the data set in force is kept
        self.assertFalse(self.key_path.exists())
        PG.append_lines(PG.Store(str(self.home)), self.home / "consent.jsonl", [{
            "at": PG.now(), "decision": "granted_at_install",
            "scope": {"data_set": "course-feedback-v2", "recipient": "127.0.0.1", "course_major": "0"}}])
        m = self.remark()
        f = self.ok("flush")
        self.assertEqual((f["status"], f["delivered_ids"]), ("delivered", [m["id"]]))
        self.assertEqual(self.key()["GROKBOT_SEND_TOKEN"], self.identity()["send_token"])

    def test_only_flush_reaches_the_network(self):
        import ast
        tree = ast.parse(R.PROGRESS.read_text(encoding="utf-8"))
        callers = {}
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for c in ast.walk(fn):
                if isinstance(c, ast.Call):
                    name = c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", None)
                    if name in ("_post", "Popen", "urlopen", "create_connection"):
                        callers.setdefault(name, set()).add(fn.name)
        self.assertEqual(callers, {"_post": {"cmd_flush"}, "Popen": {"_post"}})


class TestUpdatePath(V2):
    """UPDATE.md step 11: an update to a release whose accepted terms notice says remarks are sent turns course
    feedback on as the install does (gate `update-plan.py feedback`, then consent granted_at_install and one
    flush), and never over a decision the user already made."""

    def setUp(self):
        super().setUp()
        self.ws = self.dir                                  # self.home is <ws>/mentor, as --kb-home mentor
        self.live = self.ws / "grokbotceo"
        (self.live / "scripts").mkdir(parents=True)
        (self.live / "course").mkdir()
        shutil.copy2(SCRIPT_DIR / "terms.py", self.live / "scripts" / "terms.py")
        for name in ("TERMS.md", "TERMS-NOTICE.md", "TERMS-NOTICE.ru.md", "VERSION"):
            shutil.copy2(RELEASE_DIR / name, self.live / name)
        version = (RELEASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
        (self.ws / "VERSION").write_text(version + "\n", encoding="utf-8")
        self.serve()                                        # the endpoint: GROKBOT_FEEDBACK_URL (stub)

    def accept_terms(self):
        terms = _load("terms_for_update_path", self.live / "scripts" / "terms.py")
        terms.accept(self.live, self.ws / "terms-acceptance.json", "Yes", locale="en", mode="update")

    def gate(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, self.env, clear=True), contextlib.redirect_stdout(out):
            code = UP.main(["feedback", "--workspace", str(self.ws)])
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def update_step(self):
        """The step as UPDATE.md writes it: gate; consent without a participant key; flush only if written."""
        g = self.gate()
        if not g["run"]:
            return g, None, None
        c = self.ok("consent", "--decision", "granted_at_install")
        r = self.ok("flush", "--endpoint", c["endpoint"]) if c.get("written") and c.get("endpoint") else None
        return g, c, r

    def test_notice_version_of_this_release_says_remarks(self):
        terms = _load("terms_for_notice_version", SCRIPT_DIR / "terms.py")
        self.assertGreaterEqual(int(terms.notice(RELEASE_DIR)["notice_version"]), UP.FEEDBACK_NOTICE_MIN)

    def test_update_from_install_without_consent_turns_feedback_on(self):
        self.accept_terms()
        g, c, r = self.update_step()
        self.assertEqual(g["run"], True)
        self.assertEqual((c["decision"], c["data_set"], c["written"], c["notice_due"]),
                         ("granted_at_install", "course-feedback-v2", True, True))
        self.assertNotIn("key_file", c)                     # no participant key on an update
        self.assertEqual((r["status"], r["key_file"]), ("registered", "written"))
        self.assertEqual(set(self.key()), {"GROKBOT_INSTALL_ID", "GROKBOT_SEND_TOKEN"})
        self.assertEqual(self.gate(), {"run": False, "reason": "consent_recorded"})   # a rerun does nothing

    def test_earlier_stop_is_never_overridden(self):
        self.install()
        self.ok("consent", "--decision", "revoked")
        self.accept_terms()
        self.assertEqual(self.gate(), {"run": False, "reason": "consent_recorded"})
        again = self.ok("consent", "--decision", "granted_at_install")       # progress.py refuses as well
        self.assertEqual((again["written"], again["decision"]), (False, "revoked"))

    def test_earlier_v1_decision_is_never_overridden(self):
        self.ok("consent", "--decision", "revoked")          # a v1 decision, no v2 line
        self.accept_terms()
        self.assertEqual(self.gate(), {"run": False, "reason": "earlier_decision"})
        again = self.ok("consent", "--decision", "granted_at_install")
        self.assertEqual((again["written"], again["decision"], again["data_set"]),
                         (False, "revoked", "course-feedback-v1"))
        self.assertEqual(self.stub.requests, [])

    def test_no_acceptance_no_feedback(self):
        self.assertEqual(self.gate(), {"run": False, "reason": "terms_not_accepted"})
        (self.ws / "terms-acceptance.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.gate(), {"run": False, "reason": "terms_not_accepted"})

    def test_notice_without_remarks_no_feedback(self):
        n = self.live / "TERMS-NOTICE.md"
        n.write_text(re.sub(r"Notice version: \d+", "Notice version: 1", n.read_text(encoding="utf-8"), count=1),
                     encoding="utf-8")
        self.accept_terms()
        self.assertEqual(self.gate(), {"run": False, "reason": "notice_without_remarks"})

    def test_no_endpoint_no_feedback(self):
        self.accept_terms()
        self.env.pop("GROKBOT_FEEDBACK_URL")
        self.assertEqual(self.gate(), {"run": False, "reason": "no_endpoint"})
        (self.live / "course" / "feedback.json").write_text('{"endpoint": "https://x.example"}', encoding="utf-8")
        self.assertEqual(self.gate()["run"], True)

    def test_partial_update_no_feedback(self):
        self.accept_terms()
        (self.ws / "update-state.json").write_text(json.dumps({"bots": {"mentor": {"outcome": "failed"}}}),
                                                   encoding="utf-8")
        self.assertEqual(self.gate(), {"run": False, "reason": "update_not_complete"})
        (self.ws / "update-state.json").unlink()
        (self.ws / "VERSION").write_text("0.2.0\n", encoding="utf-8")
        self.assertEqual(self.gate(), {"run": False, "reason": "update_not_complete"})
        self.assertFalse((self.home / "consent.jsonl").exists())


class TestRuntimeAndInvariants(unittest.TestCase):
    """Static guards: the thanks instruction (design appendix, verbatim) replaces "say nothing" on delivered;
    U20 bans proposing course changes, not thanking for a remark."""

    def setUp(self):
        self.text = RUNTIME_FILE.read_text(encoding="utf-8")
        self.sec = self.text.split("## 3a.")[1].split("## 4.")[0]

    def test_thanks_instruction_verbatim(self):
        self.assertEqual(self.text.count(THANKS), 1)
        self.assertIn("delivered_ids", self.sec)

    def test_delivered_is_no_longer_silent(self):
        self.assertNotRegex(self.sec, r"`delivered`[^\n]*say nothing")
        for line in self.sec.splitlines():
            if "say nothing" in line:
                self.assertNotIn("`delivered`", line)

    def test_stop_resume_words_and_notice(self):
        for needle in ("«не отправляй»", "«снова отправляй»", "--decision acknowledged", "notice_due",
                       "--decision revoked", "--decision granted"):
            self.assertIn(needle, self.text)

    def test_show_my_id_rule(self):
        for needle in ("«покажи мой ID»", "P whoami"):
            self.assertIn(needle, self.text)
        self.assertIn("contact address in `grokbotceo/TERMS.md`", self.text)   # where to ask for a copy or deletion

    def test_held_remark_rule(self):
        self.assertIn("`\"held\": true`", self.sec)

    def test_only_remark_text_is_sent(self):
        self.assertIn("never the rest of the chat, never quiz answers", " ".join(self.sec.split()))

    def test_u20_bans_proposals_not_thanks(self):
        if not INVARIANTS.exists():
            self.skipTest("INVARIANTS.md not in this checkout")
        u20 = INVARIANTS.read_text(encoding="utf-8").split("### U20")[1].split("### U21")[0]
        self.assertIn("благодарность за замечание", u20)
        self.assertNotIn("молча", u20)


if __name__ == "__main__":
    unittest.main(verbosity=1)
