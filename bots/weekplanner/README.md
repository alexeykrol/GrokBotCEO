# Weekplanner

**Role:** Manages weekly planning and tracking

**Key responsibility:** Monday planning session, Sunday tracking review, progress monitoring

## What Weekplanner Does

**Monday morning planning:**
- Reviews previous week outcomes
- Discusses priorities for new week with owner
- Records week plan

**Sunday evening tracking:**
- Reviews week progress against plan
- Records outcomes (done/blocked/deferred)
- Prepares input for next week's planning

**Event-triggered tracking:**
- Owner reports task progress ("сделал", "застрял", "не буду")
- Bot updates week tracking state
- Identifies blockers for escalation

## Anti-Jobs

Weekplanner does NOT:
- Manage daily tasks (Reminder bot handles those)
- Track long-term projects (Projects Manager handles those)
- Make decisions about priorities (facilitates owner's planning)

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Planning and tracking workflow *(template in progress)*
- `routines.md` — Monday planning, Sunday tracking schedules *(template in progress)*

## Setup Notes

1. Adjust planning time to Monday morning preference
2. Adjust tracking review to Sunday evening preference
3. Configure data storage for week plans and outcomes
4. Define planning format (goals, tasks, success criteria)

---

**Status:** v0.1 placeholder (full template in progress)
