# reminders-initiation — Capture One-Off Tasks

**Called by:** Reminder bot (on owner request)

## Purpose

Capture one-off task with context, deadline, priority for later reminder.

## Inputs

- Task description from owner
- Deadline (date/time or relative: "tomorrow", "next week")
- Priority (optional: high/normal/low)
- Context (why, dependencies, resources)

## Outputs

- Task record in {{REMINDER_DATA_PATH}}/tasks.jsonl
- Confirmation to owner with assigned task ID
- Scheduled reminder set

## Success Criteria

- Task captured with all required context
- Reminder scheduled at correct time
- Task ID assigned for tracking

Related: Reminder bot, reminders-tracking process
