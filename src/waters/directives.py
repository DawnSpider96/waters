from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")

COUNT_RE = re.compile(r"<\{count=(\d+)\}>")
MODELS_RE = re.compile(r"<\{models=\[([^\]]*)\]\}>")
EFFORTS_RE = re.compile(r"<\{efforts=\[([^\]]*)\]\}>")
I_RE = re.compile(r"<\{i\}>")


@dataclass(frozen=True)
class PromptConfig:
    path: Path
    count: int
    models: tuple[str | None, ...]
    efforts: tuple[str | None, ...]
    body: str

    @property
    def num_workers(self) -> int:
        return self.count * len(self.models) * len(self.efforts)


@dataclass(frozen=True)
class Worker:
    index: int
    prompt_path: Path
    model: str | None
    effort: str | None
    instance: int
    i_value: str

    @property
    def name(self) -> str:
        return f"agent-{self.index}"


def parse_prompt_file(path: Path) -> PromptConfig:
    text = path.read_text()
    if not text.strip():
        raise ValueError(f"prompt file is empty: {path}")

    count = 1
    models: tuple[str | None, ...] = (None,)
    efforts: tuple[str | None, ...] = (None,)
    seen_count = seen_models = seen_efforts = False

    body_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()

        m = COUNT_RE.fullmatch(stripped)
        if m:
            if seen_count:
                raise ValueError(f"multiple <{{count=...}}> directives in {path}")
            n = int(m.group(1))
            if n < 1:
                raise ValueError(f"<{{count={n}}}> must be >= 1 in {path}")
            count = n
            seen_count = True
            continue

        m = MODELS_RE.fullmatch(stripped)
        if m:
            if seen_models:
                raise ValueError(f"multiple <{{models=...}}> directives in {path}")
            models = tuple(_parse_list_inner(m.group(1), "models", path))
            seen_models = True
            continue

        m = EFFORTS_RE.fullmatch(stripped)
        if m:
            if seen_efforts:
                raise ValueError(f"multiple <{{efforts=...}}> directives in {path}")
            items = _parse_list_inner(m.group(1), "efforts", path)
            for e in items:
                if e not in VALID_EFFORTS:
                    raise ValueError(
                        f"invalid effort {e!r} in {path}; "
                        f"allowed: {list(VALID_EFFORTS)}"
                    )
            efforts = tuple(items)
            seen_efforts = True
            continue

        body_lines.append(line)

    return PromptConfig(
        path=path,
        count=count,
        models=models,
        efforts=efforts,
        body="".join(body_lines),
    )


def _parse_list_inner(inner: str, name: str, path: Path) -> list[str]:
    inner = inner.strip()
    if not inner:
        raise ValueError(
            f"<{{{name}=[]}}> is empty in {path}; omit the directive instead"
        )
    items = [item.strip() for item in inner.split(",")]
    if any(not item for item in items):
        raise ValueError(f"empty entry in <{{{name}=[...]}}> in {path}")
    return items


def expand_workers(configs: list[PromptConfig]) -> list[Worker]:
    workers: list[Worker] = []
    next_index = 1
    for cfg in configs:
        for model in cfg.models:
            for effort in cfg.efforts:
                for inst in range(1, cfg.count + 1):
                    workers.append(Worker(
                        index=next_index,
                        prompt_path=cfg.path,
                        model=model,
                        effort=effort,
                        instance=inst,
                        i_value=_make_i_value(next_index, model, effort),
                    ))
                    next_index += 1
    return workers


def _make_i_value(index: int, model: str | None, effort: str | None) -> str:
    parts = [str(index)]
    if model is not None:
        parts.append(re.sub(r"[^A-Za-z0-9]", "_", model))
    if effort is not None:
        parts.append(effort)
    return "_".join(parts)


def materialize_prompts(
    workers: list[Worker],
    configs: list[PromptConfig],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_by_path = {c.path: c for c in configs}
    for w in workers:
        body = cfg_by_path[w.prompt_path].body
        target = out_dir / f"agent-{w.index}.md"
        target.write_text(I_RE.sub(w.i_value, body))
