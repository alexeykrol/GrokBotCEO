# ПЛАН Processes — Not Implemented

These processes are documented as ПЛАН (planned) in source but not yet implemented. They remain in planning status.

## precedent-judge

**Status:** ПЛАН in source  
**Disposition:** Not included in v0.1 (requires ≥30 decisions corpus, no implementation)  
**Purpose:** Bot Maker analyzes typical approval questions, provides verdict based on past decisions  
**Blocker:** Needs decisions.jsonl corpus ≥30 entries, precedent matching logic

## daily-standup

**Status:** ПЛАН in source  
**Disposition:** Not included in v0.1 (planned after routine migration, no implementation)  
**Purpose:** Daily standup from board blocked/review items → owner  
**Blocker:** Depends on routine migration from chatty bots, board.jsonl usage patterns

## grokbotceo-public-repo

**Status:** ПЛАН (docs only) in source, approved 2026-11-07  
**Disposition:** Documented in source company-structure/processes/grokbotceo-public-repo.md  
**Purpose:** Export sanitized content to public repository  
**Implementation status:** Docs only, export pipeline/mentor/upgrade-hook not implemented  
**Note:** This v0.1 release IS the foundation for this process

---

**Why ПЛАН processes not included:**
- Require implementation not yet complete
- Depend on prerequisites not present (corpus, usage patterns)
- Documented for future reference, not current capability

**User action:** These are planning artifacts. Do not enable or configure until actually implemented and verified.
