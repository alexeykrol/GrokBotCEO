# Adapting the System to Your Needs

## What You Can Customize

GrokBotCEO is designed as a template system. You're expected to adapt it to your work, not use it exactly as shipped.

### 1. Schedules

**All process schedules are configurable.**

How to adjust:
- Edit process cards in `company-structure/processes/`
- Change cron expressions to match your timezone and daily routine
- Test manually before enabling automation

Examples:
- Move morning reading from early morning to your actual wake time
- Adjust weekly planning to your preferred planning day
- Align data sync with your backup schedule

### 2. Bot Roles

**Add, remove, or merge bots based on your actual needs.**

When to add a bot:
- You need separate routines, credentials, or channels
- Role is distinct enough to justify isolated chat history
- Existing bots can't handle this scope

When to merge bots:
- Two bots rarely run and share similar access
- Combined chat history wouldn't be too noisy
- No credential or channel conflicts

### 3. Reading Filters

**Customize which posts get through to you.**

Reading filter protocol defines relevance criteria. Adjust:
- Keywords and topics you care about
- Threshold for "practical relevance"
- Language and translation preferences

### 4. Data Storage

**Choose where bots store data.**

Default: Local JSONL files in `data/` folder  
Options:
- Switch to database (SQLite, Postgres)
- Use Notion for certain datasets
- Keep append-only logs for audit trail

### 5. Integrations

**Connect only services you actually use.**

Available integrations:
- X (Twitter) for post reading
- Telegram for channels and messages
- Notion for project management
- GitHub for repository analysis
- Calendar for scheduling

Enable per bot based on its role.

### 6. Protocols

**Adapt decision rules to your judgment style.**

Protocols define criteria (reading filter, review standards, handoff requirements). Rewrite them to match your:
- Quality standards
- Risk tolerance
- Approval preferences
- Work style

## What You Should NOT Customize

### Core Architecture Patterns

Keep these patterns intact:
- **Append-only logs** for decisions and board state
- **Board protocol** status flow (inbox → in_progress → review → done)
- **One bot = one job** principle
- **Anti-jobs** lists to prevent role overlap
- **Handoff protocol** for work transfer

Why: These patterns ensure system maintainability and auditability.

## Customization Workflow

1. **Test in staging:** Don't edit live bot prompts directly
2. **Use Bot Maker:** Route changes through Bot Maker for review
3. **Document changes:** Update process cards and protocols when you adjust behavior
4. **Version prompts:** Keep history of what worked and what didn't

---

**Related:**
- [bots.md](bots.md) — Understanding bot roles before customizing
- [processes.md](processes.md) — Process structure you're adapting
