- **weekly-monitor-report:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * {{DAY_OF_WEEK}}`, disabled by default. Generates comprehensive weekly report with usage metrics, improvement proposals, and posts proposals section to improvements channel.

**Setup:**
1. Replace `{{OWNER_TIMEZONE}}` with your timezone (e.g., `America/Los_Angeles`, `Europe/London`)
2. Replace `{{HOUR}}` and `{{MINUTE}}` with preferred report time (e.g., `19 0` for 7:00 PM)
3. Replace `{{DAY_OF_WEEK}}` with day number (0=Sunday, 6=Saturday) - suggest Sunday (0) for week-ending report
4. Ensure {{MONITOR_DATA_PATH}} directory exists before first run
5. Configure {{IMPROVEMENTS_CHANNEL_ID}} so proposals get posted to right place

**Data storage:** Monitor saves historical reports to {{MONITOR_DATA_PATH}}/YYYY-Www.json and proposal tracking to {{MONITOR_DATA_PATH}}/proposals.jsonl

**Autonomy level:** L1 (reports only, never applies changes)
