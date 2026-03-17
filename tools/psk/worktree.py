import subprocess
from pathlib import Path

ENV_FILES = [".env", ".env.local", ".env.development.local", "credentials.env"]


def get_repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Not inside a git repository")
    return Path(result.stdout.strip())


def resolve_worktree_path(
    branch: str,
    worktrees_dir: str | None = None,
    worktree_path: str | None = None,
) -> Path:
    if worktrees_dir and worktree_path:
        raise ValueError("Use either --worktrees-dir or --worktree-path, not both")

    if worktree_path:
        return Path(worktree_path)

    repo_root = get_repo_root()
    if not worktrees_dir:
        worktrees_dir = str(repo_root.parent / f"{repo_root.name}-worktrees")

    safe_branch = branch.replace("/", "-")
    return Path(worktrees_dir) / safe_branch


def create_worktree(branch: str, path: Path, new_branch: bool = False) -> None:
    if new_branch:
        cmd = ["git", "worktree", "add", "-b", branch, str(path)]
    else:
        cmd = ["git", "worktree", "add", str(path), branch]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(1)

    repo_root = get_repo_root()
    for filename in ENV_FILES:
        src = repo_root / filename
        dst = path / filename
        if src.is_file():
            dst.symlink_to(src)
            print(f"symlinked {filename}")


def remove_worktree(path: Path) -> None:
    result = subprocess.run(["git", "worktree", "remove", str(path)])
    if result.returncode == 0:
        subprocess.run(["git", "worktree", "prune"])
