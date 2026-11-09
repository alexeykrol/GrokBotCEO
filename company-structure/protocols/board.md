# board — Task Lifecycle Protocol

Task status tracking with five stages.

## Status Flow

```
inbox → in_progress → review → done
           ↓            ↓
        blocked ← ← ← ← ←
```

## Status Definitions

| Status | Meaning | Who Sets It |
|---|---|---|
| `inbox` | Task arrived, not yet claimed | Any bot or owner |
| `in_progress` | Bot accepted ownership and is working | Bot that claimed it |
| `review` | Result ready, awaiting quality check | Bot that completed work |
| `blocked` | Missing data, access, or owner approval needed | Any bot when stuck |
| `done` | Review passed or owner approved | Reviewer or owner |

## Storage Format

**Location:** `{{WORKSPACE_PATH}}/data/board.jsonl`

**Format:** Append-only log, one JSON line per status change:

```json
{"id": "task-identifier", "status": "in_progress", "owner": "bot-name", "handoff": "...", "updated": "2026-11-07T19:30:00-0800"}
```

**Important:** Never edit old lines. Append new line for each status change. Current status = last line for each `id`.

## Rules

### For Bots

1. **Claiming work:** When accepting handoff, append `in_progress` line with your name as `owner`
2. **Completing work:** When done, append `review` line (or `done` if no review needed)
3. **Getting stuck:** Append `blocked` line with reason, escalate to owner
4. **Never skip review:** If protocol requires review, must go through `review` status first

### For Owner

- Can set any task to `done` directly (overrides review)
- Can set stuck tasks to `blocked` for bot attention
- Can reassign by updating `owner` field in new line

## Integration with Other Protocols

- **Handoff protocol:** When bot passes work to another, creates `inbox` entry
- **Review protocol:** `review` status triggers reviewer to check quality
- Works with Monitor for tracking task completion rates

---

**Customize:** Adjust status names, add custom statuses, define your own flow. Keep append-only log pattern for auditability.
