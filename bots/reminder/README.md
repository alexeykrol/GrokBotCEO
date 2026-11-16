# Reminder

**Installed bot.** Keeps the user's one-off tasks and reminds about them on time. Its own bot with
its own name in the sidebar (`{{REMINDER_BOT}}` from `config.json`: `Reminder`, or the same word in
the user's language).

## What it does

- Takes a task in plain words, restates it in one line (what and when), asks for a date as a form
  only if none was given, and saves it.
- Keeps tasks in `data/reminder/tasks.jsonl` in the user's workspace on the bot computer
  (append-only: done, moved or cancelled is a new line).
- Answers "what do I have"; marks tasks done, moves or cancels them.
- An exact time ("remind me at 15:00"): creates a one-time routine; the request is the yes.
- Morning check (routine `morning reminders`, 09:00 in the user's timezone): one message with the
  tasks due today and overdue; nothing due, nothing sent. Created only after the user's yes: in
  the install plan ("Yes, with routines") or in Reminder's chat later. See [routines.md](routines.md).
- Carries the standard routing block (`bots/_blocks/routing.md`): a request to change something for
  good goes to Bot Maker.

## Anti-jobs

- Never does the task itself and never writes to anyone but the user.
- Never decides priorities, invents dates or reads other bots' data.
- Never creates or turns on a routine without the user's yes; changes only routines it created.
- Never asks for passwords, tokens or keys.

## Files

- `profile.json` — name only: `{{REMINDER_BOT}}`
- `prompt.md` — the bot's full text; placeholders `{{REMINDER_BOT}}`, `{{WORKSPACE_PATH}}`,
  `{{BOT_MAKER_BOT}}`; includes `[[block:routing]]`
- `routines.md` — the routines it may create, and when
