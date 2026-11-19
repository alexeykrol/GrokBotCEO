#!/usr/bin/env python3
"""
update-plan.py - bookkeeping for an update of an installed GrokBotCEO (UPDATE.md). No network,
no bot tools. The bot decides and talks to the user; this script compares, counts and copies.

Commands (every path is relative to --workspace unless absolute; default workspace: .):

  version  [--target TAG]           installed version vs the target; prints JSON
                                    {installed, target, action: update|current|newer_installed|not_installed
                                    |resume}. resume: update-state.json has bots still pending, failed or
                                    stopped, or the release is swapped in and `finish` did not run
                                    (checked before "current"); target is then the unfinished one.
                                    (--target defaults to VERSION of --release)
  config   [--set KEY=value ...]    keys the new release needs vs config.json; writes the build config
           [--apply]                <out>/config.json (config.json without keys the new release does not
                                    know, plus the --set keys); prints JSON {missing, unknown, set}.
                                    --apply also writes the --set keys into config.json, only keys that
                                    are absent there; a key the user already has is never changed.
  plan     [--main-agent-id ID]     per core bot: status unchanged|changed|missing_copy|new|removed and
                                    action update|ask|offer|leave|none|skip; writes <out>/plan.json,
                                    <out>/<bot>.update.json (UpdateAgent: agent_id + description),
                                    <out>/diff/<bot>.*.diff, and for the main bot <out>/main-grok.md.
                                    Needs `bot-payload-compiler.py build` into <out> first. Pins per bot
                                    live_sha256 (text running now) and expected_sha256 (the new text).
                                    In an unfinished update: applied bots -> done, kept bots -> leave,
                                    unfinished bots -> approved true only if both pins equal the pins of
                                    the user's yes (else ask: a fresh diff and a fresh yes).
  approve  [--bots A,B]             after the user's yes: the approved set is every `update` bot, every
                                    `approved: true` bot and the ticked --bots; they become pending with
                                    the plan's pins; other ask/offer bots become kept (never pending).
  recheck  --bot ID                 right before UpdateAgent / CreateAgent: the live text (profile.json, or
           [--live-file FILE|-]     --live-file, - = stdin) and the payload still match the pins of the
                                    yes. Prints {go}; go false (exit 2): the bot is stopped, not written.
  swap     [--staging DIR]          replace grokbotceo/ with the fetched release in DIR, by rename, with a
                                    journal in update-state.json; the old tree is kept as grokbotceo.old/
                                    until `finish` completes. Same version already in place: no-op.
  record   --bot ID --check RESULT  after UpdateAgent / CreateAgent and the write check. VERIFIED: refresh
           [--agent-id ID]          bots/core/<bot>/prompt.md and agent.json (the confirmed baseline).
           [--routine not chosen|asked|failed]
                                    MISMATCH / NOT VERIFIED: baseline kept, attempt in last_update, the bot
                                    stays failed. NOT APPLIED (UpdateAgent/CreateAgent error): bot failed.
  finish                            nothing pending/failed/stopped: VERSION <- grokbotceo/VERSION, old tree
                                    deleted, complete true. Otherwise VERSION is NOT written, the state is
                                    partial, the old tree kept; complete false. Both: .gitignore lines,
                                    bots/my and bots/marketplace kept; prints the paths to `git add`
  feedback                          after a complete update: may the update turn on course feedback
                                    (UPDATE.md step 11, as install step 11)? Prints {run, reason}; run true
                                    only when the update is complete, terms-acceptance.json is a valid
                                    acceptance of grokbotceo/'s terms with notice version >= 2 (the notice
                                    that says remarks are sent), an endpoint is configured, and
                                    mentor/consent.jsonl holds no consent line at all (no v2 line, and no
                                    earlier decision either: an update never overrides one). Reads only.

Every command first recovers an interrupted swap: grokbotceo/ missing and grokbotceo.old/ present ->
grokbotceo.old/ is renamed back; and an interrupted finish: `finish` writes its intent ("finalizing")
before VERSION, so a cut-off finish is completed (VERSION, journal committed, old tree removed) by the
next command, never while a bot is unfinished. grokbotceo.old/ is deleted only by `finish` after the journal says
committed. update-state.json and grokbotceo.old/ live outside build/update/, so deleting build/update/
never loses an unfinished update. There is no platform compare-and-swap: a change made in the seconds
between `recheck` and the write cannot be excluded.

Shared options: --workspace DIR (.), --release DIR (build/update/release: the fetched release),
--old-release DIR (grokbotceo: the installed release copy), --out DIR (build/update/out),
--agents-dir DIR (~/agent-data/agents), --config FILE (config.json).

Status of a core bot (a bot folder of the release with profile.json, or main-grok):
  unchanged     live description == bots/core/<bot>/prompt.md, and agent.json is not "edited": true
  changed       the live text differs from the installed copy, or agent.json says "edited": true
  missing_copy  the bot is found on the bot computer but bots/core/<bot>/prompt.md is missing
  new           in the release, not found on the bot computer
  removed       in bots/core/, no longer in the release
Action: unchanged -> update (none if the new text equals the live one); changed and missing_copy ->
ask; new -> offer; removed -> leave; skip when the bot cannot be updated safely (reason given).

Never read or written: bots/my/, bots/marketplace/ (their agent ids are only excluded from the
search by name), any bot folder other than profile.json, any config.json value the user set.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_AGENTS_DIR = Path.home() / "agent-data" / "agents"
AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
BOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")
INCLUDE_RE = re.compile(r"\[\[block:([a-z0-9][a-z0-9-]*)\]\]")
MAIN = "main-grok"
GITIGNORE_LINES = ("grokbotceo/", "build/", "mentor/kb/", "grokbotceo.old/", "update-state.json")
CHECKS = ("VERIFIED", "MISMATCH", "NOT VERIFIED", "NOT APPLIED")
ROUTINES = ("not chosen", "asked", "failed")
ROUTINE_BOTS = ("reminder", "monitor")
MARKER = "GrokBotCEO"  # first word of the main-bot block; an unmatched older block is never doubled
STATE_FILE = "update-state.json"   # next to grokbotceo/, outside build/update/
LIVE_TREE = "grokbotceo"
OLD_TREE = "grokbotceo.old"         # the replaced release, kept until the update is complete
STATE_FORMAT = 1
UNFINISHED = ("pending", "failed", "stopped")
APPROVABLE = ("update", "ask", "offer")


class UpdateError(ValueError):
    pass


# ---------------------------------------------------------------- small helpers

def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_json(path: Path) -> Optional[Any]:
    text = read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def same(a: Optional[str], b: Optional[str]) -> bool:
    """Equal as Grok Bot stores them: trailing whitespace is trimmed on save (see bot-mirror.py)."""
    return a is not None and b is not None and a.rstrip() == b.rstrip()


def sha(text: Optional[str]) -> Optional[str]:
    """Identity of a bot text, compared as `same` compares (trailing whitespace ignored)."""
    return None if text is None else hashlib.sha256(text.rstrip().encode("utf-8")).hexdigest()


def combine(base: str, block: str) -> str:
    """Same as bot-payload-compiler.py combine_text: old text, blank line, block."""
    base, block = base.rstrip(), block.strip()
    return f"{base}\n\n{block}" if base else block


def rel(path: Path, workspace: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path)


def parse_version(text: Optional[str]) -> Optional[Tuple[int, int, int, float]]:
    m = VERSION_RE.match((text or "").strip())
    if not m:
        return None
    rc = float(m.group(4)) if m.group(4) is not None else float("inf")  # 0.2.0-rc6 < 0.2.0
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), rc)


def load_compiler(release: Path):
    path = release / "scripts" / "bot-payload-compiler.py"
    if not path.is_file():
        raise UpdateError(f"no compiler in the release: {path}")
    spec = importlib.util.spec_from_file_location("grokbotceo_compiler_update", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- live bots

def read_profile(agents_dir: Path, agent_id: str) -> Optional[Dict[str, Any]]:
    """{name, description} of a bot from profile.json only; None if missing or unreadable."""
    if not AGENT_ID_RE.match(agent_id or ""):
        return None
    data = read_json(agents_dir / agent_id / "profile.json")
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return None
    desc = data.get("description")
    return {"name": data["name"], "description": desc if isinstance(desc, str) else ""}


def live_bots(agents_dir: Path) -> List[Dict[str, str]]:
    try:
        entries = sorted(d for d in agents_dir.iterdir() if d.is_dir())
    except OSError:
        return []
    found = []
    for d in entries:
        if not AGENT_ID_RE.match(d.name) or (d / "group.json").exists():  # group.json: a channel
            continue
        p = read_profile(agents_dir, d.name)
        if p is not None:
            found.append({"agent_id": d.name, "name": p["name"]})
    return found


def recorded_ids(workspace: Path, folder: str) -> Dict[str, str]:
    """agent_id -> bot folder, for agent.json files under bots/<folder>/*/ (read only)."""
    ids = {}
    for path in sorted((workspace / "bots" / folder).glob("*/agent.json")):
        data = read_json(path)
        if isinstance(data, dict) and isinstance(data.get("agent_id"), str):
            ids[data["agent_id"]] = path.parent.name
    return ids


# ---------------------------------------------------------------- state and recovery

def load_state(ws: Path) -> Optional[Dict[str, Any]]:
    path = ws / STATE_FILE
    if not path.exists():
        return None
    data = read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("bots", {}), dict):
        raise UpdateError(f"{path} is not readable; it is never deleted automatically")
    data.setdefault("bots", {})
    return data


def save_state(ws: Path, state: Dict[str, Any]) -> None:
    state["format"] = STATE_FORMAT
    atomic_write(ws / STATE_FILE, dump(state))


def unfinished(state: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {k: [] for k in UNFINISHED}
    for bot, b in sorted(((state or {}).get("bots") or {}).items()):
        if isinstance(b, dict) and b.get("outcome") in UNFINISHED:
            out[b["outcome"]].append(bot)
    return out


def has_unfinished(state: Optional[Dict[str, Any]]) -> bool:
    return any(unfinished(state).values())


def remove_tree(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def open_update(state: Optional[Dict[str, Any]]) -> bool:
    """An update that is not complete: a bot left, or the release swapped in and `finish` not done."""
    if has_unfinished(state):
        return True
    journal = (state or {}).get("swap")
    return bool(state and state.get("target") and isinstance(journal, dict)
                and journal.get("phase") in ("moving", "swapped", "finalizing"))


def finalize(ws: Path, state: Dict[str, Any], version: str) -> None:
    """Complete an update; every step is idempotent, so recovery can rerun it from any boundary.

    intent (state + journal "finalizing") -> VERSION -> journal "committed" -> old tree removed ->
    journal dropped."""
    journal = state.get("swap") if isinstance(state.get("swap"), dict) else None
    state["phase"], state["finalize"] = "finalizing", {"version": version}
    if journal is not None:
        journal["phase"] = "finalizing"
    save_state(ws, state)                          # the intent is on disk before VERSION is published
    atomic_write(ws / "VERSION", version + "\n")
    state["phase"] = "complete"
    if journal is not None:
        journal["phase"] = "committed"             # journal first, then the old tree goes
    save_state(ws, state)
    old = ws / OLD_TREE
    if journal is not None and (old.exists() or old.is_symlink()):
        remove_tree(old)
    state.pop("swap", None)
    state.pop("finalize", None)
    save_state(ws, state)


def recover(ws: Path) -> List[str]:
    """Finish or undo an interrupted swap or finish. Never deletes the old tree unless the journal says
    committed, or finishes an update while a bot is unfinished."""
    live, old = ws / LIVE_TREE, ws / OLD_TREE
    state = load_state(ws)
    journal = (state or {}).get("swap")
    done: List[str] = []
    if not (live.exists() or live.is_symlink()) and old.is_dir():
        os.rename(old, live)
        done.append(f"{LIVE_TREE}/ restored from {OLD_TREE}/")
        if state is not None and journal is not None:
            state.pop("swap", None)
            save_state(ws, state)
        return done
    if not isinstance(journal, dict):
        return done
    phase = journal.get("phase")
    if phase == "moving":
        if live.exists() and old.exists():
            journal["phase"] = "swapped"          # both renames had happened
            done.append("swap completed")
        elif live.exists():
            state.pop("swap", None)              # the first rename never happened
        save_state(ws, state)
    elif phase == "committed":
        if old.exists() or old.is_symlink():
            remove_tree(old)
            done.append(f"{OLD_TREE}/ removed (update committed)")
        state.pop("swap", None)
        state.pop("finalize", None)
        save_state(ws, state)
    elif not has_unfinished(state):
        # finish was cut off after its intent ("finalizing"), or after VERSION was published by code
        # without the intent: complete it. VERSION is only written when it equals grokbotceo/VERSION.
        live_version = (read_text(live / "VERSION") or "").strip()
        intent = (state.get("finalize") or {}).get("version") if phase == "finalizing" else None
        published = phase == "swapped" and state.get("target") == live_version \
            and installed_version(ws) == live_version
        if (intent and intent == live_version) or published:
            finalize(ws, state, live_version)
            done.append(f"update to {live_version} finished")
    return done


# ---------------------------------------------------------------- version

def installed_version(workspace: Path) -> Optional[str]:
    for path in (workspace / "VERSION", workspace / "installed" / "VERSION"):  # installed/: early rc
        text = read_text(path)
        if text is not None and text.strip():
            return text.strip()
    return None


def cmd_version(args) -> Dict[str, Any]:
    ws = args.workspace
    target = args.target
    if not target:
        text = read_text(args.release / "VERSION")
        if text is None:
            raise UpdateError("no --target and no VERSION in the release")
        target = text.strip()
    target = target.strip()
    if target.startswith("v"):
        target = target[1:]
    if parse_version(target) is None:
        raise UpdateError(f"target is not a version: {target!r}")
    installed = installed_version(ws)
    state = load_state(ws)
    if open_update(state):   # before "current": a partial update is never reported as done
        out = {"installed": installed, "target": state.get("target"), "requested": target,
               "action": "resume"}
        out.update(unfinished(state))
        return out
    out = {"installed": installed, "target": target}
    if installed is None:
        out["action"] = "not_installed"
    else:
        iv, tv = parse_version(installed), parse_version(target)
        if iv is None:
            out["action"], out["note"] = "update", "installed version not recognized"
        elif iv == tv:
            out["action"] = "current"
        elif iv > tv:
            out["action"] = "newer_installed"
        else:
            out["action"] = "update"
    return out


# ---------------------------------------------------------------- config

def parse_sets(items: Optional[List[str]]) -> Dict[str, str]:
    sets = {}
    for item in items or []:
        if "=" not in item:
            raise UpdateError(f"--set must be KEY=value: {item!r}")
        k, v = item.split("=", 1)
        sets[k.strip()] = v
    return sets


def cmd_config(args) -> Dict[str, Any]:
    compiler = load_compiler(args.release)
    config = read_json(args.config)
    if not isinstance(config, dict):
        raise UpdateError(f"config.json is missing or not a JSON object: {args.config}")
    known = set(compiler.KEY_DOCS)
    required = set(compiler.stage1_keys(args.release / "bots"))
    sets = parse_sets(args.set)
    for k in sets:
        if k not in known:
            raise UpdateError(f"--set {k}: not a key of this release")
        if k in config:
            raise UpdateError(f"--set {k}: config.json already has it; a value the user set is never changed")
    build = {k: v for k, v in config.items() if k in known}
    build.update(sets)
    compiler.validate_params(build, source="update config")
    missing = sorted(required - set(build))
    out = {"missing": [{"key": k, "meaning": compiler.KEY_DOCS[k][0], "example": compiler.KEY_DOCS[k][1]}
                       for k in missing],
           "unknown": sorted(set(config) - known), "set": sorted(sets),
           "build_config": rel(args.out / "config.json", args.workspace), "applied": []}
    atomic_write(args.out / "config.json", dump(build))
    if args.apply:
        if missing:
            raise UpdateError("--apply refused: keys still missing: " + ", ".join(missing))
        if sets:
            new = dict(config)
            new.update(sets)  # only absent keys reach here (checked above)
            atomic_write(args.config, json.dumps(new, indent=2, ensure_ascii=False) + "\n")
            out["applied"] = sorted(sets)
    return out


# ---------------------------------------------------------------- plan

def release_bots(release: Path) -> List[str]:
    bots = release / "bots"
    if not bots.is_dir():
        raise UpdateError(f"no bots/ in the release: {release}")
    return sorted(d.name for d in bots.iterdir()
                  if d.is_dir() and not d.name.startswith("_") and (d / "profile.json").is_file())


def resolve_block_simple(bot_dir: Path, params: Dict[str, str]) -> Optional[str]:
    """The installed release's main-bot block as it was built: shared blocks, then {{KEY}} values.

    Used only to find the old block inside the live text; a key without a value stays as it is (no match).
    """
    text = read_text(bot_dir / "block.md")
    if text is None or not text.strip():
        return None
    blocks = bot_dir.parent / "_blocks"

    def sub(m):
        inner = read_text(blocks / f"{m.group(1)}.md")
        return inner.strip() if inner is not None else m.group(0)

    text = INCLUDE_RE.sub(sub, text)
    for k, v in params.items():
        text = text.replace("{{" + k + "}}", v)
    return text.strip()


def diff_info(old: str, new: str, path: Path, workspace: Path, a: str, b: str) -> Dict[str, Any]:
    lines = list(difflib.unified_diff(old.rstrip().splitlines(), new.rstrip().splitlines(),
                                      fromfile=a, tofile=b, lineterm=""))
    atomic_write(path, "\n".join(lines) + ("\n" if lines else ""))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {"file": rel(path, workspace), "added": added, "removed": removed}


def find_by_name(name: str, candidates: List[Dict[str, str]]) -> List[str]:
    return [c["agent_id"] for c in candidates if c["name"] == name]


def plan_core_bot(bot: str, ws: Path, out: Path, agents_dir: Path,
                  candidates: List[Dict[str, str]]) -> Dict[str, Any]:
    payload = read_json(out / f"{bot}.payload.json")
    new_text = read_text(out / f"{bot}.md")
    if not isinstance(payload, dict) or new_text is None:
        raise UpdateError(f"{bot}: no build output in {out}; run bot-payload-compiler.py build first")
    name = payload.get("name")
    core = ws / "bots" / "core" / bot
    record = read_json(core / "agent.json")
    record = record if isinstance(record, dict) else {}
    copy = read_text(core / "prompt.md")
    edited = record.get("edited") is True
    entry: Dict[str, Any] = {"bot": bot, "name": name, "agent_id": None, "agent_id_from": None,
                             "edited": edited, "expected": rel(out / f"{bot}.md", ws),
                             "create_payload": rel(out / f"{bot}.payload.json", ws),
                             "update_payload": None, "diff_release": None, "diff_live": None, "reason": None}
    agent_id = record.get("agent_id") if isinstance(record.get("agent_id"), str) else None
    if agent_id:
        entry["agent_id_from"] = "record"
    else:
        found = find_by_name(name, candidates)
        if len(found) == 1:
            agent_id, entry["agent_id_from"] = found[0], "name"
        elif len(found) > 1:
            entry.update(status="missing_copy", action="skip", candidates=found,
                         reason="several bots on the bot computer have this name")
            return entry
    live = read_profile(agents_dir, agent_id) if agent_id else None
    if live is None:
        entry.update(status="new", action="offer", agent_id=None, live_sha256=None,
                     expected_sha256=sha(new_text),
                     reason="recorded bot is not on the bot computer" if agent_id else None)
        return entry
    entry["agent_id"] = agent_id
    text = live["description"]
    entry["live_sha256"], entry["expected_sha256"] = sha(text), sha(new_text)
    if copy is None:
        entry["status"] = "missing_copy"
    elif same(text, copy) and not edited:
        entry["status"] = "unchanged"
    else:
        entry["status"] = "changed"
    if copy is not None:
        entry["diff_release"] = diff_info(copy, new_text, out / "diff" / f"{bot}.release.diff", ws,
                                          f"{bot}/installed", f"{bot}/new")
    entry["diff_live"] = diff_info(text, new_text, out / "diff" / f"{bot}.live.diff", ws,
                                   f"{bot}/live", f"{bot}/new")
    if same(text, new_text):
        entry["action"] = "none"
    else:
        entry["action"] = "update" if entry["status"] == "unchanged" else "ask"
        upd = out / f"{bot}.update.json"
        atomic_write(upd, dump({"agent_id": agent_id, "description": new_text.rstrip()}))
        entry["update_payload"] = rel(upd, ws)
    return entry


def plan_main_bot(ws: Path, release: Path, old_release: Path, out: Path, agents_dir: Path,
                  params: Dict[str, str], main_agent_id: Optional[str], compiler,
                  old_block: Optional[str] = None) -> Dict[str, Any]:
    """old_block: the installed GrokBotCEO part as pinned at the first plan of this update (provenance);
    None -> resolved from old_release."""
    core = ws / "bots" / "core" / MAIN
    record = read_json(core / "agent.json")
    record = record if isinstance(record, dict) else {}
    copy = read_text(core / "prompt.md")
    previous = read_text(core / "previous.md")
    edited = record.get("edited") is True
    entry: Dict[str, Any] = {"bot": MAIN, "name": None, "agent_id": None, "agent_id_from": None,
                             "edited": edited, "expected": None, "create_payload": None,
                             "update_payload": None, "diff_release": None, "diff_live": None, "reason": None}
    agent_id = record.get("agent_id") if isinstance(record.get("agent_id"), str) else None
    if agent_id:
        entry["agent_id_from"] = "record"
    elif main_agent_id:
        agent_id, entry["agent_id_from"] = main_agent_id, "main-agent-id"
    live = read_profile(agents_dir, agent_id) if agent_id else None
    if live is None:
        entry.update(status="missing_copy", action="skip",
                     reason="main bot not found; Bot Maker can add GrokBotCEO to it later")
        return entry
    entry["agent_id"], entry["name"] = agent_id, live["name"]
    text = live["description"]
    new_block = compiler.resolve_placeholders(compiler.load_extension_block(release / "bots" / MAIN),
                                              params).strip()
    if old_block is None:
        old_block = resolve_block_simple(old_release / "bots" / MAIN, params)
    entry["live_sha256"] = sha(text)
    if copy is None:
        status = "missing_copy"
    elif same(text, copy) and not edited:
        status = "unchanged"
    else:
        status = "changed"
    entry["status"] = status
    base = None
    if new_block in text:
        new_text, kind = text, "none"
    elif old_block and text.count(old_block) == 1:
        new_text, kind = text.replace(old_block, new_block), "replace"
        base = previous if previous is not None else text.replace(old_block, "").rstrip()
    elif MARKER in text:
        entry.update(action="skip", reason="an older GrokBotCEO part is in the text and cannot be matched; "
                                           "Bot Maker can change it with the user")
        return entry
    else:
        new_text, kind = combine(text, new_block), "add"
        base = text
    new_path = out / f"{MAIN}.md"
    atomic_write(new_path, new_text.rstrip())
    entry["expected_sha256"] = sha(new_text)
    entry["expected"] = rel(new_path, ws)
    if base is not None:
        atomic_write(out / f"{MAIN}.base.md", base)
        entry["base"] = rel(out / f"{MAIN}.base.md", ws)
    if copy is not None:
        entry["diff_release"] = diff_info(copy, new_text, out / "diff" / f"{MAIN}.release.diff", ws,
                                          f"{MAIN}/installed", f"{MAIN}/new")
    entry["diff_live"] = diff_info(text, new_text, out / "diff" / f"{MAIN}.live.diff", ws,
                                   f"{MAIN}/live", f"{MAIN}/new")
    if kind == "none":
        entry["action"] = "none"
    else:
        if kind == "add":
            entry["action"] = "offer"
            entry["reason"] = "the main bot has no GrokBotCEO part yet"
        else:
            entry["action"] = "update" if status == "unchanged" else "ask"
        upd = out / f"{MAIN}.update.json"
        atomic_write(upd, dump({"agent_id": agent_id, "description": new_text.rstrip()}))
        entry["update_payload"] = rel(upd, ws)
    return entry


def cmd_plan(args) -> Dict[str, Any]:
    ws, out = args.workspace, args.out
    compiler = load_compiler(args.release)
    config = read_json(out / "config.json")  # the build config written by `config`
    if not isinstance(config, dict):
        raise UpdateError(f"no build config {out / 'config.json'}: run `config` first")
    params = {k: v for k, v in config.items() if isinstance(v, str)}
    agents_dir = args.agents_dir
    # Bots the user made or imported are never matched by name, so they can never be touched.
    excluded = set(recorded_ids(ws, "my")) | set(recorded_ids(ws, "marketplace"))
    excluded |= set(recorded_ids(ws, "core"))
    if args.main_agent_id:
        excluded.add(args.main_agent_id)
    candidates = [c for c in live_bots(agents_dir) if c["agent_id"] not in excluded]
    in_release = release_bots(args.release)
    version = read_text(args.release / "VERSION")
    target = version.strip() if version else None
    state = load_state(ws)
    resuming = open_update(state)
    if resuming and state.get("target") != target:
        raise UpdateError(f"an update to {state.get('target')} is unfinished; fetch v{state.get('target')} "
                          f"to finish it first")
    old_release = args.old_release
    if not args.old_release_given and (ws / OLD_TREE).is_dir():
        old_release = ws / OLD_TREE      # the swap already happened: the replaced release is kept here
    old_block = state.get("old_main_block") if resuming else None
    if old_block is None:
        old_block = resolve_block_simple(old_release / "bots" / MAIN, params)
    entries = []
    if (args.release / "bots" / MAIN / "block.md").is_file():
        entries.append(plan_main_bot(ws, args.release, old_release, out, agents_dir, params,
                                     args.main_agent_id, compiler, old_block=old_block or ""))
    for bot in in_release:
        entries.append(plan_core_bot(bot, ws, out, agents_dir, candidates))
    core_dir = ws / "bots" / "core"
    if core_dir.is_dir():
        for d in sorted(core_dir.iterdir()):
            if d.is_dir() and d.name != MAIN and d.name not in in_release and BOT_ID_RE.match(d.name):
                record = read_json(d / "agent.json")
                entries.append({"bot": d.name, "status": "removed", "action": "leave",
                                "agent_id": record.get("agent_id") if isinstance(record, dict) else None,
                                "reason": "no longer in the release; left as it is"})
    if resuming:
        apply_resume(state, entries, out)
    else:
        swap = (state or {}).get("swap")
        state = {"target": target, "from": installed_version(ws), "phase": "planned",
                 "old_main_block": old_block, "bots": {}}
        if swap is not None:
            state["swap"] = swap
    for e in entries:
        b = state["bots"].setdefault(e["bot"], {"outcome": "planned"})
        b.update({"action": e.get("action"), "agent_id": e.get("agent_id"),
                  "live_sha256": e.get("live_sha256"), "expected_sha256": e.get("expected_sha256")})
    save_state(ws, state)
    counts: Dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    plan = {"installed_version": installed_version(ws), "target_version": target,
            "resume": resuming, "bots": entries, "counts": counts}
    atomic_write(out / "plan.json", dump(plan))
    return plan


def drop_payload(entry: Dict[str, Any], out: Path) -> None:
    entry["update_payload"] = None
    p = out / f"{entry['bot']}.update.json"
    if p.exists():
        p.unlink()


def apply_resume(state: Dict[str, Any], entries: List[Dict[str, Any]], out: Path) -> None:
    """An unfinished update: applied and kept bots are left alone; an unfinished bot keeps the user's
    yes only if the text running now and the new text are exactly those the yes was given for."""
    for e in entries:
        b = state["bots"].get(e["bot"])
        if not isinstance(b, dict):
            continue
        outcome = b.get("outcome")
        if outcome == "applied":
            e.update(action="done", reason="updated earlier in this update")
            drop_payload(e, out)
        elif outcome in ("kept", "skipped"):
            e.update(action="leave", reason="left as it was in this update, as the user chose")
            drop_payload(e, out)
        elif outcome in UNFINISHED:
            same_pins = (e.get("live_sha256") == b.get("approved_live_sha256")
                         and e.get("expected_sha256") == b.get("approved_expected_sha256")
                         and e.get("agent_id") == b.get("approved_agent_id"))
            if e.get("action") == "none" and e.get("status") != "new":
                e["found_applied"] = True     # runs the new text already: only check and record
                e["approved"] = True
            elif e.get("action") in APPROVABLE and same_pins:
                e["approved"] = True
            else:
                e["approved"] = False
                if e.get("action") in APPROVABLE:
                    e.update(action="ask", reason="changed after the user's yes; a fresh yes is needed")
                b["outcome"] = "stopped"


# ---------------------------------------------------------------- approve, recheck

def load_plan(out: Path) -> Dict[str, Any]:
    plan = read_json(out / "plan.json")
    if not isinstance(plan, dict):
        raise UpdateError(f"no plan: {out / 'plan.json'}")
    return plan


def plan_state(ws: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    state = load_state(ws)
    if state is None or state.get("target") != plan.get("target_version"):
        raise UpdateError("update-state.json does not belong to this plan: run `plan` again")
    return state


def cmd_approve(args) -> Dict[str, Any]:
    ws, out = args.workspace, args.out
    plan = load_plan(out)
    state = plan_state(ws, plan)
    ticked = {b.strip() for b in (args.bots or "").split(",") if b.strip()}
    entries = {e.get("bot"): e for e in plan.get("bots", [])}
    for bot in ticked:
        e = entries.get(bot)
        if e is None or e.get("action") not in ("ask", "offer"):
            raise UpdateError(f"{bot}: not a choice in the plan (only ask/offer bots can be ticked)")
    approved, kept = [], []
    for bot, e in entries.items():
        b = state["bots"].setdefault(bot, {"outcome": "planned"})
        action = e.get("action")
        if action in ("done", "leave") and b.get("outcome") in ("applied", "kept", "skipped"):
            continue
        # an unfinished bot whose pins moved was turned into `ask` by the plan, so `update` is always safe
        yes = action == "update" or e.get("approved") is True or bot in ticked
        if yes and (action in APPROVABLE or e.get("found_applied")):
            b.update(outcome="pending", approved_live_sha256=e.get("live_sha256"),
                     approved_expected_sha256=e.get("expected_sha256"),
                     approved_agent_id=e.get("agent_id"))
            approved.append(bot)
        elif action in ("ask", "offer"):
            b["outcome"] = "kept"
            kept.append(bot)
        elif b.get("outcome") in UNFINISHED:
            b.update(outcome="skipped", reason=e.get("reason"))   # cannot be updated safely now
            kept.append(bot)
        elif b.get("outcome") == "planned":
            b["outcome"] = "none"
    state["phase"] = "approved"
    save_state(ws, state)
    return {"approved": approved, "kept": kept}


def cmd_recheck(args) -> Dict[str, Any]:
    ws, out = args.workspace, args.out
    plan = load_plan(out)
    state = plan_state(ws, plan)
    e = next((x for x in plan.get("bots", []) if x.get("bot") == args.bot), None)
    b = state["bots"].get(args.bot)
    if e is None or not isinstance(b, dict):
        raise UpdateError(f"{args.bot}: not in the plan")
    if b.get("outcome") != "pending":
        raise UpdateError(f"{args.bot}: not waiting for a write (outcome {b.get('outcome')}); write nothing")
    if e.get("found_applied"):
        raise UpdateError(f"{args.bot}: runs the new text already; only check and record")
    reasons = []
    expected = read_text(ws / e["expected"]) if e.get("expected") else None
    if sha(expected) != b.get("approved_expected_sha256"):
        reasons.append("the new text is not the one the user said yes to")
    agent_id = b.get("approved_agent_id")
    if agent_id:
        upd = read_json(ws / e["update_payload"]) if e.get("update_payload") else None
        if not isinstance(upd, dict) or upd.get("agent_id") != agent_id \
                or sha(upd.get("description")) != b.get("approved_expected_sha256"):
            reasons.append("the update payload is not the one the user said yes to")
        if args.live_file is not None:
            live = sys.stdin.read() if str(args.live_file) == "-" else read_text(args.live_file)
        else:
            p = read_profile(args.agents_dir, agent_id)
            live = p["description"] if p else None
        if live is None:
            reasons.append("the text running now cannot be read")
        elif sha(live) != b.get("approved_live_sha256"):
            reasons.append("the bot was changed after the plan")
    else:
        payload = read_json(ws / e["create_payload"]) if e.get("create_payload") else None
        if not isinstance(payload, dict) or sha(payload.get("description")) != b.get("approved_expected_sha256"):
            reasons.append("the create payload is not the one the user said yes to")
        else:
            excluded = set(recorded_ids(ws, "my")) | set(recorded_ids(ws, "marketplace"))
            if any(c["name"] == payload.get("name") and c["agent_id"] not in excluded
                   for c in live_bots(args.agents_dir)):
                reasons.append("a bot with this name is on the bot computer now")
    if reasons:
        b.update(outcome="stopped", reason="; ".join(reasons))
        save_state(ws, state)
        return {"bot": args.bot, "go": False, "reason": b["reason"]}
    return {"bot": args.bot, "go": True,
            "payload": e.get("update_payload") if agent_id else e.get("create_payload")}


# ---------------------------------------------------------------- swap

def check_release_tree(path: Path) -> str:
    if not path.is_dir() or path.is_symlink():
        raise UpdateError(f"staging is not a folder: {path}")
    version = read_text(path / "VERSION")
    if version is None or parse_version(version) is None:
        raise UpdateError(f"staging has no valid VERSION: {path}")
    for need in ("scripts/bot-payload-compiler.py", "scripts/bot-mirror.py", "bots", "UPDATE.md"):
        if not (path / need).exists():
            raise UpdateError(f"staging is not a complete release (no {need}): {path}")
    return version.strip()


TERMS_RECORD = "terms-acceptance.json"   # the user's local acceptance of the terms (terms.py)


def check_terms_accepted(staging: Path, ws: Path) -> None:
    """A release that carries terms (TERMS-NOTICE.md) is swapped in only after the user accepted them
    (legal B-12). The check is the new release's own terms.py, so a skipped prose step cannot bypass it."""
    if not (staging / "TERMS-NOTICE.md").exists():
        return
    script = staging / "scripts" / "terms.py"
    if not script.is_file():
        raise UpdateError("staging carries terms but no scripts/terms.py: not swapped")
    spec = importlib.util.spec_from_file_location("staging_terms", script)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        reason = mod.validate(staging, ws / TERMS_RECORD)
    except Exception as e:  # any failure of the check is a refusal (fail closed)
        reason = f"terms check failed: {e}"
    if reason:
        raise UpdateError(f"the terms of the new release are not accepted ({reason}); nothing was changed: "
                          f"show the plan with the terms notice again (UPDATE.md step 7)")


def cmd_swap(args) -> Dict[str, Any]:
    ws = args.workspace
    staging = args.staging if args.staging.is_absolute() else ws / args.staging
    live = ws / "grokbotceo"
    version = check_release_tree(staging)
    if args.expect_version and version != args.expect_version.lstrip("v"):
        raise UpdateError(f"staging VERSION is {version}, expected {args.expect_version}")
    check_terms_accepted(staging, ws)
    recovered = recover(ws)
    old = ws / OLD_TREE
    live_version = read_text(live / "VERSION")
    if live_version is not None and live_version.strip() == version:
        return {"swapped": False, "already": True, "version": version, "recovered": recovered}
    if old.exists() or old.is_symlink():
        raise UpdateError(f"{OLD_TREE}/ holds the release of an unfinished update; finish it first "
                          f"(it is never deleted before that)")
    state = load_state(ws) or {"bots": {}}
    state.setdefault("target", version)
    state["swap"] = {"phase": "moving", "version": version,
                     "from": live_version.strip() if live_version else None}
    save_state(ws, state)   # the journal is on disk before the first rename
    moved_old = False
    if live.exists() or live.is_symlink():
        os.rename(live, old)  # failure here: nothing moved, the old tree stays
        moved_old = True
    try:
        os.rename(staging, live)
    except Exception:
        if moved_old and not live.exists():
            os.rename(old, live)  # put the old tree back
        state.pop("swap", None)
        save_state(ws, state)
        raise
    state["swap"]["phase"] = "swapped"
    save_state(ws, state)
    return {"swapped": True, "version": version, "old_kept": OLD_TREE if moved_old else None,
            "recovered": recovered}


# ---------------------------------------------------------------- record

def cmd_record(args) -> Dict[str, Any]:
    ws, out = args.workspace, args.out
    if args.check not in CHECKS:
        raise UpdateError(f"--check must be one of {', '.join(CHECKS)}")
    if args.routine and args.routine not in ROUTINES:
        raise UpdateError(f"--routine must be one of {', '.join(ROUTINES)}")
    if not BOT_ID_RE.match(args.bot):
        raise UpdateError(f"invalid bot id {args.bot!r}")
    plan = load_plan(out)
    entry = next((e for e in plan.get("bots", []) if e.get("bot") == args.bot), None)
    if entry is None:
        raise UpdateError(f"{args.bot}: not in the plan")
    if entry.get("action") in ("leave", "skip", "done"):
        raise UpdateError(f"{args.bot}: action is {entry['action']}; nothing to record")
    state = load_state(ws)
    b = (state or {}).get("bots", {}).get(args.bot) if state else None
    target = plan.get("target_version")
    expected = ws / entry["expected"] if entry.get("expected") else None
    text = read_text(expected) if expected else None
    if entry.get("action") in APPROVABLE or entry.get("found_applied"):
        # a written bot: only one the user said yes to, with the very text of that yes
        outcome = b.get("outcome") if isinstance(b, dict) else None
        if outcome not in ("pending", "failed", "applied"):
            raise UpdateError(f"{args.bot}: not approved for writing (outcome {outcome}); record nothing")
        if args.check != "NOT APPLIED" and sha(text) != b.get("approved_expected_sha256"):
            raise UpdateError(f"{args.bot}: the expected text is not the one the user said yes to")
    if args.check == "NOT APPLIED":   # UpdateAgent / CreateAgent error: nothing changed
        if isinstance(b, dict) and b.get("outcome") in ("pending", "failed"):
            b["outcome"] = "failed"
            save_state(ws, state)
        return {"bot": args.bot, "recorded": None, "check": args.check,
                "outcome": b.get("outcome") if isinstance(b, dict) else None}
    agent_id = args.agent_id or entry.get("agent_id")
    if not agent_id or not AGENT_ID_RE.match(agent_id):
        raise UpdateError(f"{args.bot}: no agent id (pass --agent-id for a created bot)")
    if text is None:
        raise UpdateError(f"{args.bot}: cannot read {expected}")
    core = ws / "bots" / "core" / args.bot
    record = read_json(core / "agent.json")
    record = record if isinstance(record, dict) else {}
    # agent_id is identity (a created bot exists even if its text is wrong); the attempt is kept apart
    # from the confirmed baseline (check, version, edited, prompt.md), which moves only on VERIFIED
    record["agent_id"] = agent_id
    record["last_update"] = {"target": target, "check": args.check}
    if args.bot in ROUTINE_BOTS and args.routine:
        record["routine"] = args.routine
    if args.check != "VERIFIED":
        atomic_write(core / "agent.json", json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        if isinstance(b, dict) and b.get("outcome") in ("pending", "failed", "applied"):
            b["outcome"] = "failed"   # unresolved: finish cannot hide it, VERSION is not written
            save_state(ws, state)
        return {"bot": args.bot, "recorded": None, "check": args.check, "outcome": "failed"}
    record.update({"check": args.check, "version": target, "edited": False})
    if args.bot == MAIN:
        record["mode"] = "extended"
        if not (core / "previous.md").exists() and entry.get("base"):
            base = read_text(ws / entry["base"])
            if base is not None:
                atomic_write(core / "previous.md", base)
    if args.bot in ROUTINE_BOTS:
        record.setdefault("routine", "not chosen")
    atomic_write(core / "prompt.md", text)
    atomic_write(core / "agent.json", json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    if isinstance(b, dict) and b.get("outcome") in ("pending", "failed", "applied"):
        b["outcome"] = "applied"
        save_state(ws, state)
    return {"bot": args.bot, "recorded": rel(core, ws), "check": args.check}


# ---------------------------------------------------------------- finish

def cmd_finish(args) -> Dict[str, Any]:
    ws = args.workspace
    version = read_text(ws / LIVE_TREE / "VERSION")
    if version is None or parse_version(version) is None:
        raise UpdateError("grokbotceo/VERSION is missing or not a version: swap first")
    version = version.strip()
    state = load_state(ws)
    left = unfinished(state)
    complete = not any(left.values())
    if not complete and state.get("target") != version:
        raise UpdateError(f"the unfinished update is to {state.get('target')}, grokbotceo/ is {version}")
    gi = ws / ".gitignore"
    lines = (read_text(gi) or "").splitlines()
    added = [l for l in GITIGNORE_LINES if l not in lines]
    if added or not gi.exists():
        atomic_write(gi, "\n".join(lines + added) + "\n")
    for folder in ("my", "marketplace"):
        d = ws / "bots" / folder
        if not d.exists():
            d.mkdir(parents=True)
            (d / ".gitkeep").write_text("", encoding="utf-8")
    paths = [p for p in (".gitignore", "config.json", "VERSION", "bots/core", "channels",
                         "mentor/progress.json") if (ws / p).exists()]
    paths += [f"bots/{f}/.gitkeep" for f in ("my", "marketplace") if (ws / "bots" / f / ".gitkeep").exists()]
    kept = sorted(k for k, b in ((state or {}).get("bots") or {}).items()
                  if isinstance(b, dict) and b.get("outcome") in ("kept", "skipped"))
    if complete and state is None:
        atomic_write(ws / "VERSION", version + "\n")
    elif complete:
        finalize(ws, state, version)
    if state is not None:
        if not complete:
            state["phase"] = "partial"
            save_state(ws, state)
    out = {"complete": complete, "version": version if complete else installed_version(ws),
           "target": version, "gitignore_added": added, "git_add": paths, "left_as_it_was": kept}
    out.update(left)
    return out


# ---------------------------------------------------------------- feedback

FEEDBACK_NOTICE_MIN = 2                  # the first terms notice that says course remarks are sent
FEEDBACK_DATA_SET_V2 = "course-feedback-v2"
CONSENT_FILE = "mentor/consent.jsonl"    # progress.py --kb-home mentor


def load_terms(release: Path):
    script = release / "scripts" / "terms.py"
    if not script.is_file():
        raise UpdateError(f"{script} is missing")
    spec = importlib.util.spec_from_file_location("release_terms", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def configured_endpoint(release: Path) -> Optional[str]:
    """As progress.py endpoint_of: env GROKBOT_FEEDBACK_URL, else "endpoint" in course/feedback.json.
    Only presence is checked here; progress.py validates the URL itself."""
    url = os.environ.get("GROKBOT_FEEDBACK_URL")
    if not url:
        cfg = read_json(release / "course" / "feedback.json")
        url = cfg.get("endpoint") if isinstance(cfg, dict) else None
    return url.strip() if isinstance(url, str) and url.strip() else None


def consent_lines(ws: Path) -> List[Dict[str, Any]]:
    text = read_text(ws / CONSENT_FILE)
    out: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("decision"):
            out.append(rec)
    return out


def cmd_feedback(args) -> Dict[str, Any]:
    """Read-only gate for the update's "turn on course feedback" step. The decision itself stays with
    progress.py (`consent --decision granted_at_install` never writes over an earlier decision); this gate
    only says whether to run it at all."""
    ws = args.workspace
    live = ws / LIVE_TREE

    def no(reason: str) -> Dict[str, Any]:
        return {"run": False, "reason": reason}

    version = read_text(live / "VERSION")
    if version is None or version.strip() != (installed_version(ws) or "") or open_update(load_state(ws)):
        return no("update_not_complete")
    try:
        terms = load_terms(live)
        if terms.validate(live, ws / TERMS_RECORD):
            return no("terms_not_accepted")
        rec = read_json(ws / TERMS_RECORD)
        notice_version = int(str(rec.get("notice_version")))
    except Exception:  # any failure of the terms check is a no (fail closed)
        return no("terms_not_accepted")
    if notice_version < FEEDBACK_NOTICE_MIN:
        return no("notice_without_remarks")
    if configured_endpoint(live) is None:
        return no("no_endpoint")
    lines = consent_lines(ws)
    if any((r.get("scope") or {}).get("data_set") == FEEDBACK_DATA_SET_V2
           for r in lines if isinstance(r.get("scope"), dict)):
        return no("consent_recorded")
    if lines:
        return no("earlier_decision")
    return {"run": True, "reason": "accepted_notice_v%d" % notice_version}


# ---------------------------------------------------------------- CLI

COMMANDS = {"version": cmd_version, "config": cmd_config, "plan": cmd_plan, "approve": cmd_approve,
            "recheck": cmd_recheck, "swap": cmd_swap, "record": cmd_record, "finish": cmd_finish,
            "feedback": cmd_feedback}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="GrokBotCEO update bookkeeping (see module doc)")
    ap.add_argument("command", choices=sorted(COMMANDS))
    ap.add_argument("--workspace", type=Path, default=Path("."))
    ap.add_argument("--release", type=Path, default=None)
    ap.add_argument("--old-release", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--target")
    ap.add_argument("--set", action="append")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--main-agent-id")
    ap.add_argument("--staging", type=Path, default=Path("build/update/release"))
    ap.add_argument("--expect-version")
    ap.add_argument("--bot")
    ap.add_argument("--check")
    ap.add_argument("--agent-id")
    ap.add_argument("--routine")
    ap.add_argument("--bots")
    ap.add_argument("--live-file", type=Path, default=None)
    return ap


def resolve_args(args) -> None:
    ws = args.workspace

    def under(p: Optional[Path], default: str) -> Path:
        p = p if p is not None else Path(default)
        return p if p.is_absolute() else ws / p

    args.old_release_given = args.old_release is not None
    args.release = under(args.release, "build/update/release")
    args.old_release = under(args.old_release, "grokbotceo")
    args.out = under(args.out, "build/update/out")
    args.config = under(args.config, "config.json")
    if args.main_agent_id and not AGENT_ID_RE.match(args.main_agent_id):
        raise UpdateError(f"invalid --main-agent-id {args.main_agent_id!r}")
    if args.command == "record" and (not args.bot or not args.check):
        raise UpdateError("record needs --bot and --check")
    if args.command == "recheck" and not args.bot:
        raise UpdateError("recheck needs --bot")
    if args.live_file is not None and str(args.live_file) != "-" and not args.live_file.is_absolute():
        args.live_file = ws / args.live_file


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        resolve_args(args)
        recovered = recover(args.workspace)   # every command: an interrupted swap is undone first
        result = COMMANDS[args.command](args)
        if recovered and isinstance(result, dict):
            result.setdefault("recovered", recovered)
    except (UpdateError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 2 if isinstance(result, dict) and result.get("go") is False else 0


if __name__ == "__main__":
    sys.exit(main())
