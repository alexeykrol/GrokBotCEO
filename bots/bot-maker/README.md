# Bot Maker

**Role:** Designs and updates bots, manages system changes

**Key responsibility:** Creating high-quality focused bots with clear roles and explicit anti-jobs

## What Bot Maker Does

- Designs new bots when needed (based on "one bot = one job" test)
- Updates existing bot configurations
- Manages bot prompts, profiles, settings, routines
- Posts change proposals to improvements channel for review
- Applies approved changes with clear documentation

## Anti-Jobs

Bot Maker does NOT:
- Make changes without approval (all diffs go through review)
- Create bots that overlap existing roles
- Design shareable templates by default (bots are for your use)
- Handle routine execution (only designs them)

## Files

- `profile.json` — Bot name and metadata, avatar (persona is in `prompt.md`)
- `prompt.md` — Core instructions
- `settings.json` — Configuration flags
- `routines.md` — Scheduled maintenance tasks

## Setup Notes

1. **Improvements channel:** Replace `{{IMPROVEMENTS_CHANNEL}}` placeholder with your actual review channel name
2. **Change format:** Bot posts diffs as ЧТО (what) / ГДЕ (where) / ПОЧЕМУ (why)
3. **Approval required:** Bot waits for owner approval before applying changes
4. **Routines:** Adjust cron schedules to your timezone

## Routines

Bot Maker runs:
- **Daily data sync:** Commits data files to git, syncs with remote
- **Transcript healthcheck:** Monitors bot chat health (optional, can pause)
- **Routine healthcheck:** Verifies scheduled tasks run correctly (optional)

---

**Status:** v0.1 template (sanitized from private source)
