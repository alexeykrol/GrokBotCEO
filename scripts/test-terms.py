#!/usr/bin/env python3
"""
Tests for scripts/terms.py and the acceptance of the terms at install and update (legal tech
requirements, group B, items 8-13). Stdlib only, temp folders only, no network.
"""
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
TERMS_SCRIPT = SCRIPT_DIR / "terms.py"

spec = importlib.util.spec_from_file_location("terms_under_test", TERMS_SCRIPT)
terms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(terms)

VAGUE = ["", "   ", "ok", "OK", "yes", "Yes", "sure", "go ahead", "fine", "Да", "да", "давай", "ок", "ага",
         "конечно", "делай", "yes to everything", "да на всё", "я согласен", "I agree", "accept",
         "Yes, with routines and delete my old bots", "Да, с рутинами? а что это значит",
         "what are routines?", "Нет", "No", "Yes with routines please", "y", "+", "👍"]


def run(*args):
    return subprocess.run([sys.executable, "-B", "-I", str(TERMS_SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)


def section(text, start, end):
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.release = self.tmp / "release"
        self.release.mkdir()
        for name in ("TERMS-NOTICE.md", "TERMS-NOTICE.ru.md", "TERMS.md", "VERSION"):
            shutil.copy2(ROOT_DIR / name, self.release / name)
        self.record = self.tmp / "ws" / "terms-acceptance.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestNotice(Base):
    """Item 8: a fixed, versioned text, shown verbatim; the shown text equals the shipped file."""

    def test_shown_text_is_the_shipped_text(self):
        shipped = (ROOT_DIR / "TERMS-NOTICE.md").read_text(encoding="utf-8")
        body = shipped.split("<!-- notice:begin -->")[1].split("<!-- notice:end -->")[0].strip()
        r = run("show", "--release", ROOT_DIR, "--locale", "en")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["text"], body)
        self.assertEqual(out["sha256"], hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.assertEqual((out["locale"], out["notice_version"], out["terms_version"]), ("en", "3", "3"))
        self.assertEqual(out["yes_answers"], ["Yes, with routines", "Yes, without routines"])
        self.assertEqual(out["no_answer"], "No")

    def test_notice_wording(self):
        body = terms.notice(ROOT_DIR)["text"]
        notice_credit = re.search(r"(?m)^\s+Based on (BotCEO by .+?) — ",
                                  (ROOT_DIR / "NOTICE").read_text(encoding="utf-8")).group(1)
        for needle in ["BotCEO is free.", f'"Based on {notice_credit}"', "(BotCEO License 1.0)",
                       "you may not pass them on", 'By choosing "Yes" you accept these terms.',
                       "In this closed test, remarks you write to the Mentor about the course are sent to the "
                       "author with a random installation ID, without your name. To stop, tell the Mentor "
                       "«не отправляй». By choosing"]:
            self.assertIn(needle, body)
        # The links are filled at release: check the structure, not the placeholder.
        self.assertRegex(body, r"Full terms: \S.*? · Privacy: \S.*?\. By choosing")
        self.assertTrue(body.endswith('By choosing "Yes" you accept these terms.'))
        self.assertNotIn("telemetry", body.lower(), "the telemetry line comes only with the first telemetry release")

    def test_russian_draft_is_not_shown(self):
        ru = (ROOT_DIR / "TERMS-NOTICE.ru.md").read_text(encoding="utf-8")
        self.assertRegex(ru, r"(?m)^Status: draft$")
        self.assertIn("ЧЕРНОВИК", ru)
        out = json.loads(run("show", "--release", ROOT_DIR, "--locale", "ru").stdout)
        self.assertEqual(out["locale"], "en", "an unreviewed translation is never shown")
        self.assertEqual(out["yes_answers"], ["Да, с рутинами", "Да, без рутин"])
        self.assertEqual(out["no_answer"], "Нет")

    def test_reviewed_translation_is_shown(self):
        p = self.release / "TERMS-NOTICE.ru.md"
        p.write_text(p.read_text(encoding="utf-8").replace("Status: draft", "Status: reviewed"), encoding="utf-8")
        out = terms.notice(self.release, "ru-RU")
        self.assertEqual(out["locale"], "ru")
        self.assertTrue(out["text"].startswith("BotCEO бесплатен."))
        p.write_text(p.read_text(encoding="utf-8").replace("Notice version: 3", "Notice version: 0"), encoding="utf-8")
        self.assertEqual(terms.notice(self.release, "ru")["locale"], "en", "a stale translation is not shown")

    def test_other_language_gets_english_text_and_labels(self):
        out = json.loads(run("show", "--release", self.release, "--locale", "de").stdout)
        self.assertEqual(out["locale"], "en")
        self.assertEqual(out["yes_answers"], ["Yes, with routines", "Yes, without routines"])

    def test_update_labels(self):
        out = json.loads(run("show", "--release", self.release, "--locale", "ru", "--mode", "update").stdout)
        self.assertEqual((out["yes_answers"], out["no_answer"]), (["Да"], "Нет"))

    def test_broken_notice_fails_closed(self):
        (self.release / "TERMS-NOTICE.md").write_text("no markers\n", encoding="utf-8")
        r = run("show", "--release", self.release)
        self.assertEqual(r.returncode, 1)
        self.assertIn("error", json.loads(r.stdout))


class TestAcceptance(Base):
    """Items 10, 11, 13: only the button or its exact words; recorded locally only."""

    def test_vague_and_blanket_replies_record_nothing(self):
        for words in VAGUE:
            with self.subTest(answer=words):
                r = run("accept", "--release", self.release, "--record", self.record, "--locale", "ru",
                        "--answer", words)
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertFalse(json.loads(r.stdout)["accepted"])
                self.assertFalse(self.record.exists())

    def test_exact_buttons_accept(self):
        for loc, words in [("ru", "Да, с рутинами"), ("ru", "Да, без рутин"), ("ru", "  да, без рутин. "),
                           ("en", "Yes, with routines"), ("en", "yes, without routines!"),
                           ("ru", "Yes, without routines")]:
            with self.subTest(answer=words):
                self.record.unlink(missing_ok=True)
                r = run("accept", "--release", self.release, "--record", self.record, "--locale", loc,
                        "--answer", words)
                self.assertEqual(r.returncode, 0, r.stdout)
                rec = json.loads(self.record.read_text(encoding="utf-8"))
                self.assertEqual(rec["answer"], words)

    def test_record_fields(self):
        r = run("accept", "--release", self.release, "--record", self.record, "--locale", "ru",
                "--answer", "Да, без рутин")
        self.assertEqual(r.returncode, 0, r.stdout)
        rec = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertEqual(sorted(rec), sorted(terms.RECORD_FIELDS))
        shown = terms.notice(self.release, "ru")
        self.assertEqual(rec["terms_version"], "3")
        self.assertEqual(rec["notice_version"], "3")
        self.assertEqual(rec["notice_sha256"], shown["sha256"])
        self.assertEqual((rec["locale"], rec["ui_locale"], rec["mode"]), ("en", "ru", "install"))
        self.assertEqual(rec["release_version"], (ROOT_DIR / "VERSION").read_text().strip())
        self.assertRegex(rec["accepted_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_update_answers(self):
        for words, ok in [("Да", True), ("Да, и ещё 1, 3", True), ("да, и ещё 2", True), ("Yes", True),
                          ("Yes, and also 1,2", True), ("Да, и ещё всё", False), ("Да, с рутинами", False),
                          ("ок", False), ("Да, но потом", False)]:
            with self.subTest(answer=words):
                self.assertIs(terms.is_acceptance(words, "ru", "update"), ok)

    def test_no_network(self):
        """Item 11: the script has no network code, and accepting works with the network cut."""
        tree = ast.parse(TERMS_SCRIPT.read_text(encoding="utf-8"))
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(imported & {"socket", "ssl", "http", "urllib", "requests", "subprocess", "ftplib",
                                     "smtplib", "asyncio"}, imported)

        def no_net(*a, **k):
            raise AssertionError("network call")
        with mock.patch.object(socket, "socket", no_net), mock.patch.object(socket, "create_connection", no_net):
            out = terms.accept(self.release, self.record, "Да, без рутин", "ru")
        self.assertTrue(out["accepted"])

    def test_record_never_reaches_the_sender(self):
        """The only network command of the release (progress.py flush) never reads the record."""
        for rel in ("course/progress.py", "scripts/sync-data.sh"):
            self.assertNotIn("terms-acceptance", (ROOT_DIR / rel).read_text(encoding="utf-8"), rel)


class TestRequireAndCheck(Base):
    """Items 12, 13: nothing is built or swapped without an acceptance of the current terms."""

    def accept(self, words="Да, без рутин", locale="ru", mode="install"):
        return terms.accept(self.release, self.record, words, locale, mode)

    def test_require_without_record(self):
        r = run("require", "--release", self.release, "--record", self.record)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(json.loads(r.stdout)["ok"])
        self.assertTrue(json.loads(run("check", "--release", self.release, "--record", self.record).stdout)["show"])

    def test_require_after_accept(self):
        self.accept()
        self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 0)
        self.assertFalse(json.loads(run("check", "--release", self.release, "--record", self.record).stdout)["show"])

    def test_new_terms_version_asks_again(self):
        self.accept()
        p = self.release / "TERMS.md"
        p.write_text(p.read_text(encoding="utf-8").replace("Version 3 ·", "Version 4 ·", 1), encoding="utf-8")
        out = json.loads(run("check", "--release", self.release, "--record", self.record).stdout)
        self.assertTrue(out["show"])
        self.assertIn("terms version changed", out["reason"])
        self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 2)
        self.assertTrue(self.accept("Да, и ещё 2", mode="update")["accepted"])
        self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 0)

    def test_tampered_or_broken_record(self):
        self.accept()
        rec = json.loads(self.record.read_text(encoding="utf-8"))
        for change in ({"notice_sha256": "0" * 64}, {"answer": "ok"}, {"notice_version": "0"}):
            with self.subTest(change=change):
                self.record.write_text(json.dumps({**rec, **change}), encoding="utf-8")
                self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 2)
        self.record.write_text("{", encoding="utf-8")
        self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 2)
        self.record.write_text(json.dumps({"terms_version": "3"}), encoding="utf-8")
        self.assertEqual(run("require", "--release", self.release, "--record", self.record).returncode, 2)

    def test_rejected_answer_keeps_an_old_record(self):
        self.accept()
        before = self.record.read_bytes()
        self.assertFalse(self.accept("ok")["accepted"])
        self.assertEqual(self.record.read_bytes(), before)


class TestInstructions(unittest.TestCase):
    """Items 8, 9, 12, 13 in the bot's recipes: the notice is part of the plan; no third question;
    nothing is created before the acceptance is recorded."""

    def setUp(self):
        self.loading = (ROOT_DIR / "LOADING-INSTRUCTIONS.md").read_text(encoding="utf-8")
        self.update = (ROOT_DIR / "UPDATE.md").read_text(encoding="utf-8")

    def test_install_step_6_shows_and_records(self):
        step6 = section(self.loading, "## 6. Plan and approval", "## 7.")
        for needle in ["terms.py show --release grokbotceo --locale <ll>", "**verbatim**", "`yes_answers`",
                       "`no_answer`", "terms.py accept --release grokbotceo --record terms-acceptance.json",
                       '--answer "<the user\'s exact answer words>"', "never\nfrom other free text, silence or a change of topic",
                       "show the same form again", "never sent anywhere"]:
            self.assertIn(needle, step6)
        self.assertLess(step6.index("terms.py show"), step6.index('Ask: "Shall I do this?"'))
        self.assertEqual(len(re.findall(r"\bAsk( one question)?:", step6)), 1, "no third question")

    def test_install_build_is_gated(self):
        step7 = section(self.loading, "## 7. Build", "## 8.")
        self.assertLess(step7.index("terms.py require --release grokbotceo --record terms-acceptance.json"),
                        step7.index("bot-payload-compiler.py build"))
        self.assertLess(self.loading.index("terms.py require"), self.loading.index("Call `CreateAgent`"))
        self.assertIn("git add .gitignore config.json VERSION terms-acceptance.json", self.loading)

    def test_update_reasks_on_new_terms(self):
        step7 = section(self.update, "## 7. One plan, one form", "## 8.")
        for needle in ["terms.py check --release build/update/release --record terms-acceptance.json",
                       "--mode update", "**verbatim**", "terms.py accept", "show the same form again"]:
            self.assertIn(needle, step7)
        self.assertLess(step7.index("terms.py accept"), step7.index("U approve [--bots"))
        step8 = section(self.update, "## 8. Swap", "## 9.")
        self.assertLess(step8.index("terms.py require"), step8.index("update-plan.py swap"))
        self.assertIn("git add terms-acceptance.json", self.update)

    def test_readme_names_the_notice(self):
        for name in ("README.md", "README.ru.md"):
            self.assertIn("(TERMS-NOTICE.md)", (ROOT_DIR / name).read_text(encoding="utf-8"))


def bash_block(md_text, heading, nth=0):
    """The nth ```bash block of the section that starts with `heading`."""
    sec = md_text[md_text.index(heading):]
    sec = sec[:sec.find("\n## ", 1)] if "\n## " in sec[1:] else sec
    return re.findall(r"```bash\n(.*?)```", sec, re.S)[nth]


def tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def copy_release(dst, version=None):
    dst.mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(ROOT_DIR / "bots", dst / "bots", ignore=ignore)
    shutil.copytree(ROOT_DIR / "scripts", dst / "scripts", ignore=ignore)
    for name in ("TERMS.md", "TERMS-NOTICE.md", "TERMS-NOTICE.ru.md", "UPDATE.md", "VERSION"):
        shutil.copy2(ROOT_DIR / name, dst / name)
    if version:
        (dst / "VERSION").write_text(version + "\n")
    return dst


class TestDocumentedBlocksStop(unittest.TestCase):
    """P1 (Codex review): the documented shell blocks, run whole as the bot runs them, stop without a
    valid acceptance: no payloads, no swap, no state change, nonzero exit. With one they succeed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / "ws"
        self.ws.mkdir()
        self.home = self.tmp / "home"
        agent = self.home / "agent-data" / "agents" / "main-0001"
        agent.mkdir(parents=True)
        (agent / "profile.json").write_text(json.dumps({"name": "Grok", "description": "Old text"}))
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
        self.env["PATH"] = str(Path(sys.executable).parent) + ":" + self.env["PATH"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_block(self, block):
        return subprocess.run(["bash", "-c", block], cwd=self.tmp, env=self.env, capture_output=True, text=True,
                              timeout=120)

    # ---- install, LOADING-INSTRUCTIONS step 7

    def install_fixture(self):
        self.rel = copy_release(self.ws / "grokbotceo")
        (self.ws / "config.json").write_text(json.dumps({
            "WORKSPACE_PATH": str(self.ws), "BOT_MAKER_BOT": "Bot Maker", "MENTOR_BOT": "Mentor",
            "REMINDER_BOT": "Reminder", "TRANSLATOR_BOT": "Translator", "MONITOR_BOT": "Monitor"}))
        block = bash_block((ROOT_DIR / "LOADING-INSTRUCTIONS.md").read_text(encoding="utf-8"), "## 7. Build")
        self.assertIn("terms.py require", block)
        return block.replace("<WORKSPACE_PATH>", str(self.ws)).replace("<main bot agent_id>", "main-0001")

    def assert_install_refused(self, block):
        before = tree(self.ws)
        r = self.run_block(block)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.ws / "build").exists(), "nothing is built without the acceptance")
        self.assertEqual(tree(self.ws), before)

    def test_install_block_refuses_without_receipt(self):
        self.assert_install_refused(self.install_fixture())

    def test_install_block_refuses_with_invalid_receipt(self):
        block = self.install_fixture()
        record = self.ws / "terms-acceptance.json"
        for bad in ("{", json.dumps({"terms_version": "3"})):
            with self.subTest(record=bad):
                record.write_text(bad)
                self.assert_install_refused(block)
        terms.accept(self.rel, record, "Да, без рутин", "ru")
        tos = self.rel / "TERMS.md"
        tos.write_text(tos.read_text(encoding="utf-8").replace("Version 3 ·", "Version 4 ·", 1), encoding="utf-8")
        self.assert_install_refused(block)

    def test_install_block_builds_with_receipt(self):
        block = self.install_fixture()
        self.assertTrue(terms.accept(self.rel, self.ws / "terms-acceptance.json", "Да, без рутин", "ru")["accepted"])
        r = self.run_block(block)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        built = sorted(p.name for p in (self.ws / "build").glob("*.payload.json"))
        self.assertEqual(built, sorted(f"{b}.payload.json" for b in
                                       ("bot-maker", "mentor", "reminder", "translator", "monitor", "main-grok")))

    # ---- update, UPDATE.md step 8

    def update_fixture(self):
        old = self.ws / "grokbotceo"
        old.mkdir()
        (old / "VERSION").write_text("0.2.0\n")
        self.staging = copy_release(self.ws / "build" / "update" / "release")
        self.version = (ROOT_DIR / "VERSION").read_text().strip()
        block = bash_block((ROOT_DIR / "UPDATE.md").read_text(encoding="utf-8"), "## 8. Swap")
        self.assertIn("terms.py require", block)
        self.assertIn("update-plan.py swap", block)
        return block.replace("<WORKSPACE_PATH>", str(self.ws)).replace("<tag>", "v" + self.version)

    def assert_not_swapped(self, before):
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), "0.2.0")
        self.assertFalse((self.ws / "grokbotceo.old").exists())
        self.assertFalse((self.ws / "update-state.json").exists())
        self.assertEqual(tree(self.ws), before)

    def test_update_block_refuses_without_receipt(self):
        block = self.update_fixture()
        before = tree(self.ws)
        r = self.run_block(block)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_not_swapped(before)

    def test_swap_itself_refuses_without_receipt(self):
        """The prose gate skipped: swap alone still refuses, nothing changes."""
        self.update_fixture()
        before = tree(self.ws)
        for record in (None, "{", json.dumps({"terms_version": "3"})):
            with self.subTest(record=record):
                if record is not None:
                    (self.ws / "terms-acceptance.json").write_text(record)
                    before = tree(self.ws)
                r = subprocess.run([sys.executable, "-B", "-I", str(self.staging / "scripts" / "update-plan.py"),
                                    "swap", "--workspace", str(self.ws), "--expect-version", "v" + self.version],
                                   capture_output=True, text=True, env=self.env)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn("not accepted", r.stderr)
                self.assert_not_swapped(before)

    def test_update_block_swaps_with_receipt(self):
        block = self.update_fixture()
        self.assertTrue(terms.accept(self.staging, self.ws / "terms-acceptance.json", "Да, и ещё 1", "ru",
                                     "update")["accepted"])
        r = self.run_block(block)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), self.version)
        self.assertTrue((self.ws / "grokbotceo.old").is_dir())


if __name__ == "__main__":
    unittest.main()
