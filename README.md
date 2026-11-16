# GrokBotCEO

**English** · [Русский](README.ru.md)

A ready set of Grok Bot bots that you install by pasting one command into your Grok Bot chat. At
its centre is **Mentor**, a bot that teaches you how Grok Bot and your own system of bots work, so
that after a short course you can run and change that system yourself.

**Status:** release candidate ([VERSION](VERSION)). Checked with tests and a local emulator; a
short check in Grok Bot itself is still pending. Reports are welcome in
the Issues tab of [this repository](https://github.com/alexeykrol/GrokBotCEO).

## What Mentor gives you

- **A guided course in small steps.** One idea per message: what a bot, a channel, a routine and a
  connection are; how your system is put together; the golden rule (to change something for good,
  tell any bot, and nothing changes without your yes). You can stop at any step and continue later.
- **Answers to "how does this work".** Any time, in or outside the course, Mentor answers from its
  own knowledge base, built from the course. When the base has no answer, or a feature has not been
  verified on the platform yet, it says so honestly instead of guessing.
- **Your first own bot.** The course ends with you creating your first bot through Bot Maker and
  practising what only you can do in the app (channels, sections).
- **Language.** The course texts are in Russian, and the course works in Russian. The other bots
  speak your language.

## Install

Paste this into your Grok Bot chat:

```
Install GrokBotCEO for me.

Repository: https://github.com/alexeykrol/GrokBotCEO (latest release)
Follow LOADING-INSTRUCTIONS.md from that release step by step. Do not improvise steps that are not there.

Rules:
- Ask before creating any bot. Show me the plan first and wait for my "yes".
- Never ask for passwords, tokens or keys in chat.
- Do not turn on any schedule unless I choose it in the plan. Do not send any message on my behalf.
- If a required capability is missing, stop and tell me exactly what is missing.
```

Your bot shows a plan and creates nothing before your yes: **Yes, with routines**, **Yes, without
routines** or **No**. It asks you only one more thing: whether you want a copy on your own
computer. About 20–30 minutes, including the course start. When it is done, open Mentor and write
«Начнём курс» ("Let's start the course").

Step by step: [ONBOARDING.md](ONBOARDING.md) · [ONBOARDING.ru.md](ONBOARDING.ru.md).

## What gets installed

- **Your main bot, extended** — not a new bot: it learns GrokBotCEO and keeps its name; its old text is saved for rollback.
- **Bot Maker** — creates and changes your bots, after your yes, and keeps a record of every change.
- **Mentor** — the course and answers about how things work (see above).
- **Reminder** — keeps your one-off tasks and reminds you on time; never does the task itself.
- **Translator** — translates a text or a post in two passes (draft, your corrections, final); never publishes.
- **Monitor** — a weekly report on how your bots are used, with proposals; never changes a bot.
- **The #Improvements channel** (named in your language, for example #Улучшения) — you, your main bot and Bot Maker; every lasting change is agreed here.
- **Routines, only if you choose them** — Reminder's morning reminders (09:00) and Monitor's weekly report (Sunday 20:00), in your timezone.

Bot names except Bot Maker are in your language. Each bot's full text is in `bots/<bot>/prompt.md`.

## What is written where

Everything stays in your workspace on the Grok Bot computer:

```
<workspace>/          a git repo with no remote: every change is a commit that quotes your yes
  grokbotceo/         this release, read-only; an update replaces it
  config.json         your values: the workspace path and the bot names
  VERSION             the installed version
  bots/core/          your main bot (its text now and before) and the five installed bots
  bots/my/            bots you make through Bot Maker
  bots/marketplace/   copies (name and text only) of bots you import from the marketplace
  channels/           one file per channel: name, id, members, purpose
  mentor/             your place in the course; Mentor's knowledge base (rebuilt, not committed)
  data/               Reminder's tasks; Monitor's weekly numbers and proposals
  local-copy.json     only if you want a copy on your own computer
```

The optional read-only copy goes to your own computer (Mac or Linux), only after your yes and
only through the Grok Bot desktop app.

## What is sent over the network

The release sends nothing to us: no telemetry and no feedback by default. The course has one network
command, the feedback sender (`course/progress.py flush`), and it is off: the release ships no feedback address (no
`course/feedback.json`), the installer sets none, and without an address there is no consent
question and nothing to send. Your bots work through Grok Bot as usual; Translator reads a link only
when you send it one. The repo copy script (`scripts/sync-data.sh`) can push to git only if you
add a remote yourself; the install adds none. Bug reports and ideas: the Issues tab of [this repository](https://github.com/alexeykrol/GrokBotCEO).

## Security

- Secrets never go in chat. Services are connected in the Grok Bot settings.
- No bot is created or changed, no message sent and no routine turned on without your yes.
- Nothing is pushed anywhere. No git remote is added.

## Updates

Nothing updates by itself. New versions are announced in the releases of this repository and in
the author's Telegram channel. When updates come: your bot shows what changed, bot by bot, and
asks first; `config.json`, `bots/my/` and `bots/marketplace/` are never touched; a core bot you
changed is not touched without your answer.

## What is inside

| Folder | What it holds |
|---|---|
| `bots/` | one folder per installed bot: `prompt.md` (its full text), `profile.json` (name), `routines.md` (Reminder, Monitor); `main-grok/block.md` (added to your main bot); `_blocks/` (shared blocks) |
| `course/` | Mentor's course (Russian), its runtime rules, the progress script and the knowledge base |
| `scripts/` | the build script (bot texts + `config.json` → what is sent to Grok Bot), `bot-mirror.py` (write check, marketplace copies, the copy on your computer), tests |
| `company-structure/`, `teaching/` | the template the course teaches with: functions, processes, protocols |

## Tests

No network and no live bots needed:

```bash
for t in scripts/test-*.py; do python3 -B "$t"; done
```

## Credits

Bot Maker was made on the basis of the Bot Maker by Lauren Tan (poteto).
<!-- TODO(owner): add the link to Lauren Tan's Bot Maker here. -->

## License

Not chosen yet. Until a license file is added, the usual copyright rules apply.
