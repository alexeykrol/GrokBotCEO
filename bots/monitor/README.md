# Monitor

**Role:** Weekly reports on bot usage, proposes improvements

**Key responsibility:** Analyze bot performance and propose actionable improvements based on actual usage data

## What Monitor Does

- Generates weekly report on all bots (usage, response times, load)
- Identifies recurring failures and proposes fixes
- Detects repeated requests that could become skills
- Tracks acceptance rate of past proposals
- Posts improvement proposals to review channel
- Maintains historical data for trend analysis

## Anti-Jobs

Monitor does NOT:
- Change, pause, or delete bots or routines (only reports)
- Quote conversation content (only counts, timings, labels)
- Edit prompts or files (except own data in {{MONITOR_DATA_PATH}})
- Post anywhere except improvements channel
- Invent numbers it can't source from transcripts or tools

## Files

- `profile.json` — Bot name and metadata (persona is in `prompt.md`)
- `prompt.md` — Detailed measurement and reporting instructions
- `routines.md` — Weekly report schedule

## Setup Notes

1. **Timezone:** Replace `{{OWNER_TIMEZONE}}` with your actual timezone
2. **Report schedule:** Adjust weekly report time to your preference
3. **Improvements channel:** Replace `{{IMPROVEMENTS_CHANNEL}}` placeholder
4. **Data paths:** Replace `{{MONITOR_DATA_PATH}}` and `{{WORKSPACE_PATH}}` with your actual paths
5. **Language:** Template uses Russian; adapt to your language

## What Monitor Measures

**Per bot:**
- Usage: message count, routine runs
- Response time: median and max (first reply, final reply)
- Load: tool calls, background tasks, long runs

**System-wide:**
- Shared resources (CPU, memory, disk)
- Funnel metrics (if you use readers with stats.db): `python3 scripts/reading-dedup-sort.py report --db <stats.db>` prints cycles, posts and registry counts per platform as JSON

**Improvement proposals:**
- Recurring failures (top 3 per bot)
- Repeated requests (3+ times → skill candidate)
- Repeated instructions (2+ times → prompt rule)
- Proposal acceptance rate tracking

## Report Format

- Table: bot | calls | response time | load | vs last week
- Leaders: most used, slowest, heaviest
- Outsiders: candidates to merge or delete (0-1 calls)
- Proposals section with citations (session links)
- Open questions and gaps
- Sources for every number

---

**Status:** v0.1 template (sanitized from Russian private source)
