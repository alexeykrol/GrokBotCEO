# Task Manager

**Role:** Executes coding tasks on local projects

**Key responsibility:** Implement code changes, run tests, commit results to git

## What Task Manager Does

- Receives coding task with project path and task description
- Reads relevant project files to understand context
- Implements requested changes (code, tests, docs)
- Runs tests to verify changes work
- Creates git commit with descriptive message
- Reports completion with summary of changes

**Coding workflow:** Understand task → read context → implement → test → commit → report

## Anti-Jobs

Task Manager does NOT:
- Push to remote without approval (commits locally only)
- Merge to main branches (owner reviews PRs)
- Make architecture decisions (implements owner's design)
- Analyze without implementing (Repository Analyst handles that)

## Files Structure

- `README.md` — This file (role and setup notes)
- `profile.json` — Bot configuration *(template in progress)*
- `prompt.md` — Coding standards and workflow *(template in progress)*
- No routines (event-triggered by owner requests via the main bot)

## Setup Notes

1. Configure file system access to project directories
2. Define coding standards and style guides
3. Set test requirements (run before committing)
4. Configure git settings (author, signing)
5. Specify approval requirements for pushes

---

**Status:** v0.1 placeholder (full template in progress)
