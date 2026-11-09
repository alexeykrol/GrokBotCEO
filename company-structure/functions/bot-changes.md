# bot-changes — Apply Bot Configuration Changes

**Called by:** Bot Maker (after owner approval)  
**Purpose:** Apply approved changes to bot prompts, profiles, settings, or routines

## Inputs

**Required:**
- **Bot name:** Target bot to modify
- **Change type:** `prompt` | `profile` | `settings` | `routines`
- **Change description:** What changes and why (ЧТО / ГДЕ / ПОЧЕМУ format)
- **Diff or new content:** Exact changes to apply
- **Approval evidence:** Link to owner's approval message in improvements channel

**Optional:**
- **Test instructions:** How to verify change works
- **Rollback plan:** How to undo if it breaks

## Process Flow

1. **Verify approval:** Check that owner explicitly approved (not just bot proposal)
2. **Read current state:** Get current bot configuration files (snapshot reference only)
3. **Update snapshot files:** Edit prompt.md, profile.json in workspace snapshot (NOT live apply)
4. **Compile payload:** Use bot-payload-compiler.py to generate UpdateAgent payload from updated prompt.md
5. **Apply to live bot:** Call cursor.UpdateAgent with agent_id + compiled payload (name/description only)
6. **Write check:** compare the name/description returned by UpdateAgent with the payload. Equal → VERIFIED; different → MISMATCH (report, do not retry blindly); full text not returned → NOT VERIFIED (report, not a failure)
7. **Verify format:** Check JSON validity, prompt structure, cron syntax
8. **Test if specified:** Run test instructions if provided
9. **Report outcome:** Confirm changes applied AND verified, or report failure

CRITICAL: Editing workspace snapshot files (prompt.md, profile.json) does NOT apply changes to live bots.
Live updates require a cursor.UpdateAgent call. No tool is known that reads a bot's full description back, so verification relies on what UpdateAgent returns.

## Outputs

- Updated bot configuration files in `{{WORKSPACE_PATH}}/bots/<bot-name>/` (workspace snapshot/reference)
- cursor.UpdateAgent API response with updated agent_id
- Write check result: VERIFIED / NOT VERIFIED / MISMATCH
- Commit to git with descriptive message
- Report to improvements channel: applied AND verified successfully, or failed with reason

## Success Criteria

- Workspace snapshot files updated correctly (prompt.md, profile.json)
- Valid JSON/YAML syntax (if applicable)
- cursor.UpdateAgent called with compiled payload
- Write check recorded (VERIFIED, or NOT VERIFIED when the full text is not returned); MISMATCH is a failure
- Test instructions pass (if provided)
- Changes match approval

## Failure Handling

**Invalid syntax (JSON, cron, etc.):**
- Do not apply
- Report syntax error to Bot Maker
- Request corrected diff

**Bot doesn't exist:**
- Report to Bot Maker
- Suggest creating bot first

**No approval evidence:**
- Do not apply
- Report missing approval
- Wait for owner's explicit approval

**Test failed after applying:**
- Attempt rollback to previous state
- Report test failure with details
- Mark change as failed in proposals log

## Safety Rules

1. **Never apply without approval:** Only owner's message approves, not bot proposals
2. **Never delete bots:** Changes modify existing bots only (deletion requires separate flow)
3. **Backup before change:** Keep previous state for rollback
4. **Verify before commit:** Check syntax and structure before committing

## Related

- **Bot Maker bot:** Initiates change requests
- **Improvements channel:** Where approvals happen
- **Review protocol:** Changes follow standard review flow
- **Board protocol:** Track change as task (proposal → review → done)

---

**Customize:** Add validation rules, define test requirements, specify rollback automation, add change history tracking.
