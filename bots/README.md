# Bot Templates

This directory contains configuration templates for all 13 bots in the GrokBotCEO system.

## Bot Structure

Each bot directory contains:
- `README.md` — Bot purpose, role, and setup instructions
- `profile.json` — Name and metadata (avatar etc.); no persona — that lives only in `prompt.md`
- `prompt.md` — Core instructions and anti-jobs
- `settings.json` — Configuration flags
- `routines.md` — Scheduled tasks (optional, only for bots with routines)

## Setup Instructions

1. **DO NOT use serverId/channelId from templates** — these are placeholders
2. **Remove agent-id.txt if present** — this is private state file
3. **Customize prompts** — replace placeholder references with your actual channel names, usernames, paths
4. **Adjust schedules** — change cron expressions to your timezone and preferences
5. **Test before automation** — run routines manually first

## Bot Roster (13 Total)

### System Management
- **[bot-maker](bot-maker/)** — Designs and updates bots, manages system changes
- **[monitor](monitor/)** — Weekly reports on bot usage, proposes improvements

### Information Processing
- **[reader-x](reader-x/)** — Filters and routes relevant X (Twitter) posts
- **[reader-telegram](reader-telegram/)** — Filters and routes relevant Telegram posts
- **[translator](translator/)** — Translates content to Russian via two-pass Codex pipeline
- **[implementer](implementer/)** — Analyzes posts about agents/tools, proposes implementations

### Task Management
- **[weekplanner](weekplanner/)** — Manages weekly planning and tracking
- **[reminder](reminder/)** — Handles one-off tasks and CVE tracking

### Content & Projects
- **[director](director/)** — Video production assistant
- **[projects-manager](projects-manager/)** — Runs team projects from Notion

### Development
- **[repository-analyst](repository-analyst/)** — Analyzes local project folders
- **[task-manager](task-manager/)** — Executes coding tasks on local projects

### General
- **[main-grok](main-grok/)** — General discussion bot, delegates specialized tasks

---

## Anti-Jobs Principle

Each bot lists explicit "anti-jobs" — things it does NOT do. This prevents role overlap and keeps bots focused.

Example: Main Grok never owns routines or tracks recurring processes; specialized bots handle that.

---

**Status:** v0.1 templates (4 complete: bot-maker, monitor, reader-x, main-grok; 9 in progress)
