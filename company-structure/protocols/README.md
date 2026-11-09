# Protocols

Documented rules and criteria that bots follow consistently.

## Core Protocols

- **[board.md](board.md)** — Task lifecycle: inbox → in_progress → review → blocked → done
- **[handoff.md](handoff.md)** — Work transfer between bots with full context
- **[review.md](review.md)** — Quality check before marking work done
- **[reading-filter.md](reading-filter.md)** — Criteria for selecting posts (★1-5 scoring)

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

**Status:** v0.1 (4 protocols complete)
