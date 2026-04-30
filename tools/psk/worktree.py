import subprocess
from pathlib import Path


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


def list_worktrees() -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to list worktrees")

    worktrees = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = {"path": line[len("worktree ") :]}
        elif line.startswith("branch "):
            current["branch"] = line[len("branch refs/heads/") :]
        elif line.startswith("HEAD "):
            current["sha"] = line[len("HEAD ") :][:7]
        elif line == "" and current:
            worktrees.append(current)
            current = {}
    if current:
        worktrees.append(current)
    return worktrees


def remove_worktree(path: Path) -> None:
    result = subprocess.run(["git", "worktree", "remove", str(path)])
    if result.returncode != 0:
        raise SystemExit(1)
    subprocess.run(["git", "worktree", "prune"])
