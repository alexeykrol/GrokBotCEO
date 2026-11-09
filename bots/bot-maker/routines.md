- **daily-data-sync-to-repo:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *`, disabled by default. Runs scripts/sync-data.sh, commits data/, fetches origin; foreign commits on GitHub → report to owner and wait for approval (no auto-merge); otherwise pushes, no force-push; silent unless it fails.

- **transcript-healthcheck:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1-5`, paused by default. Monitors bot chat transcript health.

- **routine-healthcheck:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * 1`, paused by default. Verifies scheduled tasks run correctly.

**Autonomy levels:** daily-data-sync-to-repo — L2 (acts autonomously); healthchecks — L1 (reports only). Ladder L0–L3 defined in main README.

**Setup:**
1. Replace `{{OWNER_TIMEZONE}}` with your actual timezone (e.g., `America/Los_Angeles`)
2. Replace `{{HOUR}}` and `{{MINUTE}}` with your preferred schedule times
3. Adjust cron expressions to fit your workflow
4. Test routines manually before enabling automation
5. Keep healthchecks paused until you have multiple bots running
