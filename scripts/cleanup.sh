#!/usr/bin/env bash
# cleanup.sh — remove worktrees and delete agent temp branches for a run.
#
# Usage: cleanup.sh <run-id>
#
# Keeps the run's cache directory (prompts/, diffs/, meta.json) for
# postmortem. Only worktrees and waters/<run-id>/agent-* branches are
# removed. waters/<run-id>/merged and waters/<run-id>/winner branches
# (if they exist) are preserved.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: cleanup.sh <run-id>" >&2
    exit 2
fi

run_id="$1"
cache_root="$HOME/.cache/waters/$run_id"

if [[ -d "$cache_root" ]]; then
    for wt in "$cache_root"/agent-* "$cache_root/_merge"; do
        [[ -d "$wt" ]] || continue
        git worktree remove --force "$wt" 2>/dev/null || true
    done
fi

git worktree prune

while IFS= read -r branch; do
    [[ -n "$branch" ]] || continue
    git branch -D "$branch" 2>/dev/null || true
done < <(git branch --list "waters/$run_id/agent-*" --format='%(refname:short)')
