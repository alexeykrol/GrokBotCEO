- **{{READING_ROUTINE_NAME}}:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *`, disabled by default. Daily reading of NEW Telegram channel posts, filtering, routing, digest.

**Setup:**
1. Configure Telegram channel subscriptions
2. Share {{READING_FILTER_PATH}} with Reader X
3. Share {{READING_DATA_PATH}}/stats.db and state.json
4. Adjust schedule (suggest same time as Reader X or offset by 10-15 min)
5. Test manually before enabling

**Autonomy level:** L2 (reads and filters autonomously, routes to implementer)
