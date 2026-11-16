# weekly-report-and-proposals — Generate Improvement Proposals

**Called by:** Monitor bot (weekly-monitor-report process)

## Purpose

Generate improvement proposals from weekly usage analysis: recurring failures → prompt checks, repeated requests → skills, repeated instructions → rules.

## Inputs

- Bot transcripts (analyzed via ReadTranscript)
- Historical proposals ({{MONITOR_DATA_PATH}}/proposals.jsonl)
- Acceptance rates (proposals approved/rejected trends)

## Outputs

- Improvement proposals with:
  - Type: failure-check | skill | rule
  - Bot affected
  - Evidence (session citations)
  - Proposed change text
- Proposals sent to Bot Maker, which shows each change in #Improvements and applies it only after the owner's yes
- Proposals log updated

## Success Criteria

- Top recurring patterns identified
- Proposals actionable with evidence
- Acceptance rate tracked

Related: Monitor bot, weekly-monitor-report process
