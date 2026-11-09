# Reader X

**Role:** Filters and routes relevant X (Twitter) posts

**Key responsibility:** Daily reading of X feed and bookmarks, filtering by relevance criteria, routing valuable content

## What Reader X Does

**On-demand analysis:**
- Owner sends post link (with optional analysis notes)
- Bot reads full post (text, quotes, linked articles, threads)
- Returns verdict: VALUE or JUNK, with 2-3 reasons
- Based on same criteria as daily reading run

**Daily reading run (routine):**
1. Fetch NEW bookmarks and home feed posts since last run
2. Read full text (fetch articles when needed)
3. Score each post by relevance criteria (★1-5)
4. Select ★3+ posts that meet practical relevance filter
5. Route agent/tool posts to implementer bot for analysis
6. Send owner ONE digest grouped by rubrics, with annotations
7. Track stats (funnel, bot detection) in database

**Relevance filter:** Material must show what owner can apply in product, business, or work. Author fame alone not sufficient. Concrete benefit required.

## Anti-Jobs

Reader X does NOT:
- Post, reply, like, bookmark, or DM on X
- Install, buy, or build what posts advertise (only judges)
- Bulk-scan outside scheduled reading run
- Invent metrics or facts it couldn't read
- Automatically send material for translation (owner chooses)
- Send anything externally without approval

## Files

- `profile.json` — Bot name and metadata (persona is in `prompt.md`)
- `prompt.md` — Full reading protocol and criteria
- `routines.md` — Daily morning reading schedule
- `settings.json` — Configuration flags

## Setup Notes

1. **X connection:** Configure bot's X account connection in Grok Bot settings
2. **Reading criteria:** Adapt {{READING_FILTER_PATH}} to your interests and standards
3. **Routing:** Set {{IMPLEMENTER_BOT}} to your implementer bot name
4. **Data paths:** Replace {{WORKSPACE_PATH}}, {{READING_DATA_PATH}} with actual paths
5. **Schedule:** Adjust reading time to your timezone and daily routine
6. **Language:** Template uses Russian output; adapt to your language

## Key Features

**Article fetching:** For high-value posts (★3+) or teasers (★2 with short text + link), fetches full article text and re-scores based on complete content

**Bot detection:** Tracks repeated identical text from same accounts, flags for owner review

**Funnel tracking:** Records read/selected/routed counts per run in stats.db for monitor analysis

**Deduplication:** Uses script to dedupe posts seen in both bookmarks and feed

**Silence when nothing new:** If pre-check finds no new posts, stays silent

---

**Status:** v0.1 template (sanitized from Russian private source, complex filtering logic)
