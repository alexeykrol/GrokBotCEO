# Bot Templates

One folder per bot. This release (stage 1) installs only the two core bots; the others stay here
for later stages and are not offered by the installer.

## Bot structure

- `README.md` — purpose, anti-jobs, files
- `profile.json` — name and metadata; no bot text — that lives only in `prompt.md`
- `prompt.md` — the bot's full text, with `{{KEY}}` placeholders filled from `config.json`
- `settings.json`, `routines.md` — optional bots only; not used in this release

## Installed in stage 1

- **[main-grok](main-grok/)** — the user's main assistant; carries the mentor skill; sends bot work to Bot Maker
- **[bot-maker](bot-maker/)** — creates and changes the user's bots and keeps the repo mirror

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
