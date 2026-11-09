# post-implementation-review — Post Implementation Analysis

**Owner:** Implementer  
**Trigger:** Event (receives routed post from readers)  
**Autonomy Level:** L1 (analyzes, proposes, owner decides)

## Purpose

Analyze agent/tool/workflow posts for adoption potential. Evaluate what it does, how it works, cost/benefit, propose implementation plan.

## Inputs

- Routed post from Reader (post_id, cycle_no, article_path, channel)
- Post text and linked article (if fetched)
- Current system capabilities and gaps

## Outputs

- Analysis posted to improvements channel
- Recommendation: adopt/defer/reject + reasoning
- Implementation plan if adopt recommended

## Success Criteria

- Complete analysis covering: capabilities, architecture, costs, benefits, risks, alternatives
- Clear recommendation with evidence
- Implementation plan with steps and verification

Related: Implementer bot, improvements channel workflow
