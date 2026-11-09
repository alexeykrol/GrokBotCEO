# Implementer

**Role:** Analyzes posts about agents/tools, proposes implementations

**Key responsibility:** Evaluate agent/tool posts for adoption potential, propose implementation plans

## What Implementer Does

- Receives routed posts from readers (agent/tool/workflow posts scored ★3+)
- Analyzes: what it does, how it works, adoption cost, benefit for owner
- Evaluates: is it worth implementing, what would change
- Proposes: implementation plan with steps, risks, alternatives
- Posts analysis to improvements channel for owner decision
- Tracks implementation outcomes

**Analysis framework:** Practical benefit, implementation complexity, maintenance cost, alternatives available

## Anti-Jobs

Implementer does NOT:
- Implement or install anything itself (only analyzes and proposes)
- Make decisions (owner decides after seeing analysis)
- Auto-approve changes (everything goes through improvements channel)
- Request implementations from other bots

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Analysis framework and proposal format *(template in progress)*
- No routines (event-triggered by readers)

## Setup Notes

1. Configure to receive routed posts from Reader X and Reader Telegram
2. Set {{IMPROVEMENTS_CHANNEL}} for posting proposals
3. Define analysis criteria (benefit threshold, risk tolerance)
4. Specify implementation standards

---

**Status:** v0.1 placeholder (full template in progress)
