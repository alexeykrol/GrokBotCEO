"""Where a base's derived files live and what its config holds (SPEC §3, §8 S1/S6/S7).

Derived files live in ``$KB_HOME/<slug>/`` (default ``~/.kb``), outside the documents folder.

"Base in a box" (0.3.0): if the plugin ships a ready-made base in ``skills/kb-ask/data/``
(``kb.sqlite`` + ``box.json``), it is the default base. The plugin folder is replaced whole on
update and may be read-only, so the base is opened read-only, and the user's decisions
(verdicts, misses, conflicts) are written to ``$KB_HOME/<base name>/user/`` — they survive a
plugin update.
``kb.yaml`` is written as a subset of YAML: one line per ``key: <JSON>`` — readable both by this
code and by any YAML parser.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

DEFAULT_LIMITS = {
    "max_file_bytes": 50 * 1024 * 1024,      # S7: file <= 50 MB
    "max_files": 2000,                       # S7: corpus <= 2,000 files
    "max_text_bytes": 200 * 1024 * 1024,     # S7: <= 200 MB of text
    "max_unit_chars": 12000,                 # unit <= 12,000 chars -> parts
    "batch_chars": 60000,                    # markup batch <= 60,000 chars
}
DEFAULTS = {
    "genres": ["reflection", "idea", "practical", "reference", "narrative", "mixed", "noise"],
    "categories": [],                         # empty = the model proposes a category (MVP)
    "exclude": [],                            # fnmatch patterns relative to the corpus root
    "include_forced": [],                     # explicitly included paths (inside the corpus only)
    "vocab_corridor": [30, 70],
}
EDGE_TYPES = ("continues", "develops", "contradicts", "revisits", "applies", "duplicates")
EDGE_CONFIDENCE = ("extracted", "inferred", "ambiguous")
VERDICTS = ("valuable", "rejected", "outdated", "disputed")
# Verdict values written by 0.3.1 and earlier (Russian). Accepted as input and when reading stored
# verdicts.tsv / kb.sqlite, mapped to the English values above. Data written now is English only.
LEGACY_VERDICTS = {"ценно": "valuable", "отвергнуто": "rejected", "устарело": "outdated", "спорно": "disputed"}
RESOLUTIONS = ("kb", "model", "both", "pending")

SYSTEM_ROOTS = ("/", "/System", "/Library", "/usr", "/bin", "/sbin", "/etc", "/var", "/private",
                "/Applications", "/opt", "/dev", "/Volumes", "/cores", "/tmp", "/proc", "/sys", "/boot",
                "/root", "/home", "/Users")


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
BOX_DATA = ("skills", "kb-ask", "data")        # ready-made base inside the kb-ask skill (works without MCP)
BOX_META = "box.json"

DEMO_SLUG = "kb-demo"                         # demo base of the /kb-start skill (samples/)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class KbError(Exception):
    """An error the user should see as a message (not a traceback)."""


def normalize_verdict(value) -> str | None:
    """Canonical verdict for a stored or entered value (English, or a legacy Russian one); None if unknown."""
    v = str(value or "").strip().lower()
    if v in VERDICTS:
        return v
    return LEGACY_VERDICTS.get(v)


def kb_home() -> Path:
    return Path(os.environ.get("KB_HOME") or (Path.home() / ".kb")).expanduser()


def slug_for(corpus: Path) -> str:
    base = re.sub(r"[^\w.-]+", "-", corpus.name, flags=re.UNICODE).strip("-.")[:40] or "corpus"
    return f"{base}-{hashlib.sha256(str(corpus).encode()).hexdigest()[:6]}"


def check_corpus_root(path: str | os.PathLike) -> Path:
    """S1: the corpus is an existing folder, not a system one, not the whole home folder, not containing KB_HOME."""
    p = Path(path).expanduser()
    if not p.exists() or not p.is_dir():
        raise KbError(f"folder not found: {p}")
    real = Path(os.path.realpath(p))
    home = Path(os.path.realpath(Path.home()))
    if real == home:
        raise KbError("the whole home folder is not accepted — point to a specific documents folder")
    for root in SYSTEM_ROOTS:
        if str(real) == os.path.realpath(root) or str(real) == root:
            raise KbError(f"system folder not accepted: {real}")
    if str(real).startswith("/System/") or str(real).startswith("/usr/") or str(real).startswith("/etc/"):
        raise KbError(f"system folder not accepted: {real}")
    kh = Path(os.path.realpath(kb_home()))
    if kh == real or str(kh).startswith(str(real) + os.sep):
        raise KbError(f"the base folder {kh} is inside the corpus — derived files must live outside the documents (S6)")
    if str(real).startswith(str(kh) + os.sep):
        raise KbError("a corpus inside the bases folder ~/.kb is not accepted")
    return real


def dump_yaml(data: dict) -> str:
    lines = ["# kb.yaml — corpus config (format: \"key: JSON\", YAML-compatible)"]
    for k, v in data.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def load_yaml(text: str) -> dict:
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        key, sep, val = s.partition(":")
        if not sep:
            raise KbError(f"kb.yaml line {n}: expected \"key: value\"")
        try:
            out[key.strip()] = json.loads(val.strip())
        except json.JSONDecodeError as exc:
            raise KbError(f"kb.yaml line {n}: value is not JSON ({exc.msg})") from None
    return out


class Base:
    """One base: ``$KB_HOME/<slug>/`` with all its derived files."""

    boxed = False

    def __init__(self, root: Path):
        self.root = root
        self.yaml = root / "kb.yaml"
        self.db = root / "kb.sqlite"
        self.markup = root / "markup"
        self.units_dir = root / "units"
        self.batches = root / "batches"
        self.runs = root / "runs"
        self.status = root / "status.json"
        self.scan_json = root / "scan.json"
        self.extract_json = root / "extract.json"

    @property
    def slug(self) -> str:
        return self.root.name

    def config(self) -> dict:
        if not self.yaml.exists():
            raise KbError(f"{self.yaml} not found — run kbtool init <folder> first")
        cfg = {**DEFAULTS, **load_yaml(self.yaml.read_text(encoding="utf-8"))}
        cfg["limits"] = {**DEFAULT_LIMITS, **(cfg.get("limits") or {})}
        return cfg

    def save_config(self, cfg: dict) -> None:
        write_private(self.yaml, dump_yaml(cfg))

    def corpus(self) -> Path:
        return Path(self.config()["corpus_path"])

    def ensure_dirs(self) -> None:
        for d in (self.root, self.markup, self.units_dir, self.batches, self.runs):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)

    def prepare_writes(self) -> None:
        """Before writing a user decision: make sure the TSV folder exists."""
        self.markup.mkdir(parents=True, exist_ok=True)


class BoxedBase(Base):
    """A ready-made base shipped inside the plugin. Read-only; user records are kept separately.

    ``root`` — ``<plugin>/skills/kb-ask/data`` (``kb.sqlite``, ``box.json``);
    ``markup`` (where verdicts/misses/conflicts are written) — ``$KB_HOME/<name>/user``.
    """

    boxed = True

    def __init__(self, data_dir: Path, meta: dict):
        super().__init__(data_dir)
        self.meta = meta
        self.name = meta["name"]
        self.user_dir = kb_home() / self.name / "user"
        self.markup = self.user_dir

    @property
    def slug(self) -> str:
        return self.name

    def config(self) -> dict:
        return {"corpus_path": None, "boxed": True, "title": self.meta.get("title"),
                "topic": self.meta.get("topic")}

    def prepare_writes(self) -> None:
        real = Path(os.path.realpath(self.user_dir))
        plugin = Path(os.path.realpath(PLUGIN_ROOT))
        if real == plugin or str(real).startswith(str(plugin) + os.sep):
            raise KbError(f"the decisions folder {real} is inside the plugin — it would be lost on update; set KB_HOME outside the plugin")
        for d in (kb_home(), self.user_dir.parent, self.user_dir):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)


def box_dir(plugin_root: Path | None = None) -> Path:
    return (plugin_root or PLUGIN_ROOT).joinpath(*BOX_DATA)


def boxed_base(plugin_root: Path | None = None) -> BoxedBase | None:
    """The plugin's ready-made base, or None if there is none (plugin source, build-your-own mode)."""
    d = box_dir(plugin_root)
    meta_path, db = d / BOX_META, d / "kb.sqlite"
    if not (meta_path.is_file() and db.is_file()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KbError(f"{meta_path}: base metadata is unreadable ({exc})") from None
    if not isinstance(meta, dict) or not SLUG_RE.match(str(meta.get("name") or "")):
        raise KbError(f"{meta_path}: no valid base name (name)")
    return BoxedBase(d, meta)


def write_private(path: Path, text: str) -> None:
    """Atomically write a text file with 0600 permissions (S6)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def init_base(corpus: str | os.PathLike, slug: str | None = None) -> Base:
    """Create (or open) the base for a folder. ``slug`` is an explicit base name (e.g. the demo ``kb-demo``).

    An explicit name already bound to another folder moves to the new folder only if the old folder
    no longer exists or this is the demo base (after a plugin update the samples live at a new path).
    The markup stays valid: unit ids are content hashes.
    """
    real = check_corpus_root(corpus)
    if slug is not None and not SLUG_RE.match(slug):
        raise KbError(f"base name {slug!r}: lowercase Latin letters, digits and hyphens only, up to 40 chars")
    home = kb_home()
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    base = Base(home / (slug or slug_for(real)))
    base.ensure_dirs()
    if not base.yaml.exists():
        cfg = {"corpus_path": str(real), **DEFAULTS, "limits": dict(DEFAULT_LIMITS), "notice_shown": None}
        base.save_config(cfg)
    elif slug is not None:
        stored = load_yaml(base.yaml.read_text(encoding="utf-8"))
        old = stored.get("corpus_path")
        if old != str(real):
            if slug != DEMO_SLUG and old and os.path.isdir(old):
                raise KbError(f"base name \"{slug}\" is already used by folder {old}")
            stored["corpus_path"] = str(real)
            base.save_config(stored)
    return base


def list_bases() -> list[Base]:
    home = kb_home()
    if not home.is_dir():
        return []
    return [Base(p) for p in sorted(home.iterdir()) if (p / "kb.yaml").is_file()]


def resolve_base(kb: str | None = None, corpus: str | None = None, boxed: bool = True) -> Base:
    """The plugin's ready-made base (if any), a base by slug, by corpus path, or the only existing one."""
    box = boxed_base() if boxed else None
    if box is not None and not corpus and (not kb or kb == box.slug):
        return box
    if corpus:
        real = Path(os.path.realpath(Path(corpus).expanduser()))
        base = Base(kb_home() / slug_for(real))
        if base.yaml.exists():
            return base
        for b in list_bases():                   # a base with an explicit name (init --slug)
            if b.config().get("corpus_path") == str(real):
                return b
        raise KbError(f"no base for {real} — kbtool init {real}")
    bases = list_bases()
    if kb:
        for b in bases:
            if b.slug == kb:
                return b
        names = ([box.slug] if box is not None else []) + [b.slug for b in bases]
        raise KbError(f"no base \"{kb}\"; available: {', '.join(names) or '—'}")
    # The /kb-start demo base does not get in the way of the default choice when the user has own bases.
    bases = [b for b in bases if b.slug != DEMO_SLUG] or bases
    if len(bases) == 1:
        return bases[0]
    if not bases:
        raise KbError("no bases — run /kb-build first (kbtool init <folder>)")
    built = [b for b in bases if b.db.exists()]
    if len(built) == 1:
        return built[0]
    raise KbError(f"several bases, specify --kb: {', '.join(b.slug for b in bases)}")
