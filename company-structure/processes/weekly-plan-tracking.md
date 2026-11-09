# weekly-plan-tracking — Weekly Progress Tracking

**Owner:** Weekplanner  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 0` (Sunday evening, disabled by default) + Events (owner progress reports)  
**Autonomy Level:** L1 (tracks, owner acts)

## Purpose

Track week progress: Sunday review of outcomes, event-driven updates when owner reports progress.

## Inputs

- Week plan (from weekly-plan)
- Owner progress reports ("сделал", "застрял", "не буду")

## Outputs

- Outcomes: done/blocked/deferred + reasons
- Updated tracking state
- Input for next week planning

## Success Criteria

- All planned items have outcome recorded
- Blockers identified
- Progress visible for planning

Related: Weekplanner bot, weekly-plan process
