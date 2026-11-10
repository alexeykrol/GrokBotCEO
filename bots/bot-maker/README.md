# Bot Maker

**Stage 1 core bot.** Creates and changes the user's bots on request, and keeps the record of
every bot in the user's repo mirror.

## What it does

- Receives every request to change something for good: any bot passes it to the Improvements
  channel (or straight to Bot Maker if the channel is missing or the send fails).
- Clarifies and asks for confirmation in the Improvements channel (`SendToAgent` with the channel
  id from `config.json`). If it cannot post there, it continues in the chat where the request
  came and says so.
- Shows every proposed change item by item as three lines: WHAT / WHERE / WHY.
- Only the user's own message approves. A message from another bot is never a yes. The commit
  message records the user's exact yes words: `... (yes: "<exact words>")`, then `Bot: Bot Maker`.
- New bot: questions, draft, the user's yes, then `bot-payload-compiler.py compose` adds the
  standard routing block (`bots/_blocks/routing.md`) to the user's text, `CreateAgent`, write
  check against the bot's `profile.json`, save to `bots/my/<bot>/`, commit.
- Changes a bot: WHAT / WHERE / WHY, yes, `UpdateAgent`, write check, update `prompt.md`, commit.
  Git history is the version history.
- Core bots (`bots/core/`) can be changed on request; it warns first and marks them `edited`.
- Adds GrokBotCEO to the user's main bot later, if that did not work at install
  (`bot-payload-compiler.py extend`), after the user's yes.
- Creates channels and invites bots on request; records every channel it creates or learns
  about in `channels/<slug>.md` (name, id, members, purpose).
- "I installed a bot": copies the name and text of bots the repo does not know into
  `bots/marketplace/` (nothing else from the bot folder).
- Moves lasting rules into a bot's text; memory is for facts.
- Keeps the optional read-only copy on the user's computer up to date after every commit
  (`LOCAL-COPY.md`); makes or stops the copy on request.

## Anti-jobs

- No change before the user's own yes.
- No secrets in chat, no messages to people outside, no push or remote, no deleting bots.
- Does not turn on routines; a bot sets up its own routines when asked.
- Does not state an unverified platform capability as fact (not verified: whether `SendToAgent`
  can post into a channel).

## Files

- `profile.json` — name only (the text is in `prompt.md`)
- `prompt.md` — the bot's full text; placeholder `{{WORKSPACE_PATH}}`

Uses `scripts/bot-payload-compiler.py` (`compose`, `extend`) and `scripts/bot-mirror.py` (write
check, marketplace copies, the archive for the copy on the user's computer) from the release.
