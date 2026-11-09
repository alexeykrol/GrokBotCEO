# GrokBotCEO

A ready set of Grok Bot bots, processes, protocols and skills for running a business and a product
with AI bots. You install it once by pasting one command into your Grok Bot chat; after that the
bots are yours to change.

**Version:** see [VERSION](VERSION) — this is a release candidate. The install has been checked
with dry builds and tests, not yet on many real accounts. Reports are welcome in Issues.

## Install

→ [ONBOARDING.md](ONBOARDING.md) (English) · [ONBOARDING.ru.md](ONBOARDING.ru.md) (Русский)

About 20 minutes. Your bot asks a few questions, shows a plan, and creates nothing before your
"yes". Routines (schedules) you set up yourself, with step-by-step guidance.

## What is inside

| Folder | What it holds |
|---|---|
| `bots/` | one folder per bot: `prompt.md` (the bot's full text), `profile.json` (name and metadata), and where needed `routines.md` and `settings.json` |
| `company-structure/processes/` | recurring workflows the bots follow |
| `company-structure/protocols/` | shared rules: reading filter, board, handoff, review |
| `company-structure/functions/` | operations called on demand, such as applying a change to a bot |
| `skills/` | reusable instructions: `mentor` (explains and installs), `post` (translation workflow) |
| `scripts/` | the build script that turns bot texts and your `config.json` into payloads, reader tools, tests |
| `data-schemas/` | schemas of the data files the reader bots keep |
| `teaching/` | how bots, processes and protocols work and how to customize them |

### Bots

Core, installed by default:

- **Main Grok** — your main assistant; routes specialized work to the other bots
- **Bot Maker** — creates and changes bots for you
- **Monitor** — weekly report on how the bots are used, with improvement proposals

Optional:

- **Reader X**, **Reader Telegram** — filter posts by practical relevance and route them
- **Implementer** — reviews posts about agents and tools and proposes what to adopt
- **Translator** — translates posts in two passes; a human publishes
- **Weekplanner** — weekly plan on Monday, tracking during the week, review on Sunday
- **Reminder** — one-off tasks and nudges
- **Projects Manager** — runs team projects from Notion
- **Task Manager**, **Repository Analyst** — work on local project folders (need a connection to your computer)

`bots/director/` is included as a reference and is not offered by the installer in this version.

## How it is built

- A bot's text lives in one place, `bots/<bot>/prompt.md`, with `{{KEY}}` placeholders.
- Your values live in `config.json` in your workspace ([example](config.example.json),
  [all keys](config.schema.md)).
- `scripts/bot-payload-compiler.py build` combines the two. It checks every bot first and writes
  nothing if a key is unknown or a placeholder is left unfilled.

## Updates

Nothing updates by itself. New versions appear as releases of this repository; when you tell your
bot "update", it shows what changed, bot by bot, and asks first. Updates change algorithms and
rules, never your `config.json`. If you edited a bot by hand, you are warned before an update would
overwrite that edit and can take the update, skip it, or ask Bot Maker to merge your edit.

## Security

- Secrets never go in chat. Services are connected in the Grok Bot settings.
- No bot is created, no message sent and no routine turned on without your "yes".
- `config.json` and your workspace stay on your Grok Bot computer.

## Tests

No network and no live bots needed:

```bash
python3 scripts/test-bot-payload.py
python3 scripts/test-reader.py
python3 scripts/test-sync.py
```

## License

Not chosen yet. Until a license file is added, the usual copyright rules apply.
