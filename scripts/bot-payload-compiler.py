#!/usr/bin/env python3
"""
Bot Payload Compiler - Maps bot templates to supported CreateAgent/UpdateAgent payloads.

Contract:
- The bot persona (CreateAgent `description`) comes ONLY from `prompt.md` in the bot folder.
- `profile.json` holds identity and metadata only: `name` plus metadata fields that are
  stripped before CreateAgent. A persona field in profile.json (e.g. `description`) is an
  error, so the two sources can never contradict each other.
- Placeholders `{{KEY}}` are resolved from a fixed whitelist of keys (see KEY_DOCS),
  given by `--config config.json` and/or `--param KEY=value`.

Commands:
  create  PROFILE_JSON        print one CreateAgent payload
  update  --agent-id ID       print one UpdateAgent payload
  plan    PROFILE_JSON        print a human-readable plan (no payload, no side effects)
  build   --bots IDS --out DIR   write <id>.payload.json + <id>.md for each bot
  config-example --out-dir DIR   write config.example.json + config.schema.md
"""
import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BOTS_DIR = SCRIPT_DIR.parent / "bots"

# Supported CreateAgent arguments (whitelist)
CREATE_AGENT_WHITELIST = {"name", "description", "section_id"}

# Supported UpdateAgent arguments (whitelist)
UPDATE_AGENT_WHITELIST = {"agent_id", "name", "description"}

# Metadata fields allowed in profile.json and stripped before CreateAgent/UpdateAgent
METADATA_FIELDS = {"title", "avatarShape", "avatarColor", "namedBy", "harness", "serverId", "_comment"}

# Everything profile.json may contain. Anything else (including a persona) is rejected.
PROFILE_ALLOWED_FIELDS = {"name"} | METADATA_FIELDS

# Fields that would duplicate the persona from prompt.md. Explicitly forbidden in profile.json.
PERSONA_FIELDS = {"description", "persona", "prompt", "instructions", "system_prompt"}

PLACEHOLDER_RE = re.compile(r'\{\{([A-Z_]+)\}\}')
BOT_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')

# Placeholder keys: the single source of truth for the whitelist, the meaning of each key
# and a fictional example value (used to generate config.example.json / config.schema.md).
KEY_DOCS: Dict[str, Tuple[str, str]] = {
    "ANALYSIS_DATA_PATH": ("Folder where Repository Analyst stores analysis results", "/home/bot/grokbot/data/analysis"),
    "BOT_MAKER_BOT": ("Name of your Bot Maker bot (SendToAgent target)", "Bot Maker"),
    "CVE_NAG_INTERVAL": ("How often Reminder nags about an open CVE", "every 2 hours"),
    "CVE_PACKAGES": ("Packages whose CVE notifications Reminder tracks", "openssl, example-lib"),
    "DAY_OF_WEEK": ("Cron day-of-week field for the weekly Projects Manager routine", "1"),
    "HOUR": ("Cron hour field used in routine schedules", "9"),
    "IMPLEMENTER_BOT": ("Name of your Implementer bot (SendToAgent target)", "Implementer"),
    "IMPROVEMENTS_CHANNEL": ("Channel where bot changes are proposed and approved by the owner", "#improvements"),
    "IMPROVEMENTS_CHANNEL_ID": ("ID of the improvements channel", "channel-0000-example"),
    "MINUTE": ("Cron minute field used in routine schedules", "0"),
    "MONITOR_DATA_PATH": ("Folder where Monitor saves weekly report data", "/home/bot/grokbot/data/monitor"),
    "NOTION_PROJECT_DATABASE": ("Notion database that Projects Manager reads", "https://www.notion.so/example-workspace/0000000000000000"),
    "OUTPUT_LANGUAGE": ("Language Reader X answers in when the owner writes in it", "English"),
    "OWNER_TIMEZONE": ("Owner timezone (IANA name) for schedules and report periods", "Europe/Berlin"),
    "PLANNING_DATA_PATH": ("Folder where Weekplanner stores weekly plans", "/home/bot/grokbot/data/planning"),
    "PROJECT_TRACKING_PATH": ("Folder for Projects Manager local tracking", "/home/bot/grokbot/data/projects"),
    "PUBLISHING_CHANNEL": ("Channel where Translator posts approved translations", "@example_channel"),
    "READER_X_BOT": ("Name of your Reader X bot (SendToAgent target)", "Reader X"),
    "READING_DATA_PATH": ("Folder for reader state and stats (state.json, stats.db)", "/home/bot/grokbot/reading-data"),
    "READING_FILTER_PATH": ("File with the shared reading filter criteria", "/home/bot/grokbot/company-structure/protocols/reading-filter.md"),
    "READING_ROUTINE_NAME": ("Name of the daily reading routine", "daily-reading"),
    "REMINDER_BOT": ("Name of your Reminder bot (SendToAgent target)", "Reminder"),
    "REMINDER_DATA_PATH": ("Folder where Reminder stores tasks", "/home/bot/grokbot/data/reminders"),
    "REPORT_LANGUAGE": ("Language of Monitor reports", "English"),
    "REPOSITORY_ANALYST_BOT": ("Name of your Repository Analyst bot (SendToAgent target)", "Repository Analyst"),
    "TASK_MANAGER_BOT": ("Name of your Task Manager bot (SendToAgent target)", "Task Manager"),
    "TRANSLATOR_BOT": ("Name of your Translator bot", "Translator"),
    "VIDEO_PROJECT_PATH": ("Folder for Director video projects", "/home/bot/grokbot/videos"),
    "WEEKLY_REPORT_DAY": ("Day Monitor sends the weekly report", "Sunday"),
    "WEEKLY_REPORT_TIME": ("Time (owner timezone) Monitor sends the weekly report", "20:00"),
    "WORKSPACE_PATH": ("Root folder of the bot workspace", "/home/bot/grokbot"),
    "X_USER_ID": ("Numeric ID of the X account Reader X reads", "0000000000"),
    "X_USERNAME": ("X account Reader X reads", "@example_user"),
}

# Strict allowed placeholder keys (whitelist for all bots)
ALLOWED_PLACEHOLDER_KEYS = frozenset(KEY_DOCS)


class CompileError(ValueError):
    """Any validation failure. Subclass of ValueError for backward compatibility."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_profile(profile_path: Path) -> Dict[str, Any]:
    """Load and validate profile.json (identity + metadata only, never a persona)."""
    try:
        with open(profile_path, encoding='utf-8') as f:
            profile = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise CompileError(f"Error loading profile {profile_path}: {e}")

    if not isinstance(profile, dict):
        raise CompileError(f"profile.json must be a JSON object: {profile_path}")

    persona = sorted(set(profile) & PERSONA_FIELDS)
    if persona:
        raise CompileError(
            f"profile.json must not contain persona field(s) {', '.join(persona)}: "
            f"the persona lives only in prompt.md ({profile_path})")

    unknown = sorted(set(profile) - PROFILE_ALLOWED_FIELDS)
    if unknown:
        raise CompileError(
            f"profile.json has unsupported field(s) {', '.join(unknown)}; "
            f"allowed: {', '.join(sorted(PROFILE_ALLOWED_FIELDS))} ({profile_path})")

    if not isinstance(profile.get("name"), str) or not profile["name"].strip():
        raise CompileError(f"Profile missing required 'name' field ({profile_path})")

    return profile


def load_persona(bot_dir: Path) -> str:
    """Load the canonical persona from prompt.md in the bot folder."""
    prompt_path = bot_dir / "prompt.md"
    if not prompt_path.exists():
        raise CompileError(f"Missing canonical persona file {prompt_path} (prompt.md)")
    try:
        text = prompt_path.read_text(encoding='utf-8')
    except IOError as e:
        raise CompileError(f"Error loading prompt.md: {e}")
    if not text.strip():
        raise CompileError(f"prompt.md is empty at {prompt_path}")
    return text


def load_bot(profile_path: Path) -> Tuple[Dict[str, Any], str]:
    """Load (profile, persona) for the bot whose profile.json is given."""
    profile = load_profile(profile_path)
    persona = load_persona(profile_path.parent)
    return profile, persona


def validate_params(params: Dict[str, str], source: str = "parameters") -> None:
    """Keys must be whitelisted; values must be non-empty strings without placeholders."""
    for key, value in params.items():
        if not isinstance(key, str) or not re.fullmatch(r'[A-Z_]+', key):
            raise CompileError(f"Invalid key in {source}: {key!r} (expected UPPER_CASE)")
    invalid = sorted(set(params) - ALLOWED_PLACEHOLDER_KEYS)
    if invalid:
        raise CompileError(f"Invalid/unknown parameter keys in {source}: {', '.join(invalid)}")
    for key, value in params.items():
        if not isinstance(value, str):
            raise CompileError(f"Value for {key} in {source} must be a string, got {type(value).__name__}")
        if not value.strip():
            raise CompileError(f"Value for {key} in {source} is empty")
        if re.search(r'\{\{[A-Z_]+\}\}', value) or '{{' in value or '}}' in value:
            raise CompileError(
                f"Parameter value for {key} contains placeholder pattern "
                f"(recursive expansion not allowed): {value[:50]}")


def load_config(config_path: Path) -> Dict[str, str]:
    """Load a flat JSON config {KEY: value}; same whitelist rules as --param."""
    try:
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise CompileError(f"Error loading config {config_path}: {e}")
    if not isinstance(config, dict):
        raise CompileError(f"Config must be a flat JSON object {{KEY: value}}: {config_path}")
    validate_params(config, source=f"config {config_path.name}")
    return dict(config)


def collect_params(config_path: Optional[Path], param_strings: Optional[List[str]]) -> Dict[str, str]:
    """Merge --config (base) with --param (overrides the same key)."""
    params: Dict[str, str] = {}
    if config_path:
        params.update(load_config(config_path))
    cli: Dict[str, str] = {}
    for param_str in param_strings or []:
        if '=' not in param_str:
            raise CompileError(f"--param must be KEY=value format: {param_str}")
        key, value = param_str.split('=', 1)
        cli[key.upper()] = value
    validate_params(cli, source="--param")
    params.update(cli)
    return params


# ---------------------------------------------------------------------------
# Placeholder resolution
# ---------------------------------------------------------------------------

def resolve_placeholders(text: str, params: Dict[str, str]) -> str:
    """Resolve {{PLACEHOLDER}} patterns with provided params using single-pass deterministic substitution.

    Security contract:
    - All placeholders must match {{[A-Z_]+}} exactly
    - All found placeholders must be in ALLOWED_PLACEHOLDER_KEYS
    - All found placeholders must have values in params
    - All params keys must be in ALLOWED_PLACEHOLDER_KEYS
    - No unresolved placeholders may remain after substitution
    - No recursive expansion (values cannot introduce new placeholders)
    - Parameter order independent (deterministic result)

    Raises:
        ValueError: If any validation fails or unresolved placeholders remain
    """
    found_placeholders = set(PLACEHOLDER_RE.findall(text))

    invalid_param_keys = set(params.keys()) - ALLOWED_PLACEHOLDER_KEYS
    if invalid_param_keys:
        raise CompileError(f"Invalid/unknown parameter keys: {', '.join(sorted(invalid_param_keys))}")

    invalid_placeholders = found_placeholders - ALLOWED_PLACEHOLDER_KEYS
    if invalid_placeholders:
        raise CompileError(f"Invalid/unknown placeholders in text: {', '.join(sorted(invalid_placeholders))}")

    missing = found_placeholders - set(params.keys())
    if missing:
        raise CompileError(f"Unresolved placeholders (no value provided): {', '.join(sorted(missing))}")

    for key, value in params.items():
        if re.search(r'\{\{[A-Z_]+\}\}', value):
            raise CompileError(f"Parameter value for {key} contains placeholder pattern (recursive expansion not allowed): {value[:50]}")

    result = text
    for key in sorted(found_placeholders):
        result = result.replace(f"{{{{{key}}}}}", params[key])

    remaining_valid = PLACEHOLDER_RE.findall(result)
    if remaining_valid:
        raise CompileError(f"Unresolved placeholders after substitution: {', '.join(sorted(set(remaining_valid)))}")

    # Catches {{unknown1}}, {{123}}, {{lower}}, {{{extra}}}, leftover delimiters from values
    if '{{' in result or '}}' in result:
        malformed_examples = []
        for match in re.finditer(r'\{\{[^}]*\}\}|\{\{|\}\}', result):
            malformed_examples.append(match.group())
            if len(malformed_examples) >= 3:
                break
        raise CompileError(f"Malformed or leftover placeholder delimiters found after substitution: {', '.join(malformed_examples)}")

    return result


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

def compile_create_payload(
    profile: Dict[str, Any],
    persona: str,
    params: Optional[Dict[str, str]] = None,
    section_id: Optional[str] = None
) -> Dict[str, Any]:
    """Compile CreateAgent payload: name from profile.json, description from prompt.md."""
    if "name" not in profile:
        raise CompileError("Profile missing required 'name' field")
    persona_in_profile = sorted(set(profile) & PERSONA_FIELDS)
    if persona_in_profile:
        raise CompileError(
            f"profile must not contain persona field(s) {', '.join(persona_in_profile)}: "
            f"the persona lives only in prompt.md")
    if not isinstance(persona, str) or not persona.strip():
        raise CompileError("Description (persona from prompt.md) cannot be empty")

    params = params or {}
    try:
        name = resolve_placeholders(profile["name"], params)
        description = resolve_placeholders(persona, params)
    except ValueError as e:
        raise CompileError(f"Placeholder resolution failed: {e}")

    if not description.strip():
        raise CompileError("Description (persona) cannot be empty")

    payload = {"name": name, "description": description}
    if section_id:
        payload["section_id"] = section_id

    leaked = set(payload.keys()) - CREATE_AGENT_WHITELIST
    if leaked:
        raise CompileError(f"Payload contains non-whitelisted keys: {leaked}")
    return payload


def compile_update_payload(
    agent_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    params: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Compile UpdateAgent payload (agent_id required; name/description optional)."""
    if not agent_id:
        raise CompileError("agent_id required for UpdateAgent")

    params = params or {}
    payload = {"agent_id": agent_id}

    if name is not None:
        try:
            payload["name"] = resolve_placeholders(name, params)
        except ValueError as e:
            raise CompileError(f"Name placeholder resolution failed: {e}")

    if description is not None:
        try:
            resolved_desc = resolve_placeholders(description, params)
            if not resolved_desc.strip():
                raise CompileError("Description cannot be empty")
            payload["description"] = resolved_desc
        except ValueError as e:
            raise CompileError(f"Description placeholder resolution failed: {e}")

    leaked = set(payload.keys()) - UPDATE_AGENT_WHITELIST
    if leaked:
        raise CompileError(f"Payload contains non-whitelisted keys: {leaked}")
    return payload


def show_plan(
    profile: Dict[str, Any],
    persona: str,
    params: Dict[str, str],
    section_id: Optional[str] = None
) -> str:
    """Human-readable installation plan. Shows what would be created; never calls CreateAgent."""
    payload = compile_create_payload(profile, persona, params, section_id)

    plan = []
    plan.append("=== Installation Plan ===")
    plan.append(f"Bot name: {payload['name']}")
    plan.append("Persona source: prompt.md")
    plan.append(f"Persona length: {len(payload['description'])} characters")
    plan.append(f"Persona preview: {payload['description'][:100]}...")

    if "section_id" in payload:
        plan.append(f"Section ID: {payload['section_id']}")

    plan.append("\nMetadata stripped:")
    for field in sorted(METADATA_FIELDS):
        if field in profile:
            plan.append(f"  - {field}: {repr(profile[field])[:50]}")

    plan.append("\nManual configuration required after creation:")
    plan.append("  - Routines/schedules (via bot UI, not CreateAgent)")
    plan.append("  - Settings (via bot UI, not CreateAgent)")
    plan.append("  - Service connections (X, Telegram, Notion)")

    return "\n".join(plan)


def payload_json(payload: Dict[str, Any]) -> str:
    """Deterministic JSON serialization used for files and stdout."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# build: many bots, validate everything first, then write
# ---------------------------------------------------------------------------

def list_bot_ids(bots_dir: Path) -> List[str]:
    return sorted(d.name for d in bots_dir.iterdir() if d.is_dir() and (d / "profile.json").exists())


def parse_bot_ids(spec: str, bots_dir: Path) -> List[str]:
    if spec.strip() == "all":
        ids = list_bot_ids(bots_dir)
        if not ids:
            raise CompileError(f"No bots found in {bots_dir}")
        return ids
    ids = [s.strip() for s in spec.split(",")]
    if not ids or any(not s for s in ids):
        raise CompileError(f"--bots must be a comma-separated list of bot ids or 'all': {spec!r}")
    dupes = sorted({s for s in ids if ids.count(s) > 1})
    if dupes:
        raise CompileError(f"Duplicate bot ids in --bots: {', '.join(dupes)}")
    bad = [s for s in ids if not BOT_ID_RE.match(s)]
    if bad:
        raise CompileError(f"Invalid bot id(s) (expected lowercase letters, digits, '-'): {', '.join(bad)}")
    return ids


def compile_bots(bots_dir: Path, bot_ids: List[str], params: Dict[str, str],
                 section_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Compile every bot; collect all errors; raise once if any failed."""
    results: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    for bot_id in bot_ids:
        profile_path = bots_dir / bot_id / "profile.json"
        if not profile_path.exists():
            errors.append(f"{bot_id}: bot not found ({profile_path} missing)")
            continue
        try:
            profile, persona = load_bot(profile_path)
            results[bot_id] = compile_create_payload(profile, persona, params, section_id)
        except ValueError as e:
            errors.append(f"{bot_id}: {e}")
    if errors:
        raise CompileError("Build failed, nothing written:\n  " + "\n  ".join(errors))
    return results


def _atomic_write(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def build(bots_dir: Path, bot_ids: List[str], params: Dict[str, str], out_dir: Path,
          section_id: Optional[str] = None) -> List[Path]:
    """Write <id>.payload.json and <id>.md for each bot. Validates all bots before writing."""
    payloads = compile_bots(bots_dir, bot_ids, params, section_id)

    if out_dir.exists() and not out_dir.is_dir():
        raise CompileError(f"--out is not a directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for bot_id in sorted(payloads):
        payload = payloads[bot_id]
        json_path = out_dir / f"{bot_id}.payload.json"
        md_path = out_dir / f"{bot_id}.md"
        _atomic_write(json_path, payload_json(payload))
        _atomic_write(md_path, payload["description"])  # exact text sent as description
        written.extend([json_path, md_path])
    return written


# ---------------------------------------------------------------------------
# config-example: config.example.json + config.schema.md, computed from the files
# ---------------------------------------------------------------------------

def placeholder_usage(bots_dir: Path) -> Dict[str, List[str]]:
    """Map KEY -> sorted bot ids whose compiled sources (prompt.md, profile name) use it.

    Raises if a compiled source uses a key outside the whitelist.
    """
    usage: Dict[str, set] = {k: set() for k in ALLOWED_PLACEHOLDER_KEYS}
    unknown: List[str] = []
    for bot_id in list_bot_ids(bots_dir):
        bot_dir = bots_dir / bot_id
        sources = []
        prompt = bot_dir / "prompt.md"
        if prompt.exists():
            sources.append(("prompt.md", prompt.read_text(encoding='utf-8')))
        try:
            with open(bot_dir / "profile.json", encoding='utf-8') as f:
                name = json.load(f).get("name", "")
            sources.append(("profile.json name", name if isinstance(name, str) else ""))
        except (json.JSONDecodeError, IOError):
            pass
        for label, text in sources:
            for key in PLACEHOLDER_RE.findall(text):
                if key in usage:
                    usage[key].add(bot_id)
                else:
                    unknown.append(f"{bot_id}/{label}: {{{{{key}}}}}")
    if unknown:
        raise CompileError("Compiled sources use keys outside the whitelist:\n  " + "\n  ".join(sorted(set(unknown))))
    return {k: sorted(v) for k, v in usage.items()}


def render_config_example() -> str:
    return json.dumps({k: KEY_DOCS[k][1] for k in sorted(KEY_DOCS)}, indent=2, ensure_ascii=False) + "\n"


def render_config_schema(usage: Dict[str, List[str]]) -> str:
    lines = [
        "# config.schema.md - placeholder keys",
        "",
        "Generated by `python3 scripts/bot-payload-compiler.py config-example --out-dir .` - do not edit by hand.",
        "",
        "`config.json` is a flat JSON object `{KEY: value}`. Copy `config.example.json`, replace the",
        "fictional example values with your own, and pass it with `--config`. Only the keys below are",
        "accepted; any other key is rejected. Values must be non-empty strings without `{{` or `}}`.",
        "",
        "\"Required\" means: the build fails if the key is missing and you build at least one bot listed",
        "in \"Used by\". \"Used by\" is computed from the compiled sources (`bots/*/prompt.md` and the",
        "`name` in `bots/*/profile.json`).",
        "",
        "| Key | Meaning | Required? | Used by | Example (fictional) |",
        "|---|---|---|---|---|",
    ]
    for key in sorted(KEY_DOCS):
        meaning, example = KEY_DOCS[key]
        bots = usage.get(key, [])
        required = "yes" if bots else "no (unused)"
        used_by = ", ".join(bots) if bots else "-"
        lines.append(f"| `{key}` | {meaning} | {required} | {used_by} | `{example}` |")
    lines.append("")
    return "\n".join(lines)


def write_config_example(out_dir: Path, bots_dir: Path) -> List[Path]:
    usage = placeholder_usage(bots_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    example_path = out_dir / "config.example.json"
    schema_path = out_dir / "config.schema.md"
    _atomic_write(example_path, render_config_example())
    _atomic_write(schema_path, render_config_schema(usage))
    return [example_path, schema_path]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Compile bot payloads for CreateAgent/UpdateAgent')
    parser.add_argument('command', choices=['create', 'update', 'plan', 'build', 'config-example'])
    parser.add_argument('profile_json', nargs='?', type=Path, help='Path to profile.json (for create/plan)')
    parser.add_argument('--agent-id', help='Agent ID (for update)')
    parser.add_argument('--name', help='New name (for update)')
    parser.add_argument('--description', help='New description (for update)')
    parser.add_argument('--section-id', help='Section ID (for create/build)')
    parser.add_argument('--config', type=Path, help='Flat JSON config {KEY: value} (same whitelist as --param)')
    parser.add_argument('--param', action='append', help='Placeholder param KEY=value (repeatable, overrides --config)')
    parser.add_argument('--bots', help="Comma-separated bot ids, or 'all' (for build)")
    parser.add_argument('--bots-dir', type=Path, default=DEFAULT_BOTS_DIR, help='Bot templates folder (default: ../bots)')
    parser.add_argument('--out', type=Path, help='Output folder (for build)')
    parser.add_argument('--out-dir', type=Path, help='Output folder (for config-example)')
    parser.add_argument('--output', '-o', type=Path, help='Output JSON file (create/update/plan; default: stdout)')

    args = parser.parse_args()

    try:
        if args.command == 'config-example':
            if not args.out_dir:
                raise CompileError("--out-dir required for config-example")
            for path in write_config_example(args.out_dir, args.bots_dir):
                print(path)
            return 0

        params = collect_params(args.config, args.param)

        if args.command == 'build':
            if not args.bots:
                raise CompileError("--bots required for build")
            if not args.out:
                raise CompileError("--out required for build")
            bot_ids = parse_bot_ids(args.bots, args.bots_dir)
            written = build(args.bots_dir, bot_ids, params, args.out, args.section_id)
            for path in written:
                print(path)
            print(f"Built {len(written) // 2} bot payload(s) into {args.out}", file=sys.stderr)
            return 0

        if args.command == 'create':
            if not args.profile_json:
                raise CompileError("profile_json required for create")
            profile, persona = load_bot(args.profile_json)
            payload = compile_create_payload(profile, persona, params, args.section_id)
            output = json.dumps(payload, indent=2, ensure_ascii=False)

        elif args.command == 'update':
            if not args.agent_id:
                raise CompileError("--agent-id required for update")
            payload = compile_update_payload(args.agent_id, args.name, args.description, params)
            output = json.dumps(payload, indent=2, ensure_ascii=False)

        else:  # plan
            if not args.profile_json:
                raise CompileError("profile_json required for plan")
            profile, persona = load_bot(args.profile_json)
            output = show_plan(profile, persona, params, args.section_id)

        if args.output:
            args.output.write_text(output, encoding='utf-8')
            print(f"Written to {args.output}", file=sys.stderr)
        else:
            print(output)
        return 0

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
