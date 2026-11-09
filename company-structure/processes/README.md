# Processes

Autonomous recurring tasks that run on schedule (cron) or triggered by events.

## Process Structure

Each process card documents:
- **Purpose:** What this process does and why
- **Owner bot:** Which bot runs this process
- **Trigger:** Cron schedule or event description
- **Inputs:** What data it reads
- **Outputs:** What it produces (files, messages, database updates)
- **Success criteria:** How to verify it worked
- **Autonomy level:** L0 (manual) to L3 (fully autonomous)

## Core Processes

**System Management:**
- **[daily-data-sync.md](daily-data-sync.md)** — Commits data files to git, syncs with remote
- **[github-repo-mirroring.md](github-repo-mirroring.md)** — GitHub repository sync
- **[transcript-healthcheck.md](transcript-healthcheck.md)** — Bot chat health monitor
- **[routine-healthcheck.md](routine-healthcheck.md)** — Routine execution monitor
- **[monthly-process-revision.md](monthly-process-revision.md)** — Monthly process review

**Information Processing:**
- **[morning-reading.md](morning-reading.md)** — Daily filtering of X and Telegram posts
- **[post-implementation-review.md](post-implementation-review.md)** — Analyzes agent/tool posts for adoption

**Task Management:**
- **[weekly-plan.md](weekly-plan.md)** — Monday planning session
- **[weekly-plan-tracking.md](weekly-plan-tracking.md)** — Weekly progress tracking
- **[reminders-tracking.md](reminders-tracking.md)** — Daily reminder healthcheck

**Security:**
- **[cve-frog-nagging.md](cve-frog-nagging.md)** — CVE tracking and nagging

**Monitoring:**
- **[weekly-monitor-report.md](weekly-monitor-report.md)** — Weekly bot usage analysis and proposals

## ПЛАН Processes (Not Implemented)

See **[_PLAN-processes.md](_PLAN-processes.md)** for processes documented as ПЛАН (planned) in source:
- precedent-judge (requires ≥30 decisions corpus)
- daily-standup (planned after routine migration)
- grokbotceo-public-repo (docs only, this v0.1 IS the foundation)

## Autonomy Levels

- **L0 (Manual):** Bot performs on request only, no autonomy
- **L1 (Report):** Bot runs autonomously, reports results, takes no action
- **L2 (Act):** Bot runs and acts autonomously, reports outcomes
- **L3 (Silent):** Bot runs and acts autonomously, silent unless failure

Set level based on risk and reversibility of process actions.

---

**Status:** v0.1 (13 processes complete, 3 ПЛАН documented)
