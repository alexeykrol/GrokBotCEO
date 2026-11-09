#!/usr/bin/env python3
"""
Comprehensive tests for sync-data.sh
RED/GREEN with isolated fictional fixtures.

Fully local: temp directories and local bare git repositories only. No network:
GIT_ALLOW_PROTOCOL=file makes git refuse every non-file transport, and a stub `gh`
on PATH answers privacy questions (it never contacts anything). Global/system git
config of the machine running the tests is ignored.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SYNC_SCRIPT = SCRIPT_DIR / "sync-data.sh"

# Synthetic credentials, assembled at runtime so the file holds no credential-shaped URL
FAKE_TOKEN = "ghp" + "_" + "X" * 36
FAKE_PW = "pw-" + "SECRET"
FAKE_TOK = "tok-" + "SECRET"


def cred_url(secret: str, rest: str, user: str = "user") -> str:
    """https URL with userinfo built from parts (see FAKE_* above)."""
    return "https://" + user + ":" + secret + "@" + rest


def base_env(tmpdir: Path, gh_body: str = 'echo "stub gh: no network in tests" >&2; exit 97') -> dict:
    """Environment isolated from the host: no network transports, stub gh, empty git config."""
    bin_dir = tmpdir / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/sh\n" + gh_body + "\n")
    gh.chmod(0o755)
    gitconfig = tmpdir / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                         "[init]\n\tdefaultBranch = main\n")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k not in ("SYNC_TEST_MODE", "SYNC_ALLOW_LOCAL_REMOTE",
                                                      "APPROVED_FILES", "APPROVED_REMOTE",
                                                      "WORKSPACE_PATH")}
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_ALLOW_PROTOCOL": "file",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(tmpdir),
    })
    return env


def git(cwd, *args, env, check=True):
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=check,
                          capture_output=True, text=True)


def run_sync(cwd, env):
    return subprocess.run(["bash", str(SYNC_SCRIPT)], cwd=cwd, capture_output=True, env=env)


class TestSyncPreflight(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.env = base_env(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def init_repo(self, url=None, commit=False):
        repo = self.tmpdir / "repo"
        repo.mkdir()
        git(repo, "init", "-b", "main", env=self.env)
        if commit:
            (repo / "file.txt").write_text("test")
            git(repo, "add", "file.txt", env=self.env)
            git(repo, "commit", "-m", "init", env=self.env)
        if url:
            git(repo, "remote", "add", "origin", url, env=self.env)
        return repo

    def test_missing_workspace_path(self):
        """Should fail if WORKSPACE_PATH not set"""
        repo = self.tmpdir / "repo"
        repo.mkdir()
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": "",
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on missing WORKSPACE_PATH")
        self.assertIn(b"ERROR: WORKSPACE_PATH", result.stderr)

    def test_missing_approved_remote(self):
        """Should fail if APPROVED_REMOTE not set"""
        repo = self.init_repo("https://github.com/user/repo.git")
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo), "APPROVED_REMOTE": ""})
        self.assertNotEqual(result.returncode, 0, "Should fail on missing APPROVED_REMOTE")
        self.assertIn(b"ERROR: APPROVED_REMOTE", result.stderr)

    def test_not_in_git_repo(self):
        """Should fail if not in git repository"""
        result = run_sync(self.tmpdir, {**self.env, "WORKSPACE_PATH": str(self.tmpdir),
                                        "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail if not in git repo")
        self.assertIn(b"ERROR: Not in git repository", result.stderr)

    def test_detached_head(self):
        """Should fail on detached HEAD"""
        repo = self.init_repo(commit=True)
        commit = git(repo, "rev-parse", "HEAD", env=self.env).stdout.strip()
        git(repo, "checkout", commit, env=self.env)
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on detached HEAD")
        self.assertIn(b"ERROR: Detached HEAD", result.stderr)

    def test_no_origin_remote(self):
        """Should fail if no origin remote configured"""
        repo = self.init_repo()
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail if no origin")
        self.assertIn(b"ERROR: No 'origin' remote", result.stderr)

    def test_remote_mismatch_fetch(self):
        """Should fail if fetch remote doesn't match APPROVED_REMOTE"""
        repo = self.init_repo("https://github.com/user/actual.git")
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/different.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on remote mismatch")
        self.assertIn(b"ERROR: Fetch remote mismatch", result.stderr)

    def test_remote_mismatch_push(self):
        """Should fail if push remote doesn't match APPROVED_REMOTE"""
        repo = self.init_repo("https://github.com/user/repo.git")
        git(repo, "remote", "set-url", "--push", "origin", "https://github.com/user/different.git", env=self.env)
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on push remote mismatch")
        self.assertIn(b"ERROR: Push remote mismatch", result.stderr)

    def test_non_github_remote_rejected(self):
        """Should fail on non-GitHub remote (no privacy verification)"""
        repo = self.init_repo("https://gitlab.com/user/repo.git")
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://gitlab.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on non-GitHub remote")
        self.assertIn(b"ERROR: Non-GitHub remote", result.stderr)

    def test_github_host_spoof(self):
        """Should reject GitHub-like but invalid hosts"""
        repo = self.init_repo("https://evil-github.com/user/repo.git")
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://evil-github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0, "Should fail on non-GitHub remote")
        self.assertIn(b"ERROR: Non-GitHub remote", result.stderr)

    def test_workspace_path_through_symlink_accepted(self):
        """WORKSPACE_PATH given via a symlinked directory must match the git root.
        Old code compared raw strings: on systems where the temp dir is a symlink every
        later check was unreachable ('Git root does not match WORKSPACE_PATH')."""
        repo = self.init_repo("https://github.com/user/repo.git", commit=True)
        link = self.tmpdir / "link-to-repo"
        link.symlink_to(repo)
        result = run_sync(link, {**self.env, "WORKSPACE_PATH": str(link),
                                 "APPROVED_REMOTE": "https://github.com/user/other.git"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"Git root does not match", result.stderr)
        self.assertIn(b"ERROR: Fetch remote mismatch", result.stderr)

    def test_test_mode_does_not_bypass_privacy(self):
        """SYNC_TEST_MODE must not switch off the privacy check (old code skipped it,
        then committed locally against a repo gh reports as PUBLIC)."""
        self.env = base_env(self.tmpdir, gh_body='echo false')
        repo = self.init_repo("https://github.com/user/repo.git", commit=True)
        (repo / "data").mkdir()
        (repo / "data/board.jsonl").write_text('{"id":"t1"}\n')
        head = git(repo, "rev-parse", "HEAD", env=self.env).stdout.strip()
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo), "SYNC_TEST_MODE": "1",
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git",
                                 "APPROVED_FILES": "data/board.jsonl"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: SYNC_TEST_MODE is not supported", result.stderr)
        self.assertEqual(git(repo, "rev-parse", "HEAD", env=self.env).stdout.strip(), head)

    def test_public_repo_refused(self):
        """gh reports public -> refuse before any remote access"""
        self.env = base_env(self.tmpdir, gh_body='echo false')
        repo = self.init_repo("https://github.com/user/repo.git", commit=True)
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Repository is PUBLIC", result.stderr)

    def test_gh_failure_reported_without_secrets(self):
        """gh failure must give an explicit error (old code died silently under set -e)
        and never print credentials from the remote URL."""
        self.env = base_env(self.tmpdir, gh_body='echo "auth failed for ' + cred_url(FAKE_TOKEN, "github.com")
                            + ' token ' + FAKE_TOKEN + '" >&2; exit 1')
        url = cred_url(FAKE_TOKEN, "github.com/user/repo.git")
        repo = self.init_repo(url, commit=True)
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo), "APPROVED_REMOTE": url})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Cannot verify repository privacy", result.stderr)
        self.assertNotIn(FAKE_TOKEN.encode(), result.stderr + result.stdout)

    def test_multiple_push_urls_listed_sanitized(self):
        """Multiple push URLs: refuse and list them without credentials
        (old code called normalize_url before defining it and listed nothing)."""
        repo = self.init_repo("https://github.com/user/repo.git")
        git(repo, "remote", "set-url", "--add", "--push", "origin", cred_url(FAKE_PW, "github.com/user/repo.git", user="u"), env=self.env)
        git(repo, "remote", "set-url", "--add", "--push", "origin", "https://github.com/user/mirror.git", env=self.env)
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": "https://github.com/user/repo.git"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Multiple push URLs not allowed", result.stderr)
        self.assertIn(b"https://github.com/user/mirror.git", result.stderr)
        self.assertNotIn(FAKE_PW.encode(), result.stderr + result.stdout)
        self.assertNotIn(b"command not found", result.stderr)

    def test_mismatch_message_hides_credentials(self):
        """Remote mismatch errors print sanitized URLs only"""
        repo = self.init_repo(cred_url(FAKE_TOK, "github.com/user/actual.git"))
        result = run_sync(repo, {**self.env, "WORKSPACE_PATH": str(repo),
                                 "APPROVED_REMOTE": cred_url(FAKE_TOK, "github.com/user/other.git")})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Fetch remote mismatch", result.stderr)
        self.assertNotIn(FAKE_TOK.encode(), result.stderr + result.stdout)


class LocalRemoteCase(unittest.TestCase):
    """Working repo + local bare remote; the full fetch/commit/push path really runs."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.env = base_env(self.tmpdir)
        self.bare = self.tmpdir / "remote.git"
        git(self.tmpdir, "init", "--bare", "-b", "main", str(self.bare), env=self.env)
        self.repo = self.tmpdir / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main", env=self.env)
        git(self.repo, "remote", "add", "origin", str(self.bare), env=self.env)
        (self.repo / "data").mkdir()
        (self.repo / "data/decisions.jsonl").write_text('{"id":"d1"}\n')
        (self.repo / "data/board.jsonl").write_text('{"id":"b1"}\n')
        (self.repo / "notes.txt").write_text("tracked, not approved\n")
        git(self.repo, "add", "data/decisions.jsonl", "data/board.jsonl", "notes.txt", env=self.env)
        git(self.repo, "commit", "-m", "init", env=self.env)
        git(self.repo, "push", "-u", "origin", "main", env=self.env)
        self.sync_env = {**self.env, "WORKSPACE_PATH": str(self.repo),
                         "APPROVED_REMOTE": str(self.bare), "SYNC_ALLOW_LOCAL_REMOTE": "1",
                         "APPROVED_FILES": "data/decisions.jsonl data/board.jsonl"}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def head(self):
        return git(self.repo, "rev-parse", "HEAD", env=self.env).stdout.strip()

    def remote_head(self):
        return git(self.bare, "rev-parse", "refs/heads/main", env=self.env).stdout.strip()

    def index_clean(self):
        return git(self.repo, "diff", "--cached", "--quiet", env=self.env, check=False).returncode == 0

    def change_data(self):
        with open(self.repo / "data/decisions.jsonl", "a") as f:
            f.write('{"id":"d2"}\n')
        with open(self.repo / "data/board.jsonl", "a") as f:
            f.write('{"id":"b2"}\n')
        with open(self.repo / "notes.txt", "a") as f:
            f.write("local edit, must not be synced\n")
        (self.repo / "data/private.txt").write_text("untracked, must not be synced\n")

    def assert_unchanged(self, head, remote):
        self.assertEqual(self.head(), head, "local HEAD must be unchanged after a failure")
        self.assertTrue(self.index_clean(), "index must be clean after a failure")
        self.assertEqual(self.remote_head(), remote, "remote must be unchanged after a failure")
        self.assertIn("d2", (self.repo / "data/decisions.jsonl").read_text(), "working tree kept")


class TestSyncFullPath(LocalRemoteCase):
    def test_positive_sync_commits_only_allowlisted_and_pushes(self):
        """Full path: one commit with exactly the changed approved files, pushed and verified."""
        self.change_data()
        before = self.head()
        result = run_sync(self.repo, self.sync_env)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        after = self.head()
        self.assertNotEqual(after, before)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD~1", env=self.env).stdout.strip(), before)
        self.assertEqual(self.remote_head(), after, "remote must hold the new commit")
        files = git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", env=self.env).stdout.split()
        self.assertEqual(sorted(files), ["data/board.jsonl", "data/decisions.jsonl"])
        self.assertTrue(self.index_clean())
        status = git(self.repo, "status", "--porcelain", env=self.env).stdout
        self.assertIn(" M notes.txt", status, "non-approved edit stays local")
        self.assertIn("?? data/private.txt", status, "untracked file stays untracked")
        self.assertIn(b"Pushed and verified", result.stderr)

    def test_no_changes_no_commit(self):
        before = self.head()
        result = run_sync(self.repo, self.sync_env)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b"No changes to commit", result.stderr)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.remote_head(), before)

    def test_local_remote_requires_opt_in(self):
        env = {k: v for k, v in self.sync_env.items() if k != "SYNC_ALLOW_LOCAL_REMOTE"}
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Non-GitHub remote", result.stderr)
        self.assert_unchanged(head, remote)

    def test_local_remote_must_be_bare(self):
        other = self.tmpdir / "not-bare"
        other.mkdir()
        git(other, "init", "-b", "main", env=self.env)
        git(self.repo, "remote", "set-url", "origin", str(other), env=self.env)
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_REMOTE": str(other)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Local remote is not a bare git repository", result.stderr)
        self.assertEqual(self.head(), head)
        self.assertTrue(self.index_clean())
        self.assertEqual(self.remote_head(), remote)

    def test_foreign_commit_on_remote_refused(self):
        other = self.tmpdir / "other"
        git(self.tmpdir, "clone", str(self.bare), str(other), env=self.env)
        (other / "foreign.txt").write_text("x\n")
        git(other, "add", "foreign.txt", env=self.env)
        git(other, "commit", "-m", "foreign", env=self.env)
        git(other, "push", "origin", "main", env=self.env)
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, self.sync_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Foreign commits detected", result.stderr)
        self.assert_unchanged(head, remote)

    def test_unpushed_local_commit_refused(self):
        (self.repo / "extra.txt").write_text("x\n")
        git(self.repo, "add", "extra.txt", env=self.env)
        git(self.repo, "commit", "-m", "local only", env=self.env)
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, self.sync_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Local unpushed commits", result.stderr)
        self.assert_unchanged(head, remote)

    def test_commit_failure_restores_index(self):
        """A failing commit (hook) leaves HEAD and index as before (old code left files staged)."""
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
        hook.chmod(0o755)
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, self.sync_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Commit failed", result.stderr)
        self.assert_unchanged(head, remote)

    def test_push_failure_restores_head_and_index(self):
        """A rejected push leaves no local commit behind and publishes nothing."""
        hook = self.bare / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\necho 'remote says no' >&2\nexit 1\n")
        hook.chmod(0o755)
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, self.sync_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Push failed", result.stderr)
        self.assertIn(b"Rolled back: HEAD and index restored", result.stderr)
        self.assert_unchanged(head, remote)

    def test_database_file_in_allowlist_refused(self):
        (self.repo / "data/stats.db").write_bytes(b"SQLite format 3\x00")
        self.change_data()
        head, remote = self.head(), self.remote_head()
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": "data/board.jsonl data/stats.db"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ERROR: Database files not allowed", result.stderr)
        self.assert_unchanged(head, remote)

    def test_dot_components_rejected(self):
        head, remote = self.head(), self.remote_head()
        for bad in ("data/./board.jsonl", "data//board.jsonl", "data/.."):
            result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": bad})
            self.assertNotEqual(result.returncode, 0, bad)
            self.assertIn(b"ERROR: Path traversal not allowed", result.stderr, bad)
        self.assertEqual(self.head(), head)
        self.assertTrue(self.index_clean())
        self.assertEqual(self.remote_head(), remote)


class TestSyncValidation(LocalRemoteCase):
    """Allowlist validation, exercised on the full (local) path."""

    def test_glob_patterns_rejected(self):
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": "data/*.jsonl"})
        self.assertNotEqual(result.returncode, 0, "Should reject glob patterns")
        self.assertIn(b"ERROR: Glob patterns not allowed", result.stderr)

    def test_path_traversal_rejected(self):
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": "../outside.txt"})
        self.assertNotEqual(result.returncode, 0, "Should reject path traversal")
        self.assertIn(b"ERROR: Path traversal not allowed", result.stderr)

    def test_symlinks_rejected(self):
        (self.repo / "data/real.txt").write_text("real")
        (self.repo / "data/link.txt").symlink_to("real.txt")
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": "data/link.txt"})
        self.assertNotEqual(result.returncode, 0, "Should reject symlinks")
        self.assertIn(b"ERROR: Symlinks not allowed", result.stderr)

    def test_git_paths_rejected(self):
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": ".git/config"})
        self.assertNotEqual(result.returncode, 0, "Should reject .git paths")
        self.assertIn(b"ERROR: .git paths not allowed", result.stderr)

    def test_preexisting_staged_files_rejected(self):
        (self.repo / "data/foreign.txt").write_text("foreign")
        git(self.repo, "add", "data/foreign.txt", env=self.env)
        result = run_sync(self.repo, {**self.sync_env, "APPROVED_FILES": "data/approved.jsonl"})
        self.assertNotEqual(result.returncode, 0, "Should reject preexisting staged files")
        self.assertIn(b"ERROR: Index has preexisting staged files", result.stderr)
        staged = git(self.repo, "diff", "--cached", "--name-only", env=self.env).stdout.split()
        self.assertEqual(staged, ["data/foreign.txt"], "the user's own staging is left alone")


class TestSyncCLI(unittest.TestCase):
    def test_script_exists_and_executable(self):
        """Sync script should exist and be executable"""
        self.assertTrue(SYNC_SCRIPT.exists(), "sync-data.sh should exist")
        self.assertTrue(os.access(SYNC_SCRIPT, os.X_OK), "sync-data.sh should be executable")


if __name__ == "__main__":
    print(f"Testing: {SYNC_SCRIPT}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("NOTE: local bare remotes only; non-file git transports disabled", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stderr)
    result = runner.run(suite)

    sys.exit(0 if result.wasSuccessful() else 1)
