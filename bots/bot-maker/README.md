# Bot Maker

**Stage 1 core bot.** Creates and changes the user's bots on request, and keeps the record of
every bot in the user's repo mirror.

## What it does

- Asks a few questions, shows a draft prompt, and creates nothing before the user's "yes".
- Creates a bot (`CreateAgent`), checks what was written by reading the bot's `profile.json` on the
  bot computer, saves it to `bots/my/<bot>/` and commits.
- Changes a bot: shows what / where / why, then `UpdateAgent`, check, update `prompt.md`, commit.
  Git history is the version history.
- Core bots (`bots/core/`) can be changed on request; it warns first and marks them `edited`.
- "I installed a bot": copies the name and text of bots the repo does not know into
  `bots/marketplace/` (nothing else from the bot folder).
- Moves lasting rules into a bot's prompt; memory is for facts.
- Creates channels and invites bots on request.
- Keeps the optional read-only copy on the user's computer up to date after every commit
  (`LOCAL-COPY.md`); makes or stops the copy on request.

## Anti-jobs

- No change before an explicit "yes".
- No secrets in chat, no messages to people outside, no push or remote, no deleting bots.
- Does not turn on routines; a bot sets up its own routines when asked.
- Does not state an unverified platform capability as fact.

## Files

- `profile.json` — name only (the text is in `prompt.md`)
- `prompt.md` — the bot's full text; placeholder `{{WORKSPACE_PATH}}`

Uses `scripts/bot-mirror.py` from the release for the write check, the marketplace copies and the
archive for the copy on the user's computer.
