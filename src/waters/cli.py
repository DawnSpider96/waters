from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from . import directives, orchestrator, paths


def main() -> None:
    try:
        argv = sys.argv[1:]
        if argv and argv[0] == "resume":
            _resume_cli(argv[1:])
        else:
            _run(argv)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        print(f"\ncommand failed (exit {e.returncode}): {' '.join(map(str, e.cmd))}",
              file=sys.stderr)
        sys.exit(e.returncode)


def _run(argv: list[str]) -> None:
    args = _parse_args(argv)
    _check_tmux()
    _check_git_repo()
    _check_clean_tree()

    base_branch = _current_branch()
    base_repo = str(Path.cwd().resolve())

    configs = []
    for p in args.prompt_files:
        path = Path(p).resolve()
        if not path.exists():
            _die(f"prompt file not found: {p}")
        try:
            configs.append(directives.parse_prompt_file(path))
        except ValueError as e:
            _die(f"error parsing {p}: {e}")

    workers = directives.expand_workers(configs)
    if not workers:
        _die("no workers to run")

    run_id = paths.new_run_id()
    paths.run_dir(run_id).mkdir(parents=True, exist_ok=True)
    directives.materialize_prompts(workers, configs, paths.prompts_dir(run_id))

    _print_confirmation(run_id, base_branch, args.yolo, workers)
    if not _ask_yes_no("Proceed?", default=False):
        print("aborted.")
        shutil.rmtree(paths.run_dir(run_id), ignore_errors=True)
        return

    _write_meta(run_id, base_branch, base_repo, args.yolo, workers)

    print(f"\nCreating {len(workers)} worktree(s)...")
    subprocess.run(
        [str(paths.script_path("setup.sh")), run_id, base_branch, str(len(workers))],
        check=True,
    )

    sess = orchestrator.session_name(run_id)
    print(f"\nLaunching tmux session: {sess}")
    print(f"  Detach: Ctrl+B then d (waters keeps polling, doesn't finalize)")
    print(f"  Finalize: exit all panes (/exit or Ctrl+D), or `tmux kill-session -t {sess}`")
    print(f"  Recover: if you lose the parent process, run `waters resume {run_id}`")
    print()
    orchestrator.create_session(run_id, workers, args.yolo)
    orchestrator.attach_and_wait(run_id)

    print("\nSession ended.")
    _finalize_run(run_id, base_branch, workers)
    _decide_phase(run_id, base_branch, workers)


def _resume_cli(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="waters resume",
        description="Finalize a previous run that didn't reach the post-tmux phase.",
    )
    parser.add_argument(
        "run_id",
        help="run id (timestamp directory under ~/.cache/waters/)",
    )
    args = parser.parse_args(argv)
    _resume(args.run_id)


def _resume(run_id: str) -> None:
    _check_tmux()

    meta = _load_meta(run_id)
    base_repo = Path(meta["base_repo"])
    base_branch = meta["base_branch"]

    if not base_repo.exists():
        _die(f"base_repo from meta.json not found: {base_repo}")

    sess = orchestrator.session_name(run_id)
    if orchestrator.has_session(sess):
        _die(
            f"tmux session {sess} is still running; finish or kill it before resuming\n"
            f"  tmux kill-session -t {sess}"
        )

    # All git/script invocations expect to run inside base_repo. chdir
    # once rather than threading cwd= through every subprocess call.
    os.chdir(base_repo)
    _check_git_repo()

    if not _branch_exists(base_branch):
        _die(f"base branch {base_branch!r} not found in {base_repo}")

    workers = _workers_from_meta(meta)
    if not workers:
        _die("meta.json contains no agents")

    _validate_resume_state(run_id, workers)

    _print_resume_summary(run_id, base_repo, base_branch, workers)

    if not _ask_yes_no("Finalize and proceed to decision phase?", default=True):
        print("aborted.")
        return

    _finalize_run(run_id, base_branch, workers)
    _decide_phase(run_id, base_branch, workers)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="waters",
        description="Run multiple Claude Code agents in parallel via tmux on isolated git worktrees.",
    )
    parser.add_argument("prompt_files", nargs="+", metavar="PROMPT_FILE",
                        help="path to a prompt file (may be specified multiple times)")
    parser.add_argument("--yolo", action="store_true",
                        help="pass --dangerously-skip-permissions to every agent")
    return parser.parse_args(argv)


def _check_tmux() -> None:
    if shutil.which("tmux") is None:
        _die("tmux not found on PATH; install tmux to use waters")


def _check_git_repo() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _die("not inside a git repo")


def _check_clean_tree() -> None:
    result = subprocess.run(["git", "diff", "--quiet", "HEAD"], capture_output=True)
    if result.returncode != 0:
        _die("working tree has uncommitted changes to tracked files; commit or stash first")


def _current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    branch = result.stdout.strip()
    if branch == "HEAD":
        _die("currently in detached HEAD state; check out a branch first")
    return branch


def _branch_exists(branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
    )
    return result.returncode == 0


def _print_confirmation(run_id: str, base_branch: str, yolo: bool, workers) -> None:
    print(f"Base branch: {base_branch}")
    print(f"Run ID:      {run_id}")
    print(f"Workers:     {len(workers)} total")
    print(f"YOLO:        {'yes (--dangerously-skip-permissions)' if yolo else 'no'}")
    print()
    for w in workers:
        model = w.model if w.model is not None else "default"
        effort = w.effort if w.effort is not None else "default"
        print(f"  {w.name}: {w.prompt_path.name} | {model} | {effort} | instance {w.instance} | <{{i}}>={w.i_value}")
    print()


def _ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _write_meta(run_id, base_branch, base_repo, yolo, workers) -> None:
    meta = {
        "run_id": run_id,
        "base_branch": base_branch,
        "base_repo": base_repo,
        "started_at": datetime.now().isoformat(),
        "yolo": yolo,
        "agents": [
            {
                "name": w.name,
                "index": w.index,
                "prompt_file": str(w.prompt_path),
                "model": w.model,
                "effort": w.effort,
                "instance": w.instance,
                "i_value": w.i_value,
                "branch": f"waters/{run_id}/{w.name}",
                "worktree": str(paths.worktree_dir(run_id, w.index)),
                "materialized_prompt": str(paths.prompt_file_path(run_id, w.index)),
            }
            for w in workers
        ],
    }
    paths.meta_file_path(run_id).write_text(json.dumps(meta, indent=2))


def _load_meta(run_id: str) -> dict:
    path = paths.meta_file_path(run_id)
    if not path.exists():
        _die(f"meta.json not found: {path}")
    try:
        meta = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _die(f"meta.json is invalid JSON: {e}")
    for key in ("base_repo", "base_branch", "agents"):
        if key not in meta:
            _die(f"meta.json missing required field: {key!r}")
    return meta


def _workers_from_meta(meta: dict) -> list[directives.Worker]:
    workers: list[directives.Worker] = []
    for entry in meta["agents"]:
        try:
            workers.append(directives.Worker(
                index=entry["index"],
                prompt_path=Path(entry["prompt_file"]),
                model=entry["model"],
                effort=entry["effort"],
                instance=entry["instance"],
                i_value=entry["i_value"],
            ))
        except KeyError as e:
            _die(f"meta.json agent entry missing field: {e}")
    workers.sort(key=lambda w: w.index)
    return workers


def _validate_resume_state(run_id: str, workers) -> None:
    problems: list[str] = []
    for w in workers:
        wt = paths.worktree_dir(run_id, w.index)
        if not wt.exists():
            problems.append(f"worktree missing: {wt}")
        branch = f"waters/{run_id}/{w.name}"
        if not _branch_exists(branch):
            problems.append(f"branch missing: {branch}")
    if problems:
        _die("cannot resume:\n  " + "\n  ".join(problems))


def _print_resume_summary(run_id: str, base_repo: Path, base_branch: str, workers) -> None:
    print(f"Resuming run {run_id}")
    print(f"  Base repo:   {base_repo}")
    print(f"  Base branch: {base_branch}")
    print(f"  Agents:      {len(workers)}")
    print()
    for w in workers:
        wt = paths.worktree_dir(run_id, w.index)
        status_lines = _git_status_short(wt)
        marker = f"({len(status_lines)} uncommitted)" if status_lines else "(clean)"
        model = w.model if w.model is not None else "default"
        effort = w.effort if w.effort is not None else "default"
        print(f"  {w.name}: {model} | {effort} | {marker}")
    print()


def _git_status_short(worktree: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(worktree), "status", "--short"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _finalize_run(run_id: str, base_branch: str, workers) -> None:
    print("\nFinalizing each worktree...")
    paths.diffs_dir(run_id).mkdir(parents=True, exist_ok=True)
    for w in workers:
        subprocess.run(
            [str(paths.script_path("finalize.sh")),
             str(paths.worktree_dir(run_id, w.index)),
             w.name,
             base_branch,
             str(paths.diff_file_path(run_id, w.index))],
            check=True,
        )


def _decide_phase(run_id: str, base_branch: str, workers) -> None:
    print(f"\nRun {run_id} complete:")
    summary = []
    for w in workers:
        diff_path = paths.diff_file_path(run_id, w.index)
        line_count = _diff_line_count(diff_path)
        summary.append((w, line_count))
        model = w.model if w.model is not None else "default"
        effort = w.effort if w.effort is not None else "default"
        empty_flag = " (empty)" if line_count == 0 else ""
        print(f"  {w.name}: {model} + {effort} | {line_count} diff lines | {diff_path}{empty_flag}")

    print(f"\nDiffs: {paths.diffs_dir(run_id)}")
    print()

    while True:
        print("What now?")
        print("  [m] merge all non-empty agents into a new branch")
        print("  [p] pick one and create a branch from it")
        print("  [k] keep everything as-is for manual inspection")
        print("  [d] discard (delete worktrees + temp branches)")
        choice = input("> ").strip().lower()

        if choice == "m":
            non_empty = [w for w, lc in summary if lc > 0]
            if _do_merge(run_id, base_branch, non_empty):
                _maybe_cleanup(run_id)
            else:
                print(
                    f"\nKeeping worktrees + branches so you can retry the "
                    f"failed merges. Run cleanup when done:\n"
                    f"  {paths.script_path('cleanup.sh')} {run_id}"
                )
            return
        if choice == "p":
            _do_pick(run_id, workers)
            _maybe_cleanup(run_id)
            return
        if choice == "k":
            print(f"\nKept. Worktrees + branches preserved at:")
            print(f"  {paths.run_dir(run_id)}")
            return
        if choice == "d":
            _do_cleanup(run_id)
            print("\nDiscarded. Diffs and meta.json kept at:")
            print(f"  {paths.run_dir(run_id)}")
            return
        print("invalid choice; pick one of m/p/k/d")


def _diff_line_count(diff_path: Path) -> int:
    if not diff_path.exists():
        return 0
    text = diff_path.read_text()
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _do_merge(run_id: str, base_branch: str, non_empty_workers) -> bool:
    """Run merge.sh. Returns True on full success, False if any branch
    failed to merge cleanly. Unlike pick.sh / cleanup.sh, merge.sh is
    invoked without check=True: a conflict is user-actionable state, not
    a script bug, and we want to fall through to the retry flow rather
    than crash."""
    if not non_empty_workers:
        print("\nNo non-empty agents to merge.")
        return True
    branches = [f"waters/{run_id}/{w.name}" for w in non_empty_workers]
    print(f"\nMerging {len(branches)} branch(es) into waters/{run_id}/merged...")
    result = subprocess.run(
        [str(paths.script_path("merge.sh")), run_id, base_branch, *branches],
    )
    return result.returncode == 0


def _do_pick(run_id: str, workers) -> None:
    valid = {w.index for w in workers}
    while True:
        choice = input(f"agent number (1-{len(workers)}): ").strip()
        try:
            idx = int(choice)
        except ValueError:
            print("not a number")
            continue
        if idx not in valid:
            print("no such agent")
            continue
        match = next(w for w in workers if w.index == idx)
        branch = f"waters/{run_id}/{match.name}"
        subprocess.run(
            [str(paths.script_path("pick.sh")), run_id, branch],
            check=True,
        )
        return


def _maybe_cleanup(run_id: str) -> None:
    if _ask_yes_no("Clean up worktrees and temp branches?", default=True):
        _do_cleanup(run_id)


def _do_cleanup(run_id: str) -> None:
    subprocess.run(
        [str(paths.script_path("cleanup.sh")), run_id],
        check=True,
    )


def _die(msg: str) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
