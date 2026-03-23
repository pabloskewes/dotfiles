import subprocess
from dataclasses import dataclass
from pathlib import Path

from psk.git_tui.git_ops import (
    do_squash,
    get_commits,
    get_current_branch,
    get_merge_base,
    has_uncommitted_changes,
)

PROTECTED_BRANCHES = ("main", "staging", "production")


@dataclass
class QAPlan:
    feature_branch: str
    target_branch: str
    staging_worktree: Path
    commit_count: int
    head_sha: str
    needs_squash: bool


def _get_head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _find_worktree_path(branch: str) -> Path | None:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    current_path: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line[len("worktree ") :])
        elif line.startswith("branch refs/heads/") and current_path is not None:
            if line[len("branch refs/heads/") :] == branch:
                return current_path
        elif line == "":
            current_path = None
    return None


def _run_in(
    cwd: Path, cmd: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)


def build_qa_plan(target_branch: str = "staging", skip_squash: bool = False) -> QAPlan:
    if has_uncommitted_changes():
        raise ValueError("Working tree has uncommitted changes — commit or stash first")

    branch = get_current_branch()
    if branch in PROTECTED_BRANCHES:
        raise ValueError(f"Cannot deploy from protected branch: {branch}")

    staging_wt = _find_worktree_path(target_branch)
    if staging_wt is None:
        raise ValueError(
            f"No worktree found for branch '{target_branch}'. Create one first."
        )

    subprocess.run(["git", "fetch", "origin", "main"], capture_output=True, check=True)
    base_sha = get_merge_base("origin/main")
    commits = get_commits(base_sha)
    if not commits:
        raise ValueError("No commits found between HEAD and origin/main")

    needs_squash = not skip_squash and len(commits) > 1

    return QAPlan(
        feature_branch=branch,
        target_branch=target_branch,
        staging_worktree=staging_wt,
        commit_count=len(commits),
        head_sha=_get_head_sha(),
        needs_squash=needs_squash,
    )


def execute_qa(plan: QAPlan, squash_message: str | None = None, push: bool = False) -> str:
    """Execute the QA deploy. Returns the cherry-picked SHA."""
    if plan.needs_squash:
        if not squash_message:
            raise ValueError("Squash message required when squashing")
        do_squash(plan.commit_count, squash_message)

    sha = _get_head_sha()
    short_sha = sha[:7]

    _run_in(plan.staging_worktree, ["git", "fetch", "origin", plan.target_branch])
    _run_in(
        plan.staging_worktree,
        ["git", "reset", "--hard", f"origin/{plan.target_branch}"],
    )

    result = _run_in(plan.staging_worktree, ["git", "cherry-pick", sha], check=False)
    if result.returncode != 0:
        _run_in(plan.staging_worktree, ["git", "cherry-pick", "--abort"], check=False)
        raise RuntimeError(
            f"Cherry-pick failed for {short_sha}. "
            f"Resolve conflicts manually in {plan.staging_worktree}\n"
            f"stderr: {result.stderr.strip()}"
        )

    if push:
        _run_in(plan.staging_worktree, ["git", "push", "origin", plan.target_branch])

    return sha
