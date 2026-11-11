# How Bots Work

## What is a Bot?

A bot is an AI agent with one specific job: a prompt, profile, settings, and optionally routines (scheduled tasks).

## Key Principle: One Bot = One Job

Each bot has a focused role. When the system owner (you) needs something done, it goes to the specialized bot:
- News and posts → Readers
- One-off tasks → Reminder bot  
- Bot/routine changes → Bot Maker
- Coding tasks with local folder → Task Manager

## Bot Structure

Each bot folder contains:
- `prompt.md` — Core instructions and anti-jobs
- `profile.json` — Name and metadata, avatar (the persona lives only in `prompt.md`)
- `settings.json` — Configuration flags
- `routines.md` (optional) — Scheduled tasks this bot runs

## How Bots Communicate

**Via SendToAgent:** One bot can send work to another bot with a message and context.

**Via shared data:** Readers write to stats.db, Monitor reads from it.

**Via channels:** the core installs the #Improvements channel (you, your main bot and Bot Maker; at most 6 bots fit in a channel). Any bot that hears a request to change something for good sends it straight to Bot Maker; Bot Maker clarifies it there, shows each change as WHAT / WHERE / WHY and applies it only after your own yes.

## Anti-Jobs

Each bot prompt lists "anti-jobs" — things it specifically does NOT do. This prevents role overlap and keeps bots focused.

Example: your main bot never owns routines or tracks recurring processes; specialized bots handle that.

## Routines vs Bots

**Routine:** A saved prompt + cron schedule or event trigger, running on a bot.

**Why not put all routines on one bot?** Routines on a chatty bot re-read long transcripts on every run (75-88% of tokens). Routines live on bots where the chat is only their reports.

## Creating New Bots

When you need a new bot, check the test:
- Does it need **own routines, own access credentials, or own channel?**  
  → Yes = new bot  
  → No = skill or function in existing bot

Bot Maker creates new bots after your approval, and adds the standard routing block to each of them, so every bot passes lasting changes on to Bot Maker.

---

**Related:**
- [processes.md](processes.md) — How bots participate in processes
- [protocols.md](protocols.md) — Rules bots follow *(in progress)*
