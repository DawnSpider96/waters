#!/usr/bin/env bash
# setup.sh — create N temp branches + worktrees for a waters run.
#
# Usage: setup.sh <run-id> <base-branch> <num-agents>
#
# Run from inside the user's git repo. Branches are named
# waters/<run-id>/agent-N; worktrees live at
# ~/.cache/waters/<run-id>/agent-N.

set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "usage: setup.sh <run-id> <base-branch> <num-agents>" >&2
    exit 2
fi

run_id="$1"
base_branch="$2"
num_agents="$3"

cache_root="$HOME/.cache/waters/$run_id"
mkdir -p "$cache_root"

for ((n=1; n<=num_agents; n++)); do
    branch="waters/$run_id/agent-$n"
    worktree="$cache_root/agent-$n"
    git worktree add -b "$branch" "$worktree" "$base_branch"
done
