# morning-reading — Daily Morning Reading (Generic)

**Owner:** Reader bots (Reader X, Reader Telegram)  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *` (daily morning, disabled by default)  
**Autonomy Level:** L2 (reads and filters autonomously)

## Purpose

Daily filtering of new posts from subscribed sources (X bookmarks/feed, Telegram channels). Scores by relevance criteria, selects valuable content, routes to appropriate bots, sends digest to owner.

## Inputs

- X bookmarks and home feed (Reader X)
- Telegram subscribed channels (Reader Telegram)
- Shared relevance criteria ({{READING_FILTER_PATH}})
- Last seen state ({{READING_DATA_PATH}}/state.json)

## Outputs

- Scored posts in {{READING_DATA_PATH}}/stats.db, written by `scripts/reading-dedup-sort.py record-stats` (schema: `data-schemas/stats-db-schema.sql`, field `platform`)
- Posts marked seen (`mark-seen`) only after the digest was delivered
- Routed agent/tool posts to Implementer
- ONE digest to owner grouped by rubrics
- Updated state.json with last seen IDs

## Success Criteria

- All new posts since last run scored
- ★3+ posts with concrete benefit selected
- Digest delivered (or silence if nothing new)
- Stats recorded for Monitor analysis

Related: [Reading filter protocol](../protocols/reading-filter.md)
