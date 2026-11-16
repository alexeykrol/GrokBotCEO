# Reminder routines

Grok Bot keeps routines on its server, not in files. A bot creates its own routines when asked.
None is created without the user's yes: the install plan asks once ("Yes, with routines"), or the
user asks Reminder in its chat later.

- **morning reminders** — every day at 09:00 in the user's timezone (cron form:
  `CRON_TZ=<the user's timezone> 0 9 * * *`). Reminder reads `data/reminder/tasks.jsonl` and sends
  one short message with the open tasks due today and the overdue ones; nothing due, nothing sent.
- **reminder: <text>** — one-time routines for a task with an exact time. The user's own request
  ("remind me at 15:00") is the yes for that one routine.

The user can change the time or stop a routine by telling Reminder in its chat.
