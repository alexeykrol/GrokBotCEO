#!/usr/bin/env python3
"""Freeze manifest of the course release (plan 0.3.0 §1): release/MANIFEST.sha256.

    manifest.py gen                 write release/MANIFEST.sha256                                  (needs git)
    manifest.py check               compare the manifest with the git listing; exit 1 naming every
                                    mismatched, missing or extra path                              (needs git)
    manifest.py export OUT.tar.gz   deterministic payload archive: ONLY the manifest's files + the manifest
                                    (refuses if `check` fails); prints the archive sha256           (needs git)
    manifest.py verify [--root DIR] verify an exported / installed copy WITHOUT git: every listed hash, then
                                    every file in scope under DIR that is not listed is reported as extra

Format: the `sha256sum` format, one line per file, `<64 hex>  <path>`, paths relative to the repository root,
sorted by path (byte order of the UTF-8 path). Covered: every file under release/, services/feedback-receiver/ and
testkit/ (bench kits for testing the release, never installed for students) that git lists - tracked (`git ls-files --cached`) plus untracked-but-not-ignored (`--others
--exclude-standard`, so a file added for the freeze is covered before its commit) - that exists on disk, except
the manifest itself. Ignored files (data, caches, __pycache__) can never enter. Stdlib only; reads git through
`git -C <root> ls-files -z`. `sha256sum -c release/MANIFEST.sha256` from the repository root verifies the
listed files independently.

`verify` ignores exactly these unlisted files (created by running the code, never shipped): any path with a
`__pycache__` component, files ending in `.pyc`, and files named `.DS_Store`. Everything else in scope that is
not listed is an error, and so are symlinks, listed paths outside the scope, absolute paths or `..`. It is meant
for an exported copy; in the development checkout use `check` (the checkout holds ignored local data).

`export` is byte-reproducible: entries sorted by path, file entries only (directories are implied), mtime 0,
uid/gid 0, empty owner names, mode 0644 (0755 when the source file is executable), PAX format, gzip header with
mtime 0 and no file name. Nothing outside release/, services/feedback-receiver/ and testkit/ can enter.
"""
import argparse
import gzip
import hashlib
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = "release/MANIFEST.sha256"
SCOPES = ("release/", "services/feedback-receiver/", "testkit/")


def listed(root: Path = ROOT):
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                          "--", *SCOPES], capture_output=True, check=True).stdout
    paths = {p.decode("utf-8") for p in out.split(b"\0") if p}
    return sorted((p for p in paths if p != MANIFEST and (root / p).is_file()), key=lambda p: p.encode("utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render(root: Path = ROOT) -> bytes:
    lines = []
    for p in listed(root):
        if "\n" in p or "\\" in p:
            raise SystemExit(f"manifest: unsupported character in path {p!r}")
        lines.append(f"{sha256(root / p)}  {p}\n")
    return "".join(lines).encode("utf-8")


def parse(data: bytes):
    out = {}
    for n, line in enumerate(data.decode("utf-8").splitlines(), 1):
        digest, sep, path = line.partition("  ")
        if not sep or len(digest) != 64 or not path:
            raise ValueError(f"line {n}: not '<sha256>  <path>'")
        out[path] = digest
    return out


def check(root: Path = ROOT):
    """-> list of problems (empty = the manifest matches the tree)."""
    mpath = root / MANIFEST
    if not mpath.is_file():
        return [f"missing manifest: {MANIFEST}"]
    data = mpath.read_bytes()
    try:
        want = parse(data)
    except ValueError as e:
        return [f"malformed manifest: {e}"]
    have = listed(root)
    problems = []
    for p in sorted(set(want) - set(have)):
        problems.append(f"missing: {p}" if not (root / p).is_file() else f"not covered (ignored or out of scope): {p}")
    for p in sorted(set(have) - set(want)):
        problems.append(f"extra: {p}")
    for p in sorted(set(want) & set(have)):
        if sha256(root / p) != want[p]:
            problems.append(f"mismatch: {p}")
    if not problems and data != render(root):
        problems.append("not canonical: order or format differs from `manifest.py gen`")
    return problems


def ignorable(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return "__pycache__" in parts or rel.endswith(".pyc") or parts[-1] == ".DS_Store"


def safe_path(rel: str) -> bool:
    pp = PurePosixPath(rel)
    return (not pp.is_absolute() and ".." not in pp.parts and "\\" not in rel
            and (rel == MANIFEST or rel.startswith(SCOPES)))


def verify(root: Path):
    """No git. -> list of problems: listed files hashed, then unlisted files in scope reported as extra."""
    mpath = root / MANIFEST
    if not mpath.is_file():
        return [f"missing manifest: {MANIFEST}"]
    try:
        want = parse(mpath.read_bytes())
    except (ValueError, UnicodeDecodeError) as e:
        return [f"malformed manifest: {e}"]
    problems = []
    for rel, digest in sorted(want.items()):
        f = root / rel
        if not safe_path(rel) or rel == MANIFEST:
            problems.append(f"listed path out of scope: {rel}")
        elif f.is_symlink():
            problems.append(f"symlink: {rel}")
        elif not f.is_file():
            problems.append(f"missing: {rel}")
        elif sha256(f) != digest:
            problems.append(f"mismatch: {rel}")
    for scope in SCOPES:
        base = root / scope
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames) + sorted(d for d in dirnames if (Path(dirpath) / d).is_symlink()):
                rel = (Path(dirpath) / name).relative_to(root).as_posix()
                if rel == MANIFEST or rel in want or ignorable(rel):
                    continue
                problems.append(f"extra: {rel}")
    return problems


def export(out: Path, root: Path = ROOT) -> str:
    problems = check(root)
    if problems:
        raise SystemExit("manifest: refusing to export, the manifest does not match the tree: " + "; ".join(problems))
    paths = sorted(list(parse((root / MANIFEST).read_bytes())) + [MANIFEST], key=lambda p: p.encode("utf-8"))
    bad = [p for p in paths if not safe_path(p)]
    if bad:
        raise SystemExit(f"manifest: refusing to export paths outside the payload: {bad}")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in paths:
            f = root / rel
            data = f.read_bytes()
            info = tarfile.TarInfo(rel)
            info.size = len(data)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o755 if os.stat(f).st_mode & 0o111 else 0o644
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    gz = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz, mtime=0, compresslevel=9) as z:
        z.write(raw.getvalue())
    blob = gz.getvalue()
    tmp = out.with_name(f".{out.name}.tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, out)
    return hashlib.sha256(blob).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate, check, export or verify release/MANIFEST.sha256.")
    ap.add_argument("action", choices=("gen", "check", "export", "verify"))
    ap.add_argument("out", nargs="?", type=Path, help="export: the archive to write (.tar.gz)")
    ap.add_argument("--root", type=Path, default=None, help="verify: the copy to verify (default: this tree)")
    a = ap.parse_args(argv)
    if a.root is None:
        a.root = ROOT
    if a.action == "export":
        if a.out is None:
            ap.error("export needs OUT.tar.gz")
        digest = export(a.out, a.root)
        print(f"manifest: exported {a.out} sha256 {digest}")
        return 0
    if a.action == "verify":
        problems = verify(a.root)
        for p in problems:
            print(f"manifest: {p}", file=sys.stderr)
        if problems:
            return 1
        data = (a.root / MANIFEST).read_bytes()
        n = data.count(b"\n")
        print(f"manifest: verified, {n} files, sha256 {hashlib.sha256(data).hexdigest()}")
        return 0
    if a.action == "gen":
        data = render(a.root)
        (a.root / MANIFEST).write_bytes(data)
        n = data.count(b"\n")
        print(f"manifest: {n} files, sha256 {hashlib.sha256(data).hexdigest()}")
        return 0
    problems = check(a.root)
    for p in problems:
        print(f"manifest: {p}", file=sys.stderr)
    if problems:
        return 1
    data = (a.root / MANIFEST).read_bytes()
    n = data.count(b"\n")
    print(f"manifest: ok, {n} files, sha256 {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
