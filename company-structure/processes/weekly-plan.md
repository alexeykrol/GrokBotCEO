# weekly-plan — Weekly Planning Session

**Owner:** Weekplanner  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1` (Monday morning, disabled by default)  
**Autonomy Level:** L1 (facilitates, owner decides)

## Purpose

Monday morning planning: review previous week, discuss priorities, record plan.

## Inputs

- Previous week outcomes (from weekly-tracking)
- Owner's priorities and goals

## Outputs

- Week plan: {{PLANNING_DATA_PATH}}/week-YYYY-Www.json
- Goals, tasks, success criteria

## Success Criteria

- Plan recorded with clear goals and success criteria
- Priorities aligned with owner's focus

Related: Weekplanner bot, weekly-tracking process
