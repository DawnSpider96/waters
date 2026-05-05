#!/usr/bin/env bash
# finalize.sh — for one worktree, commit any uncommitted edits then
# write its diff vs base.
#
# Usage: finalize.sh <worktree> <agent-name> <base-branch> <diff-out-path>
#
# - `git add -A` stages everything (tracked + untracked).
# - A commit happens only if there are staged changes; if the user
#   already committed everything manually, this is a no-op.
# - Diff uses three-dot syntax so it's purely "what this agent did
#   relative to where the temp branch forked from base".

set -euo pipefail

if [[ $# -ne 4 ]]; then
    echo "usage: finalize.sh <worktree> <agent-name> <base-branch> <diff-out-path>" >&2
    exit 2
fi

worktree="$1"
agent_name="$2"
base_branch="$3"
diff_out="$4"

cd "$worktree"

git add -A

if ! git diff --cached --quiet; then
    git commit -m "waters: $agent_name final"
fi

mkdir -p "$(dirname "$diff_out")"
git diff "$base_branch"...HEAD > "$diff_out"
