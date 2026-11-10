# handoff — Work Transfer Protocol

Rules for passing work between bots with full context.

## When to Handoff

Bot A hands off to Bot B when:
- Task requires Bot B's specialized capabilities
- Bot A completed its part, Bot B does next step
- Bot A is blocked and Bot B can unblock
- Owner redirects work to different bot

## Required Elements

Every handoff message must include:

```
HANDOFF from=<sending-bot> to=<receiving-bot> item=<link-or-id> why=<1-phrase-reason> done=<completion-criterion> deadline=<date-or-none> approval=<yes-or-no>
```

**Example** (the main bot passes a lasting change on to the Improvements channel, where Bot Maker
picks it up):
```
HANDOFF from=Main-bot to=Bot-Maker item=improvements-channel why=lasting-rule-for-a-bot done=change-committed-after-users-yes deadline=— approval=yes
```

### Field Definitions

- **from:** Sending bot name
- **to:** Receiving bot name
- **item:** Link, file path, or identifier for work item
- **why:** One-phrase reason for this bot (not another)
- **done:** How receiving bot knows task is complete
- **deadline:** Date in owner's timezone, or `—` if none
- **approval:** `yes` if owner must approve result, `no` if autonomous

## Handoff Flow

1. **Sender** prepares handoff with all required elements
2. **Sender** creates board entry: `{id, status: "inbox", owner: receiving-bot, handoff: "...", updated}`
3. **Sender** sends message to receiving bot with HANDOFF line + context
4. **Receiver** checks handoff completeness: if `done=` missing, asks one clarifying question
5. **Receiver** claims work: updates board to `in_progress`
6. **Receiver** completes work per `done` criterion
7. **Receiver** updates board to `review` or `done` depending on `approval`

## Context Requirements

Beyond HANDOFF line, include:
- Relevant links or file paths
- Key decisions or constraints from previous steps
- What receiving bot should NOT do (if not obvious)
- Expected outcome format

**Good example** (sent with SendToAgent to the Improvements channel):
```
HANDOFF from=Main-bot to=Bot-Maker item=improvements-channel why=new-routine-needs-an-owner-bot done=bot-created-and-committed-after-users-yes deadline=— approval=yes

The user wants a short summary of their unread newsletters every Monday at 9.
Worked out with the user: job = weekly newsletter summary; owner = a new bot (none fits);
trigger = schedule, Monday 9:00; input = newsletters from the last 7 days; output = 5 bullets in chat.
Do NOT turn the routine on: the new bot sets it up itself after the user's yes.
```

## Anti-Patterns

**Bad:** "Can you look at this post?" — missing HANDOFF format, no done criterion  
**Bad:** Handoff without board entry — receiving bot can't track status  
**Bad:** Changing done criterion mid-task without new handoff line  

## Received Task Without done=

If you receive handoff without `done=` criterion, send ONE question back:
```
What's the done criterion? (How do I know this task is complete?)
```

Don't proceed without clear completion criterion.

---

**Customize:** Adjust required fields, add custom metadata, define your own format. Keep structured approach for bot parsing.
