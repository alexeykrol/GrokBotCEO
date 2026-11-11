# Loading Instructions — installation recipe for the bot

**Reader:** the Grok Bot that the user asked to install GrokBotCEO (see [ONBOARDING.md](ONBOARDING.md)).
Follow the steps in order. Do not add steps. Talk to the user in their language, in beginner's
words: one idea and at most one question per message; no technical words (git, repo, commit,
GitHub, config.json, paths, payload) unless the user asks.

This release installs stage 1 only, the core:

- **the user's main bot is extended, not replaced.** You do not create a new main bot. You add
  the GrokBotCEO block to the user's main bot (normally you, the bot running this install) with
  `UpdateAgent`. Its name stays;
- **Bot Maker** and **Mentor** are created;
- the **#Improvements channel** is created, named in the user's language with a leading `#`
  (`#Improvements`, `#Улучшения`); members: the user, the main bot, Bot Maker;
- a git repo in the workspace mirrors the user's system. No routines are set up.

## Contract

```
fetch → capability check → find the main bot → explain → config.json → plan → user "yes"
      → build (script) → create Bot Maker, Mentor → write checks
      → create the #Improvements channel → extend the main bot → write check
      → bots/core/, channels/, VERSION → Mentor's knowledge base (script) → first commit
      → offer a copy on the user's computer
      → final message: hand the user to Mentor
```

**Stop only at:** already installed (step 1), missing capability (step 2), user says no (step 6),
build error (step 7), CreateAgent error (step 8). These are **not** stops: a write check that
cannot be done (mark it `NOT VERIFIED`), a failed channel (step 9), a failed extension of the main
bot (step 10), a failed build of Mentor's knowledge base (step 11). Tell the user in one line and
continue.

**Questions to the user: exactly two in the whole install.** The "yes" to the plan (step 6) and
the copy offer (step 13). Everything else you decide yourself: version, main bot, names, folders.
If you cannot decide, take the safe default (skip that part; Bot Maker can do it later), say so in
one line and continue. A question the user cannot answer at once is where they give up.

**Forms.** Show both questions as a platform form: answer buttons the user taps, worded in the
user's language (for example `Да` / `Нет`). Use the platform's tool for answer options; find it
with GetDynamicTools in step 2 (its name is not verified in this release). If there is no such
tool, end the question with one short line listing the answers in the user's language.

**Never:** ask for secrets in chat; create a bot not in the approved plan; create a second main
bot; create or turn on a routine; send a message on the user's behalf; write inside `grokbotceo/`
(the release copy); send `config.json` anywhere other than the user's own computer (step 13); add
a git remote or push.

## Layout in the user's workspace

```
<WORKSPACE_PATH>/          git repo, no remote
  .gitignore               grokbotceo/, build/ and mentor/kb/
  grokbotceo/              release copy, read-only; replaced on update; not committed
  config.json              user values {KEY: value}; never overwritten by an update
  local-copy.json          optional: {"path": ...} of the read-only copy on the user's computer
  VERSION                  installed GrokBotCEO version
  bots/core/main-grok/     the user's main bot: prompt.md, previous.md, agent.json
  bots/core/<bot>/         bot-maker, mentor as installed: prompt.md, agent.json
  bots/my/<bot>/           bots the user makes through Bot Maker
  bots/marketplace/<bot>/  copies of imported bots (name and text only)
  channels/<slug>.md       one file per channel: name, id, members, purpose
  mentor/progress.json     the user's place in Mentor's course; Mentor writes and commits it
  mentor/kb/               Mentor's knowledge base, built from grokbotceo/course/; derived, not committed
  mentor/kb-user/          the user's records for that base (questions with no answer); committed by Mentor
  build/                   compiled payloads; safe to delete; not committed
```

`bots/core/<bot>/prompt.md` is always the exact text the bot runs on. `agent.json` is
`{"agent_id": "...", "check": "VERIFIED|NOT VERIFIED|MISMATCH", "version": "<VERSION>", "edited": false}`;
for `main-grok` it also has `"mode": "extended"`, and `"check"` may be `NOT APPLIED` (step 10).
`bots/core/main-grok/previous.md` is the main bot's text before the install, kept for rollback.

## 1. Fetch the release

Get the latest release of https://github.com/alexeykrol/GrokBotCEO into `<WORKSPACE_PATH>/grokbotceo/`
(`git clone --depth 1 --branch <latest tag>`, or the release archive). Read `grokbotceo/VERSION`.
"Latest" is the release GitHub marks Latest on the repository's Releases page (the releases/latest
link). If that cannot be read, take the highest version tag,
counting release candidates. Never ask the user which version to install: picking it is your job.

If `<WORKSPACE_PATH>/VERSION` (or `installed/VERSION` from an earlier release candidate) already
exists, this is not a first install: tell the user which version is installed and stop. Updating is
a separate procedure.

## 2. Capability check

Check with GetDynamicTools and one harmless shell command that you have:

| Capability | Needed for | If missing |
|---|---|---|
| `CreateAgent` (`name`, `description`, `section_id`) | creating Bot Maker and Mentor | **stop**, tell the user |
| reading and writing files in the workspace | config, build, repo | **stop**, tell the user |
| running `python3` | build script, write check | **stop**, tell the user |
| running `git` | the repo mirror | **stop**, tell the user |
| `UpdateAgent` (`agent_id`, `description`) | extending the main bot (step 10) | optional: the main bot is not extended; say so in the plan |
| `CreateChannel` | the #Improvements channel (step 9) | optional: no channel; Bot Maker then agrees changes in its own chat |
| `SendToAgent` | bots passing change requests on | optional: bots then tell the user what to say to Bot Maker |
| a tool for answer options (buttons or checkboxes); name not verified | the two questions (steps 6, 13) as forms | optional: one short line listing the answers |
| `ListSections` | not used at install: bots cannot create sections; Mentor teaches the user later | — |
| running commands on the user's computer and copying files to it (`CopyFromBox`), through the Grok Bot desktop app | the optional copy (step 13) | optional: do not offer the copy; say it needs the desktop app |

Only look for these tools in the list; do not run them in this step. Note the argument names that
GetDynamicTools shows for `CreateChannel` (step 9) and the tool for answer options (steps 6, 13).

Report the result in one short list. Do not look for workarounds.

## 3. Find the main bot

The main bot is **you**: the bot the user asked to install GrokBotCEO. Find your own `agent_id`
before creating anything:

```bash
python3 <WORKSPACE_PATH>/grokbotceo/scripts/bot-mirror.py list
```

It prints every bot on the bot computer as `{agent_id, name}`, read from
`~/agent-data/agents/*/profile.json`.

Folders of deleted bots can stay behind, so the list may show bots that no longer exist. Ignore
every entry whose name is not your own.

- **Exactly one entry has your name:** that is you, the main bot.
- **None or several, or the command fails:** do not ask. Step 10 is skipped; in the plan say in
  one line that Bot Maker will teach the main bot later. Continue.

Remember its `agent_id` and name for steps 6 and 10.

## 4. Explain

In 3–5 short sentences, in plain words: what will be added (the main bot learns GrokBotCEO and
keeps its name; two new bots, Bot Maker and Mentor; a channel called #Improvements, in the user's
language (for example #Улучшения), where changes are agreed; a record of all bots with the history of every change, kept on the bot computer), and that
nothing is created or changed before the user's "yes".

## 5. Write config.json

Stage 1 uses only the keys marked **stage 1** in `grokbotceo/config.schema.md`:

- `WORKSPACE_PATH` — the absolute path of this workspace. Fill it in yourself.
- `BOT_MAKER_BOT` — `Bot Maker`, the name in `grokbotceo/bots/bot-maker/profile.json`. Do not ask.
- `MENTOR_BOT` — `Mentor`, or the same word in the user's language (for example `Ментор`). It is
  the name the user sees in the sidebar. Do not ask.

`IMPROVEMENTS_CHANNEL_ID` (**stage 1 (runtime)**) is added in step 9, after the channel exists.
Bots read it from `config.json` when they need it; it is never built into their texts.

Write the keys to `<WORKSPACE_PATH>/config.json` as a flat JSON object `{KEY: value}`. Do not show the user
the folder or the file. Ask nothing.

## 6. Plan and approval

Show the plan, one short line each, in this order:

1. "I will add GrokBotCEO to me (your main bot); my name stays." If the main bot is another bot
   (step 3), name it: "I will add GrokBotCEO to <name> (your main bot); its name stays." If it
   could not be found, or `UpdateAgent` is missing, say instead that this part is skipped for now.
2. Create **Bot Maker**: makes and changes your bots.
3. Create **Mentor** (the name from `MENTOR_BOT`): shows you around and answers how things work.
4. Create a channel called **#Improvements** (in the user's language, for example **#Улучшения**):
   you, your main bot and Bot Maker; here Bot Maker agrees every change with you. (Skip the line
   if `CreateChannel` is missing.)
5. A record of your bots with the history of every change, kept here on the bot computer; nothing
   leaves it.
6. Afterwards I will ask if you want a copy on your own computer.

Ask: "Shall I do this?", as a form with two buttons in the user's language (for example `Да` /
`Нет`). Create and change nothing before an explicit yes. Other bots in
`grokbotceo/bots/` are not offered in this release.

## 7. Build (script, no model work)

```bash
cd <WORKSPACE_PATH>
python3 grokbotceo/scripts/bot-payload-compiler.py build \
  --config config.json --bots bot-maker,mentor --out build/
python3 grokbotceo/scripts/bot-payload-compiler.py extend \
  --bot main-grok --agent-id <main bot agent_id> --config config.json --out build/
```

`build` writes `build/<bot>.payload.json` (only `name`, `description`, optional `section_id`) and
`build/<bot>.md` (the exact `description`). It fails the whole build on an unknown key or an
unfilled `{{KEY}}`, before writing anything. On failure: show the error, fix `config.json` with
the user, rebuild. Do not edit texts by hand.

`extend` reads the main bot's current text from its `profile.json` and writes
`build/main-grok.previous.md` (the text as it is now), `build/main-grok.md` (that text without
trailing whitespace, a blank line, then the main-bot block) and `build/main-grok.payload.json`
(`agent_id` and `description`; no name, so the name stays). If `extend` fails (the text cannot be
read, or the block is already there), the main bot is not extended: one line to the user, continue.
Skip `extend` if step 3 found no main bot.

## 8. Create Bot Maker and Mentor

For each bot, in this order: `bot-maker`, `mentor`:

1. Call `CreateAgent` with exactly the fields of `build/<bot>.payload.json`. Pass the text as is.
2. Record the returned `agent_id`.
3. **Write check** — read the bot's `profile.json` on the bot computer and compare its
   `description` with what was sent, by code:

   ```bash
   python3 grokbotceo/scripts/bot-mirror.py check --agent-id <agent_id> --expected build/<bot>.md
   ```

   It reads `~/agent-data/agents/<agent_id>/profile.json` (every bot has a folder there, in the home
   folder of the bot computer) and prints `VERIFIED` (equal; trailing whitespace is ignored),
   `MISMATCH` (different) or `NOT VERIFIED` (file missing or unreadable). None of them stops the
   install.
4. Print one line: `<bot> · created · <VERIFIED|NOT VERIFIED|MISMATCH>`.

Mentor may write the first message in its own chat right after it is created; that is fine.

If `CreateAgent` returns an error: stop creating, keep what was created, go to step 11 with the
bots created so far and tell the user which bot failed and the error text.

## 9. Create the #Improvements channel

Call `CreateChannel` with the name: `#`, then the word for Improvements in the user's language,
no space: `#Improvements` in English, `#Улучшения` in Russian. Bots can neither rename nor delete a
channel, so the name must be right the first time. Members: the user, the main bot (step 3) and
Bot Maker (step 8); no other bots (at most 6 bots fit in a channel; other bots send requests
straight to Bot Maker). Use the argument names that GetDynamicTools showed; they are not verified
in this release.

- **It worked:** add `"IMPROVEMENTS_CHANNEL_ID": "<the returned id>"` to `config.json` and write
  `channels/improvements.md`:

  ```
  # <channel name>

  - id: <channel id>
  - members: the user, <main bot name>, Bot Maker (other bots send requests to Bot Maker directly)
  - purpose: requests to change something for good; Bot Maker clarifies them here, shows each
    change as WHAT / WHERE / WHY and changes nothing before the user's own yes
  - created by: <your bot name>, at install
  ```

  Print one line: `<channel name> · created`.
- **It failed:** one line to the user ("I could not create the #Improvements channel; Bot Maker
  will agree changes with you in its own chat"). Write no channel id. Continue.

## 10. Extend the main bot

Skip this step if there is no `build/main-grok.payload.json` (step 7).

1. Call `UpdateAgent` with exactly the fields of `build/main-grok.payload.json`.
2. **Write check** against the combined text:

   ```bash
   python3 grokbotceo/scripts/bot-mirror.py check --agent-id <main bot agent_id> --expected build/main-grok.md
   ```

3. Print one line: `main bot · extended · <VERIFIED|NOT VERIFIED|MISMATCH>`.

Whether a bot can `UpdateAgent` itself is **not verified**. If the call fails: one line to the
user ("I could not add GrokBotCEO to your main bot; Bot Maker can do it later: tell it
'add GrokBotCEO to my main bot'"), record `"check": "NOT APPLIED"` in step 11, continue.

## 11. Save what was installed

- `bots/core/bot-maker/`, `bots/core/mentor/` (each bot created in step 8): `prompt.md` ← copy of
  `build/<bot>.md`; `agent.json` ← `{"agent_id", "check", "version", "edited": false}`.
- `bots/core/main-grok/` (if step 3 found the main bot):
  - `previous.md` ← copy of `build/main-grok.previous.md`;
  - `prompt.md` ← the text the bot runs on now: `build/main-grok.md` if step 10 worked, otherwise
    the same text as `previous.md`;
  - if `extend` failed (no `build/main-grok.previous.md`), write neither file: only `agent.json`;
  - `agent.json` ← `{"agent_id", "check", "version", "edited": false, "mode": "extended"}`, with
    `"check": "NOT APPLIED"` if step 10 was skipped or failed.

Then `VERSION` ← contents of `grokbotceo/VERSION`, and `.gitignore` ← the three lines `grokbotceo/`,
`build/` and `mentor/kb/`. Create empty `bots/my/` and `bots/marketplace/` with a `.gitkeep` each, and
`channels/` with a `.gitkeep` if step 9 failed.

These files let a later update find which bots the user changed, and let the user roll the main
bot back. Do not skip this step.

Then build Mentor's knowledge base, silently (a script, no model work, no question):

```bash
cd <WORKSPACE_PATH>
python3 -B grokbotceo/course/kb-box/build_kb.py --kb-home mentor
```

Print one line: `Mentor's knowledge base · built`. If it fails, print
`Mentor's knowledge base · not built: <the error in one line>` and continue: Mentor builds it
itself on the first question. Do not retry, do not tell the user anything else about it.

## 12. First commit

```bash
cd <WORKSPACE_PATH>
[ -d .git ] || git init
git config user.name "GrokBotCEO bots"
git config user.email "grokbotceo@localhost"
git add .gitignore config.json VERSION bots/ channels/
git commit -m "Install GrokBotCEO <VERSION> (yes: \"<the user's exact yes words>\")" -m "Bot: <your bot name>"
```

The identity is set for this repo only. Add only these paths, never everything. Every later commit
in this repo ends with a line `Bot: <name of the bot that made it>`. No remote is added. A copy on
GitHub is optional and later; do not set it up. A copy on the user's own computer is offered in
step 13.

## 13. Offer a copy on the user's computer

Ask one question: "Do you want a read-only copy of your bots and their history on your own
computer (Mac or Linux)? It is refreshed after every change.", as a form with two buttons in the
user's language (for example `Да` / `Нет`). Neither answer is a stop.

- **Yes:** follow `grokbotceo/LOCAL-COPY.md` ([LOCAL-COPY.md](LOCAL-COPY.md)): warn about the
  permission question, find the home folder, pick the folder, write
  `<WORKSPACE_PATH>/local-copy.json`, commit it:

  ```bash
  cd <WORKSPACE_PATH>
  git add local-copy.json
  git commit -m "Add a copy on my computer (yes: \"<the user's exact yes words>\")" -m "Bot: <your bot name>"
  ```

  then make the first copy (pack, copy the file, unpack). Windows, a `STOP:` line or a failed
  copy: tell the user in one line and go on to step 14.
- **No:** say there is no copy on their computer now; they can tell Bot Maker at any time
  "make a copy on my computer" (in their language).

## 14. Final message: hand the user to Mentor

One short message in beginner's words, no technical words: what is ready (your main bot now
knows GrokBotCEO; Bot Maker; Mentor; the #Improvements channel, by its real name), and anything that did not work, in
one plain line each. One sentence: "Nothing changes without your yes." Then hand over:
"Open Mentor in the list on the left; it will show you around." (Use the name from `MENTOR_BOT`.)
Do not start the tour yourself.

---

## Reference: native tools

| Tool | Accepted arguments | Not accepted |
|---|---|---|
| `CreateAgent` | `name` (required), `description`, `section_id` | settings, routines, avatar, any other key |
| `UpdateAgent` | `agent_id` (required), `name`, `description` | settings, routines, deletion |
| `CreateChannel` | a name and members; read the argument names from GetDynamicTools | renaming, deleting, sections |
| `SendToAgent` | to a bot by `agent_id`; to a channel by its id (both seen working in a test run) | — |

`description` is the bot's full working text. After `CreateAgent` or `UpdateAgent` the text is in
`~/agent-data/agents/<agent_id>/profile.json` on the bot computer, readable from the shell; that is
what the write check compares. Grok Bot trims trailing whitespace when it saves a description, so
the build sends the text without it and the check ignores it. Bot memory and routines are not on
disk.

## Reference: files of a bot in the release

| File | Role |
|---|---|
| `bots/<bot>/prompt.md` | the bot's full text — the only source of `description` |
| `bots/<bot>/profile.json` | name and metadata; metadata is stripped by the build |
| `bots/main-grok/block.md` | the block added to the user's main bot (no profile.json: not a new bot) |
| `bots/_blocks/<name>.md` | shared blocks; `[[block:<name>]]` in a text is replaced by the block |
| `bots/<bot>/routines.md` | optional bots only: routines, not used in this release |
| `bots/<bot>/settings.json` | optional bots only: settings, not used in this release |

Editing files in the workspace does not change a live bot. A bot changes only through
`UpdateAgent` (Bot Maker, updates).

## Tests (no network, no live bots)

```bash
python3 -B scripts/test-bot-payload.py
```
