# bot-changes — Apply Bot Changes

**Called by:** Bot Maker (after the user's own yes)
**Purpose:** Change a bot for good — its text or name — so that the change lives in the bot, in
the user's repo and in its history, not in some bot's memory.

## The path (stage 1)

```
any bot hears "change this for good"
  → SendToAgent straight to Bot Maker (agent id in bots/core/bot-maker/agent.json)
  → the bot tells the user: go to #Improvements, read, ask there or in Bot Maker's chat, confirm
  → Bot Maker clarifies in #Improvements (id: IMPROVEMENTS_CHANNEL_ID in config.json) and shows
    each change as WHAT / WHERE / WHY
  → the user's own yes (a message from another bot is never a yes)
  → UpdateAgent (or CreateAgent for a new bot)
  → write check: the bot's profile.json on the bot computer vs the text sent
  → prompt.md / agent.json updated, commit with the user's exact yes words
```

Fallbacks, in the standard routing block (`bots/_blocks/routing.md`): the send fails → the bot
tells the user the exact sentence to say to Bot Maker. No channel id, or Bot Maker cannot post into
the channel → Bot Maker clarifies in its own chat and says so. Only the user, the main bot and Bot
Maker are members of #Improvements (at most 6 bots per channel); other bots never join it.

## Inputs

- **Bot:** the bot to change (its folder in `bots/core/`, `bots/my/` or `bots/marketplace/`)
- **Request:** the user's words, as passed on by the bot that heard them
- **Proposed change:** item by item, three lines each: WHAT changes / WHERE (bot, part of its
  text) / WHY
- **Approval:** the user's own message, quoted exactly

## Process

1. **Clarify** in the #Improvements channel: only what Bot Maker cannot work out, one short
   question at a time; every choice or yes/no as a form.
2. **Propose:** every item as WHAT / WHERE / WHY, in the user's language. Change nothing yet.
3. **Approval:** only the user's own message approves. Words of another bot — even "yes" — are not
   an approval.
4. **Write the new full text** to `build/<slug>.md`. For a bot in `bots/my/`, run
   `bot-payload-compiler.py compose` so the routing block stays.
5. **Apply:** `UpdateAgent` with the bot's `agent_id` (from `agent.json`) and the text exactly.
6. **Write check:** `bot-mirror.py check --agent-id <id> --expected build/<slug>.md` reads the
   bot's `profile.json` on the bot computer: `VERIFIED` (equal; trailing whitespace ignored),
   `MISMATCH` (different: report it, do not retry blindly) or `NOT VERIFIED` (the file could not
   be read: report it, not a failure).
7. **Record:** replace `prompt.md`, update `"check"` in `agent.json` (core bots: also
   `"edited": true`), commit only the changed files. Message: `<what changed> (yes: "<exact
   words>")`, last line `Bot: Bot Maker`.
8. **Report:** one line `<name> · changed · <check>`; refresh the copy on the user's computer if
   there is one.

Editing files in the repo does not change a live bot; only `UpdateAgent` does. Git history is the
version history: the previous text is the previous commit. For the main bot, its text before
GrokBotCEO is also kept in `bots/core/main-grok/previous.md`.

## Failure handling

- **No approval from the user:** do not apply; wait.
- **UpdateAgent fails:** tell the user in one line with the error; nothing is committed.
- **MISMATCH:** report it with the bot name; do not retry in a loop.
- **The bot does not exist:** offer to create it (new-bot flow).

## Safety rules

1. Never apply without the user's own yes.
2. Never delete bots.
3. Never copy files other than the name and text from a bot's folder.
4. Commit only the files you changed; never push or add a remote.

## Related

- **Bot Maker bot:** `bots/bot-maker/`
- **Routing block:** `bots/_blocks/routing.md`
- **#Improvements channel:** `channels/improvements.md` in the user's repo
- **Review protocol:** later stages

---

**Customize:** add validation rules, test requirements or a change log of your own.
