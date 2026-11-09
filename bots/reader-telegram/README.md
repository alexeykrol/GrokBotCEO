# Reader Telegram

**Role:** Filters and routes relevant Telegram posts

**Key responsibility:** Daily reading of subscribed Telegram channels, filtering by relevance criteria, routing valuable content

## What Reader Telegram Does

- Daily reading run: fetches NEW posts from subscribed channels since last run
- Scores posts by same relevance criteria as Reader X (★1-5)
- Selects ★3+ posts that meet practical relevance filter
- Routes agent/tool posts to implementer bot
- Sends owner ONE digest grouped by rubrics, with annotations
- Tracks stats in shared database for monitor analysis

**Relevance filter:** Same as Reader X - material must show what owner can apply in product, business, or work

## Anti-Jobs

Reader Telegram does NOT:
- Post, reply, or forward in Telegram channels
- Install, buy, or build what posts advertise
- Bulk-scan outside scheduled reading run
- Automatically translate (owner chooses what to translate)

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Reading protocol and criteria *(template in progress)*
- `routines.md` — Daily reading schedule *(template in progress)*

## Setup Notes

Similar to Reader X but for Telegram:
1. Configure Telegram channel subscriptions
2. Share {{READING_FILTER_PATH}} with Reader X for consistent criteria
3. Share {{READING_DATA_PATH}}/stats.db and state.json for coordination
4. Adjust schedule to run after or with Reader X

---

**Status:** v0.1 placeholder (full template in progress)
