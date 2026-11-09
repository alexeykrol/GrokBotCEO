#!/bin/bash
#
# sync-data.sh - FAIL-CLOSED git sync with mandatory preflight checks
# NEVER pushes to public remotes, NEVER pushes unapproved files
# Version 3: all-or-nothing commit+push with rollback, exact allowlist postcondition,
#            no test-mode bypass, optional local bare remote, credentials never printed
#
# Contract:
#   - Success: exactly one new commit containing only changed APPROVED_FILES is on
#     both the local branch and origin (verified after push), or "No changes".
#   - Failure at any step: explicit "ERROR:" message and non-zero exit; local HEAD and
#     index are back to their state before the run (working-tree files are never touched),
#     and nothing partial is published.
#
# Supported remotes:
#   - GitHub (https://github.com/... or git@github.com:...), privacy verified with `gh`.
#   - A local bare repository (absolute path or file:// URL) when SYNC_ALLOW_LOCAL_REMOTE=1
#     (local backup; also used by scripts/test-sync.py). A local path is never public.
#   Everything else is refused.
#
set -euo pipefail

# Configuration (user must set these)
WORKSPACE_PATH="${WORKSPACE_PATH:-}"
APPROVED_REMOTE="${APPROVED_REMOTE:-}"
APPROVED_FILES="${APPROVED_FILES:-data/decisions.jsonl data/board.jsonl}"
SYNC_ALLOW_LOCAL_REMOTE="${SYNC_ALLOW_LOCAL_REMOTE:-}"

# Rollback state (see on_exit)
STAGE="none"       # none | staged | committed | pushed
START_HEAD=""

# Remove credentials and tokens from anything we print
sanitize() {
    sed -E 's#(://)[^/@[:space:]]+@#\1#g; s#gh[pousr]_[A-Za-z0-9_]{10,}#[REDACTED]#g; s#github_pat_[A-Za-z0-9_]{10,}#[REDACTED]#g'
}

# Normalize URL for comparison and logging: strip credentials
normalize_url() {
    printf '%s\n' "$1" | sanitize
}

# Run a git command with its output sanitized onto stderr; returns git's exit code
git_sanitized() {
    local rc=0
    git "$@" 2>&1 | sanitize >&2 || rc=${PIPESTATUS[0]}
    return "$rc"
}

on_exit() {
    local rc=$?
    if [ "$rc" -ne 0 ] && { [ "$STAGE" = "staged" ] || [ "$STAGE" = "committed" ]; }; then
        echo "Rolling back local HEAD and index (working tree untouched)..." >&2
        if [ "$STAGE" = "committed" ]; then
            git reset -q --soft "$START_HEAD" >/dev/null 2>&1 || true
        fi
        git reset -q >/dev/null 2>&1 || true
        if [ "$(git rev-parse HEAD 2>/dev/null)" = "$START_HEAD" ] && git diff --cached --quiet 2>/dev/null; then
            echo "✓ Rolled back: HEAD and index restored" >&2
        else
            echo "ERROR: Rollback incomplete - inspect HEAD and index manually" >&2
        fi
    fi
    exit "$rc"
}
trap on_exit EXIT

is_local_remote() {
    case "$1" in
        /*|file:///*) return 0 ;;
        *) return 1 ;;
    esac
}

local_remote_path() {
    case "$1" in
        file://*) printf '%s\n' "${1#file://}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

# Preflight check function
preflight_check() {
    echo "=== PREFLIGHT CHECK ===" >&2

    if [ -n "${SYNC_TEST_MODE:-}" ]; then
        echo "ERROR: SYNC_TEST_MODE is not supported (it skipped privacy, fetch and push checks)" >&2
        echo "  Tests use a local bare remote with SYNC_ALLOW_LOCAL_REMOTE=1 instead" >&2
        exit 1
    fi

    # 1. Check workspace path configured AND is actual git root
    if [ -z "$WORKSPACE_PATH" ]; then
        echo "ERROR: WORKSPACE_PATH not configured" >&2
        exit 1
    fi

    if [ ! -d "$WORKSPACE_PATH" ]; then
        echo "ERROR: WORKSPACE_PATH does not exist: $WORKSPACE_PATH" >&2
        exit 1
    fi

    # 2. Verify we're in git repo
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        echo "ERROR: Not in git repository" >&2
        exit 1
    fi

    # Check we're in workspace root (not subdir); compare physical paths (symlinked tmp dirs)
    GIT_ROOT=$(cd "$(git rev-parse --show-toplevel)" && pwd -P)
    CURRENT_DIR=$(pwd -P)
    WORKSPACE_REAL=$(cd "$WORKSPACE_PATH" && pwd -P)
    if [ "$CURRENT_DIR" != "$GIT_ROOT" ]; then
        echo "ERROR: Must run from git root: $GIT_ROOT" >&2
        echo "  Current directory: $CURRENT_DIR" >&2
        exit 1
    fi

    if [ "$GIT_ROOT" != "$WORKSPACE_REAL" ]; then
        echo "ERROR: Git root does not match WORKSPACE_PATH" >&2
        echo "  WORKSPACE_PATH: $WORKSPACE_REAL" >&2
        echo "  Git root:       $GIT_ROOT" >&2
        exit 1
    fi

    # Check not detached HEAD
    if ! git symbolic-ref HEAD >/dev/null 2>&1; then
        echo "ERROR: Detached HEAD state - checkout a branch first" >&2
        exit 1
    fi

    # Check not bare repo
    if git rev-parse --is-bare-repository 2>/dev/null | grep -q true; then
        echo "ERROR: Bare repository - clone a working copy" >&2
        exit 1
    fi

    # 3. Check approved remote configured
    if [ -z "$APPROVED_REMOTE" ]; then
        echo "ERROR: APPROVED_REMOTE not configured (must be exact git remote URL)" >&2
        exit 1
    fi

    # 4. Get actual FETCH and PUSH remote URLs (ALL of them, not just first)
    ACTUAL_FETCH=$(git remote get-url origin 2>/dev/null || echo "")

    if [ -z "$ACTUAL_FETCH" ]; then
        echo "ERROR: No 'origin' remote configured" >&2
        exit 1
    fi

    # Get ALL push URLs (git can have multiple push destinations)
    ACTUAL_PUSH_URLS=$(git remote get-url --push --all origin 2>/dev/null || echo "")
    if [ -z "$ACTUAL_PUSH_URLS" ]; then
        echo "ERROR: No push URL configured for origin" >&2
        exit 1
    fi
    PUSH_URL_COUNT=$(printf '%s\n' "$ACTUAL_PUSH_URLS" | grep -c '^')

    # Reject multiple push destinations (ambiguous, potential leak)
    if [ "$PUSH_URL_COUNT" -gt 1 ]; then
        echo "ERROR: Multiple push URLs not allowed (potential unvalidated destination leak)" >&2
        echo "  Found $PUSH_URL_COUNT push URLs:" >&2
        printf '%s\n' "$ACTUAL_PUSH_URLS" | while read -r url; do
            echo "    $(normalize_url "$url")"
        done >&2
        echo "  Configure single approved remote only" >&2
        exit 1
    fi

    ACTUAL_PUSH="$ACTUAL_PUSH_URLS"

    NORMALIZED_APPROVED=$(normalize_url "$APPROVED_REMOTE")
    NORMALIZED_FETCH=$(normalize_url "$ACTUAL_FETCH")
    NORMALIZED_PUSH=$(normalize_url "$ACTUAL_PUSH")

    # 5. Verify normalized remote match for BOTH fetch and push
    if [ "$NORMALIZED_FETCH" != "$NORMALIZED_APPROVED" ]; then
        echo "ERROR: Fetch remote mismatch" >&2
        echo "  Approved: $NORMALIZED_APPROVED" >&2
        echo "  Actual:   $NORMALIZED_FETCH" >&2
        exit 1
    fi

    if [ "$NORMALIZED_PUSH" != "$NORMALIZED_APPROVED" ]; then
        echo "ERROR: Push remote mismatch" >&2
        echo "  Approved: $NORMALIZED_APPROVED" >&2
        echo "  Actual:   $NORMALIZED_PUSH" >&2
        exit 1
    fi

    # 6. Classify remote: exact GitHub host, or opted-in local bare repo
    if printf '%s\n' "$NORMALIZED_FETCH" | grep -Eq '^(https://|git@)github\.com[:/]'; then
        REMOTE_KIND=github
    elif [ "$SYNC_ALLOW_LOCAL_REMOTE" = "1" ] && is_local_remote "$ACTUAL_FETCH"; then
        REMOTE_KIND=local
    else
        echo "ERROR: Non-GitHub remote - cannot verify privacy" >&2
        echo "  Remote: $NORMALIZED_FETCH" >&2
        echo "  This script only supports GitHub remotes with 'gh' CLI verification" >&2
        echo "  (or a local bare repository with SYNC_ALLOW_LOCAL_REMOTE=1)" >&2
        exit 1
    fi

    # 7. MANDATORY: Verify repository is PRIVATE (before accessing)
    if [ "$REMOTE_KIND" = "github" ]; then
        if ! command -v gh >/dev/null 2>&1; then
            echo "ERROR: GitHub remote requires 'gh' CLI to verify privacy" >&2
            echo "  Install: https://cli.github.com/" >&2
            exit 1
        fi

        REPO_NAME=$(printf '%s\n' "$NORMALIZED_FETCH" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
        if ! printf '%s\n' "$REPO_NAME" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'; then
            echo "ERROR: Cannot parse GitHub repository name from remote" >&2
            exit 1
        fi

        if ! VISIBILITY=$(gh repo view "$REPO_NAME" --json isPrivate -q .isPrivate 2>&1); then
            echo "ERROR: Cannot verify repository privacy via gh CLI" >&2
            echo "  Repository: $REPO_NAME" >&2
            echo "  gh output: $(printf '%s\n' "$VISIBILITY" | head -3 | sanitize)" >&2
            exit 1
        fi

        if [ "$VISIBILITY" = "false" ]; then
            echo "ERROR: Repository is PUBLIC - refusing to push data" >&2
            echo "  Repository: $REPO_NAME" >&2
            exit 1
        elif [ "$VISIBILITY" = "true" ]; then
            echo "✓ Repository visibility: PRIVATE" >&2
        else
            echo "ERROR: Unexpected privacy value: $(printf '%s\n' "$VISIBILITY" | head -1 | sanitize)" >&2
            exit 1
        fi
    else
        LOCAL_PATH=$(local_remote_path "$ACTUAL_FETCH")
        if [ ! -d "$LOCAL_PATH" ] || \
           [ "$(git --git-dir="$LOCAL_PATH" rev-parse --is-bare-repository 2>/dev/null || echo false)" != "true" ]; then
            echo "ERROR: Local remote is not a bare git repository: $LOCAL_PATH" >&2
            exit 1
        fi
        echo "✓ Local bare remote (not public by construction)" >&2
    fi

    # 8. Check if remote is accessible
    if ! git ls-remote origin HEAD >/dev/null 2>&1; then
        echo "ERROR: Cannot access remote (check credentials)" >&2
        exit 1
    fi

    # 9. Check for dirty index (preexisting staged files)
    if ! git diff --cached --quiet; then
        echo "ERROR: Index has preexisting staged files" >&2
        echo "  Unstage them first: git reset HEAD" >&2
        git diff --cached --name-only >&2
        exit 1
    fi

    echo "✓ Preflight checks passed" >&2
}

# Validate approved files: explicit relative paths only, no globs/traversal/symlinks/DBs
validate_approved_files() {
    echo "Validating approved files..." >&2
    VALIDATED_FILES=""

    set -f  # no glob expansion while splitting
    local OLD_IFS="$IFS"
    IFS=' '
    for FILE_PATTERN in $APPROVED_FILES; do
        IFS="$OLD_IFS"
        if printf '%s\n' "$FILE_PATTERN" | grep -q '[*?[]'; then
            echo "ERROR: Glob patterns not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
            exit 1
        fi

        if printf '%s\n' "$FILE_PATTERN" | grep -q '^/'; then
            echo "ERROR: Absolute paths not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
            exit 1
        fi

        # Every path component must be a plain name: no '', '.', '..'
        case "/$FILE_PATTERN/" in
            */./*|*/../*|*//*)
                echo "ERROR: Path traversal not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
                exit 1
                ;;
        esac

        if printf '%s\n' "$FILE_PATTERN" | grep -Eq '^\.git/|/\.git/|^\.git$|/\.git$'; then
            echo "ERROR: .git paths not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
            exit 1
        fi

        # Live database files cannot be committed consistently by copying them
        if printf '%s\n' "$FILE_PATTERN" | grep -Eiq '\.(db|sqlite|sqlite3)(-wal|-shm|-journal)?$'; then
            echo "ERROR: Database files not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
            echo "  A live SQLite file is not a consistent snapshot; export a snapshot file instead" >&2
            exit 1
        fi

        if [ ! -e "$FILE_PATTERN" ] && [ ! -L "$FILE_PATTERN" ]; then
            echo "  Skipped (not found): $FILE_PATTERN" >&2
            continue
        fi

        if [ -L "$FILE_PATTERN" ]; then
            echo "ERROR: Symlinks not allowed in APPROVED_FILES: $FILE_PATTERN" >&2
            exit 1
        fi

        if [ ! -f "$FILE_PATTERN" ]; then
            echo "ERROR: Not a regular file: $FILE_PATTERN" >&2
            exit 1
        fi

        VALIDATED_FILES="$VALIDATED_FILES $FILE_PATTERN"
    done
    IFS="$OLD_IFS"
    set +f
}

# Main sync function
sync_data() {
    preflight_check

    CURRENT_BRANCH=$(git branch --show-current)
    if [ -z "$CURRENT_BRANCH" ]; then
        echo "ERROR: Cannot determine current branch" >&2
        exit 1
    fi
    START_HEAD=$(git rev-parse HEAD)

    # Config errors first, before touching the remote
    validate_approved_files

    echo "Fetching from origin..." >&2
    if ! git_sanitized fetch --quiet origin "refs/heads/$CURRENT_BRANCH:refs/remotes/origin/$CURRENT_BRANCH"; then
        echo "ERROR: Failed to fetch from remote" >&2
        exit 1
    fi

    if ! REMOTE_HEAD=$(git rev-parse --verify --quiet "refs/remotes/origin/$CURRENT_BRANCH"); then
        echo "ERROR: Remote branch origin/$CURRENT_BRANCH not found" >&2
        echo "  Push branch first: git push -u origin $CURRENT_BRANCH" >&2
        exit 1
    fi

    if [ "$START_HEAD" != "$REMOTE_HEAD" ]; then
        if ! BEHIND_COUNT=$(git rev-list --count "HEAD..refs/remotes/origin/$CURRENT_BRANCH" 2>&1); then
            echo "ERROR: Failed to check remote commits (git rev-list failed)" >&2
            exit 1
        fi
        if [ "$BEHIND_COUNT" -gt 0 ]; then
            echo "ERROR: Foreign commits detected on remote ($BEHIND_COUNT commits)" >&2
            echo "  Review remote changes and merge/rebase manually" >&2
            exit 1
        fi
        if ! AHEAD_COUNT=$(git rev-list --count "refs/remotes/origin/$CURRENT_BRANCH..HEAD" 2>&1); then
            echo "ERROR: Failed to check local commits (git rev-list failed)" >&2
            exit 1
        fi
        if [ "$AHEAD_COUNT" -gt 0 ]; then
            echo "ERROR: Local unpushed commits detected ($AHEAD_COUNT commits)" >&2
            echo "  Push or reset them before running sync" >&2
            git log --oneline "refs/remotes/origin/$CURRENT_BRANCH..HEAD" >&2
            exit 1
        fi
    fi
    echo "✓ No foreign or unpushed commits" >&2

    if [ -z "$VALIDATED_FILES" ]; then
        echo "No files to sync" >&2
        return 0
    fi

    # Stage ONLY validated files using literal pathspec (no glob expansion)
    echo "Staging approved files..." >&2
    STAGE="staged"
    set -f
    for FILE in $VALIDATED_FILES; do
        git --literal-pathspecs add -- "$FILE"
        echo "  Staged: $FILE" >&2
    done
    set +f

    # Postcondition: the index differs from HEAD only in allowlisted paths
    STAGED_LIST=$(git -c core.quotepath=off diff --cached --name-only)
    if [ -n "$STAGED_LIST" ]; then
        while IFS= read -r staged; do
            case " $VALIDATED_FILES " in
                *" $staged "*) ;;
                *)
                    echo "ERROR: Staged path outside allowlist: $staged" >&2
                    exit 1
                    ;;
            esac
        done <<EOF
$STAGED_LIST
EOF
    fi

    if git diff --cached --quiet; then
        STAGE="none"
        echo "No changes to commit" >&2
        return 0
    fi

    TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
    if ! git commit -q -m "Data sync: $TIMESTAMP" >&2; then
        echo "ERROR: Commit failed" >&2
        exit 1
    fi
    STAGE="committed"
    echo "✓ Committed approved files:" >&2
    git diff-tree --no-commit-id --name-only -r HEAD | sed 's#^#    #' >&2

    # Push (NEVER force push, explicit remote and branch)
    echo "Pushing to origin/$CURRENT_BRANCH..." >&2
    if ! git_sanitized push --quiet origin "refs/heads/$CURRENT_BRANCH:refs/heads/$CURRENT_BRANCH"; then
        echo "ERROR: Push failed" >&2
        exit 1
    fi

    # Verify the remote now points at our commit
    LOCAL_HEAD=$(git rev-parse HEAD)
    PUSHED_HEAD=$(git ls-remote origin "refs/heads/$CURRENT_BRANCH" 2>/dev/null | cut -f1)
    if [ "$PUSHED_HEAD" != "$LOCAL_HEAD" ]; then
        echo "ERROR: Remote branch does not match local commit after push" >&2
        exit 1
    fi
    STAGE="pushed"
    echo "✓ Pushed and verified origin/$CURRENT_BRANCH" >&2
}

# Run sync
sync_data
