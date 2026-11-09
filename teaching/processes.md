# How Processes Work

## What is a Process?

A **process** is an autonomous recurring task that runs on schedule (cron) or triggered by an event. Each process belongs to a specific bot and represents that bot's routine work.

## Process Types

### 1. Scheduled Processes (Cron)
Processes that run at specific times on a regular schedule.

Examples:
- Morning reading (daily)
- Weekly planning (Monday morning)
- Weekly tracking (Sunday evening)
- Data sync (nightly)

**Configuration:** Uses cron expressions with timezone-aware scheduling.

### 2. Event-Triggered Processes
Processes that run when specific events happen.

Examples:
- Post implementation review (when reader forwards a relevant post)
- GitHub mirroring (when repository changes detected)
- Plan tracking (when user reports task progress)

**Trigger types:** Messages, file changes, status updates

## Process Lifecycle

```
Define → Test → Deploy → Monitor → Revise
```

1. **Define:** Document trigger, bot owner, inputs/outputs, success criteria
2. **Test:** Run manually to verify behavior
3. **Deploy:** Enable automation (cron or event listener)
4. **Monitor:** Track execution frequency and outcomes
5. **Revise:** Adjust based on usage patterns

## Process vs Function

**Process:** Autonomous, has own trigger (schedule or event)  
**Function:** Called by another bot or process, no own trigger

Example:
- **Process:** "Weekly monitor report" runs every Sunday, analyzes data, writes report
- **Function:** "Apply bot changes" waits for Bot Maker to call it with approved changes

## Where Processes Live

Each process has a card in `company-structure/processes/` with:
- **Trigger:** Cron schedule or event description
- **Bot owner:** Which bot runs this process
- **Inputs:** What data it reads
- **Outputs:** What it produces
- **Success criteria:** How to verify it worked

## Process Coordination

Processes coordinate through:
- **Shared data files:** One process writes, another reads (e.g., stats database)
- **Board protocol:** Task status tracking (inbox → in_progress → review → done)
- **Handoff protocol:** Work transfer between bots with context
- **Shared channels:** Bots post proposals to collaborative channels

---

**Related:**
- [bots.md](bots.md) — Bot structure and communication
- [protocols.md](protocols.md) — Rules for board, handoff, review *(in progress)*
