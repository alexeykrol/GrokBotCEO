# Loading Instructions — installation recipe for the bot

**Reader:** the Grok Bot that the user asked to install GrokBotCEO (see [ONBOARDING.md](ONBOARDING.md)).
Follow the steps in order. Do not add steps. Talk to the user in their language.

This release installs stage 1 only: **Main Grok** (with the mentor skill) and **Bot Maker**, plus a
git repo in the workspace that mirrors the user's system. No routines are set up.

## Contract

```
fetch → capability check → mentor explains → config.json → plan (2 bots) → user "yes"
      → build (script) → CreateAgent per bot → write check → bots/core/ + VERSION
      → git commit → offer a copy on the user's computer → mentor tour
```

**Stop only at:** already installed (step 1), missing capability (step 2), user says no (step 5),
build error (step 6), CreateAgent error (step 7). A write check that cannot be done is **not** a
stop: mark the bot `NOT VERIFIED` and continue.

**Never:** ask for secrets in chat; create a bot not in the approved plan; create or turn on a
routine; send a message on the user's behalf; write inside `grokbotceo/` (the release copy); send
`config.json` anywhere other than the user's own computer (step 10); add a git remote or push.

## Layout in the user's workspace

```
<WORKSPACE_PATH>/          git repo, no remote
  .gitignore               grokbotceo/ and build/
  grokbotceo/              release copy, read-only; replaced on update; not committed
  config.json              user values {KEY: value}; never overwritten by an update
  local-copy.json          optional: {"path": ...} of the read-only copy on the user's computer
  VERSION                  installed GrokBotCEO version
  bots/core/<bot>/         our bots as installed: prompt.md, agent.json
  bots/my/<bot>/           bots the user makes through Bot Maker
  bots/marketplace/<bot>/  copies of imported bots (name and text only)
  build/                   compiled payloads; safe to delete; not committed
```

`bots/core/<bot>/prompt.md` is the exact `description` sent. `agent.json` is
`{"agent_id": "...", "check": "VERIFIED|NOT VERIFIED|MISMATCH", "version": "<VERSION>", "edited": false}`.

## 1. Fetch the release

Get the latest release of https://github.com/alexeykrol/GrokBotCEO into `<WORKSPACE_PATH>/grokbotceo/`
(`git clone --depth 1 --branch <latest tag>`, or the release archive). Read `grokbotceo/VERSION`.

If `<WORKSPACE_PATH>/VERSION` (or `installed/VERSION` from an earlier release candidate) already
exists, this is not a first install: tell the user which version is installed and stop. Updating is
a separate procedure.

## 2. Capability check

Check with GetDynamicTools and one harmless shell command that you have:

| Capability | Needed for | If missing |
|---|---|---|
| `CreateAgent` (`name`, `description`, `section_id`) | creating bots | **stop**, tell the user |
| reading and writing files in the workspace | config, build, repo | **stop**, tell the user |
| running `python3` | build script, write check | **stop**, tell the user |
| running `git` | the repo mirror | **stop**, tell the user |
| `ListSections` | placing bots in a section | optional: create without section |
| running commands on the user's computer and copying files to it (`CopyFromBox`), through the Grok Bot desktop app | the optional copy (step 10) | optional: do not offer the copy; say it needs the desktop app |

Only look for these last tools in the list; do not run them in this step.

Report the result in one short list. Do not look for workarounds.

## 3. Mentor explains

Read `grokbotceo/skills/mentor/SKILL.md`. Explain in 3–5 sentences what will be installed: two
bots, a repo that mirrors the system, nothing created before the user's "yes".

## 4. Write config.json

Stage 1 uses only the keys marked **stage 1** in `grokbotceo/config.schema.md`:

- `WORKSPACE_PATH` — the absolute path of this workspace. Fill it in yourself.
- `BOT_MAKER_BOT` — `Bot Maker`, the name in `grokbotceo/bots/bot-maker/profile.json`. Do not ask.

Write them to `<WORKSPACE_PATH>/config.json` as a flat JSON object `{KEY: value}`. Show the user the
file in one message and let them correct the path. Ask nothing else.

## 5. Plan and approval

Show the plan:

- exactly two bots, in this order: `main-grok`, `bot-maker`; for each: name, one line about its
  job, length of its text;
- the repo: `<WORKSPACE_PATH>` becomes a git repo with `bots/core/`, `bots/my/`, `bots/marketplace/`;
  no remote, nothing leaves the bot computer. A copy on the user's own computer is offered
  separately, after install (step 10).

Ask: "Create these two bots and the repo? Reply yes." Create nothing before an explicit yes. Other
bots in `grokbotceo/bots/` are not offered in this release.

## 6. Build (script, no model work)

```bash
cd <WORKSPACE_PATH>
python3 grokbotceo/scripts/bot-payload-compiler.py build \
  --config config.json --bots main-grok,bot-maker --out build/
```

The script writes `build/<bot>.payload.json` (only `name`, `description`, optional `section_id`)
and `build/<bot>.md` (the exact `description`). It fails the whole build on an unknown key or an
unfilled `{{KEY}}`, before writing anything. On failure: show the error, fix `config.json` with
the user, rebuild. Do not edit texts by hand.

## 7. Create the bots

For each bot, in plan order:

1. Call `CreateAgent` with exactly the fields of `build/<bot>.payload.json`. Pass the text as is.
2. Record the returned `agent_id`.
3. **Write check** — read the bot's `profile.json` on the bot computer and compare its
   `description` with what was sent, by code:

   ```bash
   python3 grokbotceo/scripts/bot-mirror.py check --agent-id <agent_id> --expected build/<bot>.md
   ```

   It reads `~/agent-data/agents/<agent_id>/profile.json` (every bot has a folder there, in the home
   folder of the bot computer) and prints `VERIFIED` (equal), `MISMATCH` (different) or
   `NOT VERIFIED` (file missing or unreadable). None of them stops the install.
4. Print one line: `<bot> · created · <VERIFIED|NOT VERIFIED|MISMATCH>`.

If `CreateAgent` returns an error: stop creating, keep what was created, go to step 8 with the
bots created so far and tell the user which bot failed and the error text.

## 8. Save what was installed

For every created bot:

- `bots/core/<bot>/prompt.md` ← copy of `build/<bot>.md`;
- `bots/core/<bot>/agent.json` ← `{"agent_id", "check", "version", "edited": false}`.

Then `VERSION` ← contents of `grokbotceo/VERSION`, and `.gitignore` ← the two lines `grokbotceo/`
and `build/`. Create empty `bots/my/` and `bots/marketplace/` with a `.gitkeep` each.

These files let a later update find which bots the user changed. Do not skip this step.

## 9. First commit

```bash
cd <WORKSPACE_PATH>
[ -d .git ] || git init
git config user.name "GrokBotCEO bots"
git config user.email "grokbotceo@localhost"
git add .gitignore config.json VERSION bots/
git commit -m "Install GrokBotCEO <VERSION>" -m "Bot: <your bot name>"
```

The identity is set for this repo only. Add only these paths, never everything. Every later commit in this repo ends with a line
`Bot: <name of the bot that made it>`. No remote is added. A copy on GitHub is optional and
later; mention it, do not set it up. A copy on the user's own computer is offered in step 10.

## 10. Offer a copy on the user's computer

Ask one question: "Do you want a read-only copy of this repo on your own computer (Mac or Linux)?
It is refreshed after every change. Reply yes or no." Neither answer is a stop.

- **Yes:** follow `grokbotceo/LOCAL-COPY.md` ([LOCAL-COPY.md](LOCAL-COPY.md)): warn about the
  permission question, find the home folder, agree on the path, write
  `<WORKSPACE_PATH>/local-copy.json`, commit it:

  ```bash
  cd <WORKSPACE_PATH>
  git add local-copy.json
  git commit -m "Add a copy on my computer" -m "Bot: <your bot name>"
  ```

  then make the first copy (pack, copy the file, unpack). Windows, a `STOP:` line or a failed
  copy: tell the user in one line and go on to step 11.
- **No:** say they can ask Bot Maker at any time: "make a copy on my computer".

## 11. Report and hand over to the mentor tour

One short message: the two bots and their check results; where the repo is (and the copy, if one
was made); how updates work (one sentence: "updates are offered, never applied without your yes;
config.json and your own bots are never touched"). Then start the tour from `grokbotceo/skills/mentor/SKILL.md`, step 1.

---

## Reference: native tools

| Tool | Accepted arguments | Not accepted |
|---|---|---|
| `CreateAgent` | `name` (required), `description`, `section_id` | settings, routines, avatar, any other key |
| `UpdateAgent` | `agent_id` (required), `name`, `description` | settings, routines, deletion |

`description` is the bot's full working text. After `CreateAgent` or `UpdateAgent` the text is in
`~/agent-data/agents/<agent_id>/profile.json` on the bot computer, readable from the shell; that is what the
write check compares. Bot memory and routines are not on disk.

## Reference: files of a bot in the release

| File | Role |
|---|---|
| `bots/<bot>/prompt.md` | the bot's full text — the only source of `description` |
| `bots/<bot>/profile.json` | name and metadata; metadata is stripped by the build |
| `bots/<bot>/routines.md` | optional bots only: routines, not used in this release |
| `bots/<bot>/settings.json` | optional bots only: settings, not used in this release |

Editing files in the workspace does not change a live bot. A bot changes only through
`UpdateAgent` (Bot Maker, updates).

## Tests (no network, no live bots)

```bash
python3 -B scripts/test-bot-payload.py
```
