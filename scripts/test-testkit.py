#!/usr/bin/env python3
"""Local dry run of testkit/mentor-phase-a (Codex rc2 review, item 3: one reproducible delivery route).

Exports this tree with manifest.py export, then runs the kit exactly as the scenario orders it, on a
temporary workspace that is itself a committed git repository with the test root INSIDE it (rc4, Codex
rc3 review: the fixture must reproduce /workspace): record parent state -> append `/mentor-test-a/` and
`/mentor-test-a.incoming/` to the parent .gitignore -> archive into the incoming dir + hash check -> install.sh (from the archive) -> snapshot B0 -> setup-git -> build.sh
(hashes vs EXPECTED.sha256) -> prep.sh -> baseline commit -> snapshot B1. A global core.hooksPath with
marker hooks is active the whole time. Negative cases: inherited GIT_DIR, snapshot of symlinks / missing
trees / broken git. No network, no bots, no /workspace.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

GLOBAL_HOOK = "#!/bin/sh\necho \"$0\" >> \"$MARKER\"\n"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = "testkit/mentor-phase-a"


def read(p, mode="r"):
    with open(p, mode) as f:
        return f.read()


def write(p, text):
    with open(p, "w") as f:
        f.write(text)


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kw)


class TestKitDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="testkit-")
        cls.archive = os.path.join(cls.tmp, "release.tar.gz")
        r = sh([sys.executable, "-I", "-B", os.path.join(ROOT, "release/scripts/manifest.py"), "export", cls.archive])
        assert r.returncode == 0, r.stdout + r.stderr
        cls.sha = hashlib.sha256(read(cls.archive, "rb")).hexdigest()
        # isolated HOME: identity for the parent repo + a GLOBAL hooksPath that the kit must not run
        home = os.path.join(cls.tmp, "home")
        cls.hooks = os.path.join(cls.tmp, "global-hooks")
        cls.marker = os.path.join(cls.tmp, "hook-ran.log")
        os.makedirs(home)
        os.makedirs(cls.hooks)
        write(os.path.join(home, ".gitconfig"),
              "[user]\n\tname = parent\n\temail = parent@example.com\n[core]\n\thooksPath = %s\n" % cls.hooks)
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        cls.env.update(HOME=home, MENTOR_KIT_LOCAL="1", PYTHONDONTWRITEBYTECODE="1", MARKER=cls.marker)
        # parent workspace = committed git repository, like /workspace
        cls.ws = os.path.join(cls.tmp, "ws")
        os.makedirs(os.path.join(cls.ws, "mentor"))
        os.makedirs(os.path.join(cls.ws, "grokbotceo/course"))
        write(os.path.join(cls.ws, "mentor/progress.json"), "{}\n")
        write(os.path.join(cls.ws, "grokbotceo/course/course.json"), "{}\n")
        write(os.path.join(cls.ws, ".gitignore"), "*.tmp\n")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "parent"]):
            r = sh(["git", "-C", cls.ws, *cmd], env=cls.env)
            assert r.returncode == 0, r.stderr
        for name in ("pre-commit", "commit-msg", "post-commit"):  # armed only after the parent commit
            write(os.path.join(cls.hooks, name), GLOBAL_HOOK)
            os.chmod(os.path.join(cls.hooks, name), 0o755)
        cls.root = os.path.join(cls.ws, "mentor-test-a")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def kit(self, script, *args, env=None):
        return sh(["bash", os.path.join(self.root, "src", KIT, script), *args], env=env or self.env)

    def parent_state(self):
        g = lambda *a: sh(["git", "-C", self.ws, *a], env=self.env).stdout
        return {"config": read(os.path.join(self.ws, ".git/config")), "head": g("rev-parse", "HEAD"),
                "index": g("ls-files", "-s"), "refs": g("for-each-ref"), "log": g("log", "--format=%H %an")}

    def test_1_full_route_nested(self):
        before = self.parent_state()
        gi = os.path.join(self.ws, ".gitignore")
        orig = read(gi, "rb")
        self.assertTrue(orig.endswith(b"\n"))
        # step 1: the only write outside the test root comes FIRST — append exactly two root-anchored lines
        r = sh(["sh", "-c", "printf '/mentor-test-a/\\n/mentor-test-a.incoming/\\n' >> .gitignore"], cwd=self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(read(gi, "rb"), orig + b"/mentor-test-a/\n/mentor-test-a.incoming/\n")
        # step 2: the single archive file in the incoming directory, hash checked before anything runs
        incoming = os.path.join(self.ws, "mentor-test-a.incoming")
        os.makedirs(incoming)
        shutil.copyfile(self.archive, os.path.join(incoming, "course-0.3.0-rc4.tar.gz"))
        self.assertEqual(hashlib.sha256(read(os.path.join(incoming, "course-0.3.0-rc4.tar.gz"), "rb")).hexdigest(),
                         self.sha)
        # a look-alike directory is NOT hidden by the narrowed rule
        os.makedirs(os.path.join(self.ws, "mentor-test-ab"))
        write(os.path.join(self.ws, "mentor-test-ab/x"), "x\n")
        st = sh(["git", "-C", self.ws, "status", "--short", "--untracked-files=all"], env=self.env).stdout
        self.assertIn("?? mentor-test-ab/x", st)
        shutil.rmtree(os.path.join(self.ws, "mentor-test-ab"))
        inst = sh(["tar", "-xzf", self.archive, "-O", KIT + "/install.sh"])
        self.assertEqual(inst.returncode, 0, inst.stderr)
        r = subprocess.run(["bash", "-s", "--", os.path.join(incoming, "course-0.3.0-rc4.tar.gz"), self.sha, self.root],
                           input=inst.stdout,
                           capture_output=True, text=True, env=self.env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("verified", r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "grokbotceo/course/progress.py")))

        r = self.kit("snapshot.sh", "B0", self.root, self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.kit("setup-git.sh", self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.kit("build.sh", self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SendToAgent 0", r.stdout)
        r = self.kit("prep.sh", self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('"revision": 33', r.stdout)
        r = self.kit("setup-git.sh", "--baseline", self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("author mentor-test-a", r.stdout)
        top = sh(["git", "-C", self.root, "rev-parse", "--show-toplevel"], env=self.env).stdout.strip()
        self.assertEqual(os.path.realpath(top), os.path.realpath(self.root))
        r = self.kit("snapshot.sh", "B1", self.root, self.ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        b0 = read(os.path.join(self.root, "evidence/B0.txt"))
        b1 = read(os.path.join(self.root, "evidence/B1.txt"))
        self.assertEqual(b0, b1)                       # nothing outside the test root changed after step 1
        self.assertIn("#   M .gitignore", b0)          # the one sanctioned parent change, visible in both
        self.assertNotIn("mentor-test-a", b0)          # the test root is ignored by the parent
        self.assertEqual(self.parent_state(), before)  # parent config/HEAD/index/refs/log untouched
        self.assertFalse(os.path.exists(self.marker), "a global hook ran")
        log = sh(["git", "-C", self.root, "log", "--format=%an %s"], env=self.env).stdout
        self.assertEqual(log, "mentor-test-a prep baseline\n")
        # each step refuses a second run (a test root is used once)
        self.assertNotEqual(self.kit("build.sh", self.root).returncode, 0)
        self.assertNotEqual(self.kit("prep.sh", self.root).returncode, 0)
        self.assertNotEqual(self.kit("snapshot.sh", "B1", self.root, self.ws).returncode, 0)
        self.assertNotEqual(self.kit("setup-git.sh", self.root).returncode, 0)

    def test_2_inherited_git_env_refused(self):
        kit = os.path.join(ROOT, KIT, "setup-git.sh")
        other = os.path.join(self.ws, "mentor-test-g")
        os.makedirs(other)
        before = self.parent_state()
        for extra in ({"GIT_DIR": os.path.join(self.ws, ".git")}, {"GIT_WORK_TREE": self.ws},
                      {"GIT_CONFIG_GLOBAL": os.devnull}, {"GIT_INDEX_FILE": "/tmp/x"}):
            with self.subTest(extra=extra):
                r = sh(["bash", kit, other], env=dict(self.env, **extra))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertFalse(os.path.exists(os.path.join(other, ".git")))
                self.assertFalse(os.path.exists(os.path.join(other, ".gitignore")))
        self.assertEqual(self.parent_state(), before)

    def snap(self, label, ws):
        root = os.path.join(self.tmp, "snaproot")
        os.makedirs(os.path.join(root, "evidence"), exist_ok=True)
        r = sh(["bash", os.path.join(ROOT, KIT, "snapshot.sh"), label, root, ws], env=self.env)
        return r, os.path.join(root, "evidence", label + ".txt")

    def make_ws(self, name, git=True):
        ws = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(ws, "mentor"))
        os.makedirs(os.path.join(ws, "grokbotceo/course"))
        write(os.path.join(ws, "mentor/progress.json"), "{}\n")
        if git:
            for cmd in (["init", "-q"], ["add", "-A"], ["-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "p"]):
                assert sh(["git", "-C", ws, *cmd], env=self.env).returncode == 0
        return ws

    def test_3_snapshot_fail_closed(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        write(os.path.join(outside, "f.json"), "x\n")
        cases = []
        ws = self.make_ws("ws-dirlink")
        os.symlink(outside, os.path.join(ws, "mentor/linked"))
        cases.append(("dirlink", ws))
        ws = self.make_ws("ws-filelink")
        os.symlink(os.path.join(outside, "f.json"), os.path.join(ws, "grokbotceo/course/f.json"))
        cases.append(("filelink", ws))
        ws = self.make_ws("ws-nogit", git=False)
        cases.append(("nogit", ws))
        ws = self.make_ws("ws-missing")
        shutil.rmtree(os.path.join(ws, "grokbotceo"))
        cases.append(("missing", ws))
        ws = self.make_ws("ws-toplink")
        shutil.rmtree(os.path.join(ws, "mentor"))
        os.symlink(outside, os.path.join(ws, "mentor"))
        cases.append(("toplink", ws))
        for label, ws in cases:
            with self.subTest(case=label):
                r, out = self.snap("S" + label, ws)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertFalse(os.path.exists(out))
                self.assertFalse(os.path.exists(out + ".tmp"))
        r, out = self.snap("Sgood", self.make_ws("ws-good"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.isfile(out))

    def test_4_wrong_hash_and_existing_root_refused(self):
        other = os.path.join(self.tmp, "mentor-test-x")
        inst = sh(["tar", "-xzf", self.archive, "-O", KIT + "/install.sh"]).stdout
        r = subprocess.run(["bash", "-s", "--", self.archive, "0" * 64, other], input=inst,
                           capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(os.path.exists(other))
        os.makedirs(other)
        r = subprocess.run(["bash", "-s", "--", self.archive, self.sha, other], input=inst,
                           capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run(["bash", "-s", "--", self.archive, self.sha, "/workspace/mentor"], input=inst,
                           capture_output=True, text=True, env=dict(self.env, MENTOR_KIT_LOCAL="0"), timeout=60)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
