#!/usr/bin/env bash
# merge.sh — create waters/<run-id>/merged from base and merge agent
# branches into it sequentially. Skip conflicting branches but keep
# going so cleanly-merging branches still land in the result.
#
# Usage: merge.sh <run-id> <base-branch> <branches...>
#
# A worktree at ~/.cache/waters/<run-id>/_merge is used to perform the
# merges. On full success it is removed. On any conflict it is *kept*
# (already checked out on <merged>) so the user can cd in and retry the
# failed merges manually. Exits 1 if any branch failed; agent temp
# branches are left intact in either case.

set -euo pipefail

if [[ $# -lt 3 ]]; then
    echo "usage: merge.sh <run-id> <base-branch> <branches...>" >&2
    exit 2
fi

run_id="$1"
base_branch="$2"
shift 2
branches=("$@")

merged_branch="waters/$run_id/merged"
merge_worktree="$HOME/.cache/waters/$run_id/_merge"

if git rev-parse --verify "refs/heads/$merged_branch" >/dev/null 2>&1; then
    echo "merged branch '$merged_branch' already exists — aborting" >&2
    exit 1
fi

git worktree add -b "$merged_branch" "$merge_worktree" "$base_branch"

orig_dir="$(pwd)"
cd "$merge_worktree"

failed_branches=()
for branch in "${branches[@]}"; do
    if ! git merge --no-ff -m "waters: merge $branch" "$branch"; then
        failed_branches+=("$branch")
        git merge --abort 2>/dev/null || true
    fi
done

cd "$orig_dir"

if [[ ${#failed_branches[@]} -eq 0 ]]; then
    git worktree remove --force "$merge_worktree"
    echo "merged branch: $merged_branch"
    exit 0
fi

echo "merged branch: $merged_branch (partial — ${#failed_branches[@]} branch(es) skipped)" >&2
echo "" >&2
echo "merge worktree kept at: $merge_worktree" >&2
echo "  cd into it to retry the conflicting merges manually:" >&2
for b in "${failed_branches[@]}"; do
    echo "    git merge --no-ff $b" >&2
done
echo "" >&2
echo "agent temp branches are intact; remove the merge worktree" >&2
echo "(and the rest) with cleanup.sh when you're done." >&2
exit 1
