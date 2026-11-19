# BotCEO

**English** · [Русский](README.ru.md)

A ready set of bots that works with Grok Bot and that you install by pasting one command into your Grok Bot chat. At
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
Install BotCEO for me.

Repository: https://github.com/alexeykrol/GrokBotCEO (latest release)
Follow LOADING-INSTRUCTIONS.md from that release step by step. Do not improvise steps that are not there.

Rules:
- Ask before creating any bot. Show me the plan first and wait for my "yes".
- Never ask for passwords, tokens or keys in chat.
- Do not turn on any schedule unless I choose it in the plan. Do not send any message on my behalf.
- If a required capability is missing, stop and tell me exactly what is missing.
```

Your bot shows a plan and creates nothing before your yes: **Yes, with routines**, **Yes, without
routines** or **No**. The plan ends with a short notice of the terms
([TERMS-NOTICE.md](TERMS-NOTICE.md)); choosing a "Yes" accepts them. It asks you only one more thing: whether you want a copy on your own
computer. About 20–30 minutes, including the course start. When it is done, open Mentor and write
«Начнём курс» ("Let's start the course").

Step by step: [ONBOARDING.md](ONBOARDING.md) · [ONBOARDING.ru.md](ONBOARDING.ru.md).

## What gets installed

- **Your main bot, extended** — not a new bot: it learns BotCEO and keeps its name; its old text is saved for rollback.
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
  terms-acceptance.json  your acceptance of the terms (version, time); kept here, never sent
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

No telemetry. The only thing the release sends us is your remarks about the course, so the author can
fix it. When you tell the Mentor something about a lesson, it sends that remark (only that text, up
to 1000 characters, never the rest of the chat or your quiz answers) to the author's server (address in `course/feedback.json`)
under a random installation ID, without your name. The Mentor tells you this once at the start of
the course; say «не отправляй» to stop and «снова отправляй» to resume. The one network command is
`course/progress.py flush`; the address is in `course/feedback.json`. Your bots work through Grok Bot as usual; Translator reads a link only
when you send it one. The repo copy script (`scripts/sync-data.sh`) can push to git only if you
add a remote yourself; the install adds none. Bug reports and ideas: the Issues tab of [this repository](https://github.com/alexeykrol/GrokBotCEO).

## Security

- Secrets never go in chat. Services are connected in the Grok Bot settings.
- No bot is created or changed, no message sent and no routine turned on without your yes.
- Nothing is pushed anywhere. No git remote is added.

## Updates

Nothing updates by itself. New versions are announced in the releases of this repository and in
the author's Telegram channel. To update, tell Bot Maker "update BotCEO" (in releases
published as GrokBotCEO: "update GrokBotCEO"; from 0.2.1 on it knows how). If you installed an earlier version, paste this into your Grok Bot chat instead:

```
Update BotCEO for me.

Repository: https://github.com/alexeykrol/GrokBotCEO (latest release)
Follow UPDATE.md from that release step by step. Do not improvise steps that are not there.
Show me the plan first and wait for my "yes".
```

What happens:

- Your bot downloads the new version next to the old one first. If the download fails, nothing
  changes.
- It shows one plan: what changes, bot by bot, in plain words, and asks once.
- A core bot you did not change is updated with your "yes". A core bot you changed, or one your
  bot cannot compare, is updated only if you tick it; the plan says what your own changes would
  lose. In your main bot only the BotCEO part is replaced; your own part stays.
- New bots of the release are offered, never added on their own; no routine starts unless you
  tick it.
- Your course progress carries over to the new course.
- Never touched: the settings you set (`config.json`), your own bots (`bots/my/`), imported bots
  (`bots/marketplace/`), and any other bot.
- Every update is one entry in the history of changes, with your exact "yes"; the copy on your
  computer, if you have one, is refreshed.

## What is inside

| Folder | What it holds |
|---|---|
| `bots/` | one folder per installed bot: `prompt.md` (its full text), `profile.json` (name), `routines.md` (Reminder, Monitor); `main-grok/block.md` (added to your main bot); `_blocks/` (shared blocks) |
| `course/` | Mentor's course (Russian), its runtime rules, the progress script and the knowledge base |
| `scripts/` | the build script (bot texts + `config.json` → what is sent to Grok Bot), `bot-mirror.py` (write check, marketplace copies, the copy on your computer), `update-plan.py` (what an update changes, bot by bot), `terms.py` (the terms notice and the local record of your yes), tests |
| `company-structure/`, `teaching/` | the template the course teaches with: functions, processes, protocols |

## Tests

No network and no live bots needed:

```bash
for t in scripts/test-*.py; do python3 -B "$t"; done
```

## Credits

The idea of a bot that builds bots was inspired by Lauren Tan's dr eggbot. Bot Maker is an independent implementation and is not affiliated with or endorsed by her.

## License

BotCEO is open, credit required. It has two parts:

- **The open part** — the bots, the operating system for your bots (`company-structure/`), the course
  engine and the scripts — is under the **BotCEO License 1.0** ([LICENSE](LICENSE), with
  [NOTICE](NOTICE)). You may use it, change it, pass it on and build commercial products on it, **on
  condition of the credit and link**: "Based on BotCEO by Alexey Krol — https://github.com/alexeykrol/GrokBotCEO".
- **The course materials** (lessons, knowledge base, teaching guides) are all rights reserved: see
  the [Course License](COURSE-LICENSE.md).

Which file belongs to which part: [LICENSE-MAP.md](LICENSE-MAP.md). Names and logos:
[TRADEMARKS.md](TRADEMARKS.md). Terms of use: [TERMS.md](TERMS.md); the short notice your bot shows
before installing: [TERMS-NOTICE.md](TERMS-NOTICE.md). Privacy: [PRIVACY.md](PRIVACY.md).

The licenses and terms of the latest release are also offered for the earlier releases, including
those published as GrokBotCEO. Exception: the Bot Maker bot in releases before
0.3.0, and any other material not listed in the latest LICENSE-MAP.md, are not
licensed. Bot Maker is licensed starting with release 0.3.0.

We do not accept outside pull requests at this time.
