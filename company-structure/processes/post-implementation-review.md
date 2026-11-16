# post-implementation-review — Post Implementation Analysis

**Owner:** an analyst bot you make (this release does not install one)  
**Trigger:** Event (receives routed post from readers)  
**Autonomy Level:** L1 (analyzes, proposes, owner decides)

## Purpose

Analyze agent/tool/workflow posts for adoption potential. Evaluate what it does, how it works, cost/benefit, propose implementation plan.

## Inputs

- A post sent on by a reader bot or by you (link, text, linked article)
- Post text and linked article (if fetched)
- Current system capabilities and gaps

## Outputs

- Analysis sent to Bot Maker, which shows any change in #Improvements
- Recommendation: adopt/defer/reject + reasoning
- Implementation plan if adopt recommended

## Success Criteria

- Complete analysis covering: capabilities, architecture, costs, benefits, risks, alternatives
- Clear recommendation with evidence
- Implementation plan with steps and verification

Related: improvements channel workflow
