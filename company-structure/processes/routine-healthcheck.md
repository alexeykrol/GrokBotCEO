# routine-healthcheck — Routine Execution Monitor

**Owner:** Bot Maker  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1` (weekly Monday, paused by default)  
**Autonomy Level:** L1 (monitors, reports failures)

## Purpose

Verify scheduled routines run correctly: check execution logs, detect missed runs, report failures.

## Inputs

- Routine schedules from bot routines.md files
- Execution logs (bot transcripts, monitoring data)

## Outputs

- Health report: routines running, missed runs, failures
- Silent if all healthy

## Success Criteria

- All enabled routines verified
- Missed runs and failures reported

Related: Bot Maker bot, routine maintenance
