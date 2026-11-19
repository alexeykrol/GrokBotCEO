# Update — the update recipe for the bot

**Reader:** the bot the user asked to update BotCEO: Bot Maker, or the user's main bot (for
an install from before 0.2.1 the user pastes the update request from [README.md](README.md)).
Follow the steps in order. Do not add steps. Talk to the user in their language, in beginner's
words: one idea and at most one question per message; no technical words (git, repo, commit,
GitHub, config.json, paths, payload, diff) unless the user asks.

If you read this file on the web, read it again from the fetched release
(`build/update/release/UPDATE.md`, step 2) and follow that copy.

An update:

- brings the release copy (`grokbotceo/`) to the target version;
- updates the texts of the installed core bots (Bot Maker, Mentor, Reminder, Translator, Monitor,
  and the BotCEO part of the user's main bot) **only after the user's yes**; a core bot the user
  changed, or one whose installed copy is missing, is updated only if the user ticks it;
- offers the core bots that are new in the release, or were never created;
- carries the user's course progress over and rebuilds Mentor's knowledge base;
- after a complete update whose terms notice (accepted by the user) says course remarks are sent,
  turns course feedback on as a fresh install does — never over a decision the user already made;
- if a bot could not be updated, ends as **partial**: the version number is not moved, and the next
  "update BotCEO" finishes only what is left (step 2 `resume`);
- never touches: values the user set in `config.json`, `bots/my/`, `bots/marketplace/`, any bot
  that is not a core bot, the user's own part of the main bot's text.

## Contract

```
version check → fetch the target into staging, check the commit → config keys → build (script)
      → plan (script) → terms check (script) → one plan, one form (with the terms notice if the
        terms changed) → user "yes" → acceptance recorded if shown (script) → approve (script)
      → swap the release in → config keys written
      → per approved bot: recheck (script) → UpdateAgent / CreateAgent → write check → record
      → routines, only if ticked (as install step 8a)
      → course progress migrated → Mentor's knowledge base → finish: VERSION only if every
        approved bot is done (else partial) → commit → course feedback (only after a complete
        update with the remarks notice accepted; gate by script) → local copy refreshed → final message
```

**Stop only at:** not installed, already current or newer (steps 1–2), fetch or commit check failed
(step 2), missing capability (step 3), build error (step 5), user says no (step 7), swap failed
(step 8), no recorded acceptance of changed terms (step 8). Every stop before step 8 leaves everything as it was: nothing is changed before the
swap. These are **not** stops: one bot's UpdateAgent or CreateAgent error, a bot changed after the
plan, a write check that is not `VERIFIED` (step 9: that bot is left unfinished), a failed routine
request, a failed course migration or knowledge-base build (step 10), course feedback not set up
(step 11). Tell the user in one line and
continue. An unfinished bot makes the update **partial** (step 11): the next update run finishes it.

**Questions to the user: one in the whole update** — the plan (step 7). The only other possible
question is a new config key with no default (step 4), and the release has none today.

**Never:** change a bot that is not in the approved plan; change a value the user set in
`config.json`; read or write `bots/my/` or `bots/marketplace/` (the script only reads their agent
ids, so their bots are never matched by name); write inside `grokbotceo/` (the swap replaces it
whole); create or turn on a routine, or ask a bot for one, without the user's tick; delete a bot;
add a git remote or push; `git add` anything not listed in step 11; delete or edit
`update-state.json` or `grokbotceo.old/` by hand (the script keeps them until the update is complete);
send a bot's payload without a `recheck` that printed `go: true` right before.

All commands run on the bot computer inside `<WORKSPACE_PATH>` (from `config.json`). `U` below
stands for `python3 -B -I build/update/release/scripts/update-plan.py` until the swap (step 8) and
`python3 -B -I grokbotceo/scripts/update-plan.py` after it. Every `U` command prints JSON; read it,
do not show it to the user.

## 1. Version check

Find the target: the release GitHub marks Latest on https://github.com/alexeykrol/GrokBotCEO
(the releases/latest link); if that cannot be read, the highest version tag `v<version>`,
counting release candidates. Never ask the user which version.

Read `<WORKSPACE_PATH>/VERSION` (an install from an early release candidate has
`installed/VERSION` instead) and compare it with the tag without the leading `v`. If
`<WORKSPACE_PATH>/update-state.json` exists, do not stop here whatever the versions say: an earlier
update may be unfinished, and step 2 (`U version`) decides.

- no such file: say BotCEO is not installed here; installing is LOADING-INSTRUCTIONS.md. Stop.
- the same version: say the newest version is already installed. Stop.
- different: tell the user in one line: "Version <installed> is installed, <target> is out. I will
  check what changes and show you before touching anything." Continue. Step 2 confirms by code
  (`U version`) that the target is really newer.

## 2. Fetch the target into staging and check the commit

**First, before deleting anything,** look for an unfinished update:

```bash
cd <WORKSPACE_PATH>
ls -d grokbotceo grokbotceo.old update-state.json 2>/dev/null
```

- `grokbotceo.old` is listed and `grokbotceo` is not: an earlier update stopped in the middle of
  the swap. Put the release back first: `mv grokbotceo.old grokbotceo`.
- `grokbotceo.old` or `update-state.json` is listed: keep them. They are outside `build/update/`, so
  the cleanup below does not touch them; never delete them yourself. `U version` below tells you
  whether that update is unfinished.

Then fetch:

```bash
rm -rf build/update/release build/update/out
git ls-remote https://github.com/alexeykrol/GrokBotCEO "refs/tags/<tag>" "refs/tags/<tag>^{}"
git clone -q --depth 1 --branch <tag> https://github.com/alexeykrol/GrokBotCEO build/update/release
git -C build/update/release rev-parse HEAD
cat build/update/release/VERSION
```

Checks, all by comparing the printed text:

- the commit from `rev-parse HEAD` equals the `ls-remote` commit (the `^{}` line if there is one,
  else the plain tag line);
- `VERSION` equals the tag without the leading `v`.

Anything fails (no network, clone error, a different commit or version): say in one line that the
new version could not be downloaded, delete `build/update/`, stop. The installed `grokbotceo/` was
not touched. Then:

```bash
U version --target <tag>
```

It prints `installed`, `target` and `action`:

- `update`: continue.
- `resume`: an earlier update to `target` did not finish (`pending`, `failed` and `stopped` name the
  bots left; all three empty means only its last step was cut off). Tell the user in one line: "The last update did not finish; I will finish it." If
  `target` is not the tag you fetched, fetch again with tag `v<target>` (the same commands and
  checks above). Continue with every step as usual: the plan knows what is already done.
- `current`, `newer_installed` or `not_installed`: say so in one line, delete `build/update/`, stop.

From here on read the rest of this file from `build/update/release/UPDATE.md`.

## 3. Capability check

As install step 2, only: reading and writing files, `python3`, `git` (**stop** if missing);
`UpdateAgent` (**stop** if missing: an update is UpdateAgent); `CreateAgent` (optional: new bots
are then not offered); `SendToAgent` (optional: routines as install step 8a); the tool for answer
options (optional: one short line listing the answers). Report in one short list.

Find the main bot only if `bots/core/main-grok/agent.json` is missing: as install step 3
(`python3 grokbotceo/scripts/bot-mirror.py list`; the main bot is the user's everyday assistant,
normally you if you are not Bot Maker). Exactly one match: remember its `agent_id` as
`<main id>`. Otherwise do not ask: the main bot is skipped in this update.

## 4. Config keys

```bash
U config
```

It prints `missing` (keys the new release needs that `config.json` lacks), `unknown` (keys this
release no longer knows; they stay in `config.json`, they are only left out of the build) and writes
the build config `build/update/out/config.json`. It never changes `config.json` here.

For each missing key, choose the value as install step 5 says, without asking: `WORKSPACE_PATH` is
this workspace; a `*_BOT` key is the bot's name as in install step 5 (the same word in the user's
language). A key with no rule there: ask the user one short question for it. Then:

```bash
U config --set KEY=value [--set KEY=value ...]
```

`--set` refuses a key the user already has: a value the user set is never changed. The keys are
written into `config.json` only after the yes (step 8).

## 5. Build (script, no model work)

```bash
python3 -B -I build/update/release/scripts/bot-payload-compiler.py build \
  --config build/update/out/config.json \
  --bots bot-maker,mentor,reminder,translator,monitor --out build/update/out/
```

`--bots` is every folder of `build/update/release/bots/` that has `profile.json`. On failure show
the error in one line and stop; nothing was changed.

## 6. Plan (script, no model work)

```bash
U plan [--main-agent-id <main id>]
```

Pass `--main-agent-id` only if you found it in step 3. It compares, per core bot, the text the bot
runs now (`~/agent-data/agents/<id>/profile.json`), the installed copy (`bots/core/<bot>/prompt.md`)
and the new text, and writes `build/update/out/plan.json`. Each bot has a `status` and an `action`:

| status | meaning | action |
|---|---|---|
| `unchanged` | runs exactly the installed text | `update` (or `none`: the new text is the same) |
| `changed` | the user changed it (the text differs, or `"edited": true`) | `ask` (or `none`) |
| `missing_copy` | runs, but there is no installed copy to compare with | `ask` (or `none`) |
| `new` | in the release, not on the bot computer | `offer` |
| `removed` | in `bots/core/`, no longer in the release | `leave` |

When finishing an unfinished update (`resume`), also: `done` (updated earlier in this update; never
touched again), `leave` with a reason (the user kept it as it was). An unfinished bot has `approved`:
`true` means the user already said yes and neither the bot's current text nor the new text has
changed since, so no new question; `false` means it changed after that yes, and it is `ask` with a
fresh diff. `found_applied: true`: it already runs the new text, only check and record it (step 9).

`skip` (with a `reason`) means the bot cannot be updated safely (main bot not found, two bots with
one name, an older BotCEO part in the main bot that the script cannot match). The main bot with
no BotCEO part yet is `offer`. For the main bot only the BotCEO part is replaced; the user's
own part stays.

For every `ask` bot, read `diff_live.file` (what this bot loses and gets: the user's own changes are
the `-` lines) and, if present, `diff_release.file` (what the release changed). Write a "what
changes" summary: at most two short lines, plain words, no quotes from the text longer than a few
words. Judge only the meaning; the counting is in the plan.

## 7. One plan, one form

First check, by code, whether the terms changed since the user last accepted them (an install from
before the terms notice has no record, so it counts as changed):

```bash
cd <WORKSPACE_PATH>
python3 -B -I build/update/release/scripts/terms.py check --release build/update/release --record terms-acceptance.json
```

If it prints `"show": true`, the plan message below also carries the terms notice and the form's
yes is also the acceptance of the new terms: get the notice with

```bash
python3 -B -I build/update/release/scripts/terms.py show --release build/update/release --locale <ll> --mode update
```

(`<ll>` is the user's language code), show its `text` **verbatim** as one paragraph after item 3
below (no paraphrase, no shortening, no translation of your own), and label the buttons exactly
`yes_answers` and `no_answer` from that output. In that case there is always a form, also when
finishing an unfinished update.

When finishing an unfinished update, no bot is `ask` or `offer` and the terms check above printed
`"show": false`: ask nothing. Say in one line
"Finishing the update: <names>." and go on with `U approve` below.

Otherwise show one message, short lines, in this order:

1. "Update to version <target>." Then one line per `update` bot: "<name>: <what changes, a few
   words>". `none` bots: one line "Already up to date: <names>". `removed` bots: "<name> is no
   longer part of BotCEO; I leave it as it is." `skip` bots: one plain line each with the
   reason, and that Bot Maker can do it later.
2. Choices, each unticked: every `ask` bot ("<name>: you changed this bot. The new version
   <summary>; your changes in it <would go | stay, for the main bot>"), every `offer` bot ("Add
   <name>: <what it does>"), and for an offered Reminder or Monitor its routine as a separate
   choice ("with morning reminders" / "with the weekly report"), exactly as install step 6 words it.
3. "Your own bots, your settings and imported bots are not touched."

Ask it as a form: the choices as checkboxes and the buttons `Да` / `Нет` (in the user's language),
with the platform's tool for answer options (its name is not verified; find it with
GetDynamicTools). Without that tool: one short line listing the answers, for example
"Да / Да, и ещё 1, 3 / Нет". Change nothing before the user's own yes. Remember the user's exact
answer words for the commit (step 11) and the routine requests (step 9).

- **No:** for a new update, say nothing was changed; delete `build/update/`. Stop. When finishing an
  unfinished update, "No" keeps the choices as they are: run `U approve` without `--bots` and
  continue — unless the terms notice was shown: then "No" stops, nothing is changed (the new
  release is not swapped in without the acceptance).
- **Yes:** if the notice was shown, first record the acceptance with the user's exact answer words:

  ```bash
  python3 -B -I build/update/release/scripts/terms.py accept --release build/update/release \
    --record terms-acceptance.json --mode update --locale <ll> --answer "<the user's exact answer words>"
  ```

  It accepts only the yes button or its exact words (with the ticked numbers, for example
  "Да, и ещё 1, 3"). `"accepted": false` (exit 2): a vague or other answer is not a yes, also not
  silence or a change of topic; show the same form again and change nothing.

  Then the approved set is every `update` bot, every `approved: true` bot, plus every ticked
  choice. Record it, by code, before anything is changed:

  ```bash
  U approve [--bots <ticked bot>,<ticked bot>]
  ```

  `--bots` lists only the ticked `ask` / `offer` bots (their `bot` ids). Every other `ask` / `offer`
  bot is kept as it is and is never updated by this update, also not when it is finished later.

## 8. Swap the release in, write the config keys

```bash
cd <WORKSPACE_PATH> &&
python3 -B -I build/update/release/scripts/terms.py require --release build/update/release --record terms-acceptance.json &&
python3 -B -I build/update/release/scripts/update-plan.py swap --expect-version <tag>
```

Run it as one block, as written. `terms.py require` fails (exit 2) when the terms of the new
release are not accepted: then the swap does not run; go back to the form of step 7 (nothing was
changed). `swap` checks the same itself and refuses (nonzero, nothing changed) without a valid
acceptance.

It checks the staging tree, writes a journal into `update-state.json`, then renames `grokbotceo/`
to `grokbotceo.old/` and the new release into its place. If anything fails, the old `grokbotceo/`
stays or is put back; if the computer stops between the two renames, the next run puts it back
(step 2). `grokbotceo.old/` is kept until the update is complete. When finishing an unfinished
update the release is usually in place already: it prints `already: true` and changes nothing. On
failure: tell the user in one line that nothing was changed, stop. On success `U` is now `python3 -B -I
grokbotceo/scripts/update-plan.py`. If step 4 set keys:

```bash
U config --release grokbotceo --set KEY=value [--set KEY=value ...] --apply
```

## 9. Update and create the approved bots

For each approved bot (the `approved` list `U approve` printed), in plan order (main bot first,
then the others):

- **Recheck**, by code, immediately before the write:

  ```bash
  U recheck --bot <bot>
  ```

  It reads the text the bot runs now and compares it, and the payload file, with what the user said
  yes to. `go: true`: write at once. `go: false` (with a `reason`): **do not write** — the payload is
  old; the bot is stopped. One line to the user: "<name> was changed after the plan, so I left it as
  it is; ask me to update again to see the new difference." Go to the next bot. There is no
  compare-and-swap on the platform: a change made in the few seconds between `recheck` and the write
  cannot be excluded, so run `recheck` right before the write, with nothing in between.
- `update` or a ticked `ask`: `UpdateAgent` with exactly the fields of the bot's `update_payload`
  file (`agent_id` and `description`; never a name). A ticked `offer` for the main bot: the same.
- a ticked `offer` (a new bot): `CreateAgent` with exactly the fields of its `create_payload` file;
  record the returned `agent_id`.
- `found_applied: true`: no recheck and no write; only the write check and the record below.
- **Write check**, by code:

  ```bash
  python3 grokbotceo/scripts/bot-mirror.py check --agent-id <agent_id> --expected <expected>
  ```

  (`<expected>` is the bot's `expected` file in the plan.)
- **Record**, by code:

  ```bash
  U record --bot <bot> --check <VERIFIED|MISMATCH|NOT VERIFIED> [--agent-id <id of a created bot>] \
    [--routine "not chosen"|asked|failed]
  ```

  `VERIFIED` refreshes `bots/core/<bot>/prompt.md` and `agent.json` (`version` = target,
  `"edited": false`; the routine state, `mode` and the main bot's `previous.md` are kept) and marks
  the bot done. `MISMATCH` or `NOT VERIFIED`: the copy, `version` and `edited` stay as they were (the
  new text is not confirmed), only `agent_id` and `last_update` are written, and the bot stays
  unfinished.
- Print one line: `<bot> · updated|created · <check>`.

Also run `U record --bot <bot> --check <the check result>` for every bot with action `none` whose
status is `unchanged` or `missing_copy`, so its copy and version are current.

An `UpdateAgent` or `CreateAgent` error: that bot is left exactly as it was; mark it, by code:

```bash
U record --bot <bot> --check "NOT APPLIED"
```

One line to the user with the error; continue with the next bot. Do not retry: the update ends as
partial and the next update run tries that bot again. Whether a bot can `UpdateAgent` itself is not
verified: if you are the main bot and updating yourself fails, say Bot Maker can do it ("update
BotCEO" in its chat).

**Routines (only ticked ones).** For a created Reminder or Monitor whose routine the user ticked,
ask the bot as install step 8a says, with the words "BotCEO update" instead of "BotCEO
install", then `U record --bot <bot> --check <check> --agent-id <id> --routine asked|failed`. Not
ticked: `--routine "not chosen"`. An update never asks an already installed bot for a routine.

## 10. Course progress and Mentor's knowledge base

Only if `mentor/progress.json` exists (otherwise Mentor creates it on the first lesson):

```bash
cd <WORKSPACE_PATH>
python3 -B grokbotceo/course/progress.py migrate --json
```

It moves the user's progress to the new course version and keeps a backup (course/SCHEMA.md,
"Migration"). Print one line: `course progress · carried over`. An error: print
`course progress · not carried over: <the error in one line>` and continue; Mentor runs the same
migration first in every course session, so nothing is lost.

Then always:

```bash
python3 -B grokbotceo/course/kb-box/build_kb.py --kb-home mentor
```

`Mentor's knowledge base · built`, or `· not built: <error>` and continue (Mentor builds it itself
on the first question). Do not retry.

## 11. VERSION, commit and course feedback

```bash
cd <WORKSPACE_PATH>
U finish
```

It adds any missing `.gitignore` line (`grokbotceo/`, `build/`, `mentor/kb/`, `grokbotceo.old/`,
`update-state.json`), keeps `bots/my/` and `bots/marketplace/`, and prints `complete` and `git_add`
(the paths to commit).

- `complete: true`: every approved bot is done. It wrote `VERSION` from `grokbotceo/VERSION` and
  deleted `grokbotceo.old/`.
- `complete: false`: some approved bots are not done (`pending`, `failed`, `stopped`). `VERSION` is
  **not** changed and `grokbotceo.old/` and `update-state.json` are kept: the next "update
  BotCEO" finishes only those bots.

Then:

```bash
[ -d .git ] || git init
git config user.name "GrokBotCEO bots"
git config user.email "grokbotceo@localhost"
git add <every path from git_add>
[ -f terms-acceptance.json ] && git add terms-acceptance.json
git commit -m "<Update | Partial update> BotCEO <installed> -> <target> (yes: \"<the user's exact yes words>\")" -m "Bot: <your bot name>"
```

`Partial update` when `complete` is false. Only the paths from `git_add`, plus
`terms-acceptance.json` (the local record of the terms the user accepted; it is never sent); never everything, never
`bots/my/` or `bots/marketplace/`. If `complete` is true: `rm -rf build/update`.

**Course feedback** (`grokbotceo/course/EVENT-SCHEMA.md` §5; as install step 11; silent, no question).
Only if `complete` is true. First the gate, by code:

```bash
cd <WORKSPACE_PATH> && U feedback
```

It prints `run` and `reason`. `run` is true only when the user has accepted the terms notice that says
course remarks are sent (notice version 2 or later, shown in step 7 or accepted before), the install
has no course-feedback decision yet (no consent line at all, so a «не отправляй» said earlier stays as
it is), and an endpoint is configured. `run: false`: do nothing here and print nothing — whatever the
reason. `run: true`: run

```bash
cd <WORKSPACE_PATH> && python3 -B grokbotceo/course/progress.py --kb-home mentor consent --decision granted_at_install
```

(an update has no personal link, so never `--participant-key`). It never writes over an earlier
decision (`"written": false`). If it printed JSON with `"written": true` and an `endpoint`, run as its
own call, with `<ENDPOINT>` that value copied exactly:

```bash
cd <WORKSPACE_PATH> && python3 -B grokbotceo/course/progress.py --kb-home mentor flush --endpoint <ENDPOINT>
```

This registers the installation and writes the key file `~/.grokbotceo/course.env` (mode 600);
never show its content. An error, `"written": false`, `"endpoint": null` or a flush status other than
`registered`: print `Course feedback · not set up` and continue; Mentor registers on the first
remark. Otherwise print `Course feedback · on`. Do not retry. The consent and key files are not
committed. Mentor tells the user about remarks again when the course starts (`notice_due`).

## 12. Refresh the copy on the user's computer

Only if `local-copy.json` exists: refresh it as `grokbotceo/LOCAL-COPY.md` says (pack, copy the
file, unpack). A `STOP:` line or a failure: one line to the user, no retry. No `local-copy.json`:
do nothing and do not offer one.

## 13. Final message

One short message in beginner's words: the version is now <target>; which bots were updated or
added, by their real names; which were left as they were and why, one plain line each (a changed
bot not ticked; a skipped bot; a removed bot; anything that failed). If `complete` was false instead:
"The update is not finished: <names> could not be updated (<reason in plain words>). Say \"update
BotCEO\" again later and I will finish only these." One sentence: "Nothing changes without your
yes."

---

## Reference

| File | What it is |
|---|---|
| `build/update/release/` | the fetched release (staging); becomes `grokbotceo/` in step 8 |
| `build/update/out/config.json` | build config: `config.json` minus unknown keys, plus the new keys |
| `build/update/out/<bot>.md` | the exact new text of a bot (`expected`) |
| `build/update/out/<bot>.payload.json` | `CreateAgent` payload of a new bot |
| `build/update/out/<bot>.update.json` | `UpdateAgent` payload: `agent_id` + `description` |
| `build/update/out/diff/<bot>.live.diff` | the text running now → the new text |
| `build/update/out/diff/<bot>.release.diff` | the installed copy → the new text |
| `build/update/out/plan.json` | the plan: per bot `status`, `action`, `reason`, files, `live_sha256` / `expected_sha256` |
| `update-state.json` | the update in progress: target, per approved bot `pending` / `applied` / `failed` / `stopped` / `kept`, the pins of the yes, the swap journal, the old BotCEO part of the main bot |
| `grokbotceo.old/` | the replaced release, kept until the update is complete |
| `terms-acceptance.json` | the user's acceptance of the terms (version, SHA-256 of the notice shown, language, time, release); local only, never sent |

`build/` is not committed; `build/update/` is deleted at the end of a complete update.
`update-state.json` and `grokbotceo.old/` are outside it on purpose and are not committed. The script reads a bot's
`~/agent-data/agents/<agent_id>/profile.json` only, and only its `name` and `description`.

## Tests (no network, no live bots)

```bash
python3 -B scripts/test-update-plan.py
```
