- **reminders-tracking:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *`, disabled by default. Daily morning healthcheck: tasks due today.
- **cve-frog-nagging:** `CRON_TZ={{OWNER_TIMEZONE}} */{{INTERVAL_MINUTES}} {{HOUR_START}}-{{HOUR_END}} * * *`, disabled by default. CVE notification nagging.

**Setup:**
1. Configure daily reminder time (morning healthcheck)
2. Set CVE monitoring sources and {{CVE_PACKAGES}}
3. Define {{CVE_NAG_INTERVAL}} (e.g., */30 8-23 for every 30 min, 8am-11pm)
4. Create {{REMINDER_DATA_PATH}} directory
5. Test manually before enabling

**Autonomy level:** L1 (reminds, never acts on tasks)
