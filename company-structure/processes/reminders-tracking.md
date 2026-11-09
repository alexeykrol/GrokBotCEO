# reminders-tracking — Daily Reminder Healthcheck

**Owner:** Reminder  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *` (daily morning, disabled by default)  
**Autonomy Level:** L1 (reminds, never acts)

## Purpose

Morning healthcheck: remind owner of tasks due today.

## Inputs

- Tasks: {{REMINDER_DATA_PATH}}/tasks.jsonl
- Today's date in owner timezone

## Outputs

- Reminder message with tasks due today
- Silent if no tasks due

## Success Criteria

- Tasks due today listed
- No future task nags (only today)

Related: Reminder bot, one-off tasks function
