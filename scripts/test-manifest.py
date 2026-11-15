#!/usr/bin/env python3
"""
Tests for the freeze manifest (scripts/manifest.py, release/MANIFEST.sha256; plan 0.3.0 §1).

The committed manifest must match this tree. The generator and checker are exercised on a scratch git
repository in a temporary folder: deterministic output, the manifest excluded, ignored files never listed,
and every mismatched, missing or extra path named. Stdlib + git, no network.
"""
import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MF = _load("manifest_under_test", SCRIPT_DIR / "manifest.py")
HAVE_GIT = shutil.which("git") is not None and (ROOT / ".git").exists()


def quiet(fn, *a):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(*a)
    return code, out.getvalue(), err.getvalue()


@unittest.skipUnless(HAVE_GIT, "needs git and a git checkout")
class TestCommittedManifest(unittest.TestCase):
    def test_manifest_matches_tree(self):
        self.assertEqual(MF.check(ROOT), [])
        data = (ROOT / MF.MANIFEST).read_bytes()
        self.assertEqual(data, MF.render(ROOT))
        paths = [line.split("  ", 1)[1] for line in data.decode().splitlines()]
        self.assertEqual(paths, sorted(paths, key=lambda p: p.encode()))
        self.assertNotIn(MF.MANIFEST, paths)
        self.assertTrue(all(p.startswith(MF.SCOPES) for p in paths))
        self.assertIn("release/course/progress.py", paths)
        self.assertIn("services/feedback-receiver/feedback_receiver/app.py", paths)
        self.assertFalse([p for p in paths if "__pycache__" in p or p.endswith((".pyc", ".db", ".DS_Store"))])


@unittest.skipUnless(shutil.which("git"), "needs git")
class TestGenCheck(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="manifest-"))
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("release/a.txt", "a\n")
        self.write("release/course/b.json", "{}\n")
        self.write("services/feedback-receiver/app.py", "x = 1\n")
        self.write("services/other/skip.py", "out of scope\n")
        self.write("docs/skip.md", "out of scope\n")
        self.write(".gitignore", "*.db\n__pycache__/\n")
        self.write("release/data.db", "ignored")
        self.write("release/__pycache__/x.pyc", "ignored")
        subprocess.run(["git", "-C", str(self.root), "add", "release/a.txt", "services"], check=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def test_gen_is_deterministic_scoped_and_sha256sum_format(self):
        self.assertEqual(quiet(MF.main, ["gen", "--root", str(self.root)])[0], 0)
        first = (self.root / MF.MANIFEST).read_bytes()
        self.assertEqual(quiet(MF.main, ["gen", "--root", str(self.root)])[0], 0)   # manifest itself excluded
        self.assertEqual((self.root / MF.MANIFEST).read_bytes(), first)
        lines = first.decode().splitlines()
        self.assertEqual([l.split("  ")[1] for l in lines],
                         ["release/a.txt", "release/course/b.json", "services/feedback-receiver/app.py"])
        self.assertEqual(lines[0], hashlib.sha256(b"a\n").hexdigest() + "  release/a.txt")
        self.assertEqual(quiet(MF.main, ["check", "--root", str(self.root)])[0], 0)
        if shutil.which("sha256sum"):
            r = subprocess.run(["sha256sum", "-c", MF.MANIFEST], cwd=self.root, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_names_mismatch_missing_extra(self):
        quiet(MF.main, ["gen", "--root", str(self.root)])
        self.write("release/a.txt", "changed\n")
        (self.root / "release/course/b.json").unlink()
        self.write("release/new.md", "new\n")
        self.write("release/more.db", "ignored, never extra")
        code, _, err = quiet(MF.main, ["check", "--root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertIn("mismatch: release/a.txt", err)
        self.assertIn("missing: release/course/b.json", err)
        self.assertIn("extra: release/new.md", err)
        self.assertNotIn("more.db", err)

    def test_check_malformed_and_absent(self):
        self.assertEqual(MF.check(self.root), [f"missing manifest: {MF.MANIFEST}"])
        self.write(MF.MANIFEST, "nonsense\n")
        self.assertTrue(MF.check(self.root)[0].startswith("malformed manifest"))


@unittest.skipUnless(shutil.which("git"), "needs git")
class TestExportVerify(unittest.TestCase):
    """export (git) -> extract into a folder with no .git -> verify (no git)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="manifest-export-"))
        self.root = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write("release/a.txt", "a\n")
        self.write("release/course/Курс.md", "кириллица\n")
        self.write("release/scripts/run.sh", "#!/bin/sh\necho hi\n")
        (self.root / "release/scripts/run.sh").chmod(0o755)
        self.write("services/feedback-receiver/app.py", "x = 1\n")
        self.write("services/other/skip.py", "out of scope\n")
        self.write("docs/skip.md", "out of scope\n")
        self.write("private/secret.txt", "never shipped\n")
        self.write("mailbox/x.md", "never shipped\n")
        self.write(".claude/SNAPSHOT.md", "never shipped\n")
        self.write(".gitignore", "*.db\n__pycache__/\n")
        self.write("release/data.db", "ignored")
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        self.assertEqual(quiet(MF.main, ["gen", "--root", str(self.root)])[0], 0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text, root=None):
        p = (root or self.root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def export(self, name="payload.tar.gz"):
        out = self.tmp / name
        code, stdout, err = quiet(MF.main, ["export", str(out), "--root", str(self.root)])
        self.assertEqual(code, 0, err)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        self.assertIn(digest, stdout)
        return out, digest

    def extract(self, archive, name="copy"):
        dest = self.tmp / name
        dest.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar.getmembers():
                self.assertTrue(m.isfile(), m.name)
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dest, filter="data")
            else:
                tar.extractall(dest)
        self.assertFalse((dest / ".git").exists())
        return dest

    def test_export_extract_verify_and_sha256sum(self):
        archive, _ = self.export()
        copy = self.extract(archive)
        code, out, err = quiet(MF.main, ["verify", "--root", str(copy)])
        self.assertEqual(code, 0, err)
        self.assertIn("verified, 4 files", out)
        self.assertTrue(os.access(copy / "release/scripts/run.sh", os.X_OK))
        if shutil.which("sha256sum"):
            r = subprocess.run(["sha256sum", "-c", MF.MANIFEST], cwd=copy, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # runtime litter is ignored, nothing else is
        self.write("release/__pycache__/m.cpython-312.pyc", "x", copy)
        self.write("release/course/stray.pyc", "x", copy)
        self.write("services/feedback-receiver/.DS_Store", "x", copy)
        self.assertEqual(MF.verify(copy), [])

    def test_export_is_byte_reproducible(self):
        a, da = self.export("one.tar.gz")
        b, db = self.export("two.tar.gz")
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(da, db)

    def test_archive_holds_only_the_allowlist(self):
        archive, _ = self.export()
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            for m in tar.getmembers():
                self.assertEqual((m.mtime, m.uid, m.gid, m.uname, m.gname), (0, 0, 0, "", ""))
        listed = [l.split("  ", 1)[1] for l in (self.root / MF.MANIFEST).read_text("utf-8").splitlines()]
        self.assertEqual(sorted(names), sorted(listed + [MF.MANIFEST]))
        for n in names:
            self.assertTrue(n == MF.MANIFEST or n.startswith(MF.SCOPES), n)
            self.assertFalse(n.startswith(("/", "docs/", "private/", "mailbox/", ".claude/", "services/other/")), n)
            self.assertNotIn("..", n.split("/"))
        self.assertNotIn("release/data.db", names)

    def test_verify_detects_tamper_missing_extra(self):
        copy = self.extract(self.export()[0])
        self.write("release/a.txt", "tampered\n", copy)
        (copy / "services/feedback-receiver/app.py").unlink()
        self.write("release/course/new.md", "extra\n", copy)
        self.write("services/feedback-receiver/data.db", "extra too: no .gitignore here\n", copy)
        code, _, err = quiet(MF.main, ["verify", "--root", str(copy)])
        self.assertEqual(code, 1)
        self.assertIn("mismatch: release/a.txt", err)
        self.assertIn("missing: services/feedback-receiver/app.py", err)
        self.assertIn("extra: release/course/new.md", err)
        self.assertIn("extra: services/feedback-receiver/data.db", err)

    def test_verify_rejects_symlink_and_out_of_scope_listing(self):
        copy = self.extract(self.export()[0])
        target = copy / "release/a.txt"
        target.unlink()
        target.symlink_to(copy / MF.MANIFEST)
        self.assertIn("symlink: release/a.txt", MF.verify(copy))
        m = copy / MF.MANIFEST
        m.write_bytes(m.read_bytes() + f"{'0' * 64}  docs/skip.md\n".encode())
        self.assertIn("listed path out of scope: docs/skip.md", MF.verify(copy))
        m.unlink()
        self.assertEqual(MF.verify(copy), [f"missing manifest: {MF.MANIFEST}"])

    def test_export_refuses_stale_manifest(self):
        self.write("release/a.txt", "changed after gen\n")
        with self.assertRaises(SystemExit):
            quiet(MF.main, ["export", str(self.tmp / "x.tar.gz"), "--root", str(self.root)])
        self.assertFalse((self.tmp / "x.tar.gz").exists())


@unittest.skipUnless(HAVE_GIT, "needs git and a git checkout")
class TestRealTreeExport(unittest.TestCase):
    """The committed manifest exports and the exported copy verifies without git."""

    def test_real_export_verifies(self):
        tmp = Path(tempfile.mkdtemp(prefix="manifest-real-"))
        try:
            out = tmp / "payload.tar.gz"
            digest = MF.export(out, ROOT)
            self.assertEqual(digest, hashlib.sha256(out.read_bytes()).hexdigest())
            dest = tmp / "copy"
            dest.mkdir()
            with tarfile.open(out, "r:gz") as tar:
                names = tar.getnames()
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(dest, filter="data")
                else:
                    tar.extractall(dest)
            self.assertTrue(all(n == MF.MANIFEST or n.startswith(MF.SCOPES) for n in names))
            self.assertEqual(MF.verify(dest), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
