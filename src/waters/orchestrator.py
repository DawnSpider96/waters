from __future__ import annotations

import shlex
import subprocess
import time

from . import paths
from .directives import Worker

POLL_INTERVAL_SEC = 2.0


def session_name(run_id: str) -> str:
    return f"waters-{run_id}"


def has_session(name: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", name],
        capture_output=True,
    )
    return result.returncode == 0


def build_window_command(worker: Worker, run_id: str, yolo: bool) -> str:
    worktree = paths.worktree_dir(run_id, worker.index)
    prompt = paths.prompt_file_path(run_id, worker.index)
    parts = [f"cd {shlex.quote(str(worktree))}", "&&", "claude"]
    if worker.model is not None:
        parts.append(f"--model {shlex.quote(worker.model)}")
    if worker.effort is not None:
        parts.append(f"--effort {shlex.quote(worker.effort)}")
    if yolo:
        parts.append("--dangerously-skip-permissions")
    # Embed the prompt as a single-quoted literal. `"$(cat ...)"` would
    # let the shell expand $VAR/backticks/etc. in the prompt body before
    # claude ever sees it — violating the "sent verbatim" contract.
    parts.append(shlex.quote(prompt.read_text()))
    return " ".join(parts)


def create_session(run_id: str, workers: list[Worker], yolo: bool) -> None:
    sess = session_name(run_id)
    if has_session(sess):
        raise RuntimeError(f"tmux session already exists: {sess}")
    if not workers:
        raise ValueError("no workers to launch")

    first = workers[0]
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", sess, "-n", first.name,
         build_window_command(first, run_id, yolo)],
        check=True,
    )
    for w in workers[1:]:
        subprocess.run(
            ["tmux", "new-window", "-t", sess, "-n", w.name,
             build_window_command(w, run_id, yolo)],
            check=True,
        )


def attach_and_wait(run_id: str) -> None:
    sess = session_name(run_id)
    subprocess.run(["tmux", "attach-session", "-t", sess])
    while has_session(sess):
        time.sleep(POLL_INTERVAL_SEC)
