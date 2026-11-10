# GrokBotCEO

A ready set of Grok Bot bots for running a business and a product with AI bots. You install it
once by pasting one command into your Grok Bot chat; after that the bots are yours to change.

**Version:** see [VERSION](VERSION) — this is a release candidate. The install has been checked
with dry builds and tests, not yet on many real accounts. Reports are welcome in Issues.

## Install

→ [ONBOARDING.md](ONBOARDING.md) (English) · [ONBOARDING.ru.md](ONBOARDING.ru.md) (Русский)

About 20–30 minutes, including your first own bot. Your bot shows a plan and creates nothing
before your "yes".

## What this release installs (stage 1: the core)

- **Your main bot, extended** — no second main bot is created. The default bot you already have
  learns GrokBotCEO and keeps its name; its old text is saved so it can be rolled back.
- **Bot Maker** — creates and changes bots for you. You say what bot you need; it asks a few
  questions, shows the text, creates the bot after your "yes", checks what was written and saves it.
- **Mentor** — its own bot in your sidebar: a short guided tour that explains bots, channels,
  routines and connections, ends with you creating your first own bot, and answers "how does
  this work" any time later.
- **The Improvements channel** — you, your main bot and Bot Maker. Tell any bot to change
  something for good; it passes the request here, and Bot Maker shows each change as what / where /
  why and applies it only after your own "yes".
- **A repo mirror** of your system: your workspace on the bot computer becomes a git repo.
- **An optional copy on your own computer** (Mac or Linux): right after install your bot offers a
  read-only copy of that repo on your computer, refreshed after every change. Say yes or no; you
  can ask Bot Maker for it later.

```
<workspace>/
  bots/core/          your main bot (with its old text) and our bots as installed
  bots/my/            bots you make through Bot Maker
  bots/marketplace/   copies of bots you import from the marketplace (name and text only)
  channels/           one file per channel: id, members, purpose
  config.json         your values
  local-copy.json     optional: where the copy on your computer is
  VERSION             installed version
```

Every change Bot Maker makes is a commit, signed with the name of the bot that made it and your
exact "yes" words. No remote is set up; a copy on GitHub is optional and comes later.

Later stages add a catalog of ready bots (installed the same way, through Bot Maker), then an
improvement loop, then processes and teams. Their bots are already in `bots/` but not installed yet.

## What is inside

| Folder | What it holds |
|---|---|
| `bots/` | one folder per bot: `prompt.md` (the bot's full text) and `profile.json` (name); `main-grok/block.md` (added to your main bot); `_blocks/` (shared blocks) |
| `scripts/` | the build script (bot texts + your `config.json` → payloads), `bot-mirror.py` (write check, marketplace copies, the archive for the copy on your computer), tests |
| `company-structure/`, `teaching/`, `data-schemas/`, `skills/post/` | material for later stages |

## How it is built

- A bot's text lives in one place, `bots/<bot>/prompt.md`, with `{{KEY}}` placeholders.
- Your values live in `config.json` in your workspace ([example](config.example.json),
  [all keys](config.schema.md)). Stage 1 needs three keys, all filled in by the installer, plus
  the id of the Improvements channel, written after the channel is created.
- `scripts/bot-payload-compiler.py build` combines the two. It checks every bot first and writes
  nothing if a key is unknown or a placeholder is left unfilled.

## Updates

Nothing updates by itself. New versions are announced in the releases of this repository and in
the author's Telegram channel. The update procedure comes with stage 2; these are the rules it
follows:

- you say "update"; your bot shows what changed, bot by bot, and asks first;
- `config.json`, `bots/my/` and `bots/marketplace/` are never touched;
- a core bot you changed is not touched without your answer: take the update, skip it, or ask
  Bot Maker to carry your change into the new version.

## Security

- Secrets never go in chat. Services are connected in the Grok Bot settings.
- No bot is created or changed, no message sent and no routine turned on without your "yes".
- `config.json` and your repo live on your Grok Bot computer. Nothing is pushed anywhere. The
  optional copy goes only to your own computer, and only after your yes.

## Tests

No network and no live bots needed:

```bash
python3 -B scripts/test-bot-payload.py
python3 -B scripts/test-reader.py
python3 -B scripts/test-sync.py
```

## License

Not chosen yet. Until a license file is added, the usual copyright rules apply.
