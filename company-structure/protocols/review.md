# review — Quality Check Protocol

Quality check before marking work done.

## When Review Happens

- Bot completes work and sets status to `review` on board
- Reviewer (another bot or owner) checks result against criteria below
- Reviewer either passes (→ `done`) or fails (→ `in_progress` with feedback)

## Review Criteria

Adapt these to your standards:

### Completeness
- ✓ Requested result delivered
- ✓ All specified outputs present
- ✓ Done criterion from handoff met

### Quality
- ✓ No obvious errors or omissions
- ✓ Links and references work
- ✓ Format matches specification

### Safety
- ✓ Secrets/credentials not leaked in output or logs
- ✓ No unintended side effects
- ✓ Changes documented if needed

### Context
- ✓ Sufficient information for owner to understand result
- ✓ Sources cited for claims and numbers
- ✓ Gaps or assumptions explicitly noted

## Review Outcomes

### Pass
Reviewer updates board status to `done`:
```json
{"id": "task-id", "status": "done", "reviewer": "reviewer-name", "updated": "2026-11-07T19:40:00-0800"}
```

### Fail
Reviewer updates board status back to `in_progress` with feedback:
```json
{"id": "task-id", "status": "in_progress", "owner": "original-bot", "feedback": "Links broken on lines 5-7", "updated": "2026-11-07T19:40:00-0800"}
```

Original bot fixes issues and returns to `review` when ready.

### Blocked
If reviewer needs info to complete review:
```json
{"id": "task-id", "status": "blocked", "blocker": "Need access to test environment", "updated": "2026-11-07T19:40:00-0800"}
```

## Who Reviews

Depends on task type and approval requirements:

| Task Type | Reviewer |
|---|---|
| High-risk changes (bot prompts, credentials, external posts) | Owner always |
| Routine outputs (reports, summaries) | Another bot or owner |
| Autonomous processes (data sync, healthchecks) | Self-review or no review |

Set `approval=yes` in handoff protocol when owner review required.

## Review Workflow

1. **Bot completes work** → sets status `review` on board
2. **Reviewer notified** (via board monitoring or explicit mention)
3. **Reviewer checks** against criteria above
4. **Reviewer decides:** pass / fail / blocked
5. **Reviewer updates board** with outcome
6. **If fail:** original bot iterates and returns to step 1

## Self-Review

For autonomous L2+ processes, bot may self-review:
- Check own output against success criteria
- Log result (pass/fail) in process card
- Escalate failures to owner
- Set `done` if criteria met

---

**Customize:** Define your quality standards, adjust criteria, add domain-specific checks. Keep pass/fail/blocked outcomes.
