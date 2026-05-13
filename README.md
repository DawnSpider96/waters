# waters

Run N Claude Code agents in parallel on isolated git worktrees, all in one tmux session. Watch them work, intervene mid-task, then merge or pick.

See [PLAN.md](PLAN.md) for the full design rationale.

## Requirements

- macOS or Linux
- `tmux` on PATH
- `git` and a clean working tree
- Python ≥ 3.11 with [`uv`](https://docs.astral.sh/uv/)
- `claude` CLI (Claude Code)

## Install (source-checkout only)

The bash scripts under `scripts/` aren't packaged into the wheel, so a regular `pip install` won't work. Run from a checkout:

```bash
git clone <this-repo> ~/repos_fun/waters
cd ~/repos_fun/waters
uv sync
```

Then either invoke via uv:

```bash
uv run --project ~/repos_fun/waters waters task.md
```

or alias it in your shell:

```bash
alias waters='uv run --project ~/repos_fun/waters waters'
```

## Shared prompts directory (`WATERS_PROMPTS_DIR`)

Waters can symlink a fixed directory of yours into every worktree as `waters_prompts/`, so agents can read prompts and write planning/decision files to a single shared location without anything ever entering your repo's git history.

**Configure** an absolute path either via env var or via `~/.config/waters/.env`:

```bash
# ~/.config/waters/.env
WATERS_PROMPTS_DIR=/Users/you/watersp
```

The path **must be absolute** (relative paths break across worktrees, which run from different cwds). `~` is expanded.

**What waters does** when `WATERS_PROMPTS_DIR` is set:

1. After creating each worktree, symlinks `<worktree>/waters_prompts` → your configured directory.
2. Appends `/waters_prompts` to the repo's shared `.git/info/exclude` (idempotent), so git ignores the symlink in every worktree without you having to touch `.gitignore`.

If `WATERS_PROMPTS_DIR` is unset, this whole mechanism is skipped — waters runs as before.

### Contract for agents running inside a worktree

`waters_prompts/` inside a worktree is a real-on-disk directory (via symlink) that the agent may treat as part of the repo for **read and write** purposes:

- **Read** anything under `waters_prompts/` — prompts, prior decisions, plans, notes — as if it were a normal subtree of the repo.
- **Write** anything under `waters_prompts/` — new planning files, decision records, intermediate scratch — and trust that those writes persist to the shared central directory immediately.
- These writes will **not** appear in `git status`, **not** be part of any commit, and **not** propagate via the worktree's branch or any merge. Only changes to actual repo files become real code changes.
- Other concurrently-running waters worktrees share the same backing directory, so writes are visible across agents. Use distinct filenames (e.g. include `<{i}>` in the path) to avoid clobbering.

## Quick start

Write a prompt file `task.md`:

```
<{count=1}>
<{models=[opus, sonnet]}>
<{efforts=[max, high]}>

Refactor handler<{i}>.py to remove the global state.
```

From inside a clean git repo:

```bash
waters task.md
```

Or pass several prompt files in one run — their workers concatenate into a single sweep with global 1-indexing (`agent-1`..`agent-N`) across all files:

```bash
waters refactor.md docs.md tests.md
```

You'll see the assignment table, confirm, and land in a tmux session with one window per (model × effort × instance) combo. Switch windows with `Ctrl+B` then `1`..`N`. Detach with `Ctrl+B d` (waters keeps polling — it doesn't finalize until you exit all panes).

When the session ends, waters auto-commits any uncommitted edits in each worktree, writes a `.diff`, and asks:

- `[m]` merge — merge all non-empty branches into `waters/<run-id>/merged`
- `[p]` pick — create `waters/<run-id>/winner` from one chosen branch
- `[k]` keep — leave everything in place for inspection
- `[d]` discard — delete worktrees + temp branches

## Prompt directives

| Directive | Default | Meaning |
|---|---|---|
| `<{count=N}>` | `1` | Instances **per permutation** |
| `<{models=[a, b, ...]}>` | claude default | Models to sweep. Shortcuts (`opus`, `sonnet`, `haiku`) or full IDs (`claude-opus-4-7`). |
| `<{efforts=[a, b, ...]}>` | claude default | Effort levels: `low`, `medium`, `high`, `xhigh`, `max` |
| `<{i}>` | substituted | Worker id: `<global-index>[_<model>][_<effort>]`, e.g. `3_opus_max`. Use it in filenames you want unique across the sweep (`module<{i}>.py` → `module3_opus_max.py`). |

Each prompt file produces `count × |models| × |efforts|` workers. Multiple prompt files concatenate worker lists with global 1-indexing.

Declarations are stripped from the body; the rest is sent to claude verbatim (shell metachars in the prompt are not expanded).

## CLI

```
waters [--yolo] <prompt-file> [<prompt-file>...]
waters resume <run-id>
```

`--yolo` passes `--dangerously-skip-permissions` to every agent (run-wide; doesn't vary per permutation).

`waters resume <run-id>` re-runs the post-tmux finalize + decision phase for a previous run — see [Recovery](#recovery).

## State layout

```
~/.cache/waters/<run-id>/
  meta.json
  prompts/agent-N.md   # materialized prompts (declarations stripped, <{i}> substituted)
  agent-N/             # worktree
  diffs/agent-N.diff
  _merge/              # only present after a merge with conflicts (see below)
```

After `[d]` discard, worktrees and `waters/<run-id>/agent-*` branches are removed; `prompts/`, `diffs/`, and `meta.json` are kept for postmortem.

## Recovery

If you lose the parent `waters` process before the post-tmux finalize phase runs (terminal closed, tmux killed externally, lost ssh session, etc.), resume from the run id:

```bash
waters resume <run-id>
```

The run id is printed at launch as `Run ID: ...`. If you've lost it, `ls -t ~/.cache/waters/` lists run ids (timestamp directories) newest first.

`resume` reads `meta.json` from the cache, refuses if the original tmux session is still running, validates that worktrees and `agent-*` branches still exist, then runs the same `finalize` + `[m]/[p]/[k]/[d]` flow as a normal session end. Safe to re-run after partial progress: hand-committed worktrees aren't double-committed, diffs overwrite cleanly, and `merged` / `winner` branches refuse to clobber existing ones. Runnable from any directory — `resume` chdirs into the `base_repo` recorded in `meta.json` itself.

## Merge conflicts

Branches are merged in agent-index order. If one conflicts, that single merge is aborted and the rest still merge — cleanly-merging agents always land in the result. The `_merge` worktree is kept on partial failure (already on `<merged>`) so you can resolve manually:

```bash
cd ~/.cache/waters/<run-id>/_merge
git merge --no-ff waters/<run-id>/agent-3
# resolve, commit
```

When you're done, run `scripts/cleanup.sh <run-id>` from your repo to remove all worktrees and `agent-*` branches.

## Branches created

Per run:

- `waters/<run-id>/agent-N` — one per worker, forked from your current branch
- `waters/<run-id>/merged` — after `[m]` (kept whether or not all merges succeeded)
- `waters/<run-id>/winner` — after `[p]`

None are pushed to a remote.
