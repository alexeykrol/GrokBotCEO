# morning-reading — Daily Morning Reading (Generic)

**Owner:** reader bots you make, one per source (this release does not install any)  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *` (daily morning, disabled by default)  
**Autonomy Level:** L2 (reads and filters autonomously)

## Purpose

Daily filtering of new posts from subscribed sources (X bookmarks/feed, Telegram channels). Scores by relevance criteria, selects valuable content, routes to appropriate bots, sends digest to owner.

## Inputs

- X bookmarks and home feed
- Telegram subscribed channels
- Shared relevance criteria ({{READING_FILTER_PATH}})
- Last seen state ({{READING_DATA_PATH}}/state.json)

## Outputs

- Scored posts recorded in {{READING_DATA_PATH}}
- Posts marked seen only after the digest was delivered
- Agent/tool posts sent on to an analyst bot, if you have one
- ONE digest to owner grouped by rubrics
- Updated state.json with last seen IDs

## Success Criteria

- All new posts since last run scored
- ★3+ posts with concrete benefit selected
- Digest delivered (or silence if nothing new)
- Counts recorded so the weekly report can show them

Related: [Reading filter protocol](../protocols/reading-filter.md)
