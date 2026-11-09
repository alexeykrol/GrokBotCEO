# daily-data-sync — Daily Data Sync to Git

**Owner:** Bot Maker  
**Trigger:** `CRON_TZ={{OWNER_TIMEZONE}} {{MINUTE}} {{HOUR}} * * *` (daily, disabled by default, suggest nighttime when enabled)  
**Autonomy Level:** L2 (acts autonomously, reports outcomes)

## Purpose

Commit data files to git repository daily, fetch remote changes, push local commits. Ensures data is backed up and synchronized without manual intervention.

## Inputs

- `{{WORKSPACE_PATH}}/data/` directory (all data files)
- `{{WORKSPACE_PATH}}/data/decisions.jsonl` (decision log)
- `{{WORKSPACE_PATH}}/data/board.jsonl` (task status)
- Other data files created by bots

## Process Flow

1. **Preflight checks:**
   - Verify WORKSPACE_PATH matches git root
   - Verify exact remote URL match (fetch and push URLs)
   - Validate GitHub host (reject non-GitHub remotes; a local bare repository is accepted only with `SYNC_ALLOW_LOCAL_REMOTE=1`)
   - **MANDATORY: Verify repository is PRIVATE** via `gh repo view --json isPrivate` (no test-mode bypass exists)
   - Check no dirty index (preexisting staged files)

2. **Fetch and conflict check:**
   - Fetch remote changes from GitHub
   - Check for foreign commits on remote → ABORT if found, no auto-merge
   - Check for local unpushed commits → ABORT if found (clean state required)

3. **File validation:**
   - Validate APPROVED_FILES list (explicit relative paths only)
   - Reject globs, path traversal (`..`, `.`, empty components), symlinks, .git paths, live database files (`*.db`, `*.sqlite*`)
   - Stage only validated files; abort if the index then contains any other path

4. **Commit and push:**
   - Create commit with UTC timestamp
   - Push to origin (never force-push), then verify the remote branch equals the new commit
   - Report silent on success, notify owner on failure

5. **All-or-nothing:** if staging, commit or push fails, the script restores local HEAD and index to their state before the run (working-tree files are never touched) and exits with an explicit `ERROR:` line. Credentials and tokens are stripped from every printed URL and git/gh message.

## Outputs

- Git commits in local repository
- Pushed commits to remote (if no conflicts)
- Report message to owner (on failure or conflict only)

## Success Criteria

- All data/ changes committed
- Commits pushed to remote (or conflict reported)
- No data loss
- Git history intact (no force-push)

## Failure Handling

**Conflict with remote:**
- Stop before pushing
- Report foreign commits to owner with summary
- Wait for owner's approval ("да" or explicit approval message)
- Do not merge automatically

**Script failure:**
- Report error details to owner
- Do not retry automatically (investigate manually)
- Escalate if script broken

## Configuration

**Environment variables (REQUIRED):**
```bash
export WORKSPACE_PATH="/path/to/repo"  # Must be git root
export APPROVED_REMOTE="git@github.com:org/repo.git"  # Exact URL
export APPROVED_FILES="data/decisions.jsonl data/board.jsonl"  # Space-separated relative paths
```

**CRITICAL SAFETY (enforced by script):**
- **GitHub only:** Non-GitHub remotes rejected (no GitLab/Bitbucket support)
- **Mandatory privacy check:** Requires `gh` CLI, verifies `isPrivate: true`, rejects public repos
- **Fail-closed:** Unknown privacy/auth failure → ABORT, no silent continue
- **Explicit file allowlist:** No globs, no path traversal, no symlinks, no .git paths
- **Normalized URL comparison:** Strips credentials for exact remote match validation
- **No force push:** Always respects remote history

**Prerequisites:**
- GitHub repository (PRIVATE visibility)
- `gh` CLI installed and authenticated (`gh auth login`)
- Clean git state (no detached HEAD, no bare repo, no dirty index)

**Schedule:** Adjust to your timezone and preferred backup time (suggest nighttime when bots least active)

**Script location:** `scripts/sync-data.sh` (included, see tests in `scripts/test-sync.py`: fully local, temp dirs and local bare repositories, non-file git transports disabled; covers the positive commit+push path and failures at each stage)

**Database files:** a live SQLite file (e.g. stats.db) is not a consistent snapshot and is refused in APPROVED_FILES.

## Related

- **Board protocol:** Syncs board.jsonl with task status changes
- **Monitor:** Tracks sync execution in weekly report
- **GitHub mirroring:** Integrated with this process since 2026-11-03 (example pattern)

---

**Customize:** Adjust schedule, add pre-commit hooks, define commit message format, add post-push notifications.
