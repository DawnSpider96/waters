from __future__ import annotations

from datetime import datetime
from pathlib import Path

CACHE_ROOT = Path.home() / ".cache" / "waters"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def run_dir(run_id: str) -> Path:
    return CACHE_ROOT / run_id


def prompts_dir(run_id: str) -> Path:
    return run_dir(run_id) / "prompts"


def diffs_dir(run_id: str) -> Path:
    return run_dir(run_id) / "diffs"


def worktree_dir(run_id: str, agent_index: int) -> Path:
    return run_dir(run_id) / f"agent-{agent_index}"


def prompt_file_path(run_id: str, agent_index: int) -> Path:
    return prompts_dir(run_id) / f"agent-{agent_index}.md"


def diff_file_path(run_id: str, agent_index: int) -> Path:
    return diffs_dir(run_id) / f"agent-{agent_index}.diff"


def meta_file_path(run_id: str) -> Path:
    return run_dir(run_id) / "meta.json"


def script_path(name: str) -> Path:
    p = SCRIPTS_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"script not found: {p}")
    return p
