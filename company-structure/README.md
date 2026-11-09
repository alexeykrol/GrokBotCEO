# Company Structure

Processes, protocols, and functions that make up the GrokBotCEO operating system.

## Structure

### [processes/](processes/)
Autonomous recurring tasks that run on schedule (cron) or triggered by events. Each process has:
- **Owner bot:** Which bot runs this process
- **Trigger:** Cron schedule or event description
- **Inputs:** What data it reads
- **Outputs:** What it produces
- **Success criteria:** How to verify it worked

### [protocols/](protocols/)
Documented rules and criteria that bots follow consistently. Protocols ensure predictable behavior and prevent inconsistent decisions.

Core protocols:
- **Board:** Task lifecycle (inbox → in_progress → review → blocked → done)
- **Handoff:** Work transfer between bots with full context
- **Review:** Quality check before marking work done
- **Reading filter:** Criteria for selecting posts

### [functions/](functions/)
Called operations with no own trigger. Functions are invoked by bots or processes but don't run autonomously.

Examples:
- Bot changes application
- Translation publishing
- Reminders initiation

---

## How They Work Together

1. **Processes** run autonomously and produce outputs
2. **Functions** are called by processes when needed
3. **Protocols** govern how both processes and functions behave
4. All three coordinate through shared data (board, handoff, review)

---

**Status:** v0.1 templates (core documents in progress)
