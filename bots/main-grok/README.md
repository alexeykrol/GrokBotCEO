# Main Grok

**Stage 1 core bot.** The user's main assistant. Carries the mentor skill.

## What it does

- Everyday questions and work, in the user's language.
- Mentor: on "tour" or a question about how the system works, follows `skills/mentor/SKILL.md`.
- "What do I have installed": reads the repo mirror and answers from it.
- Sends "make or change a bot, a channel or a routine" and "I installed a bot" to Bot Maker
  (`SendToAgent`). When more bots are added, Bot Maker adds them to Main Grok's routing.

## Anti-jobs

- Does not create, change or delete bots itself, and does not write to the repo.
- Does not turn on routines or ask for secrets in chat.

## Files

- `profile.json` — name only (the text is in `prompt.md`)
- `prompt.md` — the bot's full text; placeholders `{{WORKSPACE_PATH}}`, `{{BOT_MAKER_BOT}}`
