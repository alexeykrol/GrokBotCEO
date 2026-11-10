# Bot Templates

One folder per bot. This release (stage 1) installs only the core; the others stay here for later
stages and are not offered by the installer.

## Bot structure

- `README.md` — purpose, anti-jobs, files
- `profile.json` — name and metadata; no bot text — that lives only in `prompt.md`
- `prompt.md` — the bot's full text, with `{{KEY}}` placeholders filled from `config.json`
- `settings.json`, `routines.md` — optional bots only; not used in this release

A line `[[block:<name>]]` in a text is replaced by a shared block from [`_blocks/`](_blocks/).

## Stage 1: the core

- **Your main bot** — not a new bot: the installer adds **[main-grok/block.md](main-grok/)** to the
  default bot you already have (its name stays). Everyday work; sends lasting changes to Improvements.
- **[bot-maker](bot-maker/)** — creates and changes your bots, agrees every change with you in the
  Improvements channel, and keeps the repo mirror
- **[mentor](mentor/)** — shows you around and answers how things work; brings you to your first own bot
- **The Improvements channel** — you, your main bot and Bot Maker; created at install
- **[_blocks/routing.md](_blocks/)** — the standard routing block that every core bot carries and
  Bot Maker adds to every bot it creates

## Later stages (not offered in this release)

- **[reminder](reminder/)**, **[weekplanner](weekplanner/)** — one-off tasks; weekly plan
- **[reader-x](reader-x/)**, **[reader-telegram](reader-telegram/)** — filter and route posts
- **[translator](translator/)** — two-pass translation; a human publishes
- **[monitor](monitor/)**, **[implementer](implementer/)** — usage report and improvement proposals
- **[projects-manager](projects-manager/)**, **[task-manager](task-manager/)**, **[repository-analyst](repository-analyst/)** — projects and local folders
- **[director](director/)** — reference only

## Anti-jobs principle

Each bot lists explicit anti-jobs — things it does NOT do. This keeps bots focused and prevents
overlap.
