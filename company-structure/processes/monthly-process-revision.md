# monthly-process-revision — Monthly Process Review

**Owner:** Reminder  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} 1,2 * *` (1st and 2nd of month, disabled by default)  
**Autonomy Level:** L1 (reminds, owner reviews)

## Purpose

Monthly reminder to review process effectiveness, adjust schedules, remove unused processes.

## Inputs

- Process cards in company-structure/processes/
- Monitor historical data (usage patterns)

## Outputs

- Reminder to owner with review checklist
- Suggested processes for review (low usage, outdated)

## Success Criteria

- Review reminder delivered
- Owner reviews and decides adjustments

Related: Monitor weekly reports, process lifecycle
