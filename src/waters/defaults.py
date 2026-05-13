from __future__ import annotations

from pathlib import Path

from .directives import COUNT_RE, EFFORTS_RE, MODELS_RE

DEFAULT_COUNT_LINE = "<{count=1}>"
DEFAULT_MODELS_LINE = "<{models=[claude-opus-4-7]}>"
DEFAULT_EFFORTS_LINE = "<{efforts=[low, max]}>"


def ensure_defaults(path: Path) -> list[str]:
    """Prepend default directive lines to ``path`` for any of count/models/
    efforts not already declared. Mutates the file in place. Returns the
    list of directive names that were inserted, in insertion order."""
    text = path.read_text()

    has_count = has_models = has_efforts = False
    for line in text.splitlines():
        stripped = line.strip()
        if COUNT_RE.fullmatch(stripped):
            has_count = True
        elif MODELS_RE.fullmatch(stripped):
            has_models = True
        elif EFFORTS_RE.fullmatch(stripped):
            has_efforts = True

    prefix: list[str] = []
    inserted: list[str] = []
    if not has_count:
        prefix.append(DEFAULT_COUNT_LINE)
        inserted.append("count")
    if not has_models:
        prefix.append(DEFAULT_MODELS_LINE)
        inserted.append("models")
    if not has_efforts:
        prefix.append(DEFAULT_EFFORTS_LINE)
        inserted.append("efforts")

    if not inserted:
        return []

    separator = "" if text.startswith("\n") or not text else "\n"
    path.write_text("\n".join(prefix) + "\n" + separator + text)
    return inserted
