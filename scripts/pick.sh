#!/usr/bin/env bash
# pick.sh — create waters/<run-id>/winner pointing at a chosen branch.
#
# Usage: pick.sh <run-id> <chosen-branch>

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: pick.sh <run-id> <chosen-branch>" >&2
    exit 2
fi

run_id="$1"
chosen_branch="$2"

winner_branch="waters/$run_id/winner"

if git rev-parse --verify "refs/heads/$winner_branch" >/dev/null 2>&1; then
    echo "winner branch '$winner_branch' already exists — aborting" >&2
    exit 1
fi

git branch "$winner_branch" "$chosen_branch"
echo "winner branch: $winner_branch (from $chosen_branch)"
