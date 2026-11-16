# Bots

One folder per bot this release installs. Nothing else is shipped.

## Bot structure

- `README.md` — purpose, anti-jobs, files
- `profile.json` — the name only; no bot text — that lives only in `prompt.md`
- `prompt.md` — the bot's full text, with `{{KEY}}` placeholders filled from `config.json`
- `routines.md` — Reminder and Monitor only: the routine the bot may create after the user's yes

A line `[[block:<name>]]` in a text is replaced by a shared block from [`_blocks/`](_blocks/).

## What is installed

- **Your main bot** — not a new bot: the installer adds **[main-grok/block.md](main-grok/)** to the
  default bot you already have (its name stays). Everyday work; sends lasting changes to Bot Maker.
- **[bot-maker](bot-maker/)** — creates and changes your bots, agrees every change with you in the
  #Improvements channel, and keeps the repo mirror
- **[mentor](mentor/)** — the course in small steps; answers how things work; brings you to your
  first own bot
- **[reminder](reminder/)** — one-off tasks and reminders; optional morning routine
- **[translator](translator/)** — two-pass translation; never publishes
- **[monitor](monitor/)** — a weekly report on the bots with proposals; optional weekly routine;
  never changes anything
- **The #Improvements channel** — you, your main bot and Bot Maker (at most 6 bots fit in a
  channel, so no other bots); created at install, named in your language
- **[_blocks/routing.md](_blocks/)** — the standard routing block that every installed bot except
  Bot Maker carries and Bot Maker adds to every bot it creates

## Routines

No routine is created without the user's yes. The install plan offers "Yes, with routines" and
"Yes, without routines"; with routines, the installer asks Reminder and Monitor to create their own
routine (a bot creates its own routines). The user can also ask either bot in its chat later.

## Anti-jobs principle

Each bot lists explicit anti-jobs — things it does NOT do. This keeps bots focused and prevents
overlap.
