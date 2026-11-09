# reading-filter — Post Relevance Criteria

Criteria for selecting posts from X and Telegram feeds. Used by Reader bots to score posts (★1-5) and select valuable content (★3+).

## Scoring Framework

**★5 — Must read**
- Directly applicable to active project or immediate need
- Novel technique with clear implementation path
- Critical announcement affecting current tools/workflows
- Actionable insight with concrete steps

**★4 — Very relevant**
- Practical value for product/business/work
- Clear how-to or case study with lessons
- Relevant tool/agent/workflow analysis
- Tactical advice from trusted source

**★3 — Relevant (selection threshold)**
- Useful technique or approach
- Interesting tool/agent worth investigating
- Industry analysis with takeaways
- Example worth studying

**★2 — Marginal**
- Interesting but not immediately applicable
- General discussion with some substance
- Author credible but content light

**★1 — Not relevant**
- Off-topic or entertainment
- Pure commentary without substance
- Promotional spam
- Already known / no new value

## Practical Relevance Filter

**Include if material shows what owner can apply in:**
- Product development (features, architecture, tools)
- Solo business (marketing, sales, operations)
- Film/media production (techniques, tools, workflows)
- Skills development (programming, design, writing)

**Exclude:**
- Author fame alone (credentials without substance)
- Long general discussions without concrete benefit
- News without actionable implications
- Reactions and hot takes without analysis

## Edge Cases

**When uncertain:**
- Default to including at ★2-3 if practical angle exists
- Forward with note explaining doubt
- Track in stats for calibration

**Article fetching:**
- ★3+ posts linking external articles → fetch full text, re-score
- ★2 posts with <200 chars + link → fetch article, may upgrade to ★3+
- Paywalled or JS-only → score teaser, note limitation

## Routing Rules

**★3+ agent/tool/workflow posts → Implementer** for analysis (with post_id, cycle_no, article_path)

**All selected posts (★3+) → Owner digest** grouped by rubrics:
- Agents & Tools
- Development Techniques  
- Business & Marketing
- Film & Media
- Other

## Customization

Adapt criteria to your interests:
1. Edit scoring definitions
2. Adjust practical relevance filter
3. Update routing rules
4. Test with sample posts
5. Refine based on digest quality

---

**Location:** Store as {{READING_FILTER_PATH}}/reading-filter.md  
**Used by:** Reader X, Reader Telegram (re-read every run for changes)  
**Related:** morning-reading process, Reader bot prompts
