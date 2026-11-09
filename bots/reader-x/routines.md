- **{{READING_ROUTINE_NAME}}:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *`, disabled by default. Daily reading of NEW X bookmarks and home feed, filtering by relevance criteria, routing agent/tool posts to implementer, sending digest to owner.

**Setup:**
1. Replace `{{OWNER_TIMEZONE}}` with your timezone (e.g., `America/Los_Angeles`)
2. Replace `{{HOUR}}` and `{{MINUTE}}` with preferred morning reading time (e.g., `6 0` for 6:00 AM)
3. Set flexible window ±15 minutes for routine execution
4. Ensure {{READING_DATA_PATH}} directory exists with subdirectories: `articles/`, and state.json file
5. Configure X account connection for {{X_USERNAME}} in bot settings before first run
6. Create/adapt {{READING_FILTER_PATH}} with your relevance criteria before first run
7. Initialize stats.db from the shipped schema before first run: `sqlite3 {{READING_DATA_PATH}}/stats.db < data-schemas/stats-db-schema.sql` (older database: `scripts/reading-dedup-sort.py migrate --db {{READING_DATA_PATH}}/stats.db`)
8. Test reading script {{WORKSPACE_PATH}}/scripts/reading-dedup-sort.py manually first

**Data storage:**
- {{READING_DATA_PATH}}/state.json — last seen bookmark and feed post IDs
- {{READING_DATA_PATH}}/stats.db — funnel stats, post scores, bot detection
- {{READING_DATA_PATH}}/articles/<post_id>.md — full article texts

**Autonomy level:** L2 (reads and filters autonomously, routes to implementer; implementer proposals require owner approval)

**Silence when nothing new:** If pre-check finds no new posts since last run, routine completes silently (still records cycle in stats.db)
