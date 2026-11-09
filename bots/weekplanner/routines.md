- **weekly-plan:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1`, disabled by default. Monday morning planning session.
- **weekly-tracking:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 0`, disabled by default. Sunday evening tracking review.

**Setup:**
1. Adjust planning time to Monday morning preference
2. Adjust tracking time to Sunday evening preference
3. Create {{PLANNING_DATA_PATH}} directory
4. Define planning format (goals, tasks, success criteria)
5. Test manually before enabling

**Autonomy level:** L1 (facilitates planning, owner decides priorities)
