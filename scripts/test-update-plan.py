#!/usr/bin/env python3
"""
Tests for update-plan.py (UPDATE.md bookkeeping). Model-free, no network, temp folders only.

Covered: every status (unchanged, changed, missing_copy, new, removed), the missing-copy case of a
real 0.2.0 install (bots/core/bot-maker/agent.json only, Mentor created without a copy, no main-bot
copy), "edited": true, the main bot (unchanged / changed / missing copy / never extended / older
part that cannot be matched), bots/my and bots/marketplace never touched (even with a clashing
name), config keys (added, never overwritten, unknown ones dropped from the build config), version
checks, the atomic swap (refused staging and a failed rename both leave the old tree), record and
finish.

Partial update and resume (Codex 021 review): a failed UpdateAgent leaves the update partial (VERSION
not moved, `version` says resume), resume re-applies only unfinished bots and still recognises the old
main-bot block after the swap, created bots are never created twice, kept/unticked bots never become
pending, an edit after the plan stops that bot (recheck) and survives a resume with a stale payload,
a swap cut off after the first rename is restored by the next command, MISMATCH / NOT VERIFIED keep
the confirmed baseline and leave the bot unfinished.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RELEASE_DIR = SCRIPT_DIR.parent
UPDATE_SCRIPT = SCRIPT_DIR / "update-plan.py"
COMPILER = SCRIPT_DIR / "bot-payload-compiler.py"
CORE_BOTS = ("bot-maker", "mentor", "reminder", "translator", "monitor")

spec = importlib.util.spec_from_file_location("update_plan", UPDATE_SCRIPT)
update_plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_plan)

CONFIG = {"WORKSPACE_PATH": "/workspace", "BOT_MAKER_BOT": "Bot Maker", "MENTOR_BOT": "Ментор",
          "REMINDER_BOT": "Напоминальник", "TRANSLATOR_BOT": "Переводчик", "MONITOR_BOT": "Монитор",
          "IMPROVEMENTS_CHANNEL_ID": "chan-1"}


def run(*args):
    return subprocess.run([sys.executable, "-B", "-I", str(UPDATE_SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True)


def tree(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def copy_release(dst: Path, version: str = None, block_extra: str = "") -> Path:
    """A copy of this release tree (bots, scripts, VERSION, UPDATE.md), optionally changed."""
    dst.mkdir(parents=True)
    shutil.copytree(RELEASE_DIR / "bots", dst / "bots")
    (dst / "scripts").mkdir()
    for name in ("bot-payload-compiler.py", "bot-mirror.py"):
        shutil.copy2(SCRIPT_DIR / name, dst / "scripts" / name)
    shutil.copy2(RELEASE_DIR / "UPDATE.md", dst / "UPDATE.md")
    (dst / "VERSION").write_text((version or (RELEASE_DIR / "VERSION").read_text().strip()) + "\n")
    if block_extra:
        block = dst / "bots" / "main-grok" / "block.md"
        block.write_text(block.read_text(encoding="utf-8").replace(
            "If you are not sure", block_extra + "\n\nIf you are not sure"), encoding="utf-8")
    return dst


def compile_build(release: Path, config: Path, out: Path, bots=CORE_BOTS):
    r = subprocess.run([sys.executable, "-B", "-I", str(release / "scripts" / "bot-payload-compiler.py"),
                        "build", "--config", str(config), "--bots", ",".join(bots), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


class Fixture(unittest.TestCase):
    """A workspace with an old release (grokbotceo/), a new one (build/update/release) and live bots."""

    OLD_VERSION = "0.2.0"
    NEW_VERSION = "0.2.1"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / "workspace"
        self.ws.mkdir()
        self.agents = self.tmp / "agents"
        self.agents.mkdir()
        # old release: the main block without the new line; new release: same tree, a changed block
        # and a changed Translator text, so "update" has something to do
        self.old = copy_release(self.ws / "grokbotceo", self.OLD_VERSION)
        self.new = copy_release(self.ws / "build" / "update" / "release", self.NEW_VERSION,
                                block_extra="New line of release 0.2.1.")
        tr = self.new / "bots" / "translator" / "prompt.md"
        tr.write_text(tr.read_text(encoding="utf-8") + "\nNew rule of 0.2.1.\n", encoding="utf-8")
        (self.ws / "config.json").write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
        (self.ws / "VERSION").write_text(self.OLD_VERSION + "\n")
        self.out = self.ws / "build" / "update" / "out"
        # the texts as the OLD release built them (what was installed)
        self.old_build = self.tmp / "old-build"
        compile_build(self.old, self.ws / "config.json", self.old_build)
        self.n = 0

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers
    def agent(self, name, description, agent_id=None):
        self.n += 1
        agent_id = agent_id or f"agent-{self.n:04d}"
        d = self.agents / agent_id
        d.mkdir(parents=True)
        (d / "profile.json").write_text(json.dumps({"name": name, "description": description, "harness": "x"},
                                                   ensure_ascii=False), encoding="utf-8")
        return agent_id

    def old_text(self, bot):
        return (self.old_build / f"{bot}.md").read_text(encoding="utf-8")

    def old_name(self, bot):
        return json.loads((self.old_build / f"{bot}.payload.json").read_text(encoding="utf-8"))["name"]

    def core(self, bot, agent_id, prompt=None, **extra):
        d = self.ws / "bots" / "core" / bot
        d.mkdir(parents=True, exist_ok=True)
        rec = {"agent_id": agent_id, "check": "VERIFIED", "version": self.OLD_VERSION, "edited": False}
        rec.update(extra)
        (d / "agent.json").write_text(json.dumps(rec), encoding="utf-8")
        if prompt is not None:
            (d / "prompt.md").write_text(prompt, encoding="utf-8")
        return d

    def installed(self, bot, live_text=None, copy=True, **extra):
        """A core bot installed by the old release; live_text overrides what runs now."""
        text = self.old_text(bot)
        aid = self.agent(self.old_name(bot), text if live_text is None else live_text)
        self.core(bot, aid, text if copy else None, **extra)
        return aid

    def old_block(self):
        c = update_plan.load_compiler(self.old)
        return c.resolve_placeholders(c.load_extension_block(self.old / "bots" / "main-grok"), CONFIG).strip()

    def new_block(self):
        c = update_plan.load_compiler(self.new)
        return c.resolve_placeholders(c.load_extension_block(self.new / "bots" / "main-grok"), CONFIG).strip()

    def main_installed(self, own="I am the user's helper.", copy=True, live=None):
        combined = update_plan.combine(own, self.old_block())
        aid = self.agent("Grok", combined if live is None else live)
        if copy:
            d = self.core("main-grok", aid, combined, mode="extended")
            (d / "previous.md").write_text(own, encoding="utf-8")
        return aid

    def plan(self, *extra, ok=True):
        r = run("config", "--workspace", self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        compile_build(self.new, self.out / "config.json", self.out)
        r = run("plan", "--workspace", self.ws, "--agents-dir", self.agents, *extra)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
            return {e["bot"]: e for e in json.loads(r.stdout)["bots"]}
        return r


class TestStatuses(Fixture):
    def test_every_status(self):
        self.installed("bot-maker")                                     # unchanged, text same -> none
        self.installed("translator")                                    # unchanged, release changed -> update
        self.installed("mentor", live_text=self.old_text("mentor") + "\nMy own rule.")  # changed -> ask
        self.installed("monitor", live_text=self.old_text("monitor") + "\nTweak.", copy=False)  # missing_copy -> ask
        # reminder: never installed -> new / offer
        self.core("old-helper", "agent-gone", "old text")              # removed -> leave
        plan = self.plan()
        st = {b: (e["status"], e["action"]) for b, e in plan.items()}
        self.assertEqual(st["bot-maker"], ("unchanged", "none"))
        self.assertEqual(st["translator"], ("unchanged", "update"))
        self.assertEqual(st["mentor"], ("changed", "ask"))
        self.assertEqual(st["monitor"], ("missing_copy", "ask"))
        self.assertEqual(st["reminder"], ("new", "offer"))
        self.assertEqual(st["old-helper"], ("removed", "leave"))
        # update payload is exactly agent_id + the new text; never a name
        upd = json.loads((self.ws / plan["translator"]["update_payload"]).read_text(encoding="utf-8"))
        self.assertEqual(set(upd), {"agent_id", "description"})
        self.assertIn("New rule of 0.2.1.", upd["description"])
        self.assertGreaterEqual(plan["translator"]["diff_release"]["added"], 1)
        self.assertEqual(plan["translator"]["diff_release"]["removed"], 0)
        self.assertIsNone(plan["bot-maker"]["update_payload"])
        # the changed bot: the live diff shows the user's own line would go
        self.assertGreaterEqual(plan["mentor"]["diff_live"]["removed"], 1)
        live_diff = (self.ws / plan["mentor"]["diff_live"]["file"]).read_text(encoding="utf-8")
        self.assertIn("-My own rule.", live_diff)
        saved = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["target_version"], "0.2.1")
        self.assertEqual(saved["counts"]["new"], 1)

    def test_edited_flag_means_changed(self):
        # Bot Maker replaced prompt.md after a change and set edited: live == copy, still changed
        text = self.old_text("translator") + "\nUser rule."
        aid = self.agent(self.old_name("translator"), text)
        self.core("translator", aid, text, edited=True)
        plan = self.plan()
        self.assertEqual((plan["translator"]["status"], plan["translator"]["action"]), ("changed", "ask"))

    def test_recorded_bot_gone_is_offered_again(self):
        self.core("reminder", "agent-deleted", self.old_text("reminder"))
        plan = self.plan()
        self.assertEqual((plan["reminder"]["status"], plan["reminder"]["action"]), ("new", "offer"))
        self.assertIsNone(plan["reminder"]["agent_id"])

    def test_two_bots_with_the_name_are_skipped(self):
        self.agent("Ментор", "a")
        self.agent("Ментор", "b")
        plan = self.plan()
        self.assertEqual(plan["mentor"]["action"], "skip")
        self.assertEqual(len(plan["mentor"]["candidates"]), 2)
        self.assertFalse((self.out / "mentor.update.json").exists())


class TestWorkingAccount020(Fixture):
    """The 0.2.0 layout seen live: bots/core/bot-maker/agent.json only, Mentor created, no copies."""

    def test_missing_copies(self):
        bm = self.agent("Bot Maker", self.old_text("bot-maker"))
        self.core("bot-maker", bm, None)                       # agent.json only
        mentor = self.agent("Ментор", self.old_text("mentor"))  # created, no bots/core/mentor
        main = self.agent("Grok", update_plan.combine("Own text.", self.old_block()))
        plan = self.plan("--main-agent-id", main)
        self.assertEqual(plan["bot-maker"]["status"], "missing_copy")
        self.assertEqual(plan["bot-maker"]["agent_id"], bm)
        self.assertEqual(plan["bot-maker"]["agent_id_from"], "record")
        self.assertEqual(plan["mentor"]["status"], "missing_copy")
        self.assertEqual(plan["mentor"]["agent_id"], mentor)
        self.assertEqual(plan["mentor"]["agent_id_from"], "name")
        # live text cannot be compared with a copy: the user is asked, unless nothing would change
        self.assertIn(plan["bot-maker"]["action"], ("ask", "none"))
        self.assertIsNone(plan["bot-maker"]["diff_release"])
        self.assertIsNotNone(plan["bot-maker"]["diff_live"])
        for bot in ("reminder", "translator", "monitor"):
            self.assertEqual(plan[bot]["status"], "new", bot)
        m = plan["main-grok"]
        self.assertEqual((m["status"], m["action"]), ("missing_copy", "ask"))
        new = (self.ws / m["expected"]).read_text(encoding="utf-8")
        self.assertTrue(new.startswith("Own text.\n\n"))
        self.assertIn("New line of release 0.2.1.", new)
        self.assertEqual(new.count("GrokBotCEO. You are the user's main bot"), 1)

    def test_main_bot_not_found_is_skipped(self):
        plan = self.plan()
        self.assertEqual((plan["main-grok"]["status"], plan["main-grok"]["action"]), ("missing_copy", "skip"))


class TestMainBot(Fixture):
    def test_unchanged_keeps_own_part(self):
        self.main_installed()
        m = self.plan()["main-grok"]
        self.assertEqual((m["status"], m["action"]), ("unchanged", "update"))
        new = (self.ws / m["expected"]).read_text(encoding="utf-8")
        self.assertEqual(new, update_plan.combine("I am the user's helper.", self.new_block()))
        upd = json.loads((self.ws / m["update_payload"]).read_text(encoding="utf-8"))
        self.assertEqual(set(upd), {"agent_id", "description"})

    def test_changed_own_part_is_asked_and_kept(self):
        own = "I am the user's helper.\nAlways answer in two lines."
        live = update_plan.combine(own, self.old_block())
        self.main_installed(live=live)
        m = self.plan()["main-grok"]
        self.assertEqual((m["status"], m["action"]), ("changed", "ask"))
        new = (self.ws / m["expected"]).read_text(encoding="utf-8")
        self.assertTrue(new.startswith(own))

    def test_never_extended_is_offered(self):
        aid = self.agent("Grok", "Plain main bot.")
        self.core("main-grok", aid, "Plain main bot.", check="NOT APPLIED", mode="extended")
        m = self.plan()["main-grok"]
        self.assertEqual(m["action"], "offer")
        new = (self.ws / m["expected"]).read_text(encoding="utf-8")
        self.assertEqual(new, update_plan.combine("Plain main bot.", self.new_block()))

    def test_unmatched_older_part_is_never_doubled(self):
        aid = self.agent("Grok", "Own.\n\nGrokBotCEO. An old rc block that no release tree has.")
        plan = self.plan("--main-agent-id", aid)
        self.assertEqual(plan["main-grok"]["action"], "skip")
        self.assertFalse((self.out / "main-grok.update.json").exists())

    def test_already_current(self):
        aid = self.agent("Grok", update_plan.combine("Own.", self.new_block()))
        m = self.plan("--main-agent-id", aid)["main-grok"]
        self.assertEqual(m["action"], "none")


class TestNeverTouched(Fixture):
    def test_bots_my_and_marketplace_untouched(self):
        # the user's own bot carries a core bot's name: it must never be matched or touched
        own = self.agent("Монитор", "My own monitor, made through Bot Maker.")
        imp = self.agent("Переводчик", "An imported translator.")
        d = self.ws / "bots" / "my" / "monitor"
        d.mkdir(parents=True)
        (d / "prompt.md").write_text("My own monitor, made through Bot Maker.", encoding="utf-8")
        (d / "agent.json").write_text(json.dumps({"agent_id": own, "check": "VERIFIED"}))
        d = self.ws / "bots" / "marketplace" / "perevodchik"
        d.mkdir(parents=True)
        (d / "prompt.md").write_text("An imported translator.", encoding="utf-8")
        (d / "agent.json").write_text(json.dumps({"agent_id": imp, "source": "marketplace"}))
        self.installed("bot-maker")
        my_before = tree(self.ws / "bots" / "my")
        mk_before = tree(self.ws / "bots" / "marketplace")
        agents_before = tree(self.agents)
        config_before = (self.ws / "config.json").read_bytes()
        plan = self.plan()
        self.assertEqual((plan["monitor"]["status"], plan["monitor"]["agent_id"]), ("new", None))
        self.assertEqual((plan["translator"]["status"], plan["translator"]["agent_id"]), ("new", None))
        ids = {e.get("agent_id") for e in plan.values()}
        self.assertNotIn(own, ids)
        self.assertNotIn(imp, ids)
        for p in self.out.glob("*.update.json"):
            self.assertNotIn(json.loads(p.read_text(encoding="utf-8"))["agent_id"], (own, imp))
        # the rest of the flow: the user ticks every ask bot, record every planned bot, finish
        asks = ",".join(b for b, e in plan.items() if e["action"] == "ask")
        self.assertEqual(run("approve", "--workspace", self.ws, "--bots", asks).returncode, 0)
        for bot, e in plan.items():
            if e["action"] in ("update", "none", "ask"):
                r = run("record", "--workspace", self.ws, "--bot", bot, "--check", "VERIFIED")
                self.assertEqual(r.returncode, 0, r.stderr)
        r = run("swap", "--workspace", self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run("finish", "--workspace", self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("bots/my", json.loads(r.stdout)["git_add"])
        self.assertEqual(tree(self.ws / "bots" / "my"), my_before)
        self.assertEqual(tree(self.ws / "bots" / "marketplace"), mk_before)
        self.assertEqual(tree(self.agents), agents_before, "live bot folders are only read")
        self.assertEqual((self.ws / "config.json").read_bytes(), config_before)

    def test_record_refuses_leave_and_skip(self):
        self.core("old-helper", "agent-x", "old")
        self.plan()
        r = run("record", "--workspace", self.ws, "--bot", "old-helper", "--check", "VERIFIED")
        self.assertNotEqual(r.returncode, 0)
        r = run("record", "--workspace", self.ws, "--bot", "../my/x", "--check", "VERIFIED")
        self.assertNotEqual(r.returncode, 0)


class TestConfig(Fixture):
    def test_missing_key_is_added_never_overwritten(self):
        cfg = dict(CONFIG)
        del cfg["MONITOR_BOT"]
        cfg["OLD_REMOVED_KEY"] = "x"
        (self.ws / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        r = run("config", "--workspace", self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([m["key"] for m in out["missing"]], ["MONITOR_BOT"])
        self.assertEqual(out["unknown"], ["OLD_REMOVED_KEY"])
        build_cfg = json.loads((self.out / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("OLD_REMOVED_KEY", build_cfg)
        # --apply refused while a key is missing
        self.assertNotEqual(run("config", "--workspace", self.ws, "--apply").returncode, 0)
        # overwriting a key the user set is refused
        r = run("config", "--workspace", self.ws, "--set", "MENTOR_BOT=Mentor")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("never changed", r.stderr)
        r = run("config", "--workspace", self.ws, "--set", "MONITOR_BOT=Монитор", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        saved = json.loads((self.ws / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["MONITOR_BOT"], "Монитор")
        self.assertEqual(saved["OLD_REMOVED_KEY"], "x", "user keys stay in config.json")
        self.assertEqual(saved["MENTOR_BOT"], "Ментор")


class TestVersion(Fixture):
    def v(self, *args):
        r = run("version", "--workspace", self.ws, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_versions(self):
        self.assertEqual(self.v()["action"], "update")
        self.assertEqual(self.v("--target", "v0.2.1")["target"], "0.2.1")
        self.assertEqual(self.v("--target", "v0.2.0")["action"], "current")
        self.assertEqual(self.v("--target", "v0.1.9")["action"], "newer_installed")
        (self.ws / "VERSION").write_text("0.2.0-rc6\n")
        self.assertEqual(self.v("--target", "v0.2.0")["action"], "update")
        (self.ws / "VERSION").unlink()
        self.assertEqual(self.v()["action"], "not_installed")
        (self.ws / "installed").mkdir()
        (self.ws / "installed" / "VERSION").write_text("0.1.0-rc3\n")
        self.assertEqual(self.v()["installed"], "0.1.0-rc3")
        self.assertEqual(self.v()["action"], "update")


class TestSwap(Fixture):
    def test_swap_replaces_tree(self):
        r = run("swap", "--workspace", self.ws, "--expect-version", "v0.2.1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), "0.2.1")
        self.assertFalse((self.ws / "build" / "update" / "release").exists())
        self.assertFalse((self.ws / "build" / "update" / "release.old").exists())

    def test_incomplete_staging_leaves_old_tree(self):
        before = tree(self.old)
        (self.new / "scripts" / "bot-payload-compiler.py").unlink()   # a half-done fetch
        r = run("swap", "--workspace", self.ws)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(tree(self.ws / "grokbotceo"), before)

    def test_missing_staging_leaves_old_tree(self):
        before = tree(self.old)
        shutil.rmtree(self.new)
        self.assertNotEqual(run("swap", "--workspace", self.ws).returncode, 0)
        self.assertEqual(tree(self.ws / "grokbotceo"), before)

    def test_wrong_version_leaves_old_tree(self):
        before = tree(self.old)
        self.assertNotEqual(run("swap", "--workspace", self.ws, "--expect-version", "0.3.0").returncode, 0)
        self.assertEqual(tree(self.ws / "grokbotceo"), before)

    def test_failed_rename_puts_old_tree_back(self):
        before = tree(self.old)
        real = os.rename
        calls = []

        def flaky(src, dst):
            calls.append((src, dst))
            if len(calls) == 2:  # the staging -> grokbotceo rename
                raise OSError("simulated failure")
            return real(src, dst)

        args = update_plan.build_parser().parse_args(["swap", "--workspace", str(self.ws)])
        update_plan.resolve_args(args)
        update_plan.os.rename = flaky
        try:
            with self.assertRaises(OSError):
                update_plan.cmd_swap(args)
        finally:
            update_plan.os.rename = real
        self.assertEqual(tree(self.ws / "grokbotceo"), before)
        self.assertTrue((self.new / "VERSION").exists(), "staging is kept for a retry")


class TestRecordAndFinish(Fixture):
    def test_record_refreshes_copy(self):
        aid = self.installed("reminder", routine="asked")
        self.installed("translator")
        main = self.main_installed()
        plan = self.plan()
        self.assertEqual(run("approve", "--workspace", self.ws).returncode, 0)
        r = run("record", "--workspace", self.ws, "--bot", "translator", "--check", "VERIFIED")
        self.assertEqual(r.returncode, 0, r.stderr)
        core = self.ws / "bots" / "core" / "translator"
        self.assertIn("New rule of 0.2.1.", (core / "prompt.md").read_text(encoding="utf-8"))
        rec = json.loads((core / "agent.json").read_text())
        self.assertEqual((rec["version"], rec["edited"], rec["check"]), ("0.2.1", False, "VERIFIED"))
        r = run("record", "--workspace", self.ws, "--bot", "reminder", "--check", "VERIFIED")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads((self.ws / "bots" / "core" / "reminder" / "agent.json").read_text())
        self.assertEqual((rec["agent_id"], rec["routine"]), (aid, "asked"), "routine state is kept")
        r = run("record", "--workspace", self.ws, "--bot", "main-grok", "--check", "VERIFIED")
        self.assertEqual(r.returncode, 0, r.stderr)
        mg = self.ws / "bots" / "core" / "main-grok"
        self.assertEqual((mg / "previous.md").read_text(encoding="utf-8"), "I am the user's helper.")
        self.assertEqual(json.loads((mg / "agent.json").read_text())["mode"], "extended")
        self.assertEqual((mg / "prompt.md").read_text(encoding="utf-8"),
                         (self.ws / plan["main-grok"]["expected"]).read_text(encoding="utf-8"))
        self.assertEqual(json.loads((mg / "agent.json").read_text())["agent_id"], main)

    def test_record_new_bot_needs_agent_id(self):
        plan = self.plan()
        self.assertEqual(plan["monitor"]["action"], "offer")
        r = run("record", "--workspace", self.ws, "--bot", "monitor", "--check", "VERIFIED", "--agent-id", "a1")
        self.assertNotEqual(r.returncode, 0, "not ticked: nothing to record")
        self.assertEqual(run("approve", "--workspace", self.ws, "--bots", "monitor").returncode, 0)
        r = run("record", "--workspace", self.ws, "--bot", "monitor", "--check", "VERIFIED")
        self.assertNotEqual(r.returncode, 0)
        r = run("record", "--workspace", self.ws, "--bot", "monitor", "--check", "VERIFIED",
                "--agent-id", "agent-new", "--routine", "not chosen")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads((self.ws / "bots" / "core" / "monitor" / "agent.json").read_text())
        self.assertEqual((rec["agent_id"], rec["routine"]), ("agent-new", "not chosen"))
        self.assertNotEqual(run("record", "--workspace", self.ws, "--bot", "monitor",
                                "--check", "FINE").returncode, 0)

    def test_finish(self):
        (self.ws / ".gitignore").write_text("grokbotceo/\nbuild/\n")
        shutil.rmtree(self.old)
        self.assertEqual(run("swap", "--workspace", self.ws).returncode, 0)
        r = run("finish", "--workspace", self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((self.ws / "VERSION").read_text(), "0.2.1\n")
        self.assertEqual(out["gitignore_added"], ["mentor/kb/", "grokbotceo.old/", "update-state.json"])
        self.assertEqual((self.ws / ".gitignore").read_text(),
                         "grokbotceo/\nbuild/\nmentor/kb/\ngrokbotceo.old/\nupdate-state.json\n")
        self.assertTrue(out["complete"])
        self.assertIn("VERSION", out["git_add"])
        self.assertTrue((self.ws / "bots" / "my" / ".gitkeep").exists())


class Crash(BaseException):
    """A process killed mid-step: no except/finally recovery code of the script gets to run."""


class Flow(Fixture):
    """The UPDATE.md sequence against a fake platform (profile.json files stand in for live bots)."""

    def u(self, *args, code=0):
        r = run(*args[:1], "--workspace", self.ws, "--agents-dir", self.agents, *args[1:])
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def approve(self, *ticked):
        return self.u("approve", "--bots", ",".join(ticked))

    def live(self, aid):
        return json.loads((self.agents / aid / "profile.json").read_text(encoding="utf-8"))["description"]

    def set_live(self, aid, text):
        p = self.agents / aid / "profile.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["description"] = text
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def update_agent(self, plan, bot):
        """UpdateAgent as UPDATE.md step 9 sends it: exactly the update_payload fields."""
        upd = json.loads((self.ws / plan[bot]["update_payload"]).read_text(encoding="utf-8"))
        self.set_live(upd["agent_id"], upd["description"])

    def create_agent(self, plan, bot):
        payload = json.loads((self.ws / plan[bot]["create_payload"]).read_text(encoding="utf-8"))
        return self.agent(payload["name"], payload["description"])

    def refetch(self):
        """A rerun: step 2 deletes build/update/ and fetches the same target again."""
        shutil.rmtree(self.ws / "build" / "update", ignore_errors=True)
        self.new = copy_release(self.ws / "build" / "update" / "release", self.NEW_VERSION,
                                block_extra="New line of release 0.2.1.")
        tr = self.new / "bots" / "translator" / "prompt.md"
        tr.write_text(tr.read_text(encoding="utf-8") + "\nNew rule of 0.2.1.\n", encoding="utf-8")

    def state(self):
        return json.loads((self.ws / "update-state.json").read_text(encoding="utf-8"))

    def count_named(self, name):
        return sum(1 for d in self.agents.iterdir()
                   if json.loads((d / "profile.json").read_text(encoding="utf-8"))["name"] == name)


class TestPartialAndResume(Flow):
    def test_failed_translator_then_finish_resumes(self):
        tr = self.installed("translator")
        self.installed("bot-maker")
        plan = self.plan()
        self.assertEqual(plan["translator"]["action"], "update")
        self.approve()
        self.u("swap")
        self.assertTrue(self.u("recheck", "--bot", "translator")["go"])
        # UpdateAgent returns an error: nothing written
        self.u("record", "--bot", "translator", "--check", "NOT APPLIED")
        fin = self.u("finish")
        self.assertFalse(fin["complete"])
        self.assertEqual(fin["failed"], ["translator"])
        self.assertEqual((self.ws / "VERSION").read_text().strip(), "0.2.0", "VERSION is not moved")
        self.assertTrue((self.ws / "grokbotceo.old").is_dir(), "old release kept until complete")
        v = self.u("version", "--target", "v0.2.1")
        self.assertEqual(v["action"], "resume")
        self.assertEqual(v["failed"], ["translator"])
        # the rerun
        self.refetch()
        plan = self.plan()
        self.assertEqual(plan["translator"]["action"], "update")
        self.assertTrue(plan["translator"]["approved"])
        self.approve()
        self.assertTrue(self.u("swap")["already"])
        self.assertTrue(self.u("recheck", "--bot", "translator")["go"])
        self.update_agent(plan, "translator")
        self.u("record", "--bot", "translator", "--check", "VERIFIED")
        fin = self.u("finish")
        self.assertTrue(fin["complete"])
        self.assertEqual((self.ws / "VERSION").read_text().strip(), "0.2.1")
        self.assertFalse((self.ws / "grokbotceo.old").exists())
        self.assertEqual(self.u("version", "--target", "v0.2.1")["action"], "current")
        self.assertIn("New rule of 0.2.1.", self.live(tr))

    def test_failed_main_bot_resume_recognises_old_block(self):
        main = self.main_installed()
        tr = self.installed("translator")
        plan = self.plan()
        self.assertEqual(plan["main-grok"]["action"], "update")
        self.approve()
        self.u("swap")
        self.u("recheck", "--bot", "main-grok")
        self.u("record", "--bot", "main-grok", "--check", "NOT APPLIED")   # UpdateAgent error
        self.u("recheck", "--bot", "translator")
        self.update_agent(plan, "translator")
        self.u("record", "--bot", "translator", "--check", "VERIFIED")
        self.assertFalse(self.u("finish")["complete"])
        tr_after = self.live(tr)
        agents_before = sorted(d.name for d in self.agents.iterdir())
        self.refetch()   # build/update/ deleted: provenance must live outside it
        plan = self.plan()
        m = plan["main-grok"]
        self.assertEqual((m["status"], m["action"]), ("unchanged", "update"), m.get("reason"))
        self.assertTrue(m["approved"])
        self.assertEqual(plan["translator"]["action"], "done")
        self.assertIsNone(plan["translator"]["update_payload"])
        self.assertFalse((self.out / "translator.update.json").exists())
        self.approve()
        self.u("recheck", "--bot", "translator", code=1)   # applied: never touched again
        self.assertTrue(self.u("recheck", "--bot", "main-grok")["go"])
        self.update_agent(plan, "main-grok")
        self.u("record", "--bot", "main-grok", "--check", "VERIFIED")
        self.assertTrue(self.u("finish")["complete"])
        self.assertEqual(self.live(main), update_plan.combine("I am the user's helper.", self.new_block()))
        self.assertEqual(self.live(tr), tr_after)
        self.assertEqual(sorted(d.name for d in self.agents.iterdir()), agents_before)

    def test_created_bot_is_not_created_twice(self):
        self.installed("translator")
        plan = self.plan()
        self.assertEqual(plan["reminder"]["action"], "offer")
        self.approve("reminder")
        self.u("swap")
        self.assertTrue(self.u("recheck", "--bot", "reminder")["go"])
        rid = self.create_agent(plan, "reminder")
        self.u("record", "--bot", "reminder", "--check", "VERIFIED", "--agent-id", rid, "--routine", "not chosen")
        self.u("record", "--bot", "translator", "--check", "NOT APPLIED")
        self.assertFalse(self.u("finish")["complete"])
        self.refetch()
        plan = self.plan()
        self.assertEqual(plan["reminder"]["action"], "done")
        self.approve()
        self.u("recheck", "--bot", "reminder", code=1)
        self.u("record", "--bot", "reminder", "--check", "VERIFIED", "--agent-id", "agent-x", code=1)
        self.assertEqual(self.count_named(self.old_name("reminder")), 1)

    def test_failed_create_then_bot_appears_is_not_created_again(self):
        plan = self.plan()
        self.approve("reminder")
        self.u("swap")
        self.u("recheck", "--bot", "reminder")
        self.create_agent(plan, "reminder")    # the platform made it, but reported an error
        self.u("record", "--bot", "reminder", "--check", "NOT APPLIED")
        self.assertFalse(self.u("finish")["complete"])
        self.refetch()
        plan = self.plan()
        r = plan["reminder"]
        self.assertNotEqual(r["action"], "offer", "never a second CreateAgent")
        # it already runs the new text: only the write check and the record are left
        self.assertTrue(r["found_applied"])
        self.approve()
        self.u("recheck", "--bot", "reminder", code=1)
        self.u("record", "--bot", "reminder", "--check", "VERIFIED", "--routine", "not chosen")
        self.assertTrue(self.u("finish")["complete"])
        self.assertEqual(self.count_named(self.old_name("reminder")), 1)

    def test_kept_and_unticked_are_never_pending(self):
        self.installed("translator")
        mentor = self.installed("mentor", live_text=self.old_text("mentor") + "\nMy own rule.")
        plan = self.plan()
        self.assertEqual(plan["mentor"]["action"], "ask")
        self.assertEqual(plan["reminder"]["action"], "offer")
        self.approve()                         # nothing ticked
        self.u("swap")
        self.u("record", "--bot", "translator", "--check", "NOT APPLIED")
        self.u("recheck", "--bot", "mentor", code=1)
        self.u("record", "--bot", "mentor", "--check", "VERIFIED", code=1)
        fin = self.u("finish")
        self.assertEqual((fin["pending"], fin["failed"], fin["stopped"]), ([], ["translator"], []))
        v = self.u("version", "--target", "v0.2.1")
        self.assertEqual((v["action"], v["failed"], v["pending"]), ("resume", ["translator"], []))
        self.refetch()
        plan = self.plan()
        self.assertEqual(plan["mentor"]["action"], "leave")
        self.assertEqual(plan["reminder"]["action"], "leave")
        self.approve()
        st = self.state()["bots"]
        self.assertEqual((st["mentor"]["outcome"], st["reminder"]["outcome"]), ("kept", "kept"))
        self.assertIn("My own rule.", self.live(mentor))


class TestFreshness(Flow):
    def test_edit_after_plan_stops_that_bot(self):
        tr = self.installed("translator")
        bm = self.installed("bot-maker", live_text=self.old_text("bot-maker"))
        plan = self.plan()
        self.approve()
        edited = self.live(tr) + "\nUSER RULE: answer in French."
        self.set_live(tr, edited)               # the user edits while the plan waits
        self.u("swap")
        r = self.u("recheck", "--bot", "translator", code=2)
        self.assertFalse(r["go"])
        self.assertEqual(self.live(tr), edited, "nothing was written")
        self.u("record", "--bot", "translator", "--check", "VERIFIED", code=1)
        fin = self.u("finish")
        self.assertEqual((fin["complete"], fin["stopped"]), (False, ["translator"]))
        self.assertEqual(self.u("version", "--target", "v0.2.1")["action"], "resume")
        self.refetch()
        plan = self.plan()
        t = plan["translator"]
        self.assertEqual((t["status"], t["action"], t["approved"]), ("changed", "ask", False))
        self.assertIn("-USER RULE", (self.ws / t["diff_live"]["file"]).read_text(encoding="utf-8"))
        self.approve()                          # the fresh form: not ticked
        self.u("recheck", "--bot", "translator", code=1)
        self.assertTrue(self.u("finish")["complete"])
        self.assertEqual(self.live(tr), edited)

    def test_main_bot_edit_after_plan_stops(self):
        main = self.main_installed()
        self.plan()
        self.approve()
        edited = "I am the user's helper.\nUSER RULE.\n\n" + self.old_block()
        self.set_live(main, edited)
        self.u("swap")
        self.assertFalse(self.u("recheck", "--bot", "main-grok", code=2)["go"])
        self.assertEqual(self.live(main), edited)

    def test_live_file_and_stdin(self):
        tr = self.installed("translator")
        self.plan()
        self.approve()
        f = self.tmp / "live.txt"
        f.write_text(self.live(tr) + "\nchanged", encoding="utf-8")
        self.assertFalse(self.u("recheck", "--bot", "translator", "--live-file", f, code=2)["go"])

    def test_stale_receipt_after_failure_never_erases_edit(self):
        tr = self.installed("translator")
        plan = self.plan()
        self.approve()
        self.u("swap")
        self.u("record", "--bot", "translator", "--check", "NOT APPLIED")
        self.assertFalse(self.u("finish")["complete"])
        edited = self.live(tr) + "\nUSER RULE."
        self.set_live(tr, edited)
        # the old plan and payload are still in build/update/out: a rerun that skipped the plan
        self.u("recheck", "--bot", "translator", code=1)
        self.assertEqual(self.u("version", "--target", "v0.2.1")["action"], "resume")
        self.refetch()
        plan = self.plan()
        self.assertFalse(plan["translator"]["approved"])
        self.assertEqual(plan["translator"]["action"], "ask")
        self.approve()
        self.assertEqual(self.live(tr), edited)
        self.assertEqual(self.state()["bots"]["translator"]["outcome"], "kept")

    def test_fresh_yes_is_tied_to_fresh_text(self):
        tr = self.installed("translator")
        self.plan()
        self.approve()
        self.set_live(tr, self.live(tr) + "\nUSER RULE.")
        self.u("swap")
        self.u("recheck", "--bot", "translator", code=2)
        self.refetch()
        plan = self.plan()
        self.approve("translator")              # the user ticks it after the fresh diff
        self.assertTrue(self.u("recheck", "--bot", "translator")["go"])
        self.set_live(tr, self.live(tr) + "\nANOTHER.")   # and edits again
        self.assertFalse(self.u("recheck", "--bot", "translator", code=2)["go"])


class TestSwapRecovery(Flow):
    def crash_after_first_rename(self):
        real = os.rename
        calls = []

        def dying(src, dst):
            calls.append((src, dst))
            if len(calls) >= 2:
                raise Crash()
            return real(src, dst)

        args = update_plan.build_parser().parse_args(["swap", "--workspace", str(self.ws)])
        update_plan.resolve_args(args)
        update_plan.os.rename = dying
        try:
            with self.assertRaises(Crash):
                update_plan.cmd_swap(args)
        finally:
            update_plan.os.rename = real

    def test_interrupted_swap_is_recovered_not_deleted(self):
        before = tree(self.old)
        self.crash_after_first_rename()
        self.assertFalse((self.ws / "grokbotceo").exists())
        self.assertEqual(tree(self.ws / "grokbotceo.old"), before)
        # step 2 of the rerun deletes build/update first: the old tree is not in it
        shutil.rmtree(self.ws / "build" / "update")
        self.assertEqual(tree(self.ws / "grokbotceo.old"), before)
        self.refetch()
        self.u("version", "--target", "v0.2.1")    # any command recovers first
        self.assertEqual(tree(self.ws / "grokbotceo"), before)
        self.u("swap")
        self.assertEqual(tree(self.ws / "grokbotceo.old"), before, "old tree kept until finish")
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), "0.2.1")

    def test_swap_rerun_never_deletes_kept_old_tree(self):
        self.installed("translator")
        self.plan()
        self.approve()
        self.u("swap")
        before = tree(self.ws / "grokbotceo.old")
        self.refetch()
        self.u("swap")
        self.assertEqual(tree(self.ws / "grokbotceo.old"), before)

    def test_finish_deletes_old_tree_only_when_complete(self):
        self.u("swap")
        self.assertTrue((self.ws / "grokbotceo.old").is_dir())
        self.assertTrue(self.u("finish")["complete"])
        self.assertFalse((self.ws / "grokbotceo.old").exists())


class TestFinishBoundaries(Flow):
    """finish cut off at every boundary (no signals: the next write raises Crash): the next command
    completes or reports it, and the following 0.2.2 update can swap. Nothing finalized while a bot
    is unfinished."""

    def done_update(self):
        """A 0.2.1 update whose bots are all done; only `finish` is left."""
        self.tr = self.installed("translator")
        plan = self.plan()
        self.approve()
        self.u("swap")
        self.u("recheck", "--bot", "translator")
        self.update_agent(plan, "translator")
        self.u("record", "--bot", "translator", "--check", "VERIFIED")
        (self.ws / "mentor").mkdir()
        (self.ws / "mentor" / "progress.json").write_text('{"done": ["L1"]}', encoding="utf-8")
        self.edited = self.live(self.tr) + "\nUSER RULE after the update."
        self.set_live(self.tr, self.edited)        # the user keeps working with the bot

    def finish_crashing(self, point):
        """Run cmd_finish in-process; raise Crash at one boundary."""
        m = update_plan
        real = {"save_state": m.save_state, "atomic_write": m.atomic_write, "remove_tree": m.remove_tree}
        n = {"save": 0}

        def save_state(ws, state):
            n["save"] += 1
            phase = state.get("phase")
            if point == "intent" and phase == "finalizing":
                raise Crash()
            if point == "committed" and phase == "complete" and isinstance(state.get("swap"), dict):
                raise Crash()
            if point == "cleanup_saved" and phase == "complete" and "swap" not in state:
                raise Crash()
            return real["save_state"](ws, state)

        def atomic_write(path, text):
            if point == "version" and Path(path).name == "VERSION" and Path(path).parent == self.ws:
                raise Crash()
            real["atomic_write"](path, text)
            if point == "after_version" and Path(path).name == "VERSION" and Path(path).parent == self.ws:
                raise Crash()

        def remove_tree(path):
            if point == "removal":
                victim = next(p for p in sorted(Path(path).rglob("*")) if p.is_file())
                victim.unlink()                    # half deleted
                raise Crash()
            return real["remove_tree"](path)

        args = update_plan.build_parser().parse_args(["finish", "--workspace", str(self.ws)])
        update_plan.resolve_args(args)
        m.save_state, m.atomic_write, m.remove_tree = save_state, atomic_write, remove_tree
        try:
            with self.assertRaises(Crash):
                update_plan.cmd_finish(args)
        finally:
            m.save_state, m.atomic_write, m.remove_tree = (real["save_state"], real["atomic_write"],
                                                           real["remove_tree"])

    def next_release(self):
        shutil.rmtree(self.ws / "build" / "update", ignore_errors=True)
        copy_release(self.ws / "build" / "update" / "release", "0.2.2")

    def check_boundary(self, point):
        self.done_update()
        progress = (self.ws / "mentor" / "progress.json").read_bytes()
        core = tree(self.ws / "bots" / "core")
        self.finish_crashing(point)
        v = self.u("version", "--target", "v0.2.2")
        if v["action"] == "resume":            # cut off before finish wrote anything durable
            self.assertEqual((v["target"], v["pending"], v["failed"], v["stopped"]), ("0.2.1", [], [], []))
            self.assertTrue(self.u("finish")["complete"])
            v = self.u("version", "--target", "v0.2.2")
        self.assertEqual((v["installed"], v["action"]), ("0.2.1", "update"), point)
        self.assertEqual((self.ws / "VERSION").read_text().strip(), "0.2.1")
        self.assertFalse((self.ws / "grokbotceo.old").exists(), point)
        self.assertNotIn("swap", self.state())
        self.next_release()
        r = self.u("swap", "--expect-version", "v0.2.2")
        self.assertTrue(r["swapped"], point)
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), "0.2.2")
        self.assertEqual(self.live(self.tr), self.edited, "the user's edit is kept")
        self.assertEqual((self.ws / "mentor" / "progress.json").read_bytes(), progress)
        self.assertEqual(tree(self.ws / "bots" / "core"), core)

    def test_before_intent(self):
        self.check_boundary("intent")

    def test_before_version(self):
        self.check_boundary("version")

    def test_after_version(self):
        self.check_boundary("after_version")

    def test_before_commit_saved(self):
        self.check_boundary("committed")

    def test_during_old_tree_removal(self):
        self.check_boundary("removal")

    def test_after_removal_before_cleanup_saved(self):
        self.check_boundary("cleanup_saved")

    def test_nothing_finalized_while_a_bot_is_unfinished(self):
        self.installed("translator")
        self.plan()
        self.approve()
        self.u("swap")
        self.u("record", "--bot", "translator", "--check", "NOT APPLIED")
        self.assertFalse(self.u("finish")["complete"])
        (self.ws / "VERSION").write_text("0.2.1\n")   # even a VERSION written by hand
        v = self.u("version", "--target", "v0.2.2")
        self.assertEqual((v["action"], v["failed"]), ("resume", ["translator"]))
        self.assertTrue((self.ws / "grokbotceo.old").is_dir())
        self.next_release()
        self.u("swap", "--expect-version", "v0.2.2", code=1)
        self.assertEqual((self.ws / "grokbotceo" / "VERSION").read_text().strip(), "0.2.1")


class TestRecordBaseline(Flow):
    def test_mismatch_and_not_verified_keep_baseline(self):
        self.installed("translator")
        mentor = self.installed("mentor", live_text=self.old_text("mentor") + "\nMine.")
        core = self.ws / "bots" / "core"
        rec = json.loads((core / "mentor" / "agent.json").read_text())
        rec["edited"] = True
        (core / "mentor" / "agent.json").write_text(json.dumps(rec))
        self.plan()
        self.approve("mentor")
        before_tr = ((core / "translator" / "prompt.md").read_bytes(),
                     json.loads((core / "translator" / "agent.json").read_text()))
        before_mn = (core / "mentor" / "prompt.md").read_bytes()
        self.u("swap")
        self.u("record", "--bot", "translator", "--check", "MISMATCH")
        self.u("record", "--bot", "mentor", "--check", "NOT VERIFIED")
        self.assertEqual((core / "translator" / "prompt.md").read_bytes(), before_tr[0])
        rec = json.loads((core / "translator" / "agent.json").read_text())
        self.assertEqual((rec["version"], rec["check"]), (before_tr[1]["version"], before_tr[1]["check"]))
        self.assertEqual(rec["last_update"], {"target": "0.2.1", "check": "MISMATCH"})
        self.assertEqual((core / "mentor" / "prompt.md").read_bytes(), before_mn)
        self.assertIs(json.loads((core / "mentor" / "agent.json").read_text())["edited"], True)
        fin = self.u("finish")
        self.assertFalse(fin["complete"])
        self.assertEqual(sorted(fin["failed"]), ["mentor", "translator"])
        self.assertEqual((self.ws / "VERSION").read_text().strip(), "0.2.0")


class TestReleaseTexts(unittest.TestCase):
    """UPDATE.md is wired in and keeps the rules the README promises."""

    def test_update_md(self):
        text = (RELEASE_DIR / "UPDATE.md").read_text(encoding="utf-8")
        for needle in ["scripts/update-plan.py", "U version", "U config", "U plan", "update-plan.py swap",
                       "U record", "U finish", "U approve", "U recheck", "NOT APPLIED", "resume",
                       "bot-payload-compiler.py build", "bot-mirror.py check", "progress.py",
                       "migrate", "build_kb.py --kb-home mentor", "LOCAL-COPY.md", "(yes: ",
                       "bots/my/", "bots/marketplace/", "config.json", "as a form", "8a",
                       "git ls-remote", "rev-parse HEAD", "Never"]:
            self.assertIn(needle, text)
        self.assertIn("one in the whole update", text)
        low = text.lower().replace("never ask the user which version", "")
        for phrase in ("which of these", "which is your main", "ask which", "ask the user which version"):
            self.assertNotIn(phrase, low)
        self.assertNotIn("git add .", text)
        self.assertNotIn("git add -A", text)

    def test_recovery_before_cleanup(self):
        text = (RELEASE_DIR / "UPDATE.md").read_text(encoding="utf-8")
        step2 = text[text.index("## 2."):text.index("## 3.")]
        first_rm = step2.index("rm -rf")
        for needle in ("grokbotceo.old", "update-state.json", "mv grokbotceo.old grokbotceo"):
            self.assertLess(step2.index(needle), first_rm, needle)
        for line in text.splitlines():
            if "rm -rf" in line:
                self.assertNotIn("grokbotceo.old", line)
                self.assertNotIn("update-state.json", line)
                self.assertNotIn("release.old", line)
        self.assertIn("compare-and-swap", text)
        self.assertIn("Partial update", text)
        # the state and the old tree are outside build/update/, so its cleanup cannot reach them
        self.assertFalse(update_plan.STATE_FILE.startswith("build"))
        self.assertFalse(update_plan.OLD_TREE.startswith("build"))

    def test_routes_to_update(self):
        bm = (RELEASE_DIR / "bots" / "bot-maker" / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("UPDATE.md", bm)
        main = (RELEASE_DIR / "bots" / "main-grok" / "block.md").read_text(encoding="utf-8")
        self.assertIn("BotCEO update", main)
        for readme in ("README.md", "README.ru.md"):
            self.assertIn("UPDATE.md", (RELEASE_DIR / readme).read_text(encoding="utf-8"), readme)


if __name__ == "__main__":
    unittest.main()
