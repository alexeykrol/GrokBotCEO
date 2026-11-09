# Protocols and Rules

## What is a Protocol?

A **protocol** is a documented rule or criterion that bots follow consistently. Protocols ensure predictable behavior and prevent bots from making inconsistent decisions.

## Core Protocols

### 1. Board Protocol

Task lifecycle with five statuses:

```
inbox → in_progress → review → blocked → done
                         ↓
                      blocked
```

**Status meanings:**
- `inbox` — Task arrived, not yet claimed
- `in_progress` — Bot accepted ownership and is working
- `review` — Result ready, awaiting review
- `blocked` — Missing data, access, or approval needed
- `done` — Review passed or owner approved

**Storage:** `data/board.jsonl` (append-only log)

### 2. Handoff Protocol

Work transfer between bots with full context.

**Required handoff elements:**
- Task description and current state
- Relevant links or references
- Why this bot (not another) should handle it
- Success criteria or expected outcome
- Deadline or urgency if applicable

**Format:** Bot sends message to target bot via SendToAgent with structured context.

### 3. Review Protocol

Quality check before marking work done.

**Review criteria (adapt to your standards):**
- Requested result delivered
- No obvious errors or omissions
- Links and references work
- Secrets/credentials not leaked
- Changes documented if needed

**Reviewer:** Another bot or system owner

**Outcomes:** `pass` (→ done), `fail` (→ in_progress with feedback), `blocked` (→ blocked)

### 4. Reading Filter Protocol

Criteria for post relevance (used by Reader bots).

**Include if:**
- Practical value (how-to, tool, analysis, case study)
- Relevant to active projects or skills
- Novel technique or approach
- Official announcement from trusted source

**Exclude:**
- Pure commentary without substance
- Retweets without added value
- Off-topic or entertainment content
- Promotional spam

**Edge cases:** When uncertain, forward with note explaining doubt.

### 5. Secrets Protocol

**Rules:**
- Secrets and credentials NEVER in chat transcripts
- Request through official app permission dialogs
- Store in secure credential manager (not plain text config)
- Each bot gets only secrets it actually needs

## Why Protocols Matter

1. **Consistency:** Same decision every time for similar input
2. **Auditability:** Clear why bot chose action X not Y
3. **Delegation confidence:** You trust bot to follow rules when you're not watching
4. **Onboarding new bots:** Copy protocol, bot inherits behavior

## Adapting Protocols

Protocols are yours to customize. When your judgment differs from default:

1. Document your criteria in protocol file
2. Update bot prompts to reference your version
3. Test with edge cases
4. Refine based on outcomes

---

**Related:**
- [bots.md](bots.md) — How bots use protocols
- [processes.md](processes.md) — Processes that follow protocols
