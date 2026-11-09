# Loading Instructions — installation recipe for the bot

**Reader:** the Grok Bot that the user asked to install GrokBotCEO (see [ONBOARDING.md](ONBOARDING.md)).
Follow the steps in order. Do not add steps. Talk to the user in their language.

## Contract

```
fetch → capability check → questions → config.json → plan → user "yes"
      → build (script) → CreateAgent per bot → write check → installed/ → routine guide
```

**Stop only at:** missing capability (step 2), user says no (step 5), build error (step 6),
CreateAgent error (step 7). A write check that cannot be done is **not** a stop: mark the bot
`NOT VERIFIED` and continue.

**Never:** ask for secrets in chat; create a bot not in the approved plan; turn on a routine;
send a message on the user's behalf; write inside `grokbotceo/` (the release copy); send
`config.json` anywhere.

## Layout in the user's workspace

```
<WORKSPACE_PATH>/
  grokbotceo/    release copy, read-only; replaced on update
  config.json    user values {KEY: value}; never overwritten by an update
  build/         compiled payloads; safe to delete and rebuild
  installed/     VERSION, agents.json, <bot>.md — exact texts that were installed
```

## 1. Fetch the release

Get the latest release of https://github.com/alexeykrol/GrokBotCEO into `<WORKSPACE_PATH>/grokbotceo/`
(`git clone --depth 1 --branch <latest tag>`, or the release archive if git is unavailable).
Read `grokbotceo/VERSION`.

If `<WORKSPACE_PATH>/installed/VERSION` already exists, this is not a first install: tell the user
which version is installed and stop. Updating is a separate procedure.

## 2. Capability check

Check with GetDynamicTools that you have:

| Capability | Needed for | If missing |
|---|---|---|
| `CreateAgent` (`name`, `description`, `section_id`) | creating bots | **stop**, tell the user |
| reading and writing files in the workspace | config, build, installed | **stop**, tell the user |
| running `python3` | the build script | **stop**, tell the user |
| `ListSections` | placing bots in a section | optional: create without section |

Report the result in one short list. Do not look for workarounds.

## 3. Explain and ask

Use the mentor skill (`grokbotceo/skills/mentor/SKILL.md`) to explain in 3–5 sentences what will be
installed. Then ask for the values in `grokbotceo/config.schema.md`, required ones first. Ask
one or two questions per message, not a form. Offer the example value where it fits.

Only ask for values used by the bots the user will keep (step 5 may cross some out — if so, drop
their keys).

## 4. Write config.json

Write the answers to `<WORKSPACE_PATH>/config.json` as a flat JSON object `{KEY: value}`. Show the
user the file and let them correct it.

## 5. Plan and approval

Show the plan:

- bots to create, core first (main-grok, bot-maker, monitor), then the optional ones the user
  wants; `director` is not offered in this version;
- for each bot: name, one line about its job, length of its text;
- what the user configures by hand afterwards: routines, bot settings, service connections.

Ask: "Create these bots? Reply yes, or cross out what you don't need." Create nothing before an
explicit yes. If the user crosses bots out, show the updated plan and ask again.

## 6. Build (script, no model work)

```bash
python3 grokbotceo/scripts/bot-payload-compiler.py build \
  --config config.json --bots main-grok,bot-maker,monitor,... --out build/
```

The script writes `build/<bot>.payload.json` (only `name`, `description`, optional `section_id`)
and `build/<bot>.md` (the exact `description`). It fails the whole build on an unknown key or an
unfilled `{{KEY}}`, before writing anything. On failure: show the error, fix `config.json` with
the user, rebuild. Do not edit texts by hand.

## 7. Create the bots

For each approved bot, in plan order:

1. Call `CreateAgent` with exactly the fields of `build/<bot>.payload.json`. Pass the text as is.
2. Record the returned `agent_id`.
3. **Write check.** If the response contains the name and the full description, compare them
   with the payload character by character: equal → `VERIFIED`, different → `MISMATCH`. If the
   response does not contain the full description → `NOT VERIFIED`. Neither result stops the
   install.
4. Print one line: `<bot> · created · <VERIFIED|NOT VERIFIED|MISMATCH>`.

If `CreateAgent` returns an error: stop creating, keep what was created, go to step 8 with the
bots created so far and tell the user which bot failed and the error text.

## 8. Save what was installed

- `installed/<bot>.md` ← copy of `build/<bot>.md` for every created bot.
- `installed/agents.json` ← `{"<bot>": {"agent_id": "...", "check": "VERIFIED|NOT VERIFIED|MISMATCH"}}`.
- `installed/VERSION` ← contents of `grokbotceo/VERSION`.

These files let a later update find which bots the user edited by hand. Do not skip this step.

If a reader bot (`reader-x` or `reader-telegram`) was created, also prepare its data folder
(`READING_DATA_PATH` from `config.json`):

```bash
python3 grokbotceo/scripts/reading-dedup-sort.py migrate --db <READING_DATA_PATH>/stats.db
echo '{}' > <READING_DATA_PATH>/state.json   # only if the file does not exist yet
```

`migrate` creates the database from `data-schemas/stats-db-schema.sql` and is safe to repeat.

## 9. Routines and settings — guide the user

No supported tool creates routines or bot settings. For each created bot that has
`bots/<bot>/routines.md` or `bots/<bot>/settings.json`, give the user a short step-by-step:
which bot to open, where to click, what to paste (with values from `config.json` filled in).
Tell them to turn routines on one at a time. Do not turn anything on yourself.

## 10. Report

One short message: created bots and their check results; what is left to configure by hand;
where the files are; how updates will work (one sentence: "updates are offered, never applied
without your yes; your config.json is never touched").

---

## Reference: native tools

| Tool | Accepted arguments | Not accepted |
|---|---|---|
| `CreateAgent` | `name` (required), `description`, `section_id` | settings, routines, avatar, any other key |
| `UpdateAgent` | `agent_id` (required), `name`, `description` | settings, routines, deletion |

No tool is known that reads a bot's full description back. That is why the write check relies
on what `CreateAgent` returns, and why missing data gives `NOT VERIFIED` instead of a stop.

## Reference: files of a bot

| File | Role |
|---|---|
| `bots/<bot>/prompt.md` | the bot's full text — the only source of `description` |
| `bots/<bot>/profile.json` | name and metadata; metadata is stripped by the build |
| `bots/<bot>/routines.md` | routines the user sets up by hand |
| `bots/<bot>/settings.json` | settings the user sets up by hand |

Editing files in the workspace does not change a live bot. A bot changes only through
`UpdateAgent` (updates) or by the user in the Grok Bot interface.

## Tests (no network, no live bots)

```bash
python3 scripts/test-bot-payload.py
```
