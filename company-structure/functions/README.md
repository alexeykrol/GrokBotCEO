# Functions

Called operations with no own trigger. Functions are invoked by bots or processes but don't run autonomously.

## Function vs Process

**Process:** Has own trigger (cron schedule or event), runs autonomously  
**Function:** No trigger, called explicitly by another bot, waits to be invoked

## Core Functions

- **[bot-changes.md](bot-changes.md)** — Applies approved changes to bot configurations
- **[telegram-translation-publishing.md](telegram-translation-publishing.md)** — Publishes approved translations to Telegram
- **[reminders-initiation.md](reminders-initiation.md)** — Captures one-off tasks for reminder tracking
- **[one-off-tasks.md](one-off-tasks.md)** — One-off task lifecycle management
- **[thinking-out-loud.md](thinking-out-loud.md)** — Voice thinking partner function
- **[weekly-report-and-proposals.md](weekly-report-and-proposals.md)** — Generate improvement proposals

## When to Use Functions

Create a function instead of a process when:
- Operation must be called explicitly (not on schedule)
- Multiple bots need to invoke same logic
- Operation is part of larger workflow
- Approval required before each execution

## Function Structure

Each function card documents:
- **Purpose:** What this function does
- **Called by:** Which bots invoke this function
- **Inputs:** Required parameters and context
- **Outputs:** What it produces or changes
- **Success criteria:** How to verify it worked
- **Failure handling:** What happens on error

---

**Status:** v0.1 (6 functions complete)
