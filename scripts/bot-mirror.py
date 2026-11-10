#!/usr/bin/env python3
"""
bot-mirror.py - bookkeeping for the user's repo mirror. No network, no bot tools.

The bots decide; this script only compares and copies, so exact checks are done by code.

Commands:
  check     --agent-id ID --expected FILE   print VERIFIED | MISMATCH | NOT VERIFIED
  list                                      print every bot on the bot computer
                                            (JSON list of {agent_id, name}); the installer
                                            uses it to find the user's main bot
  scan      --workspace DIR                 print bots on the bot computer that the mirror
                                            does not know yet (JSON list of {agent_id, name})
  snapshot  --workspace DIR --agent-id ID   copy ONLY name + description of that bot into
            [--source marketplace|unknown]  bots/marketplace/<slug>/ (prompt.md, agent.json)
  pack      --workspace DIR --out FILE      archive the committed repo (.tar.gz) for the
                                            read-only copy on the user's computer
                                            (see LOCAL-COPY.md); print the archive path
                                            and the short HEAD hash

Each bot's folder on the bot computer is <agents-dir>/<agent_id>/profile.json
(default agents-dir: agent-data/agents in the home folder of the bot computer).
Only profile.json is ever read, and only
its `name` and `description` fields are used. No other file of a bot folder is opened.

pack: the archive holds the committed repo only, so the copy equals a commit.
  - Refused if --workspace is not the top folder of a git repo, has no commit yet, or has
    uncommitted changes to tracked files.
  - Contents: the marker file .grokbotceo-copy (first member), every regular file listed by
    `git ls-files`, and the .git/ folder. Never untracked files, grokbotceo/ or build/.
  - Symlinks are never stored: a tracked file that is a symlink is skipped, and so is any
    symlink inside .git/. Only regular files and folders go in; names are relative to the
    repo root.
  - The copy is opened on the user's own computer, so nothing from .git/ that git could run
    there is copied: .git/config is replaced by a minimal one (format settings only), and
    .git/hooks/, .git/modules/, .git/worktrees/, config.worktree and *.lock files are left
    out. .git/info/exclude gets the marker name, so the copy shows a clean `git status`.
  - Owner names are dropped; modes become 644 or 755.
"""
import argparse
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_AGENTS_DIR = Path.home() / "agent-data" / "agents"
AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SOURCES = ("marketplace", "unknown")


class MirrorError(ValueError):
    pass


def valid_agent_id(agent_id: str) -> str:
    if not isinstance(agent_id, str) or not AGENT_ID_RE.match(agent_id):
        raise MirrorError(f"invalid agent id: {agent_id!r}")
    return agent_id


def read_profile(agents_dir: Path, agent_id: str) -> Optional[Dict[str, str]]:
    """Return {name, description} from profile.json, or None if missing or unreadable."""
    path = agents_dir / valid_agent_id(agent_id) / "profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name, description = data.get("name"), data.get("description")
    if not isinstance(name, str) or not isinstance(description, str):
        return None
    return {"name": name, "description": description}


def check(agents_dir: Path, agent_id: str, expected_file: Path) -> str:
    """Write check: the description on disk equals the text that was sent, character by character.

    Grok Bot trims trailing whitespace when it saves a description (verified on a test account,
    rc2), so trailing whitespace is ignored on both sides. Any other difference is a MISMATCH.
    """
    try:
        expected = expected_file.read_text(encoding="utf-8")
    except OSError as e:
        raise MirrorError(f"cannot read expected text {expected_file}: {e}")
    profile = read_profile(agents_dir, agent_id)
    if profile is None:
        return "NOT VERIFIED"
    return "VERIFIED" if profile["description"].rstrip() == expected.rstrip() else "MISMATCH"


def list_bots(agents_dir: Path) -> List[Dict[str, str]]:
    """Every bot folder with a readable profile.json that has a name.

    The description may be missing (a bot nobody wrote a text for). Folders with group.json are
    channels, not bots, and are skipped.
    """
    try:
        entries = sorted(d for d in agents_dir.iterdir() if d.is_dir())
    except OSError as e:
        raise MirrorError(f"agents folder not readable: {agents_dir}: {e}")
    found = []
    for d in entries:
        if not AGENT_ID_RE.match(d.name) or (d / "group.json").exists():
            continue
        try:
            data = json.loads((d / "profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            found.append({"agent_id": d.name, "name": data["name"]})
    return found


def known_agent_ids(workspace: Path) -> Set[str]:
    """agent_id of every bot recorded in bots/core, bots/my and bots/marketplace."""
    ids: Set[str] = set()
    for path in sorted(workspace.glob("bots/*/*/agent.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("agent_id"), str):
            ids.add(data["agent_id"])
    return ids


def scan(agents_dir: Path, workspace: Path) -> List[Dict[str, str]]:
    try:
        entries = sorted(d for d in agents_dir.iterdir() if d.is_dir())
    except OSError as e:
        raise MirrorError(f"agents folder not readable: {agents_dir}: {e}")
    known = known_agent_ids(workspace)
    found = []
    for d in entries:
        if not AGENT_ID_RE.match(d.name) or d.name in known or (d / "group.json").exists():
            continue  # group.json: a channel, not a bot
        profile = read_profile(agents_dir, d.name)
        if profile is None:
            continue
        found.append({"agent_id": d.name, "name": profile["name"]})
    return found


def slugify(name: str) -> str:
    # Keep letters of any alphabet (bot names are often not in English); drop everything else.
    slug = re.sub(r"[\W_]+", "-", name.lower(), flags=re.UNICODE).strip("-")
    return slug or "bot"


def snapshot(agents_dir: Path, workspace: Path, agent_id: str, source: str) -> Path:
    if source not in SOURCES:
        raise MirrorError(f"source must be one of {', '.join(SOURCES)}")
    if agent_id in known_agent_ids(workspace):
        raise MirrorError(f"agent {agent_id} is already in the mirror")
    profile = read_profile(agents_dir, agent_id)
    if profile is None:
        raise MirrorError(f"profile.json of agent {agent_id} is missing or unreadable")
    base = workspace / "bots" / "marketplace"
    slug = slugify(profile["name"])
    target, n = base / slug, 2
    while target.exists():
        target, n = base / f"{slug}-{n}", n + 1
    target.mkdir(parents=True)
    (target / "prompt.md").write_text(profile["description"], encoding="utf-8")
    record = {"agent_id": agent_id, "source": source}
    (target / "agent.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return target


COPY_MARKER = ".grokbotceo-copy"
COPY_MARKER_TEXT = ("Read-only copy of a GrokBotCEO repo. "
                    "Changes made here are overwritten on the next refresh.\n")
NEVER_PACKED = ("grokbotceo", "build", ".git")      # top-level names never taken from ls-files
GIT_SKIPPED_DIRS = ("hooks", "modules", "worktrees")  # inside .git/, left out entirely
GIT_SKIPPED_FILES = ("config", "config.worktree", "info/exclude")  # config, exclude: rewritten
CARRIED_EXTENSIONS = {"objectformat": ("sha1", "sha256"), "refstorage": ("files", "reftable")}


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "--no-optional-locks", *args], cwd=workspace,
                              capture_output=True)
    except OSError as e:
        raise MirrorError(f"cannot run git: {e}")


def _git_text(workspace: Path, *args: str) -> str:
    r = _git(workspace, *args)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace").strip()
        raise MirrorError(f"git {' '.join(args)} failed: {err}")
    return r.stdout.decode("utf-8", errors="replace")


def _git_config_value(workspace: Path, key: str) -> str:
    r = _git(workspace, "config", "--local", "--get", key)
    return r.stdout.decode("utf-8", errors="replace").strip() if r.returncode == 0 else ""


def _copy_git_config(workspace: Path) -> bytes:
    """A minimal .git/config for the copy: repo format only, nothing git could run."""
    extensions = []
    for key, allowed in CARRIED_EXTENSIONS.items():
        value = _git_config_value(workspace, f"extensions.{key}").lower()
        if value and value not in allowed:
            raise MirrorError(f"unsupported repo setting extensions.{key} = {value}")
        if value:
            extensions.append((key, value))
    lines = ["[core]",
             f"\trepositoryformatversion = {1 if extensions else 0}",
             "\tfilemode = true",
             "\tbare = false",
             "\tlogallrefupdates = true"]
    if extensions:
        lines.append("[extensions]")
        lines += [f"\t{key} = {value}" for key, value in extensions]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _clean_member(ti: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
    """Only regular files and folders; no owner names; modes 644 / 755."""
    if not (ti.isfile() or ti.isdir()):
        return None
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    ti.mode = 0o755 if ti.isdir() or ti.mode & 0o111 else 0o644
    return ti


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    ti = tarfile.TarInfo(name)
    ti.size, ti.mode, ti.mtime = len(data), 0o644, int(time.time())
    tar.addfile(ti, io.BytesIO(data))


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def tracked_files(workspace: Path) -> List[str]:
    """Regular files listed by `git ls-files`, minus symlinks and never-packed folders."""
    out = _git(workspace, "ls-files", "-z")
    if out.returncode != 0:
        raise MirrorError("git ls-files failed: " + out.stderr.decode("utf-8", errors="replace").strip())
    files = []
    for raw in out.stdout.split(b"\0"):
        if not raw:
            continue
        rel = os.fsdecode(raw)
        parts = rel.split("/")
        if (rel.startswith("/") or "" in parts or "." in parts or ".." in parts
                or parts[0] in NEVER_PACKED or rel == COPY_MARKER):
            continue
        if _is_regular(workspace / rel):
            files.append(rel)
    return files


def git_dir_members(workspace: Path) -> List[Tuple[Path, str]]:
    """(path, name in archive) for the .git/ folder: folders and regular files, no symlinks."""
    git_dir = workspace / ".git"
    members = []
    for dirpath, dirnames, filenames in os.walk(git_dir):
        here = Path(dirpath)
        rel_here = here.relative_to(git_dir).as_posix()
        keep = []
        for d in sorted(dirnames):
            if (here / d).is_symlink() or (rel_here == "." and d in GIT_SKIPPED_DIRS):
                continue
            keep.append(d)
        dirnames[:] = keep
        arc_here = ".git" if rel_here == "." else f".git/{rel_here}"
        members.append((here, arc_here))
        for f in sorted(filenames):
            rel = f if rel_here == "." else f"{rel_here}/{f}"
            if rel in GIT_SKIPPED_FILES or f.endswith(".lock") or not _is_regular(here / f):
                continue
            members.append((here / f, f"{arc_here}/{f}"))
    return members


def pack(workspace: Path, out: Path) -> Tuple[Path, str]:
    """Archive the committed repo for the copy on the user's computer. Returns (archive, short HEAD)."""
    git_dir = workspace / ".git"
    if not workspace.is_dir() or git_dir.is_symlink() or not git_dir.is_dir():
        raise MirrorError(f"not a git repo: {workspace} (no .git folder)")
    top = _git(workspace, "rev-parse", "--show-cdup")
    if top.returncode != 0 or top.stdout.strip():
        raise MirrorError(f"not the top folder of a git repo: {workspace}")
    head = _git(workspace, "rev-parse", "--verify", "--short", "HEAD")
    if head.returncode != 0:
        raise MirrorError("the repo has no commit yet")
    short = head.stdout.decode("utf-8", errors="replace").strip()
    if _git_text(workspace, "status", "--porcelain", "--untracked-files=no").strip():
        raise MirrorError("the repo has uncommitted changes to tracked files; "
                          "commit them first (the copy must equal a commit)")

    out = out if out.is_absolute() else Path.cwd() / out
    if git_dir.resolve() in out.resolve().parents:
        raise MirrorError("--out must not be inside .git/")
    files = tracked_files(workspace)
    git_members = git_dir_members(workspace)
    exclude = b""
    if _is_regular(git_dir / "info" / "exclude"):
        exclude = (git_dir / "info" / "exclude").read_bytes()
        if exclude and not exclude.endswith(b"\n"):
            exclude += b"\n"
    exclude += COPY_MARKER.encode("utf-8") + b"\n"

    part = out.with_name(out.name + ".part")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(part, "w:gz") as tar:
            _add_bytes(tar, COPY_MARKER, COPY_MARKER_TEXT.encode("utf-8"))
            for rel in files:
                tar.add(str(workspace / rel), arcname=rel, recursive=False, filter=_clean_member)
            for path, name in git_members:
                tar.add(str(path), arcname=name, recursive=False, filter=_clean_member)
            _add_bytes(tar, ".git/config", _copy_git_config(workspace))
            _add_bytes(tar, ".git/info/exclude", exclude)
        os.replace(part, out)
    except OSError as e:
        raise MirrorError(f"cannot write archive {out}: {e}")
    finally:
        if part.exists():
            part.unlink()
    return out, short


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bookkeeping for the GrokBotCEO repo mirror")
    parser.add_argument("command", choices=["check", "list", "scan", "snapshot", "pack"])
    parser.add_argument("--agent-id")
    parser.add_argument("--expected", type=Path, help="file with the exact text sent (check)")
    parser.add_argument("--workspace", type=Path, help="workspace root (scan, snapshot, pack)")
    parser.add_argument("--out", type=Path, help="archive to write (pack)")
    parser.add_argument("--source", default="unknown", help="marketplace | unknown (snapshot)")
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            if not args.agent_id or not args.expected:
                raise MirrorError("check needs --agent-id and --expected")
            print(check(args.agents_dir, args.agent_id, args.expected))
        elif args.command == "list":
            print(json.dumps(list_bots(args.agents_dir), indent=2, ensure_ascii=False))
        elif args.command == "scan":
            if not args.workspace:
                raise MirrorError("scan needs --workspace")
            print(json.dumps(scan(args.agents_dir, args.workspace), indent=2, ensure_ascii=False))
        elif args.command == "snapshot":
            if not args.workspace or not args.agent_id:
                raise MirrorError("snapshot needs --workspace and --agent-id")
            print(snapshot(args.agents_dir, args.workspace, args.agent_id, args.source))
        else:
            if not args.workspace or not args.out:
                raise MirrorError("pack needs --workspace and --out")
            archive, short = pack(args.workspace, args.out)
            print(archive)
            print(f"commit {short}")
        return 0
    except MirrorError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
