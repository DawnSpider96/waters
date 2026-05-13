from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "WATERS_PROMPTS_DIR"
ENV_FILE = Path.home() / ".config" / "waters" / ".env"
SYMLINK_NAME = "waters_prompts"


def load_prompts_dir() -> Path | None:
    """Resolve the configured prompts directory, or None if unconfigured.

    Looks up ``WATERS_PROMPTS_DIR`` from the process env first, then from
    ``~/.config/waters/.env``. The value must be an absolute path (relative
    paths break inside worktrees, which run from different cwds) and the
    directory must exist."""
    value = os.environ.get(ENV_VAR) or _read_env_file(ENV_FILE, ENV_VAR)
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(
            f"{ENV_VAR} must be an absolute path (got {value!r}); "
            f"relative paths are ambiguous across worktrees"
        )
    if not path.is_dir():
        raise ValueError(f"{ENV_VAR} does not exist or is not a directory: {path}")
    return path


def _read_env_file(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None
