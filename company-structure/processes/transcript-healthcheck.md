# transcript-healthcheck — Bot Chat Health Monitor

**Owner:** Bot Maker  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1-5` (weekday mornings, paused by default)  
**Autonomy Level:** L1 (monitors, reports issues)

## Purpose

Monitor bot chat transcript health: detect errors, long transcripts, stale sessions.

## Inputs

- Bot transcripts (via ReadTranscript or file system)

## Outputs

- Health report if issues found
- Silent if all healthy

## Success Criteria

- Issues detected and reported
- Actionable recommendations

Related: Bot Maker bot, routine maintenance
