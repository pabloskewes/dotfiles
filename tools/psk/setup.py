from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SymlinkStep:
    """
    Link `files` from the first existing `source` directory into `target`.

    - `sources`: one or more directories to search (first existing wins).
      Relative paths are resolved against the repo root; absolute/~ paths
      are expanded as-is.
    - `target`: directory inside the worktree where symlinks are created.
      Always relative to the worktree root.
    - `files`: file names to link.
    """

    sources: tuple[str, ...]
    target: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class RunStep:
    """
    Run a command inside the worktree.

    - `argv`: command as a list of strings.
    - `cwd`: working directory relative to the worktree root (default ".").
    - `if_exists`: only run if this path exists (relative to resolved cwd).
    - `skip_if_exists`: skip if this path already exists (relative to resolved cwd).
    """

    argv: tuple[str, ...]
    cwd: str = "."
    if_exists: str | None = None
    skip_if_exists: str | None = None


@dataclass(frozen=True)
class SetupConfig:
    symlinks: tuple[SymlinkStep, ...] = field(default_factory=tuple)
    run: tuple[RunStep, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not self.symlinks and not self.run


def _resolve_source(source_str: str, repo_root: Path) -> Path:
    p = Path(source_str).expanduser()
    if p.is_absolute():
        return p
    return (repo_root / source_str).resolve()


def _run_symlink_step(step: SymlinkStep, worktree: Path, repo_root: Path) -> None:
    source_dirs = [_resolve_source(s, repo_root) for s in step.sources]
    dst_dir = worktree / step.target

    for src_dir in source_dirs:
        if not src_dir.is_dir():
            continue
        for filename in step.files:
            src = src_dir / filename
            if not src.is_file():
                continue
            dst = dst_dir / filename
            if dst.exists() or dst.is_symlink():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(src)
            rel_target = f"{step.target}/{filename}" if step.target != "." else filename
            print(f"symlinked {rel_target}")
        # Stop at first directory that exists (candidate semantics).
        # If we found the dir but none of the files were present, still stop --
        # the user explicitly listed this as the canonical source.
        break


def _run_run_step(step: RunStep, worktree: Path) -> None:
    cwd = worktree / step.cwd

    if step.if_exists is not None and not (cwd / step.if_exists).exists():
        return

    if step.skip_if_exists is not None and (cwd / step.skip_if_exists).exists():
        return

    label = " ".join(step.argv)
    print(f"running {label} in {cwd.name}...")
    result = subprocess.run(list(step.argv), cwd=cwd)
    if result.returncode != 0:
        print(f"  {step.argv[0]} exited with code {result.returncode} — continuing")


def run_project_setup(worktree: Path, repo_root: Path, config: SetupConfig) -> None:
    """Execute all setup steps for a newly created worktree."""
    for step in config.symlinks:
        _run_symlink_step(step, worktree, repo_root)
    for step in config.run:
        _run_run_step(step, worktree)


# ---------------------------------------------------------------------------
# TOML parsing
# ---------------------------------------------------------------------------


def _parse_symlink_step(entry: object) -> SymlinkStep:
    if not isinstance(entry, dict):
        raise ValueError(f"setup.symlinks entries must be tables, got {type(entry)}")

    raw_source = entry.get("source")
    if raw_source is None:
        raise ValueError("setup.symlinks entry missing 'source'")
    if isinstance(raw_source, str):
        sources: tuple[str, ...] = (raw_source,)
    elif isinstance(raw_source, list) and all(isinstance(s, str) for s in raw_source):
        sources = tuple(raw_source)
    else:
        raise ValueError("setup.symlinks 'source' must be a string or list of strings")

    raw_target = entry.get("target", ".")
    if not isinstance(raw_target, str):
        raise ValueError("setup.symlinks 'target' must be a string")

    raw_files = entry.get("files", [])
    if not isinstance(raw_files, list) or not all(
        isinstance(f, str) for f in raw_files
    ):
        raise ValueError("setup.symlinks 'files' must be a list of strings")

    return SymlinkStep(sources=sources, target=raw_target, files=tuple(raw_files))


def _parse_run_step(entry: object) -> RunStep:
    if not isinstance(entry, dict):
        raise ValueError(f"setup.run entries must be tables, got {type(entry)}")

    raw_argv = entry.get("argv")
    if not isinstance(raw_argv, list) or not all(isinstance(a, str) for a in raw_argv):
        raise ValueError("setup.run entry 'argv' must be a list of strings")

    raw_cwd = entry.get("cwd", ".")
    if not isinstance(raw_cwd, str):
        raise ValueError("setup.run 'cwd' must be a string")

    raw_if_exists = entry.get("if_exists")
    if raw_if_exists is not None and not isinstance(raw_if_exists, str):
        raise ValueError("setup.run 'if_exists' must be a string")

    raw_skip = entry.get("skip_if_exists")
    if raw_skip is not None and not isinstance(raw_skip, str):
        raise ValueError("setup.run 'skip_if_exists' must be a string")

    return RunStep(
        argv=tuple(raw_argv),
        cwd=raw_cwd,
        if_exists=raw_if_exists,
        skip_if_exists=raw_skip,
    )


def parse_setup_config(data: dict) -> SetupConfig:
    """Parse a ``[setup]`` TOML table into a :class:`SetupConfig`."""
    setup = data.get("setup")
    if not setup:
        return SetupConfig()

    if not isinstance(setup, dict):
        raise ValueError("[setup] must be a TOML table")

    symlink_steps = tuple(
        _parse_symlink_step(entry) for entry in setup.get("symlinks", [])
    )
    run_steps = tuple(_parse_run_step(entry) for entry in setup.get("run", []))

    return SetupConfig(symlinks=symlink_steps, run=run_steps)
