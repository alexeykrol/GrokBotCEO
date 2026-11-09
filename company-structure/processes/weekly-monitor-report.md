# weekly-monitor-report — Weekly Bot Usage Report

**Owner:** Monitor  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 0` (weekly Sunday, disabled by default)  
**Autonomy Level:** L1 (reports, proposes, never applies changes)

## Purpose

Weekly analysis of bot usage: calls, response times, load, failures. Propose improvements based on actual usage patterns.

## Inputs

- Bot transcripts (via ReadTranscript across all bots)
- Historical data ({{MONITOR_DATA_PATH}}/YYYY-Www.json)
- Proposals log ({{MONITOR_DATA_PATH}}/proposals.jsonl)

## Outputs

- Weekly report with usage table, leaders, outsiders
- Improvement proposals posted to improvements channel
- Historical data saved for trends

## Success Criteria

- Report covers full week (Monday 00:00 to Sunday 23:59)
- All numbers sourced from transcripts or tools
- Proposals actionable with session citations

Related: Monitor bot, improvement proposals tracking
