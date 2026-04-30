"""Deploy a feature branch's delta to a target branch (typically staging).

Patch-mode: computes the feature-only diff from the branch split point with
`origin/main`, or from the last deploy commit recorded on `origin/<target>`,
applies it as a single new commit on top of the target worktree, and
(optionally) pushes it upstream.

Design invariants:
- Feature branch history is never rewritten.
- Target branch is never force-pushed.
- If the patch does not apply cleanly, the target worktree is restored to
  `origin/<target>` and the patch is saved to /tmp for manual inspection.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from psk.git_tui.git_ops import (
    get_commits,
    get_current_branch,
    get_merge_base,
    has_uncommitted_changes,
)

PROTECTED_SOURCE_BRANCHES = ("main", "staging", "production")
PROTECTED_TARGETS = ("main", "production")
DEPLOY_METADATA_KEYS = ("source-branch", "source-head", "source-base")


@dataclass
class StagingPlan:
    feature_branch: str
    target_branch: str
    target_worktree: Path
    feature_head_sha: str
    patch_base_sha: str
    source_base_sha: str
    target_remote_sha: str
    diff_stat: str
    changed_files: list[str]
    commit_subjects: list[str]


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        input=input_bytes,
        capture_output=capture,
        text=not capture,
    )


def _find_worktree_path(branch: str) -> Path | None:
    """Return the filesystem path of the worktree that has `branch` checked out."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
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


def _rev_parse(ref: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    ).stdout.strip()


def _diff_stat(base: str, head: str) -> str:
    return subprocess.run(
        ["git", "diff", "--stat", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _diff_name_only(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return [line for line in out.splitlines() if line]


def _diff_patch(base: str, head: str) -> bytes:
    """Generate a binary-safe patch of `base..head` (text by default)."""
    return subprocess.run(
        ["git", "diff", "--binary", f"{base}..{head}"],
        capture_output=True,
        check=True,
    ).stdout


def _parse_deploy_metadata(message: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in message.splitlines():
        key, sep, value = line.partition(":")
        if sep and key in DEPLOY_METADATA_KEYS:
            metadata[key] = value.strip()
    return metadata


def _find_last_deployed_source_head(
    target_ref: str,
    feature_branch: str,
    source_base_sha: str,
) -> str | None:
    log_output = subprocess.run(
        ["git", "log", "--format=%H%x1f%B%x1e", target_ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for record in log_output.split("\x1e"):
        if not record.strip():
            continue
        sha, _, message = record.partition("\x1f")
        metadata = _parse_deploy_metadata(message)
        if metadata.get("source-branch") != feature_branch:
            continue
        if metadata.get("source-base") != source_base_sha:
            continue
        source_head = metadata.get("source-head")
        if source_head:
            return source_head
    return None


def _is_ancestor(older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _build_deploy_commit_message(message: str, plan: StagingPlan) -> str:
    cleaned = message.rstrip()
    metadata_lines = [
        f"source-branch: {plan.feature_branch}",
        f"source-head: {plan.feature_head_sha}",
        f"source-base: {plan.source_base_sha}",
    ]
    if cleaned:
        return f"{cleaned}\n\n" + "\n".join(metadata_lines)
    return "\n".join(metadata_lines)


def build_staging_plan(target_branch: str = "staging") -> StagingPlan:
    if has_uncommitted_changes():
        raise ValueError("Working tree has uncommitted changes — commit or stash first")

    feature_branch = get_current_branch()
    if feature_branch in PROTECTED_SOURCE_BRANCHES:
        raise ValueError(f"Cannot deploy from protected branch: {feature_branch}")

    target_worktree = _find_worktree_path(target_branch)
    if target_worktree is None:
        raise ValueError(
            f"No worktree found for branch '{target_branch}'. "
            f"Create one with: git worktree add <path> {target_branch}"
        )

    subprocess.run(
        ["git", "fetch", "origin", target_branch, "main"],
        capture_output=True,
        check=True,
    )

    feature_head_sha = _rev_parse("HEAD")
    target_remote_sha = _rev_parse(f"origin/{target_branch}")
    source_base_sha = get_merge_base("origin/main")
    last_deployed_source_head = _find_last_deployed_source_head(
        f"origin/{target_branch}",
        feature_branch,
        source_base_sha,
    )
    if last_deployed_source_head and not _is_ancestor(
        last_deployed_source_head, feature_head_sha
    ):
        raise ValueError(
            "Feature history no longer contains the last deployed source-head. "
            "The branch was likely rewritten; deploy from a fresh staging-based "
            "branch or do a one-off manual deploy."
        )
    patch_base_sha = last_deployed_source_head or source_base_sha

    changed_files = _diff_name_only(patch_base_sha, "HEAD")
    if not changed_files:
        raise ValueError(
            "Nothing to deploy: no new feature changes since the last staging " "deploy"
        )
    diff_stat = _diff_stat(patch_base_sha, "HEAD")

    commit_subjects = [c.subject for c in get_commits(patch_base_sha)]

    return StagingPlan(
        feature_branch=feature_branch,
        target_branch=target_branch,
        target_worktree=target_worktree,
        feature_head_sha=feature_head_sha,
        patch_base_sha=patch_base_sha,
        source_base_sha=source_base_sha,
        target_remote_sha=target_remote_sha,
        diff_stat=diff_stat,
        changed_files=changed_files,
        commit_subjects=commit_subjects,
    )


def _save_patch_on_failure(patch_bytes: bytes) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = Path(f"/tmp/scopeo-staging-{ts}.patch")
    path.write_bytes(patch_bytes)
    return path


def _apply_patch(target_worktree: Path, patch_bytes: bytes) -> None:
    """Apply `patch_bytes` to `target_worktree` index + working tree.

    Uses `git apply --index --3way` to fall back to 3-way merge when a hunk
    doesn't apply cleanly. Raises RuntimeError with stderr + saved patch path
    on failure; leaves the worktree reset to origin/<target>.
    """
    result = subprocess.run(
        ["git", "apply", "--index", "--3way"],
        cwd=target_worktree,
        input=patch_bytes,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        saved = _save_patch_on_failure(patch_bytes)
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Patch did not apply cleanly.\n"
            f"  worktree:     {target_worktree}\n"
            f"  saved patch:  {saved}\n"
            f"  stderr:       {stderr}"
        )


def execute_staging(plan: StagingPlan, message: str, *, push: bool = True) -> str:
    """Apply the feature delta onto the target worktree, commit, optionally push.

    Returns the new commit SHA on the target branch.
    """
    patch_bytes = _diff_patch(plan.patch_base_sha, plan.feature_head_sha)

    _run(
        ["git", "reset", "--hard", f"origin/{plan.target_branch}"],
        cwd=plan.target_worktree,
    )

    try:
        _apply_patch(plan.target_worktree, patch_bytes)
    except RuntimeError:
        _run(
            ["git", "reset", "--hard", f"origin/{plan.target_branch}"],
            cwd=plan.target_worktree,
            check=False,
        )
        raise

    commit = subprocess.run(
        ["git", "commit", "-m", _build_deploy_commit_message(message, plan)],
        cwd=plan.target_worktree,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit.returncode != 0:
        raise RuntimeError(
            f"git commit failed in {plan.target_worktree}: {commit.stderr.strip()}"
        )

    new_sha = _rev_parse("HEAD", cwd=plan.target_worktree)

    if push:
        push_result = subprocess.run(
            ["git", "push", "origin", plan.target_branch],
            cwd=plan.target_worktree,
            capture_output=True,
            text=True,
            check=False,
        )
        if push_result.returncode != 0:
            raise RuntimeError(
                f"git push failed: {push_result.stderr.strip()}\n"
                f"Commit {new_sha[:7]} is staged locally in {plan.target_worktree}; "
                f"retry push manually (no --force)."
            )

    return new_sha
