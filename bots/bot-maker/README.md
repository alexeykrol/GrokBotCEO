# Bot Maker

**Installed core bot.** Creates and changes the user's bots on request and keeps a record of
each of them in the user's repo mirror.

## What it does

- Takes every request for a lasting change. Any bot hands such a request straight to Bot Maker
  (`SendToAgent`, agent id from `bots/core/bot-maker/agent.json`).
- Talks a passed-on request through in the #Improvements channel (`SendToAgent` with the channel
  id from `config.json`). When it cannot post there, it stays in its own chat and tells the user.
- Asks only what it cannot work out on its own and never asks which language a bot should use (a
  bot uses the user's language). Choices and yes/no questions are forms with buttons or checkboxes.
- Presents each proposed change as three lines: WHAT / WHERE / WHY.
- Approval is the user's own message only; words relayed by another bot do not count. The commit
  keeps the user's exact approving words: `... (yes: "<exact words>")`, then `Bot: Bot Maker`.
- New bot: asks only what is missing, gives a brief overview in the language the user writes
  in (its name, jobs, what it refuses, tools; the working text only if asked), waits for the yes, then
  `bot-payload-compiler.py compose` appends the standard routing block (`bots/_blocks/routing.md`)
  to the user's text, `CreateAgent`, write check against the bot's `profile.json`, save to
  `bots/my/<bot>/`, commit. The new bot stays out of #Improvements (a channel holds 6 bots at
  most). A new bot goes into the user's bot section when there is one (`--section-id`). Each new
  bot opens with a message naming its job plus one ready example, and offers every choice as a form.
- Changes a bot: WHAT / WHERE / WHY, yes, `UpdateAgent`, write check, new `prompt.md`, commit.
  Each bot's versions are its git history.
- Core bots (`bots/core/`) can be changed on request; it warns first and marks them `edited`.
- Adds BotCEO to the user's main bot later, if that did not work at install
  (`bot-payload-compiler.py extend`), after the user's yes.
- Makes channels and invites bots on request (a channel name begins with `#`; a bot can neither
  rename nor remove a channel); notes every channel it makes or discovers in `channels/<slug>.md`
  (name, id, members, purpose).
- A bot added from the marketplace: copies the name and text of bots the repo does not know into
  `bots/marketplace/` (nothing else from the bot folder).
- Moves lasting rules into a bot's text; memory is for facts.
- Keeps the optional read-only copy on the user's computer current after each commit
  (`LOCAL-COPY.md`); starts or ends the copy on request.

## Anti-jobs

- Nothing changes until the user says yes themselves.
- No secrets in chat, no messages to people outside, no push or remote, no deleting bots.
- Does not turn on routines; each bot schedules its own routines on request.
- Does not present an unverified platform capability as fact.

## Files

- `profile.json` — name only (the text is in `prompt.md`)
- `prompt.md` — the bot's full text; placeholders `{{WORKSPACE_PATH}}`, `{{MENTOR_BOT}}`

Uses `scripts/bot-payload-compiler.py` (`compose`, `extend`) and `scripts/bot-mirror.py` (write
check, marketplace copies, the archive for the copy on the user's computer) from the release.

## Credits

The idea of a bot that builds bots was inspired by Lauren Tan's dr eggbot. Bot Maker is an independent implementation and is not affiliated with or endorsed by her.
