# Reminder

**Role:** Handles one-off tasks and CVE tracking

**Key responsibility:** Capture one-off tasks, remind at right time, track CVE notifications

## What Reminder Does

**One-off task management:**
- Owner reports one-off task to do
- Bot captures task with context and deadline
- Reminds owner at scheduled time or on request
- Tracks completion

**CVE tracking:**
- Monitors CVE notifications for relevant packages
- Nags owner at intervals until addressed
- Records resolution

**Daily healthcheck:**
- Morning reminder of tasks due today
- Does not nag about future tasks

## Anti-Jobs

Reminder does NOT:
- Own recurring processes (specialized bots handle those)
- Manage weekly planning (Weekplanner handles that)
- Track project milestones (Projects Manager handles that)
- Make decisions about task priorities

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Task capture and reminder workflow *(template in progress)*
- `routines.md` — Daily reminder healthcheck, CVE nagging *(template in progress)*

## Setup Notes

1. Configure daily reminder time (morning healthcheck)
2. Set CVE monitoring sources and packages
3. Define nagging interval for CVEs
4. Configure task storage location

---

**Status:** v0.1 placeholder (full template in progress)
