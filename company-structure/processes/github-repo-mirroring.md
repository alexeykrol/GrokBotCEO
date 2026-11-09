# github-repo-mirroring — GitHub Repository Sync

**Owner:** Bot Maker  
**Trigger:** Event (changes in GitHub repo or local workspace)  
**Autonomy Level:** L2 (syncs autonomously, reports conflicts)

## Purpose

Sync local workspace with GitHub repository: fetch changes, handle conflicts, push approved commits.

## Inputs

- Local workspace: {{WORKSPACE_PATH}}
- GitHub repository: {{GITHUB_REPO_URL}}

## Outputs

- Synced local and remote state
- Conflict reports to owner (no auto-merge)

## Success Criteria

- Local changes fetched from remote
- Approved local commits pushed
- Conflicts reported, never auto-merged

Related: daily-data-sync process (integrated since example 2026-11-03)
